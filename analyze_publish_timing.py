"""
Analyze existing game data to answer common developer questions with real numbers:
  - Best month to publish (by review score and by revenue)
  - Best day of week to publish
  - Average price by genre
  - Review-score / revenue benchmarks by genre

Uses ONLY data already in the `games` collection — no external calls, no new
scraping. Safe to re-run anytime; it overwrites the `market_stats` collection
with fresh numbers.

Every stat records its sample size so the UI can show real confidence, not a
made-up percentage. A month/day with 5 games behind it is not "the best
month" — it's noise, and we mark it as such.

Usage:
    python analyze_publish_timing.py
    python analyze_publish_timing.py --years 5       # limit to last 5 release years
    python analyze_publish_timing.py --min-reviews 20  # exclude low-signal games
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from collections import defaultdict
from statistics import median
import re
import sys
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
stats_col = db["market_stats"]

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Steam's en-locale store API returns dates like "Feb 20, 2024".
# Some older/regional entries use "20 Feb, 2024". Handle both.
_DATE_PATTERNS = [
    (r"^([A-Za-z]{3}) (\d{1,2}), (\d{4})$", "%b %d, %Y"),
    (r"^(\d{1,2}) ([A-Za-z]{3}) (\d{4})$", "%d %b %Y"),
]


def parse_release_date(raw):
    """Best-effort parse of Steam's release_date string. Returns a date or None."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for pattern, fmt in _DATE_PATTERNS:
        if re.match(pattern, raw):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


def _num(v, default=0):
    return v if isinstance(v, (int, float)) else default


def _confidence_for_sample(n):
    """Sample-size-driven confidence label. No stat gets called 'verified' on a thin sample."""
    if n >= 200:
        return {"label": "high", "score": 90}
    if n >= 60:
        return {"label": "medium-high", "score": 75}
    if n >= 20:
        return {"label": "medium", "score": 55}
    if n >= 8:
        return {"label": "low-medium", "score": 35}
    return {"label": "low (small sample)", "score": 15}


def build_month_day_stats(games, min_reviews, label):
    """Group games by release month / day-of-week and compute review-score + revenue stats."""
    by_month = defaultdict(list)
    by_day = defaultdict(list)
    parsed_count = 0

    for g in games:
        d = parse_release_date(g.get("release_date", ""))
        if not d:
            continue
        reviews = _num(g.get("review_summary", {}).get("total_reviews"))
        if reviews < min_reviews:
            continue
        score = _num(g.get("review_summary", {}).get("positive_percent"))
        revenue = _num(g.get("estimated_revenue", {}).get("high"))
        parsed_count += 1
        by_month[d.month].append((score, revenue))
        by_day[d.weekday()].append((score, revenue))

    month_stats = []
    for m in range(1, 13):
        rows = by_month.get(m, [])
        if not rows:
            continue
        scores = [r[0] for r in rows if r[0] > 0]
        revenues = [r[1] for r in rows if r[1] > 0]
        month_stats.append({
            "month": m,
            "month_name": MONTH_NAMES[m - 1],
            "game_count": len(rows),
            "avg_review_score_pct": round(sum(scores) / len(scores), 1) if scores else 0,
            "median_revenue_estimate": int(median(revenues)) if revenues else 0,
            "confidence": _confidence_for_sample(len(rows)),
        })

    day_stats = []
    for d_idx in range(7):
        rows = by_day.get(d_idx, [])
        if not rows:
            continue
        scores = [r[0] for r in rows if r[0] > 0]
        revenues = [r[1] for r in rows if r[1] > 0]
        day_stats.append({
            "day": DAY_NAMES[d_idx],
            "game_count": len(rows),
            "avg_review_score_pct": round(sum(scores) / len(scores), 1) if scores else 0,
            "median_revenue_estimate": int(median(revenues)) if revenues else 0,
            "confidence": _confidence_for_sample(len(rows)),
        })

    best_month_by_score = max(month_stats, key=lambda x: x["avg_review_score_pct"], default=None)
    best_month_by_revenue = max(month_stats, key=lambda x: x["median_revenue_estimate"], default=None)
    best_day_by_score = max(day_stats, key=lambda x: x["avg_review_score_pct"], default=None)

    return {
        "stat_id": f"publish_timing:{label}",
        "segment": label,
        "computed_at": datetime.now(timezone.utc),
        "games_analyzed": parsed_count,
        "games_with_unparseable_dates": len(games) - parsed_count,
        "min_reviews_filter": min_reviews,
        "months": sorted(month_stats, key=lambda x: -x["avg_review_score_pct"]),
        "days_of_week": sorted(day_stats, key=lambda x: -x["avg_review_score_pct"]),
        "best_month_by_review_score": best_month_by_score,
        "best_month_by_revenue": best_month_by_revenue,
        "best_day_by_review_score": best_day_by_score,
        "source": "Steam store + SteamSpy data already collected in this database",
        "method": (
            "Games grouped by parsed release month/day-of-week. Review score = average "
            "positive review percent. Revenue = median SteamSpy-derived estimate. "
            "Only games with at least the review-count threshold are counted, to avoid "
            "single-game noise skewing a month."
        ),
        "caveat": (
            "This measures games that happened to release in a given month, not a causal "
            "effect of the month itself. Treat as directional, not a guarantee."
        ),
    }


def build_price_by_genre(genres):
    rows = []
    for genre in genres:
        docs = list(games_col.find(
            {"genres": genre, "delisted": {"$ne": True}, "is_free": {"$ne": True}},
            {"_id": 0, "price.current": 1, "review_summary.positive_percent": 1, "review_summary.total_reviews": 1},
        ))
        prices = [_num(d.get("price", {}).get("current")) for d in docs]
        prices = [p for p in prices if p > 0]
        if not prices:
            continue
        rows.append({
            "genre": genre,
            "game_count": len(prices),
            "avg_price_usd": round(sum(prices) / len(prices), 2),
            "median_price_usd": round(median(prices), 2),
            "confidence": _confidence_for_sample(len(prices)),
        })
    return {
        "stat_id": "avg_price_by_genre",
        "computed_at": datetime.now(timezone.utc),
        "genres": sorted(rows, key=lambda x: -x["avg_price_usd"]),
        "source": "Steam store pricing data already collected in this database",
    }


GENRES = ["Action", "Adventure", "Casual", "Indie", "RPG", "Simulation", "Strategy", "Sports", "Racing"]


def run(years=None, min_reviews=15):
    print("Loading games from database...")
    all_games = list(games_col.find(
        {"delisted": {"$ne": True}},
        {"_id": 0, "release_date": 1, "review_summary": 1, "estimated_revenue": 1, "genres": 1},
    ))
    print(f"  {len(all_games):,} games loaded.")

    if years:
        cutoff_year = datetime.now(timezone.utc).year - years
        filtered = []
        for g in all_games:
            d = parse_release_date(g.get("release_date", ""))
            if d and d.year >= cutoff_year:
                filtered.append(g)
        print(f"  Filtered to last {years} years: {len(filtered):,} games.")
    else:
        filtered = all_games

    results = []

    print("\nComputing overall publish-timing stats...")
    results.append(build_month_day_stats(filtered, min_reviews, "all"))

    for genre in GENRES:
        genre_games = [g for g in filtered if genre in (g.get("genres") or [])]
        if len(genre_games) < 8:
            print(f"  Skipping {genre} — too few games ({len(genre_games)})")
            continue
        print(f"  {genre}: {len(genre_games)} games")
        results.append(build_month_day_stats(genre_games, min_reviews, genre.lower()))

    print("\nComputing average price by genre...")
    results.append(build_price_by_genre(GENRES))

    print("\nWriting results to market_stats collection...")
    for r in results:
        stats_col.update_one({"stat_id": r["stat_id"]}, {"$set": r}, upsert=True)

    print(f"Done. Wrote {len(results)} stat documents to market_stats.")

    best_overall = next((r for r in results if r["stat_id"] == "publish_timing:all"), None)
    if best_overall and best_overall["best_month_by_review_score"]:
        b = best_overall["best_month_by_review_score"]
        print(f"\nBest month overall by review score: {b['month_name']} "
              f"({b['avg_review_score_pct']}% avg, n={b['game_count']}, confidence={b['confidence']['label']})")

    best_indie = next((r for r in results if r["stat_id"] == "publish_timing:indie"), None)
    if best_indie and best_indie["best_month_by_review_score"]:
        b = best_indie["best_month_by_review_score"]
        print(f"Best month for Indie by review score: {b['month_name']} "
              f"({b['avg_review_score_pct']}% avg, n={b['game_count']}, confidence={b['confidence']['label']})")


if __name__ == "__main__":
    years = None
    min_reviews = 15
    for i, arg in enumerate(sys.argv):
        if arg == "--years" and i + 1 < len(sys.argv):
            years = int(sys.argv[i + 1])
        if arg == "--min-reviews" and i + 1 < len(sys.argv):
            min_reviews = int(sys.argv[i + 1])
    run(years=years, min_reviews=min_reviews)
    client.close()
