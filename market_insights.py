"""
Core market-analysis engine: TAM/SAM/SOM sizing, revenue estimation,
outlier-adjusted per-game benchmarks, player-momentum tracking, niche/
opportunity scoring, and the free-text genre/tag inference used when a
brief question doesn't explicitly name a market.

Nothing here talks to Flask — every function takes a Mongo collection (and
sometimes a db handle for cross-collection queries like player_snapshots)
as its first argument and returns plain dicts/lists. blueprints/*.py wrap
these as JSON routes; helpers.py's brief-building code composes several of
them together into the AI-brief payload.

Revenue/owner figures throughout are SteamSpy-derived estimates, not
official Steam sales data — see SOURCE_CONFIDENCE below for what's
high-confidence (Steam metadata/reviews) vs. modeled (sales estimates).
"""
from datetime import date, datetime, timedelta, timezone
from statistics import median
import re
import time

from virtual_tags import TAG_ALIASES, build_tag_matcher, build_virtual_tag_query, game_matches_virtual_tag, is_virtual_tag

# In-process cache for summarize_market() results — market summaries involve
# several aggregation passes over `games`, so repeat requests for the same
# genre/tag within the TTL window are served from memory instead of hitting
# Mongo again. Per-process only (not shared across workers); fine at this
# scale, but wouldn't survive a multi-process deployment without moving to
# something shared like Redis.
_MARKET_CACHE = {}
_CACHE_TTL = 1800  # 30 minutes

# Look up a cached market summary, or None if missing/expired.
def _cache_get(key):
    entry = _MARKET_CACHE.get(key)
    if entry and time.monotonic() - entry["ts"] < _CACHE_TTL:
        return entry["val"]
    return None

# Store a market summary in the cache with the current timestamp.
def _cache_set(key, val):
    _MARKET_CACHE[key] = {"val": val, "ts": time.monotonic()}


GENRES = [
    "Action",
    "Adventure",
    "Casual",
    "Indie",
    "RPG",
    "Simulation",
    "Strategy",
    "Sports",
    "Racing",
]


DATA_POINT_CATALOG = {
    "game_profile": [
        "title",
        "steam_app_id",
        "store_url",
        "description",
        "developer",
        "publisher",
        "release_date",
        "genres",
        "tags",
        "platforms",
        "features",
        "supported_languages",
        "screenshots",
        "movies",
        "dlc",
    ],
    "pricing": [
        "current_price",
        "initial_price",
        "discount_percent",
        "free_to_play",
        "historical_low",
        "average_price_by_market",
        "price_benchmarks",
    ],
    "reviews": [
        "total_reviews",
        "positive_reviews",
        "negative_reviews",
        "positive_percent",
        "review_score_description",
        "average_review_score_by_market",
        "review_count_benchmarks",
    ],
    "sales_estimates": [
        "estimated_owners_low",
        "estimated_owners_high",
        "estimated_revenue_low",
        "estimated_revenue_high",
        "median_revenue_by_market",
        "top_revenue_games",
    ],
    "market_sizing": [
        "TAM_by_genre",
        "SAM_by_tag",
        "SOM_capture_range",
        "competition_count",
        "paid_game_count",
        "revenue_concentration",
        "competition_density",
    ],
    "trends": [
        "current_players",
        "player_snapshot_history",
        "genre_player_trends",
        "market_momentum",
        "under_prominent_markets",
        "doing_well_markets",
    ],
    "launch_guidance": [
        "steam_direct_fee",
        "store_page_requirements",
        "tag_strategy",
        "launch_timeline",
        "review_score_targets",
        "pricing_guidance",
    ],
}


# Coerce to a number, treating None/missing/non-numeric Mongo fields as 0 (or `default`).
def _num(value, default=0):
    return value if isinstance(value, (int, float)) else default


# Format a number as a compact dollar string (e.g. 1_500_000 -> "$1.5M").
def _money(value):
    value = _num(value)
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


# Linear-interpolation percentile (0.0-1.0), ignoring non-positive/missing values.
def _percentile(values, pct):
    clean = sorted(_num(v) for v in values if _num(v) > 0)
    if not clean:
        return 0
    if len(clean) == 1:
        return int(clean[0])

    pos = (len(clean) - 1) * pct
    lower = int(pos)
    upper = min(lower + 1, len(clean) - 1)
    weight = pos - lower
    return int(clean[lower] + (clean[upper] - clean[lower]) * weight)


# Drop the top `trim_pct` of values before computing per-game benchmarks, so
# one or two breakout hits (a Hollow Knight, a Balatro) don't drag the
# "realistic" target for a solo/small team upward. Only trims when there's
# enough sample (30+) for that to be meaningful rather than just dropping
# real data points from a small set.
def _trim_top_percent(values, trim_pct=0.01):
    clean = sorted(_num(v) for v in values if _num(v) > 0)
    if len(clean) < 30:
        return clean
    keep = max(1, int(len(clean) * (1 - trim_pct)))
    return clean[:keep]


# Heuristic 10-85 confidence score for a market's revenue estimate, based on
# sample size and how concentrated revenue is among top titles (a market
# dominated by one or two hits is less predictable for a new entrant than
# one with a broad spread of comparable performers).
def _estimate_confidence(total_games, paid_games, revenue_concentration_pct):
    score = 35
    if total_games >= 1000:
        score += 25
    elif total_games >= 300:
        score += 18
    elif total_games >= 100:
        score += 10
    elif total_games >= 30:
        score += 5

    if paid_games >= 300:
        score += 18
    elif paid_games >= 100:
        score += 12
    elif paid_games >= 30:
        score += 6

    if revenue_concentration_pct > 70:
        score -= 18
    elif revenue_concentration_pct > 50:
        score -= 10
    elif revenue_concentration_pct < 25:
        score += 8

    score = max(10, min(score, 85))
    if score >= 70:
        label = "medium-high"
    elif score >= 50:
        label = "medium"
    elif score >= 35:
        label = "low-medium"
    else:
        label = "low"

    return {
        "score": score,
        "label": label,
        "reason": (
            "Revenue is estimated from SteamSpy owner ranges and public pricing. "
            "Confidence improves with larger comparable samples and lower hit concentration."
        ),
    }


SOURCE_CONFIDENCE = {
    "steam_metadata": {
        "confidence": "high",
        "fields": ["title", "app_id", "price", "release_date", "genres", "platforms", "store_assets"],
        "reason": "Pulled from public Steam store data.",
    },
    "steam_reviews": {
        "confidence": "high",
        "fields": ["review_count", "positive_percent", "positive_reviews", "negative_reviews"],
        "reason": "Based on public Steam review data.",
    },
    "steam_current_players": {
        "confidence": "medium-high",
        "fields": ["current_players"],
        "reason": "Pulled from Steam's public current-player endpoint, but it is a point-in-time value.",
    },
    "steamspy_sales_estimates": {
        "confidence": "low-medium",
        "fields": ["estimated_owners", "estimated_revenue", "TAM", "SAM", "SOM"],
        "reason": "Steam does not publish official per-game sales; these are modeled estimates.",
    },
}


# Tags too generic to count as a real "niche" — used to filter these out of
# smaller_subgenre_report/market_opportunities so recommendations point at
# an actually-navigable subgenre instead of "Action" or "Singleplayer",
# which describe most of the catalog and aren't a market a solo dev could
# meaningfully target.
BROAD_TAGS = {
    "2D",
    "3D",
    "Action",
    "Adventure",
    "Atmospheric",
    "Casual",
    "Colorful",
    "Difficult",
    "Early Access",
    "Exploration",
    "Fantasy",
    "Female Protagonist",
    "First-Person",
    "Free to Play",
    "Funny",
    "Great Soundtrack",
    "Indie",
    "Massively Multiplayer",
    "Multiplayer",
    "Online Co-Op",
    "Open World",
    "Pixel Graphics",
    "PvE",
    "PvP",
    "RPG",
    "Realistic",
    "Replay Value",
    "Retro",
    "Sci-fi",
    "Shooter",
    "Short",
    "Simulation",
    "Singleplayer",
    "Sports",
    "Story Rich",
    "Strategy",
    "Stylized",
    "Third Person",
}

# The base Mongo filter for "games in this genre/tag". Delegates to
# virtual_tags first, since some tags (see virtual_tags.py) can't be
# expressed as a simple field match and need their own query shape.
def build_market_query(genre=None, tag=None):
    query = build_virtual_tag_query(tag, genre=genre) if tag else None
    if query:
        return query

    query = {"delisted": {"$ne": True}}
    if genre:
        query["genres"] = genre
    if tag:
        query["tags"] = build_tag_matcher(tag)
    return query


# The core market-sizing function: TAM/SAM/SOM, outlier-adjusted revenue
# benchmarks (p25/p50/p75/p90 after trimming the top 1% of paid games — see
# _trim_top_percent), pricing/review percentiles, and a confidence score,
# for every game matching this genre and/or tag. Result is cached
# (_MARKET_CACHE) since this scans the full matching game set and gets
# called repeatedly for the same market.
def summarize_market(games_col, genre=None, tag=None):
    cache_key = (genre or "", tag or "")
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    query = build_market_query(genre=genre, tag=tag)
    need_tags = tag and is_virtual_tag(tag)
    projection = {
        "_id": 0,
        "estimated_revenue": 1,
        "price": 1,
        "review_summary": 1,
        "players": 1,
        "is_free": 1,
    }
    if need_tags:
        projection["tags"] = 1

    games = list(games_col.find(query, projection))
    if need_tags:
        games = [g for g in games if game_matches_virtual_tag(g, tag)]

    if not games:
        return None

    paid = [
        g for g in games
        if not g.get("is_free") and _num(g.get("price", {}).get("current")) > 0
    ]
    revenue_lows = [_num(g.get("estimated_revenue", {}).get("low")) for g in games]
    revenue_highs = [_num(g.get("estimated_revenue", {}).get("high")) for g in games]
    paid_revenue_lows = [_num(g.get("estimated_revenue", {}).get("low")) for g in paid]
    paid_revenue_highs = [_num(g.get("estimated_revenue", {}).get("high")) for g in paid]
    prices = [_num(g.get("price", {}).get("current")) for g in paid if _num(g.get("price", {}).get("current")) > 0]
    scores = [
        _num(g.get("review_summary", {}).get("positive_percent"))
        for g in games
        if _num(g.get("review_summary", {}).get("positive_percent")) > 0
    ]
    reviews = [_num(g.get("review_summary", {}).get("total_reviews")) for g in games]
    players = [_num(g.get("players", {}).get("current")) for g in games]

    total_revenue_high = sum(revenue_highs)
    top_10_revenue = sum(sorted(revenue_highs, reverse=True)[:10])
    revenue_concentration_pct = round((top_10_revenue / total_revenue_high) * 100, 1) if total_revenue_high else 0
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    trimmed_revenues = _trim_top_percent(paid_revenue_highs, 0.01)
    median_revenue = int(median(trimmed_revenues)) if trimmed_revenues else 0
    median_reviews = int(median(reviews)) if reviews else 0
    total_players = sum(players)
    price_p50 = _percentile(prices, 0.50)
    score_p50 = _percentile(scores, 0.50)
    revenue_p25 = _percentile(trimmed_revenues, 0.25)
    revenue_p50 = _percentile(trimmed_revenues, 0.50)
    revenue_p75 = _percentile(trimmed_revenues, 0.75)
    revenue_p90 = _percentile(trimmed_revenues, 0.90)
    reviews_p75 = _percentile(reviews, 0.75)

    market_name = tag or genre or "Steam"
    market_type = "tag" if tag else "genre" if genre else "all"
    confidence = _estimate_confidence(len(games), len(paid), revenue_concentration_pct)

    result = {
        "market": market_name,
        "market_type": market_type,
        "genre": genre,
        "tag": tag,
        "total_games": len(games),
        "paid_games": len(paid),
        "avg_price_usd": avg_price,
        "avg_review_score_pct": avg_score,
        "median_reviews": median_reviews,
        "median_revenue_estimate": median_revenue,
        "median_revenue_estimate_raw": int(median(paid_revenue_highs)) if paid_revenue_highs else 0,
        "total_current_players": total_players,
        "estimated_revenue_low": sum(revenue_lows),
        "estimated_revenue_high": total_revenue_high,
        "revenue_concentration_top_10_pct": revenue_concentration_pct,
        "sample_notes": {
            "outlier_handling": "Per-game revenue benchmarks exclude the top 1% of paid games when sample size allows.",
            "paid_revenue_sample_size": len(trimmed_revenues),
            "raw_paid_revenue_sample_size": len(paid_revenue_highs),
        },
        "confidence": confidence,
        "source_confidence": SOURCE_CONFIDENCE,
        "performance_benchmarks": {
            "price_usd": {
                "p50": price_p50,
                "average": avg_price,
            },
            "review_score_pct": {
                "p50": score_p50,
                "average": avg_score,
            },
            "total_reviews": {
                "p50": median_reviews,
                "p75": reviews_p75,
            },
            "per_game_revenue_estimate": {
                "p25": revenue_p25,
                "p50": revenue_p50,
                "p75": revenue_p75,
                "p90": revenue_p90,
            },
        },
        "realistic_revenue_target": {
            "conservative": revenue_p25,
            "expected": revenue_p50,
            "strong": revenue_p75,
            "breakout": revenue_p90,
            "label": "Outlier-adjusted per-game revenue benchmarks for paid games in this market",
        },
        # TAM/SAM are intentionally identical here — both are just "total
        # estimated revenue across every matching game" (the query already
        # scopes to genre/tag, so there's no broader "addressable" universe
        # above SAM within this function to distinguish them from).
        "TAM": {
            "low": sum(revenue_lows),
            "high": total_revenue_high,
            "label": f"Estimated total market for {market_name}",
        },
        "SAM": {
            "low": sum(revenue_lows),
            "high": total_revenue_high,
            "label": f"Estimated serviceable market for {market_name}",
        },
        "SOM": {
            "low": revenue_p25,
            "high": revenue_p75,
            "label": "Outlier-adjusted realistic per-game capture range based on comparable paid games",
            # Deliberately NOT used as the primary SOM range — "X% of TAM"
            # is a much cruder estimate than the percentile-based figures
            # above, and can wildly overstate what a small team could
            # realistically earn. Kept only for reference; brief_diagnostics
            # explicitly tells the AI to ignore these when they dwarf the
            # real (outlier-adjusted) SOM range — see helpers._build_brief_diagnostics.
            "legacy_percent_capture_low": round(total_revenue_high * 0.01),
            "legacy_percent_capture_high": round(total_revenue_high * 0.10),
        },
        "disclaimer": "Revenue and owner figures are SteamSpy-based estimates, not official Steam data.",
    }
    _cache_set(cache_key, result)
    return result


# Highest-estimated-revenue games matching a genre/tag, for showing real
# example titles alongside the aggregate market_summary numbers.
def top_competitors(games_col, genre=None, tag=None, limit=10):
    query = build_market_query(genre=genre, tag=tag)
    projection = {
        "_id": 0,
        "title": 1,
        "steam_app_id": 1,
        "release_date": 1,
        # Full tags array, not a truncated slice: the query below matches
        # on the complete list, so a game can genuinely carry the resolved
        # tag while it's absent from an early slice (e.g. ranked 8th of 20
        # community tags) — truncating here previously made the AI wrongly
        # conclude matched competitors "don't actually carry the tag."
        "tags": 1,
        "price": 1,
        "is_free": 1,
        "estimated_owners": 1,
        "estimated_revenue": 1,
        "review_summary": 1,
        "players": 1,
        "store_url": 1,
    }
    capped_limit = max(1, min(int(limit), 25))
    # Virtual tags need the full sorted candidate set fetched before the
    # Python-side game_matches_virtual_tag filter runs, so $limit can only
    # be pushed into the pipeline for real (non-virtual) genre/tag queries.
    is_virtual = bool(tag and is_virtual_tag(tag))

    pipeline = [{"$match": query}, {"$sort": {"estimated_revenue.high": -1}}]
    if not is_virtual:
        pipeline.append({"$limit": capped_limit})
    pipeline.append({"$project": projection})

    docs = list(games_col.aggregate(pipeline, allowDiskUse=True))

    if is_virtual:
        docs = [doc for doc in docs if game_matches_virtual_tag(doc, tag)]

    docs = docs[:max(1, min(int(limit), 25))]

    return docs


_UPCOMING_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


# Best-effort parse of 'Mon DD, YYYY' release_date strings. Returns a sortable date or None.
def _parse_upcoming_date(raw):
    if not raw or not isinstance(raw, str):
        return None
    m = re.match(r"^([A-Za-z]{3}) (\d{1,2}), (\d{4})$", raw.strip())
    if not m:
        return None
    month = _UPCOMING_MONTHS.get(m.group(1))
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(2)))
    except ValueError:
        return None


# Sort tracked coming-soon docs soonest-release-first, dropping any whose
# release_date_raw parses to a date already in the past.
#
# coming_soon flags only update when expand_continuous/refresh_games happens
# to recrawl that specific game, so a game can ship and sit with a stale
# True flag (and its original, now-past, release date) until the next
# recrawl. Most coming-soon games have vague/unparseable dates ("Coming
# Soon", "Q3 2026") and are unaffected; this only filters the rare case of
# a real, cleanly-parsed date that's already passed.
def _sort_and_drop_stale_upcoming(docs):
    today = date.today()
    kept = []
    for doc in docs:
        parsed = _parse_upcoming_date(doc.get("release_date_raw"))
        if parsed and parsed < today:
            continue
        doc["_release_sort"] = parsed or date.max
        kept.append(doc)

    kept.sort(key=lambda d: d["_release_sort"])
    for doc in kept:
        doc.pop("_release_sort", None)
    return kept


# Future competitors currently in Steam's coming-soon queue, soonest release
# first.
#
# Sourced from upcoming_games, which is a snapshot of games already marked
# coming_soon=True in the main catalog (see scrape_upcoming_releases.py) —
# real Steam data, not a third-party estimate.
def upcoming_competitors(upcoming_col, genre=None, tag=None, limit=12):
    query = {"launched_since_tracking": False}
    if genre:
        query["genres"] = genre
    if tag:
        query["tags"] = tag

    docs = list(upcoming_col.find(
        query,
        {
            "_id": 0,
            "steam_app_id": 1,
            "title": 1,
            "release_date_raw": 1,
            "genres": 1,
            "developer": 1,
            "price_current_usd": 1,
            "header_image_url": 1,
            "store_url": 1,
            "first_seen": 1,
        },
    ))

    docs = _sort_and_drop_stale_upcoming(docs)

    return docs[:max(1, min(int(limit), 50))]


# Paginated, soonest-release-first browse of tracked coming-soon games.
#
# release_date_raw is a free-text Steam string ('Oct 22, 2026'), not a real
# date field, so sorting has to happen in Python after fetch rather than as
# a Mongo-side sort — same approach as upcoming_competitors, just paginated.
def upcoming_games_page(upcoming_col, genre=None, tag=None, page=0, limit=50):
    query = {"launched_since_tracking": False}
    if genre:
        query["genres"] = genre
    if tag:
        query["tags"] = build_tag_matcher(tag)

    docs = list(upcoming_col.find(
        query,
        {
            "_id": 0,
            "steam_app_id": 1,
            "title": 1,
            "release_date_raw": 1,
            "genres": 1,
            "tags": 1,
            "developer": 1,
            "price_current_usd": 1,
            "header_image_url": 1,
            "store_url": 1,
            "first_seen": 1,
        },
    ))

    docs = _sort_and_drop_stale_upcoming(docs)

    total = len(docs)
    page = max(0, int(page))
    limit = max(1, min(int(limit), 150))
    start = page * limit
    return docs[start:start + limit], total


# Count tracked coming-soon games per top-level genre.
def upcoming_genre_counts(upcoming_col):
    counts = []
    for genre in GENRES:
        count = upcoming_col.count_documents({"genres": genre, "launched_since_tracking": False})
        if count:
            counts.append({"genre": genre, "count": count})
    counts.sort(key=lambda c: c["count"], reverse=True)
    return counts


# Count tracked coming-soon games per curated subgenre tag within a genre.
def upcoming_subgenre_counts(upcoming_col, genre, tags):
    from market_taxonomy import children_for_subgenre

    available = []
    for tag in tags:
        count = upcoming_col.count_documents({
            "genres": genre,
            "tags": build_tag_matcher(tag),
            "launched_since_tracking": False,
        })
        if count > 0:
            children = children_for_subgenre(tag)
            available.append({
                "tag": tag,
                "count": count,
                "children": children,
                "has_children": bool(children),
            })
    return available


# Count tracked coming-soon games per child tag under a broad subgenre.
def upcoming_subgenre_children_counts(upcoming_col, children, genre=None):
    results = []
    for child in children:
        query = {"tags": build_tag_matcher(child), "launched_since_tracking": False}
        if genre:
            query["genres"] = genre
        count = upcoming_col.count_documents(query)
        if count > 0:
            results.append({"market": child, "total_games": count})
    results.sort(key=lambda c: c["total_games"], reverse=True)
    return results


# summarize_market() for every top-level genre — used to rank/compare
# genres against each other (e.g. the home screen genre chart).
def rank_genre_markets(games_col):
    summaries = []
    for genre in GENRES:
        summary = summarize_market(games_col, genre=genre)
        if summary:
            summaries.append(summary)
    return summaries


# Aggregate every tag across all matching games into per-tag totals (games,
# revenue, players, avg score/price), sorted by revenue — unlike
# rank_specific_tag_markets, this discovers tags rather than being told
# which ones to look at. $unwind on tags is what makes this expensive
# relative to a plain find(), hence the games_col-side aggregation rather
# than doing it in Python.
def rank_tag_markets(games_col, genre=None, limit=25):
    match = build_market_query(genre=genre)
    pipeline = [
        {"$match": match},
        {"$unwind": "$tags"},
        {"$group": {
            "_id": "$tags",
            "total_games": {"$sum": 1},
            "paid_games": {
                "$sum": {
                    "$cond": [
                        {"$and": [
                            {"$ne": ["$is_free", True]},
                            {"$gt": ["$price.current", 0]},
                        ]},
                        1,
                        0,
                    ]
                }
            },
            "revenue_high": {"$sum": {"$ifNull": ["$estimated_revenue.high", 0]}},
            "total_players": {"$sum": {"$ifNull": ["$players.current", 0]}},
            "avg_score": {"$avg": "$review_summary.positive_percent"},
            "avg_price": {"$avg": "$price.current"},
        }},
        {"$match": {"total_games": {"$gte": 10}}},
        {"$sort": {"revenue_high": -1}},
        {"$limit": max(1, min(int(limit), 300))},
        {"$project": {
            "_id": 0,
            "market": "$_id",
            "market_type": "tag",
            "genre": genre,
            "total_games": 1,
            "paid_games": 1,
            "estimated_revenue_high": "$revenue_high",
            "total_current_players": "$total_players",
            "avg_review_score_pct": {"$round": [{"$ifNull": ["$avg_score", 0]}, 1]},
            "avg_price_usd": {"$round": [{"$ifNull": ["$avg_price", 0]}, 2]},
        }},
    ]
    return list(games_col.aggregate(pipeline, allowDiskUse=True))


# Same shape of result as rank_tag_markets, but scoped to a known list of
# tags (e.g. a curated subgenre set) instead of discovering every tag that
# appears — cheaper when the caller already knows which tags matter.
def rank_specific_tag_markets(games_col, tags, genre=None):
    tag_list = sorted(set(tags or []))
    if not tag_list:
        return []

    match = build_market_query(genre=genre)
    match["tags"] = {"$in": tag_list}
    pipeline = [
        {"$match": match},
        {"$unwind": "$tags"},
        {"$match": {"tags": {"$in": tag_list}}},
        {"$group": {
            "_id": "$tags",
            "total_games": {"$sum": 1},
            "paid_games": {
                "$sum": {
                    "$cond": [
                        {"$and": [
                            {"$ne": ["$is_free", True]},
                            {"$gt": ["$price.current", 0]},
                        ]},
                        1,
                        0,
                    ]
                }
            },
            "revenue_high": {"$sum": {"$ifNull": ["$estimated_revenue.high", 0]}},
            "total_players": {"$sum": {"$ifNull": ["$players.current", 0]}},
            "avg_score": {"$avg": "$review_summary.positive_percent"},
            "avg_price": {"$avg": "$price.current"},
        }},
        {"$project": {
            "_id": 0,
            "market": "$_id",
            "market_type": "tag",
            "genre": genre,
            "total_games": 1,
            "paid_games": 1,
            "estimated_revenue_high": "$revenue_high",
            "total_current_players": "$total_players",
            "avg_review_score_pct": {"$round": [{"$ifNull": ["$avg_score", 0]}, 1]},
            "avg_price_usd": {"$round": [{"$ifNull": ["$avg_price", 0]}, 2]},
        }},
    ]
    return list(games_col.aggregate(pipeline, allowDiskUse=True))


# Find tags in the "goldilocks" size range (min_games-max_games) — big
# enough to trust the numbers, small enough to be an actually-navigable
# niche — and score them by revenue/player density, review quality, and fit
# to that size window. This is the main "niche opportunity" signal fed into
# the AI brief (see niche_score / why_it_matters below).
def smaller_subgenre_report(games_col, genre=None, limit=15, min_games=25, max_games=750, curated_tags=None):
    curated_tag_set = set(curated_tags or [])
    tags = (
        rank_specific_tag_markets(games_col, curated_tag_set, genre=genre)
        if curated_tag_set
        else rank_tag_markets(games_col, genre=genre, limit=300)
    )
    candidates = []

    for tag in tags:
        name = tag.get("market")
        total_games = _num(tag.get("total_games"))
        if not name or name in BROAD_TAGS:
            continue
        if curated_tag_set and name not in curated_tag_set:
            continue
        if total_games < min_games or total_games > max_games:
            continue

        paid_games = _num(tag.get("paid_games"))
        revenue = _num(tag.get("estimated_revenue_high"))
        players = _num(tag.get("total_current_players"))
        avg_score = _num(tag.get("avg_review_score_pct"))

        revenue_per_game = revenue / max(total_games, 1)
        demand_density = players / max(total_games, 1)
        quality_signal = max(0, avg_score - 70) / 30
        quality_gap = max(0, 78 - avg_score) / 78
        size_fit = 1 - min(1, abs(total_games - 150) / 600)

        tag["revenue_per_game_estimate"] = round(revenue_per_game)
        tag["current_players_per_game"] = round(demand_density, 1)
        # Weighted 0-100 score: revenue-per-game and player density carry
        # the most weight (0.35/0.25) since they're the strongest signal of
        # "worth entering." quality_signal rewards tags where existing games
        # already review well (a healthy market), quality_gap does the
        # opposite — rewards tags where reviews are mediocre despite demand
        # (room to out-execute incumbents). size_fit prefers tags near 150
        # games: enough competition data to trust, not so much it's crowded.
        tag["niche_score"] = round((
            min(1, revenue_per_game / 750_000) * 0.35
            + min(1, demand_density / 300) * 0.25
            + quality_signal * 0.15
            + quality_gap * 0.10
            + size_fit * 0.15
        ) * 100, 1)
        tag["why_it_matters"] = _small_subgenre_signal(tag)
        tag["market_summary_url"] = _market_summary_path(genre, name)
        tag["paid_game_ratio_pct"] = round((paid_games / total_games) * 100, 1) if total_games else 0
        candidates.append(tag)

    strongest = sorted(
        candidates,
        key=lambda t: (t["niche_score"], _num(t.get("revenue_per_game_estimate"))),
        reverse=True,
    )[:max(1, min(int(limit), 50))]

    less_prominent = sorted(
        candidates,
        key=lambda t: (
            _num(t.get("total_games")),
            -_num(t.get("revenue_per_game_estimate")),
            -_num(t.get("avg_review_score_pct")),
        ),
    )[:max(1, min(int(limit), 50))]

    return {
        "scope": genre or "all genres",
        "filters": {
            "curated_only": bool(curated_tag_set),
            "excluded_broad_tags": sorted(BROAD_TAGS),
            "min_games": min_games,
            "max_games": max_games,
            "reason": "Focuses on smaller Steam tags with enough games to compare but avoids giant umbrella tags.",
        },
        "strongest_small_subgenres": strongest,
        "less_prominent_small_subgenres": less_prominent,
        "how_to_read": (
            "Niche score favors revenue per game, current-player density, review signal, and manageable competition. "
            "It is directional, not a guarantee."
        ),
        "disclaimer": "Revenue and owner figures are SteamSpy-based estimates, not official Steam data.",
    }


# Like smaller_subgenre_report, but for a known list of "child" tags under
# one broad subgenre (e.g. Shooter -> First-Person Shooter, Battle Royale,
# ...) — see market_taxonomy.SUBGENRE_CHILDREN. Falls back to a plain
# summarize_market() call for any child rank_specific_tag_markets didn't
# return a row for (can happen if it has too few games to surface in the
# ranked aggregation but still clears min_games here).
def child_subgenre_report(games_col, parent, children, genre=None, limit=20, min_games=5):
    ranked = {tag["market"]: tag for tag in rank_specific_tag_markets(games_col, children, genre=genre)}
    rows = []

    for child in children:
        tag = ranked.get(child)
        if not tag:
            summary = summarize_market(games_col, genre=genre, tag=child)
            if not summary:
                continue
            tag = {
                "market": child,
                "market_type": "tag",
                "genre": genre,
                "total_games": summary["total_games"],
                "paid_games": summary["paid_games"],
                "estimated_revenue_high": summary["estimated_revenue_high"],
                "total_current_players": summary["total_current_players"],
                "avg_review_score_pct": summary["avg_review_score_pct"],
                "avg_price_usd": summary["avg_price_usd"],
            }

        total_games = _num(tag.get("total_games"))
        if total_games < min_games:
            continue

        revenue = _num(tag.get("estimated_revenue_high"))
        players = _num(tag.get("total_current_players"))
        avg_score = _num(tag.get("avg_review_score_pct"))
        revenue_per_game = revenue / max(total_games, 1)
        players_per_game = players / max(total_games, 1)

        tag["parent_subgenre"] = parent
        tag["revenue_per_game_estimate"] = round(revenue_per_game)
        tag["current_players_per_game"] = round(players_per_game, 1)
        tag["child_score"] = round((
            min(1, revenue_per_game / 750_000) * 0.40
            + min(1, players_per_game / 300) * 0.25
            + max(0, avg_score - 70) / 30 * 0.20
            + min(1, total_games / 150) * 0.15
        ) * 100, 1)
        tag["market_summary_url"] = _market_summary_path(genre, tag.get("market"))
        rows.append(tag)

    rows.sort(key=lambda t: (t["child_score"], _num(t.get("revenue_per_game_estimate"))), reverse=True)

    return {
        "genre": genre,
        "parent_subgenre": parent,
        "children_requested": children,
        "children_found": rows[:max(1, min(int(limit), 50))],
        "how_to_read": "Child score compares sub-subgenres by revenue per game, active-player density, review score, and sample size.",
        "disclaimer": "Revenue and owner figures are SteamSpy-based estimates, not official Steam data.",
    }


# Rank tags by "opportunity" — high revenue/player scale, weighted against
# review quality (a lower avg score = more room to win on quality) and
# competition size. Unlike smaller_subgenre_report, this doesn't filter to
# a size window, so broad umbrella tags (Action, Singleplayer) can and do
# show up here — they're framed as "context, not a real niche" in the AI
# prompt instructions, not filtered out.
def market_opportunities(games_col, genre=None, limit=12):
    tags = rank_tag_markets(games_col, genre=genre, limit=80)
    if not tags:
        return []

    max_revenue = max(_num(t.get("estimated_revenue_high")) for t in tags) or 1
    max_players = max(_num(t.get("total_current_players")) for t in tags) or 1
    scored = []

    for tag in tags:
        games = max(1, _num(tag.get("total_games"), 1))
        revenue_score = _num(tag.get("estimated_revenue_high")) / max_revenue
        player_score = _num(tag.get("total_current_players")) / max_players
        quality_gap = max(0, 82 - _num(tag.get("avg_review_score_pct"))) / 82
        competition_penalty = min(1, games / 500)
        opportunity_score = round(((revenue_score * 0.45) + (player_score * 0.25) + (quality_gap * 0.20) + ((1 - competition_penalty) * 0.10)) * 100, 1)

        tag["opportunity_score"] = opportunity_score
        tag["signal"] = _opportunity_signal(tag)
        scored.append(tag)

    scored.sort(key=lambda t: t["opportunity_score"], reverse=True)
    return scored[:max(1, min(int(limit), 50))]


# Split tags into "doing well" (highest revenue/players — the
# already-crowded/successful markets) vs. "less prominent" (smaller
# visibility but still enough sample to compare) via a weighted
# prominence_score. This is what answers "what's underserved" / "what's
# less prominent right now" style questions.
def prominence_report(games_col, genre=None, limit=10):
    markets = rank_tag_markets(games_col, genre=genre, limit=100)
    if not markets:
        markets = rank_genre_markets(games_col)

    max_games = max(_num(m.get("total_games")) for m in markets) or 1
    max_revenue = max(_num(m.get("estimated_revenue_high")) for m in markets) or 1
    max_players = max(_num(m.get("total_current_players")) for m in markets) or 1

    for market in markets:
        market["prominence_score"] = round((
            (_num(market.get("total_games")) / max_games * 0.35)
            + (_num(market.get("estimated_revenue_high")) / max_revenue * 0.45)
            + (_num(market.get("total_current_players")) / max_players * 0.20)
        ) * 100, 1)

    doing_well = sorted(
        markets,
        key=lambda m: (_num(m.get("estimated_revenue_high")), _num(m.get("total_current_players"))),
        reverse=True,
    )[:limit]

    less_prominent = sorted(
        [
            m for m in markets
            if _num(m.get("estimated_revenue_high")) > 0 and _num(m.get("total_games")) >= 10
        ],
        key=lambda m: (m["prominence_score"], -_num(m.get("avg_review_score_pct"))),
    )[:limit]

    return {
        "scope": genre or "all genres",
        "doing_well": doing_well,
        "less_prominent": less_prominent,
        "how_to_read": "Doing well favors revenue and current players. Less prominent favors smaller/less visible markets with enough data to compare.",
        "disclaimer": "Signals are directional and based on the local Steam/SteamSpy dataset.",
    }


# Player-count trend over the last `days` days for a genre or tag.
#
# Tries precomputed daily snapshots first (genre_snapshots/tag_snapshots —
# fast, but only exist for markets a snapshot job actually tracks), and
# falls back to aggregating raw player_snapshots for every matching game id
# if no precomputed snapshot series exists. See _summarize_momentum for the
# actual trend/confidence calculation.
#
# Known issue: real AI-brief runs have surfaced what looks like a data
# artifact — a single day's total_players collapsing far below neighboring
# days before rebounding (see daily_snapshot.py, which writes
# genre_snapshots). Worth investigating whether a snapshot run is recording
# partial/incomplete counts instead of skipping on failure. Until fixed,
# _build_question_answerability downweights low-confidence momentum rather
# than trusting it outright.
def market_momentum(games_col, db, genre=None, tag=None, days=30, max_games=1500):
    if tag and not genre:
        tag_result = _tag_snapshot_momentum(db, tag, days=days)
        if tag_result:
            return tag_result

    if genre and not tag:
        genre_result = _genre_snapshot_momentum(db, genre, days=days)
        if genre_result:
            return genre_result

    query = build_market_query(genre=genre, tag=tag)
    game_ids = [
        g["steam_app_id"]
        for g in games_col.find(query, {"_id": 0, "steam_app_id": 1}).limit(max_games)
        if g.get("steam_app_id")
    ]

    if not game_ids:
        return _empty_momentum(genre=genre, tag=tag, days=days, reason="No matching games found.")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    snapshots = list(db["player_snapshots"].aggregate([
        {"$match": {
            "steam_app_id": {"$in": game_ids},
            "timestamp": {"$gte": since},
        }},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "total_players": {"$sum": {"$ifNull": ["$current_players", 0]}},
            "games_sampled": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "_id": 0,
            "date": "$_id",
            "total_players": 1,
            "games_sampled": 1,
        }},
    ], allowDiskUse=True))

    return _summarize_momentum(
        snapshots,
        genre=genre,
        tag=tag,
        days=days,
        source="player_snapshots",
        sample_size=len(game_ids),
    )


# Momentum from the precomputed genre_snapshots collection (one row/genre/day,
# written by daily_snapshot.py). Returns None if there's no snapshot history
# yet, so the caller can fall back to the slower raw player_snapshots
# aggregation.
def _genre_snapshot_momentum(db, genre, days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    snapshots = list(db["genre_snapshots"].find(
        {"genre": genre, "date": {"$gte": since}},
        {"_id": 0, "date": 1, "total_players": 1, "total_games": 1},
    ).sort("date", 1))

    if not snapshots:
        return None

    normalized = [
        {
            "date": s.get("date"),
            "total_players": _num(s.get("total_players")),
            "games_sampled": _num(s.get("total_games")),
        }
        for s in snapshots
    ]
    return _summarize_momentum(
        normalized,
        genre=genre,
        tag=None,
        days=days,
        source="genre_snapshots",
        sample_size=max((_num(s.get("games_sampled")) for s in normalized), default=0),
    )


# Same as _genre_snapshot_momentum but for the tag_snapshots collection.
def _tag_snapshot_momentum(db, tag, days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    snapshots = list(db["tag_snapshots"].find(
        {"tag": tag, "date": {"$gte": since}},
        {"_id": 0, "date": 1, "total_players": 1, "total_games": 1},
    ).sort("date", 1))

    if not snapshots:
        return None

    normalized = [
        {
            "date": s.get("date"),
            "total_players": _num(s.get("total_players")),
            "games_sampled": _num(s.get("total_games")),
        }
        for s in snapshots
    ]
    return _summarize_momentum(
        normalized,
        genre=None,
        tag=tag,
        days=days,
        source="tag_snapshots",
        sample_size=max((_num(s.get("games_sampled")) for s in normalized), default=0),
    )


# Turn a list of {date, total_players, games_sampled} points into a
# first-vs-last percent-change trend with a confidence label.
#
# unstable_sample below only catches instability in *how many games got
# sampled* on a given day (a coverage problem) — it does NOT catch a day
# where the normal number of games were sampled but individual player
# counts came back wrong (a values problem). That's a real gap: repeated
# AI-brief runs have flagged single-day total_players collapses that this
# check doesn't catch (see the note in market_momentum above). A
# magnitude-based outlier check against neighboring days would close it.
def _summarize_momentum(snapshots, genre=None, tag=None, days=30, source="unknown", sample_size=0):
    if len(snapshots) < 2:
        return _empty_momentum(
            genre=genre,
            tag=tag,
            days=days,
            reason="Not enough historical snapshot points yet.",
            source=source,
            sample_size=sample_size,
            points=snapshots,
        )

    first = next((s for s in snapshots if _num(s.get("total_players")) > 0), snapshots[0])
    last = snapshots[-1]
    first_players = _num(first.get("total_players"))
    last_players = _num(last.get("total_players"))
    sampled_counts = [_num(s.get("games_sampled")) for s in snapshots if _num(s.get("games_sampled")) > 0]
    min_sampled = min(sampled_counts) if sampled_counts else 0
    max_sampled = max(sampled_counts) if sampled_counts else 0
    last_sampled = _num(last.get("games_sampled"))
    coverage_pct = round((last_sampled / sample_size) * 100, 1) if sample_size else None
    unstable_sample = (
        source == "player_snapshots"
        and (
            (sample_size and last_sampled < sample_size * 0.20)
            or (max_sampled and min_sampled < max_sampled * 0.50)
        )
    )
    delta = last_players - first_players
    pct = round((delta / first_players) * 100, 1) if first_players else None

    if unstable_sample:
        direction = "unknown"
    elif pct is None:
        direction = "unknown"
    elif pct >= 10:
        direction = "growing"
    elif pct <= -10:
        direction = "declining"
    else:
        direction = "flat"

    return {
        "market": tag or genre or "Steam",
        "genre": genre,
        "tag": tag,
        "days": days,
        "source": source,
        "sample_size": sample_size,
        "sample_coverage_pct": coverage_pct,
        "min_games_sampled_per_point": min_sampled,
        "max_games_sampled_per_point": max_sampled,
        "data_points": len(snapshots),
        "first_date": first.get("date"),
        "last_date": last.get("date"),
        "first_total_players": first_players,
        "last_total_players": last_players,
        "absolute_change": delta,
        "percent_change": pct,
        "direction": direction,
        "trend": snapshots[-14:],
        "confidence": "low" if unstable_sample else "medium" if len(snapshots) >= 7 else "low",
        "reason": "Snapshot coverage is too sparse or inconsistent for a directional claim." if unstable_sample else None,
        "note": "Momentum is based on current-player snapshots, not official sales growth.",
    }


# Shared "no usable momentum data" response shape, so callers (no matching
# games, too few snapshot points, ...) all return something the
# frontend/AI prompt can handle uniformly instead of null/an exception.
def _empty_momentum(genre=None, tag=None, days=30, reason="", source="unknown", sample_size=0, points=None):
    return {
        "market": tag or genre or "Steam",
        "genre": genre,
        "tag": tag,
        "days": days,
        "source": source,
        "sample_size": sample_size,
        "data_points": len(points or []),
        "direction": "unknown",
        "reason": reason,
        "trend": points or [],
        "note": "Run player/tag snapshots over time before making growth claims.",
    }


# Guess a genre/tag from free-text (a typed question, a concept
# description) by simple substring matching — no NLP/ML involved. Only
# used when the caller didn't already know the genre/tag (e.g. the user
# typed a question instead of clicking a suggestion with a known
# genre/tag — see SUGGESTIONS in static/app.js for why most canned
# suggestions bypass this and pass genre/tag explicitly instead: this
# approach can miss real matches (an acronym like "FPS" won't match the
# tag "First-Person Shooter") or find nothing for genre-agnostic
# questions ("what review score should I target").
def infer_market_context(games_col, text, known_tags=None):
    lowered = (text or "").lower()
    genre = next((g for g in GENRES if g.lower() in lowered), None)

    tag = None
    known_matches = [
        t for t in (known_tags or [])
        if t and t.lower() in lowered
    ]
    if known_matches:
        tag = sorted(known_matches, key=len, reverse=True)[0]

    common_tags = rank_tag_markets(games_col, genre=genre, limit=100)
    # Prefer the longest matching tag so "Action RPG" beats "RPG".
    matching_tags = [
        t["market"] for t in common_tags
        if t.get("market") and t["market"].lower() in lowered
    ]
    if matching_tags:
        candidates = matching_tags + ([tag] if tag else [])
        tag = sorted(candidates, key=len, reverse=True)[0]

    return {"genre": genre, "tag": tag}


# Keyword-routed canned responses for the in-app chat widget
# (blueprints/chat.py) — no LLM call, just template strings filled from
# real numbers. Distinct from the AI-brief system (blueprints/insights.py),
# which hands a JSON payload off to an external tool instead of answering
# in-app.
def answer_without_llm(games_col, message):
    text = (message or "").strip()
    lowered = text.lower()

    inferred = infer_market_context(games_col, text)
    matched_genre = inferred["genre"]
    matched_tag = inferred["tag"]

    if "less prominent" in lowered or "underserved" in lowered or "opportunit" in lowered:
        opportunities = market_opportunities(games_col, genre=matched_genre, limit=5)
        if not opportunities:
            return "I could not find enough market data yet. Try syncing more games first."
        lines = [f"No in-app LLM is active. Here are the strongest data-only opportunities for {matched_genre or 'Steam'}:"]
        for item in opportunities:
            lines.append(
                f"- {item['market']}: score {item['opportunity_score']}/100, "
                f"{item['total_games']} games, est. market {_money(item['estimated_revenue_high'])}, "
                f"{_num(item.get('avg_review_score_pct'))}% avg positive. {item['signal']}"
            )
        lines.append("For deeper natural-language reasoning, paste these results into ChatGPT.")
        return "\n".join(lines)

    if "doing well" in lowered or "popular" in lowered or "trending" in lowered:
        report = prominence_report(games_col, genre=matched_genre, limit=5)
        lines = [f"No in-app LLM is active. Markets doing well for {matched_genre or 'Steam'}:"]
        for item in report["doing_well"]:
            lines.append(
                f"- {item['market']}: est. market {_money(item['estimated_revenue_high'])}, "
                f"{item['total_games']} games, {item.get('total_current_players', 0):,} current players."
            )
        return "\n".join(lines)

    if matched_genre or matched_tag:
        summary = summarize_market(games_col, genre=matched_genre, tag=matched_tag)
        if summary:
            comps = top_competitors(games_col, genre=matched_genre, tag=matched_tag, limit=3)
            lines = [
                f"No in-app LLM is active. Data summary for {summary['market']}:",
                f"- {summary['total_games']} games, {summary['paid_games']} paid",
                f"- Estimated market: {_money(summary['estimated_revenue_low'])} - {_money(summary['estimated_revenue_high'])}",
                f"- Avg price: ${summary['avg_price_usd']}; avg review score: {summary['avg_review_score_pct']}%",
                f"- Median revenue estimate: {_money(summary['median_revenue_estimate'])}",
            ]
            if comps:
                lines.append("- Top competitors: " + ", ".join(c.get("title", "Unknown") for c in comps))
            lines.append("Revenue figures are SteamSpy estimates, not official Steam data.")
            return "\n".join(lines)

    return (
        "In-app LLM chat is intentionally off so this app does not create API costs. "
        "Use the genre pages, market cards, and insight endpoints for data. "
        "For AI reasoning, open ChatGPT and ask it to analyze the JSON from /api/insights/prominence, "
        "/api/insights/opportunities, or /api/insights/market."
    )


# Short human-readable "why this shows up as an opportunity" string for market_opportunities rows.
def _opportunity_signal(item):
    signals = []
    if _num(item.get("estimated_revenue_high")) >= 1_000_000:
        signals.append("meaningful revenue pool")
    if _num(item.get("total_games")) < 75:
        signals.append("lighter competition")
    if _num(item.get("avg_review_score_pct")) < 75:
        signals.append("possible quality gap")
    if _num(item.get("total_current_players")) > 0:
        signals.append("active player demand")
    return "; ".join(signals) if signals else "worth comparing against direct competitors"


# Short human-readable "why it matters" string for smaller_subgenre_report rows.
def _small_subgenre_signal(item):
    signals = []
    if _num(item.get("revenue_per_game_estimate")) >= 250_000:
        signals.append("healthy estimated revenue per game")
    if _num(item.get("total_games")) <= 150:
        signals.append("smaller competition pool")
    if _num(item.get("current_players_per_game")) >= 50:
        signals.append("active demand density")
    if _num(item.get("avg_review_score_pct")) < 75:
        signals.append("possible quality gap")
    if _num(item.get("avg_review_score_pct")) >= 80:
        signals.append("players reward quality in this niche")
    return "; ".join(signals) if signals else "worth deeper competitor review"


# Build the /api/insights/market URL for a niche row, so the AI brief can
# point to where to pull a full summary for that specific tag.
def _market_summary_path(genre, tag):
    if genre:
        return f"/api/insights/market?genre={genre}&tag={tag}"
    return f"/api/insights/market?tag={tag}"
