from flask import Flask, jsonify, request, render_template, Response, send_from_directory
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json

load_dotenv()

from market_insights import (
    DATA_POINT_CATALOG,
    SOURCE_CONFIDENCE,
    answer_without_llm,
    child_subgenre_report,
    market_opportunities,
    infer_market_context,
    market_momentum,
    prominence_report,
    rank_genre_markets,
    rank_tag_markets,
    summarize_market,
    smaller_subgenre_report,
    top_competitors,
)
from market_taxonomy import (
    GENRE_SUBGENRE_GROUPS,
    SUBGENRE_CHILDREN,
    all_taxonomy_tags,
    children_for_subgenre,
    groups_for_genre,
)
from virtual_tags import build_tag_matcher, build_virtual_tag_query, game_matches_virtual_tag, is_virtual_tag

app = Flask(__name__)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
genre_aggregates_col = db["genre_aggregates"]

AI_HANDOFF_TOOLS = {
    "chatgpt": {"label": "ChatGPT", "url": "https://chatgpt.com/"},
    "claude": {"label": "Claude", "url": "https://claude.ai/"},
    "gemini": {"label": "Gemini", "url": "https://gemini.google.com/"},
    "perplexity": {"label": "Perplexity", "url": "https://www.perplexity.ai/"},
    "copilot": {"label": "Microsoft Copilot", "url": "https://copilot.microsoft.com/"},
    "grok": {"label": "Grok", "url": "https://grok.com/"},
    "poe": {"label": "Poe", "url": "https://poe.com/"},
    "phind": {"label": "Phind", "url": "https://phindai.org/phind-chat/"},
    "lechat": {"label": "Mistral Le Chat", "url": "https://chat.mistral.ai/chat"},
    "you": {"label": "You.com", "url": "https://you.com/?chatMode=default"},
    "deepseek": {"label": "DeepSeek", "url": "https://chat.deepseek.com/"},
}
DEFAULT_AI_TOOL = "chatgpt"
BRIEF_MODES = {
    "general": {
        "label": "Market Deep Dive",
        "instruction": "Give a rounded market read: demand, competition, pricing, risk, and opportunity for a small indie team.",
    },
    "quick": {
        "label": "Quick Answer",
        "instruction": "Answer directly and briefly. Prioritize the user's question and the 3-5 most decision-useful data points.",
    },
    "competition": {
        "label": "Competitor Analysis",
        "instruction": "Focus on competitor shape, benchmark titles, market crowding, and where a new game could differentiate.",
    },
    "pricing": {
        "label": "Pricing and Launch",
        "instruction": "Focus on pricing, review-score expectations, wishlist/readiness signals, and launch-positioning implications.",
    },
}


def get_ai_handoff_tool(tool_id=None):
    """Return a supported AI handoff destination."""
    key = (tool_id or DEFAULT_AI_TOOL).lower()
    if key not in AI_HANDOFF_TOOLS:
        key = DEFAULT_AI_TOOL
    return {"id": key, **AI_HANDOFF_TOOLS[key]}


def get_brief_mode(mode_id=None):
    key = (mode_id or "general").lower()
    if key not in BRIEF_MODES:
        key = "general"
    return {"id": key, **BRIEF_MODES[key]}


def build_follow_up_prompts(question="", genre=None, tag=None, summary=None, include_concept=False):
    market_name = tag or genre or (summary or {}).get("market") or "this market"
    market_label = f"{market_name} on Steam"
    prompts = [
        f"What makes {market_label} attractive for a small indie team?",
        f"What risks stand out in the {market_name} market right now?",
        f"Which competitors should I study before entering {market_name}?",
        f"What price range looks most credible in {market_name}?",
        f"What tags overlap most with the audience for {market_name}?",
    ]
    if tag:
        prompts.extend([
            f"Should I position this as {tag} first or lead with the broader {genre or 'genre'}?",
            f"What sub-subgenres inside {tag} look least crowded?",
        ])
    if genre and not tag:
        prompts.extend([
            f"Which subgenres inside {genre} feel most indie-friendly?",
            f"What kind of game concept has the best chance in {genre} right now?",
        ])
    if include_concept:
        prompts.extend([
            "Which audience would most likely buy this concept on Steam?",
            "What tags should this concept probably lead with on Steam?",
        ])
    if question:
        prompts.append(f"Based on this question, what should I ask next: {question}")

    deduped = []
    seen = set()
    for prompt in prompts:
        if prompt not in seen:
            seen.add(prompt)
            deduped.append(prompt)
    return deduped[:8]


def analyze_concept(games_col, description):
    text = (description or "").strip()
    inferred = infer_market_context(
        games_col,
        text,
        known_tags=_curated_subgenre_tags() | all_taxonomy_tags(),
    )
    genre = inferred.get("genre")
    tag = inferred.get("tag")
    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    smaller = smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=6,
        curated_tags=_curated_subgenre_tags(genre),
    )
    opportunities = market_opportunities(games_col, genre=genre, limit=5)
    competitors = top_competitors(games_col, genre=genre, tag=tag, limit=5) if (genre or tag) else []
    return {
        "description": text,
        "inferred_context": inferred,
        "likely_market": summary,
        "opportunities": opportunities,
        "smaller_subgenres": smaller,
        "top_competitors": competitors,
        "follow_up_prompts": build_follow_up_prompts(
            question=text,
            genre=genre,
            tag=tag,
            summary=summary,
            include_concept=True,
        ),
    }


def build_compare_data(games_col, left_genre=None, left_tag=None, right_genre=None, right_tag=None):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        fl = ex.submit(summarize_market, games_col, left_genre, left_tag)
        fr = ex.submit(summarize_market, games_col, right_genre, right_tag)
        left, right = fl.result(), fr.result()
    if not left or not right:
        return None

    def pct_diff(a, b):
        if not a or not b:
            return None
        return round(((a - b) / b) * 100, 1)

    return {
        "left": left,
        "right": right,
        "delta": {
            "estimated_revenue_high_pct": pct_diff(left.get("estimated_revenue_high"), right.get("estimated_revenue_high")),
            "avg_review_score_pct": round(left.get("avg_review_score_pct", 0) - right.get("avg_review_score_pct", 0), 1),
            "total_games_pct": pct_diff(left.get("total_games"), right.get("total_games")),
            "som_high_pct": pct_diff(left.get("SOM", {}).get("high"), right.get("SOM", {}).get("high")),
        },
        "follow_up_prompts": [
            f"Which of these two markets looks better for a small indie team: {left['market']} or {right['market']}?",
            f"What is the biggest risk difference between {left['market']} and {right['market']}?",
            f"Which market gives a better pricing and launch setup: {left['market']} or {right['market']}?",
        ],
    }


def _niche_reliability_label(item):
    total_games = (item or {}).get("total_games") or 0
    paid_games = (item or {}).get("paid_games") or 0
    if total_games < 40 or paid_games < 30:
        return "low"
    if total_games < 120 or paid_games < 80:
        return "medium"
    return "higher"


def _recommendation_flag(reliability, confirmed_child_tag):
    if reliability == "low":
        return "caution"
    if confirmed_child_tag:
        return "yes"
    if reliability == "higher":
        return "caution"
    return "caution"


def _annotate_niche_candidates(items, confirmed_children=None):
    confirmed = set(confirmed_children or [])
    annotated = []
    for item in items or []:
        row = dict(item)
        reliability = _niche_reliability_label(row)
        confirmed_child_tag = row.get("market") in confirmed if row.get("market") else False
        recommendation_flag = _recommendation_flag(reliability, confirmed_child_tag)
        row["data_reliability"] = reliability
        row["confirmed_child_tag"] = confirmed_child_tag
        row["market_relationship"] = "confirmed_child" if confirmed_child_tag else "adjacent_or_unconfirmed"
        row["use_for_recommendation"] = recommendation_flag
        row["raw_revenue_per_game_estimate"] = row.get("revenue_per_game_estimate")
        if reliability == "low":
            row["reliability_note"] = (
                "Small sample. Revenue-per-game and opportunity signals may be skewed by one or two breakout hits."
            )
            row["revenue_per_game_estimate"] = None
            row["revenue_metric_guidance"] = (
                "Suppressed for recommendation use because this niche is low reliability. "
                "Use broad-market outlier-adjusted benchmarks and direct competitor checks instead."
            )
        elif reliability == "medium":
            row["reliability_note"] = (
                "Moderate sample. Treat niche upside as directional and validate against direct competitors."
            )
            row["revenue_metric_guidance"] = (
                "Directional only. Validate against direct competitors before using this as a planning anchor."
            )
        else:
            row["reliability_note"] = (
                "Larger sample than most niche tags here, but still directional rather than guaranteed."
            )
            row["revenue_metric_guidance"] = (
                "More decision-useful than tiny-sample niches, but still not a guaranteed outcome."
            )
        if confirmed_child_tag:
            row["recommendation_note"] = (
                "Confirmed child tag in the current taxonomy context. Safer to discuss as an FPS-specific niche."
            )
        elif reliability == "higher":
            row["recommendation_note"] = (
                "Adjacent opportunity with a stronger sample, but not confirmed as a child tag in the current taxonomy."
            )
        else:
            row["recommendation_note"] = (
                "Use as a hypothesis to validate, not as a final recommendation."
            )
        annotated.append(row)
    return annotated


def _build_brief_diagnostics(summary=None, momentum=None, smaller=None, opportunities=None, taxonomy=None):
    diagnostics = {
        "decision_rules": [
            "Prefer outlier-adjusted per-game benchmarks over raw TAM/SAM when judging indie feasibility.",
            "Treat broad-market size as context, not proof that a small team can win there.",
            "Use top competitors as examples, not the main evidence base.",
            "Downweight any niche with low data_reliability or missing taxonomy support.",
        ],
        "red_flags": [],
        "niche_reliability_guide": {
            "higher": "Larger niche sample; still directional, but more decision-useful than tiny-sample niches.",
            "medium": "Usable for exploration, but validate with direct competitor reads.",
            "low": "Thin-sample niche; do not treat large revenue-per-game numbers as realistic targets.",
        },
    }

    if summary:
        sample_notes = summary.get("sample_notes") or {}
        diagnostics["benchmark_preference"] = {
            "prefer": "realistic_revenue_target and performance_benchmarks.per_game_revenue_estimate",
            "avoid_overweighting": "TAM, SAM, and raw niche revenue-per-game values when making indie go/no-go calls",
            "reason": sample_notes.get("outlier_handling"),
        }
        legacy_low = ((summary.get("SOM") or {}).get("legacy_percent_capture_low")) or 0
        som_high = ((summary.get("SOM") or {}).get("high")) or 0
        if legacy_low and som_high and legacy_low > som_high * 50:
            diagnostics["red_flags"].append(
                "Ignore SOM legacy_percent_capture fields for decision-making; they can dwarf the outlier-adjusted SOM range."
            )

    if momentum:
        if (momentum.get("confidence") or "").lower() == "low":
            diagnostics["red_flags"].append(
                "Momentum is low-confidence. Do not use it as evidence of market growth or decline."
            )
        if momentum.get("sample_coverage_pct") is not None:
            diagnostics["momentum_reading_rule"] = {
                "sample_coverage_pct": momentum.get("sample_coverage_pct"),
                "confidence": momentum.get("confidence"),
                "instruction": "Only use momentum directionally when confidence is not low and coverage is reasonably broad.",
            }

    taxonomy_context = taxonomy or {}
    has_child_report = bool((taxonomy_context.get("child_report") or {}).get("children_found"))
    has_child_tags = bool(taxonomy_context.get("children_for_detected_tag"))
    confirmed_children = set(taxonomy_context.get("children_for_detected_tag") or [])
    confirmed_children.update(
        row.get("market")
        for row in ((taxonomy_context.get("child_report") or {}).get("children_found") or [])
        if row.get("market")
    )
    if not has_child_report and not has_child_tags:
        diagnostics["red_flags"].append(
            "Taxonomy support is thin for this market. Some niche recommendations may be adjacent tags rather than confirmed child tags."
        )

    diagnostics["recommendation_flag_guide"] = {
        "yes": "Reasonable to recommend directly, assuming the rest of the evidence is supportive.",
        "caution": "Interesting, but validate with direct competitors and treat upside as directional.",
        "no": "Do not recommend directly from this dataset alone.",
    }
    diagnostics["niche_validation"] = {
        "strongest_small_subgenres": _annotate_niche_candidates(
            (smaller or {}).get("strongest_small_subgenres"),
            confirmed_children=confirmed_children,
        ),
        "less_prominent_small_subgenres": _annotate_niche_candidates(
            (smaller or {}).get("less_prominent_small_subgenres"),
            confirmed_children=confirmed_children,
        ),
        "opportunities": _annotate_niche_candidates(
            opportunities,
            confirmed_children=confirmed_children,
        ),
    }
    diagnostics["niche_reading_rule"] = (
        "Prefer niches that have both stronger data_reliability and a clear qualitative signal. "
        "If a niche has low reliability, present it as a hypothesis to validate, not as a recommendation with firm upside."
    )
    return diagnostics


# ----------------------------
# Frontend
# ----------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/branding/<path:filename>")
def branding_file(filename):
    return send_from_directory("branding", filename)


# ----------------------------
# Game Routes
# ----------------------------

@app.route("/api/games/search")
def search_games():
    """Search games by title. Falls back to Steam API if nothing found locally."""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "No search query provided"}), 400

    results = list(games_col.find(
        {"title": {"$regex": query, "$options": "i"}},
        {"_id": 0, "steam_app_id": 1, "title": 1, "genres": 1, "tags": 1,
         "price": 1, "is_free": 1, "review_summary": 1, "estimated_revenue": 1,
         "header_image_url": 1}
    ).limit(20))

    if not results:
        from steam_api import get_steam_game_details, get_steamspy_details, parse_game
        from datetime import datetime, timezone
        # Search Steam directly by name
        search_url = f"https://store.steampowered.com/api/storesearch/?term={query}&cc=us&l=en"
        import requests as req
        r = req.get(search_url)
        if r.status_code == 200:
            items = r.json().get("items", [])[:5]
            for item in items:
                app_id = item.get("id")
                if not app_id:
                    continue
                existing = games_col.find_one({"steam_app_id": app_id}, {"_id": 0})
                if existing:
                    results.append(existing)
                    continue
                steam_data = get_steam_game_details(app_id)
                spy_data = get_steamspy_details(app_id)
                game = parse_game(steam_data, spy_data)
                if game:
                    game["last_updated"] = datetime.now(timezone.utc)
                    games_col.insert_one(game)
                    game.pop("_id", None)
                    results.append(game)

    return jsonify(results)


@app.route("/api/games/<int:app_id>")
def get_game(app_id):
    """Get full details for a single game. Fetches from Steam if not in database."""
    game = games_col.find_one({"steam_app_id": app_id}, {"_id": 0})

    if not game:
        from steam_api import get_steam_game_details, get_steamspy_details, parse_game
        from datetime import datetime, timezone
        steam_data = get_steam_game_details(app_id)
        spy_data = get_steamspy_details(app_id)
        game = parse_game(steam_data, spy_data)
        if not game:
            return jsonify({"error": "Game not found"}), 404
        game["last_updated"] = datetime.now(timezone.utc)
        games_col.insert_one(game)
        game.pop("_id", None)

    return jsonify(game)


def _parse_filters(args):
    """Build a MongoDB match dict from query string filter params."""
    filters = {}
    min_price = args.get("min_price", type=float)
    max_price = args.get("max_price", type=float)
    if min_price is not None or max_price is not None:
        price_q = {}
        if min_price is not None:
            price_q["$gte"] = min_price
        if max_price is not None:
            price_q["$lte"] = max_price
        filters["price.current"] = price_q
    min_score = args.get("min_score", type=int)
    if min_score is not None:
        filters["review_summary.positive_percent"] = {"$gte": min_score}
    year = args.get("year", type=int)
    if year is not None:
        filters["release_date"] = {"$regex": f"{year}"}
    return filters


_count_cache = {}
_count_cache_time = {}


def _cached_count(match_query):
    """Cache document counts for 5 minutes to avoid repeated full scans."""
    import time as _time
    key = str(sorted(match_query.items()))
    now = _time.time()
    if key in _count_cache and now - _count_cache_time.get(key, 0) < 300:
        return _count_cache[key]
    count = games_col.count_documents(match_query)
    _count_cache[key] = count
    _count_cache_time[key] = now
    return count


CARD_FIELDS = {
    "_id": 0,
    "steam_app_id": 1,
    "title": 1,
    "genres": 1,
    "tags": {"$slice": ["$tags", 3]},
    "price": 1,
    "is_free": 1,
    "review_summary": 1,
    "estimated_revenue": 1,
    "header_image_url": 1,
    "release_date": 1,
}


def _sorted_games_pipeline(match_query, page, limit, sort_by="revenue"):
    """
    Aggregation pipeline with configurable sort.
    Returns only card-relevant fields for faster queries and smaller responses.
    """
    sort_map = {
        "revenue":    {"estimated_revenue.low": -1},
        "reviews":    {"review_summary.total_reviews": -1},
        "score":      {"review_summary.positive_percent": -1},
        "newest":     {"release_date": -1},
        "price_low":  {"price.current": 1},
        "price_high": {"price.current": -1},
    }

    sort_spec = sort_map.get(sort_by, sort_map["revenue"])

    pipeline = [
        {"$match": match_query},
        {"$sort": sort_spec},
        {"$skip": page * limit},
        {"$limit": limit},
        {"$project": CARD_FIELDS}
    ]

    results = list(games_col.aggregate(pipeline, allowDiskUse=True))
    total   = _cached_count(match_query)
    return results, total


def _sort_virtual_games(games, sort_by):
    def revenue_key(game):
        return (game.get("estimated_revenue") or {}).get("low", 0)

    def reviews_key(game):
        return (game.get("review_summary") or {}).get("total_reviews", 0)

    def score_key(game):
        return (game.get("review_summary") or {}).get("positive_percent", 0)

    def release_key(game):
        return game.get("release_date") or ""

    def price_key(game):
        return (game.get("price") or {}).get("current", 0)

    sorters = {
        "revenue": (revenue_key, True),
        "reviews": (reviews_key, True),
        "score": (score_key, True),
        "newest": (release_key, True),
        "price_low": (price_key, False),
        "price_high": (price_key, True),
    }
    key_fn, reverse = sorters.get(sort_by, sorters["revenue"])
    return sorted(games, key=key_fn, reverse=reverse)


def _virtual_tag_results(tag, genre, page, limit, sort_by, filters):
    query = build_virtual_tag_query(tag, genre=genre or None) or {"delisted": {"$ne": True}}
    query.update(filters)
    docs = list(games_col.find(query, CARD_FIELDS))
    filtered = [doc for doc in docs if game_matches_virtual_tag(doc, tag)]
    ordered = _sort_virtual_games(filtered, sort_by)
    start = page * limit
    end = start + limit
    results = []
    for doc in ordered[start:end]:
        doc["tags"] = (doc.get("tags") or [])[:3]
        results.append(doc)
    return results, len(filtered)


@app.route("/api/export/genre/<genre>")
def export_genre_csv(genre):
    """Export all games in a genre as CSV."""
    import csv, io
    query = {"genres": genre, **_parse_filters(request.args)}
    games = list(games_col.find(query, {"_id": 0}).sort("estimated_revenue.low", -1).limit(500))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Title", "Genres", "Tags", "Price", "Review Score", "Total Reviews",
                     "Est Revenue Low", "Est Revenue High", "Est Owners Low", "Est Owners High",
                     "Current Players", "Release Date", "Free to Play"])
    for g in games:
        writer.writerow([
            g.get("title", ""),
            "; ".join(g.get("genres", [])),
            "; ".join(g.get("tags", [])[:8]),
            g.get("price", {}).get("current", ""),
            g.get("review_summary", {}).get("positive_percent", ""),
            g.get("review_summary", {}).get("total_reviews", ""),
            g.get("estimated_revenue", {}).get("low", ""),
            g.get("estimated_revenue", {}).get("high", ""),
            g.get("estimated_owners", {}).get("low", ""),
            g.get("estimated_owners", {}).get("high", ""),
            g.get("players", {}).get("current", ""),
            g.get("release_date", ""),
            g.get("is_free", False)
        ])

    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={genre}_games.csv"})


GENRE_EXCLUSIONS = {
    "Sports": ["Racing"],
    "Racing": ["Sports"],
}

@app.route("/api/games/genre/<genre>")
def get_games_by_genre(genre):
    page    = max(0, int(request.args.get("page", 0)))
    limit   = min(150, max(1, int(request.args.get("limit", 50))))
    sort_by = request.args.get("sort", "revenue")
    exclude = GENRE_EXCLUSIONS.get(genre, [])
    query   = {"genres": genre, "delisted": {"$ne": True}, **_parse_filters(request.args)}
    if exclude:
        query = {"$and": [query, {"genres": {"$nin": exclude}}]}
    results, total = _sorted_games_pipeline(query, page, limit, sort_by)
    return jsonify({"games": results, "total": total, "page": page, "limit": limit})


@app.route("/api/games/tag/<tag>")
def get_games_by_tag(tag):
    genre   = request.args.get("genre", "")
    page    = max(0, int(request.args.get("page", 0)))
    limit   = min(150, max(1, int(request.args.get("limit", 50))))
    sort_by = request.args.get("sort", "revenue")
    filters = _parse_filters(request.args)
    if is_virtual_tag(tag):
        results, total = _virtual_tag_results(tag, genre, page, limit, sort_by, filters)
        return jsonify({"games": results, "total": total, "page": page, "limit": limit})

    query = build_virtual_tag_query(tag, genre=genre or None)
    if not query:
        query = {"tags": build_tag_matcher(tag), "delisted": {"$ne": True}, **_parse_filters(request.args)}
        if genre:
            query["genres"] = genre
    results, total = _sorted_games_pipeline(query, page, limit, sort_by)
    return jsonify({"games": results, "total": total, "page": page, "limit": limit})


# ----------------------------
# Home Overview
# ----------------------------

@app.route("/api/overview")
def get_overview():
    """Genre player trend data from daily snapshots for the home screen chart."""
    from datetime import datetime, timedelta, timezone

    genres = ["Action", "Adventure", "Casual", "Indie", "RPG",
              "Simulation", "Strategy", "Sports", "Racing"]

    thirty_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    raw = list(db["genre_snapshots"].find(
        {"date": {"$gte": thirty_ago}},
        {"_id": 0, "date": 1, "genre": 1, "total_players": 1}
    ).sort("date", 1))

    # Pivot into {genre: [{date, players}]}
    trend = {g: [] for g in genres}
    for r in raw:
        if r["genre"] in trend:
            trend[r["genre"]].append({"date": r["date"], "players": r["total_players"]})

    return jsonify({"genres": genres, "trend": trend})


# ----------------------------
# Market Research Routes
# ----------------------------

@app.route("/api/market/genre/<genre>")
def get_market_overview(genre):
    """Compute TAM and outlier-adjusted benchmarks for a genre."""
    summary = summarize_market(games_col, genre=genre)
    if not summary:
        return jsonify({"error": "No games found for this genre"}), 404

    return jsonify({
        "genre": genre,
        "total_games": summary["total_games"],
        "paid_games": summary["paid_games"],
        "avg_review_score": summary["avg_review_score_pct"],
        "avg_price": summary["avg_price_usd"],
        "TAM": {**summary["TAM"], "description": summary["TAM"]["label"]},
        "SOM": {**summary["SOM"], "description": summary["SOM"]["label"]},
        "realistic_revenue_target": summary["realistic_revenue_target"],
        "performance_benchmarks": summary["performance_benchmarks"],
        "confidence": summary["confidence"],
        "source_confidence": summary["source_confidence"],
        "sample_notes": summary["sample_notes"],
        "revenue_concentration_top_10_pct": summary["revenue_concentration_top_10_pct"],
        "disclaimer": summary["disclaimer"],
    })


@app.route("/api/market/tag/<tag>")
def get_market_by_tag(tag):
    """Compute SAM/SOM and outlier-adjusted benchmarks for a tag."""
    genre = request.args.get("genre") or None
    summary = summarize_market(games_col, genre=genre, tag=tag)
    if not summary:
        return jsonify({"error": "No games found for this tag"}), 404

    return jsonify({
        "tag": tag,
        "genre": genre,
        "total_games": summary["total_games"],
        "paid_games": summary["paid_games"],
        "avg_review_score": summary["avg_review_score_pct"],
        "avg_price": summary["avg_price_usd"],
        "TAM": {**summary["TAM"], "description": summary["TAM"]["label"]},
        "SAM": {**summary["SAM"], "description": summary["SAM"]["label"]},
        "SOM": {**summary["SOM"], "description": summary["SOM"]["label"]},
        "realistic_revenue_target": summary["realistic_revenue_target"],
        "performance_benchmarks": summary["performance_benchmarks"],
        "confidence": summary["confidence"],
        "source_confidence": summary["source_confidence"],
        "sample_notes": summary["sample_notes"],
        "revenue_concentration_top_10_pct": summary["revenue_concentration_top_10_pct"],
        "disclaimer": summary["disclaimer"],
    })


@app.route("/api/market/competitors")
def get_competitors():
    """Get competitor analysis for a genre or tag."""
    genre = request.args.get("genre", "")
    tag = request.args.get("tag", "")

    if not genre and not tag:
        return jsonify({"error": "Provide a genre or tag parameter"}), 400

    query = {}
    if genre:
        query["genres"] = {"$regex": genre, "$options": "i"}
    if tag:
        query["tags"] = {"$regex": tag, "$options": "i"}

    results = list(games_col.find(query, {"_id": 0})
        .sort("estimated_owners.high", -1)
        .limit(20))

    return jsonify(results)


# ----------------------------
# No-Cost Insight Routes
# ----------------------------

@app.route("/api/insights/data-points")
def get_data_points():
    """Structured catalog of facts and derived metrics the product can expose."""
    return jsonify({
        "data_points": DATA_POINT_CATALOG,
        "disclaimer": "Revenue, owner, and market sizing figures are estimates based on SteamSpy and public Steam data."
    })


@app.route("/api/ai-tools")
def get_ai_tools():
    """Supported external AI tools for no-cost prompt handoff."""
    return jsonify({
        "default": DEFAULT_AI_TOOL,
        "tools": [
            {"id": tool_id, "label": meta["label"]}
            for tool_id, meta in AI_HANDOFF_TOOLS.items()
        ],
    })


@app.route("/api/brief-modes")
def get_brief_modes():
    return jsonify({
        "default": "general",
        "modes": [
            {"id": mode_id, "label": meta["label"]}
            for mode_id, meta in BRIEF_MODES.items()
        ],
    })


@app.route("/api/insights/accuracy")
def get_accuracy_model():
    """Explain source confidence and estimate methodology."""
    return jsonify({
        "source_confidence": SOURCE_CONFIDENCE,
        "estimate_methodology": {
            "market_size": "Summed SteamSpy owner/revenue ranges across matching games.",
            "realistic_indie_target": "Paid-game revenue percentiles from comparable games, with the top 1% trimmed when sample size allows.",
            "confidence_score": "Based on comparable sample size, paid sample size, and top-10 revenue concentration.",
            "outlier_policy": "Top hits remain in total market size, but are trimmed from per-game target benchmarks.",
        },
        "recommended_language": "Say 'estimated' for owners, revenue, TAM, SAM, and SOM. Steam does not publish official sales for all games.",
    })


@app.route("/api/insights/market")
def get_market_insight():
    """Tool-ready market summary for a genre and/or tag."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None

    if not genre and not tag:
        return jsonify({"error": "Provide genre or tag"}), 400

    summary = summarize_market(games_col, genre=genre, tag=tag)
    if not summary:
        return jsonify({"error": "No games found for this market"}), 404

    limit = min(25, max(1, request.args.get("limit", default=10, type=int)))
    return jsonify({
        "summary": summary,
        "top_competitors": top_competitors(games_col, genre=genre, tag=tag, limit=limit),
    })


@app.route("/api/insights/momentum")
def get_market_momentum():
    """Player-snapshot momentum for a genre or tag."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    days = min(365, max(2, request.args.get("days", default=30, type=int)))

    if not genre and not tag:
        return jsonify({"error": "Provide genre or tag"}), 400

    return jsonify(market_momentum(games_col, db, genre=genre, tag=tag, days=days))


@app.route("/api/insights/markets")
def get_ranked_markets():
    """Rank genres or tags by estimated market size."""
    market_type = request.args.get("type", "genres")
    genre = request.args.get("genre") or None
    limit = min(100, max(1, request.args.get("limit", default=25, type=int)))

    if market_type == "tags":
        markets = rank_tag_markets(games_col, genre=genre, limit=limit)
    else:
        markets = sorted(
            rank_genre_markets(games_col),
            key=lambda m: m.get("estimated_revenue_high", 0),
            reverse=True,
        )[:limit]

    return jsonify({
        "type": market_type,
        "genre": genre,
        "markets": markets,
        "disclaimer": "Revenue figures are SteamSpy estimates, not official Steam data."
    })


@app.route("/api/insights/opportunities")
def get_opportunities():
    """Rank markets with strong demand signals and comparatively addressable competition."""
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=12, type=int)))
    return jsonify({
        "genre": genre,
        "opportunities": market_opportunities(games_col, genre=genre, limit=limit),
        "disclaimer": "Opportunity score is directional and should be validated against direct competitors."
    })


@app.route("/api/insights/smaller-subgenres")
def get_smaller_subgenres():
    """Find smaller, more niche subgenres while filtering broad umbrella tags."""
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=15, type=int)))
    min_games = min(500, max(5, request.args.get("min_games", default=25, type=int)))
    max_games = min(5000, max(min_games, request.args.get("max_games", default=750, type=int)))
    raw_tags = request.args.get("raw_tags", "").lower() in {"1", "true", "yes"}
    return jsonify(smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=limit,
        min_games=min_games,
        max_games=max_games,
        curated_tags=None if raw_tags else _curated_subgenre_tags(genre),
    ))


@app.route("/api/taxonomy")
def get_taxonomy():
    """Return the curated genre -> subgenre -> child tag taxonomy."""
    genre = request.args.get("genre") or None
    if genre:
        return jsonify({
            "genre": genre,
            "groups": groups_for_genre(genre),
            "note": "Not every subgenre needs child tags; only broad categories are expanded.",
        })
    return jsonify({
        "groups_by_genre": GENRE_SUBGENRE_GROUPS,
        "children_by_subgenre": SUBGENRE_CHILDREN,
        "note": "Not every subgenre needs child tags; only broad categories are expanded.",
    })


@app.route("/api/insights/subgenre-children")
def get_subgenre_children():
    """Compare child tags for a broad subgenre such as Shooter or RPG."""
    parent = request.args.get("subgenre") or request.args.get("parent")
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=20, type=int)))

    if not parent:
        return jsonify({"error": "Provide subgenre or parent"}), 400

    children = children_for_subgenre(parent)
    if not children:
        return jsonify({
            "parent_subgenre": parent,
            "children_found": [],
            "message": "No child taxonomy is defined for this subgenre yet.",
        })

    return jsonify(child_subgenre_report(
        games_col,
        parent,
        children,
        genre=genre,
        limit=limit,
    ))


@app.route("/api/insights/prominence")
def get_prominence():
    """Show markets doing well and markets that are currently less prominent."""
    genre = request.args.get("genre") or None
    limit = min(25, max(1, request.args.get("limit", default=10, type=int)))
    return jsonify(prominence_report(games_col, genre=genre, limit=limit))


@app.route("/api/insights/follow-ups")
def get_follow_ups():
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    return jsonify({
        "prompts": build_follow_up_prompts(question=question, genre=genre, tag=tag, summary=summary),
    })


@app.route("/api/insights/concept", methods=["POST"])
def concept_insight():
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "Provide a game description"}), 400
    return jsonify(analyze_concept(games_col, description))


@app.route("/api/insights/compare")
def compare_markets():
    left_type = request.args.get("left_type", "genre")
    left_value = request.args.get("left") or ""
    left_genre = left_value if left_type == "genre" else request.args.get("left_genre") or None
    left_tag = left_value if left_type == "tag" else None

    right_type = request.args.get("right_type", "genre")
    right_value = request.args.get("right") or ""
    right_genre = right_value if right_type == "genre" else request.args.get("right_genre") or None
    right_tag = right_value if right_type == "tag" else None

    if not left_value or not right_value:
        return jsonify({"error": "Provide both markets to compare"}), 400

    comparison = build_compare_data(
        games_col,
        left_genre=left_genre,
        left_tag=left_tag,
        right_genre=right_genre,
        right_tag=right_tag,
    )
    if not comparison:
        return jsonify({"error": "Could not compare one or both markets"}), 404
    return jsonify(comparison)


def build_chatgpt_brief_payload(question="", genre=None, tag=None, brief_mode="general", compare=None, concept_description=""):
    """Build the market data bundle used by both the JSON API and loader page."""
    inferred = None
    mode = get_brief_mode(brief_mode)

    if question and not (genre or tag):
        inferred = infer_market_context(
            games_col,
            question,
            known_tags=_curated_subgenre_tags() | all_taxonomy_tags(),
        )
        genre = inferred.get("genre")
        tag = inferred.get("tag")

    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    momentum = market_momentum(games_col, db, genre=genre, tag=tag) if (genre or tag) else None
    child_report = None
    if tag and children_for_subgenre(tag):
        child_report = child_subgenre_report(games_col, tag, children_for_subgenre(tag), genre=genre, limit=12)
    comparison = None
    if compare:
        comparison = build_compare_data(
            games_col,
            left_genre=genre if not tag else genre,
            left_tag=tag,
            right_genre=compare.get("genre"),
            right_tag=compare.get("tag"),
        )
    concept_analysis = analyze_concept(games_col, concept_description) if concept_description else None
    taxonomy_context = {
        "genre_groups": groups_for_genre(genre) if genre else None,
        "child_report": child_report,
        "children_for_detected_tag": children_for_subgenre(tag) if tag else [],
    }
    prominence = prominence_report(games_col, genre=genre, limit=8)
    smaller = smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=10,
        curated_tags=_curated_subgenre_tags(genre),
    )
    opportunities = market_opportunities(games_col, genre=genre, limit=8)
    brief_diagnostics = _build_brief_diagnostics(
        summary=summary,
        momentum=momentum,
        smaller=smaller,
        opportunities=opportunities,
        taxonomy=taxonomy_context,
    )

    return {
        "brief_mode": mode,
        "instruction": (
            "Paste this JSON into ChatGPT and ask it to reason from the provided Steam market data only. "
            "Treat all revenue and owner figures as estimates, not official Steam data."
        ),
        "user_question": question,
        "inferred_context": inferred,
        "market_summary": summary,
        "market_momentum": momentum,
        "taxonomy_context": taxonomy_context,
        "top_competitors": top_competitors(games_col, genre=genre, tag=tag, limit=8) if (genre or tag) else [],
        "source_confidence": SOURCE_CONFIDENCE,
        "doing_well_and_less_prominent": prominence,
        "smaller_subgenres": smaller,
        "opportunities": opportunities,
        "brief_diagnostics": brief_diagnostics,
        "comparison": comparison,
        "concept_analysis": concept_analysis,
        "follow_up_prompts": build_follow_up_prompts(question=question, genre=genre, tag=tag, summary=summary),
        "data_available": DATA_POINT_CATALOG,
    }


def build_chatgpt_prompt(payload, user_question="", brief_mode="general"):
    """Convert a brief payload into the pasteable ChatGPT prompt."""
    mode = get_brief_mode(brief_mode)
    lines = [
        "You are helping an indie game developer analyze Steam market data.",
        "Use only the JSON below as your data source.",
        "Treat all revenue and owner figures as SteamSpy-based estimates, not official Steam data.",
        "Optimize for a solo developer or small indie team, not a AAA studio or publisher-backed team.",
        mode["instruction"],
        "Do not rely mainly on top competitor anecdotes. Use aggregate market metrics as the primary evidence and use competitor examples only to support a point.",
        "If confidence is weak or sample coverage is thin, say so clearly and reduce certainty.",
        "If the broad market looks crowded, identify narrower subgenres, child tags, or adjacent niches from the JSON that may be more promising.",
        "Avoid generic advice unless it is directly justified by the provided data.",
        "If a flashy niche metric conflicts with a reliability warning, trust the reliability warning.",
        "If a niche has use_for_recommendation set to caution, present it as a hypothesis to validate rather than a confident recommendation.",
    ]
    if user_question:
        lines.append(f"User question: {user_question}")
    lines.extend([
        "",
        "Your answer must follow this exact structure:",
        "1. Short answer",
        "2. Verdict",
        "3. Demand",
        "4. Competition",
        "5. Pricing",
        "6. Risks",
        "7. Best niche opportunities",
        "8. Data confidence and weak spots",
        "9. Recommendation for a small team",
        "",
        "Requirements for the analysis:",
        "- Cite the most decision-useful metrics from the JSON, especially market_summary, performance_benchmarks, revenue_concentration_top_10_pct, confidence, brief_diagnostics, smaller_subgenres, opportunities, taxonomy_context, and market_momentum when reliable.",
        "- Distinguish between broad-market conclusions and niche/subgenre conclusions.",
        "- Do not treat low-confidence momentum data as strong evidence.",
        "- If a field is missing, thin, or low-confidence, say that directly instead of filling the gap with assumptions.",
        "- Every recommendation should be tied to a specific metric, market pattern, or named niche from the JSON.",
        "- Prefer outlier-adjusted benchmarks over raw TAM/SAM or raw niche revenue-per-game figures when recommending what a small team should pursue.",
        "- If taxonomy support is thin, say whether a niche is a confirmed child tag or only an adjacent opportunity.",
        "- In niche analysis, explicitly use confirmed_child_tag, market_relationship, data_reliability, and use_for_recommendation.",
        "- If revenue_per_game_estimate is suppressed or null for a niche, do not reconstruct it from other fields or treat raw_revenue_per_game_estimate as a planning target.",
        "",
        "In the Verdict section, include these labels on separate lines:",
        "- Market Size:",
        "- Competition:",
        "- Saturation:",
        "- Barrier to Entry:",
        "- Commercial Opportunity:",
        "",
        "In Best niche opportunities, name up to 3 specific niches and explain why each looks better or worse than the broad market.",
        "In Data confidence and weak spots, explicitly list any red flags from brief_diagnostics.",
    ])
    lines.extend(["", json.dumps(payload, indent=2, sort_keys=True, default=str)])
    return "\n".join(lines)


@app.route("/api/insights/chatgpt-brief")
def get_chatgpt_brief():
    """Bundle a compact data brief users can paste into ChatGPT."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    brief_mode = request.args.get("mode") or "general"
    compare_type = request.args.get("compare_type") or None
    compare_value = request.args.get("compare_value") or None
    compare_genre = request.args.get("compare_genre") or None
    concept_description = request.args.get("concept") or ""
    compare = None
    if compare_type and compare_value:
        compare = {
            "genre": compare_value if compare_type == "genre" else compare_genre,
            "tag": compare_value if compare_type == "tag" else None,
        }
    return jsonify(build_chatgpt_brief_payload(
        question=question,
        genre=genre,
        tag=tag,
        brief_mode=brief_mode,
        compare=compare,
        concept_description=concept_description,
    ))


@app.route("/api/insights/chatgpt-prompt")
def get_chatgpt_prompt():
    """Return the prepared AI handoff prompt."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    brief_mode = request.args.get("mode") or "general"
    compare_type = request.args.get("compare_type") or None
    compare_value = request.args.get("compare_value") or None
    compare_genre = request.args.get("compare_genre") or None
    concept_description = request.args.get("concept") or ""
    compare = None
    if compare_type and compare_value:
        compare = {
            "genre": compare_value if compare_type == "genre" else compare_genre,
            "tag": compare_value if compare_type == "tag" else None,
        }
    payload = build_chatgpt_brief_payload(
        question=question,
        genre=genre,
        tag=tag,
        brief_mode=brief_mode,
        compare=compare,
        concept_description=concept_description,
    )
    return jsonify({
        "prompt": build_chatgpt_prompt(payload, user_question=question, brief_mode=brief_mode),
    })


@app.route("/chatgpt-brief-loader")
def chatgpt_brief_loader():
    """Open a dedicated handoff page that copies the brief, then sends the tab to an AI tool."""
    ai_tool = get_ai_handoff_tool(request.args.get("ai_tool"))
    return render_template(
        "brief_loader.html",
        ai_tool=ai_tool,
        loader_query=request.args.to_dict(flat=True),
    )


# ----------------------------
# Subgenres
# ----------------------------

STEAM_SUBGENRES = {
    "Action": [
        "Shooter", "First-Person Shooter", "Third-Person Shooter", "Top-Down Shooter",
        "Bullet Hell", "Platformer", "Precision Platformer", "Side Scroller", "Run and Gun",
        "Fighting", "Hack and Slash", "Beat 'em Up", "Brawler", "Stealth",
        "Soulslike", "Battle Royale", "Tower Defense", "Action Roguelike", "Rhythm",
        "Open World", "Survival", "Looter Shooter", "Military", "Co-op",
        "Parkour", "Space", "Sci-fi", "Arena Shooter", "2D", "Metroidvania"
    ],
    "Adventure": [
        "Point & Click", "Visual Novel", "Walking Simulator", "Puzzle Platformer",
        "Interactive Fiction", "Escape Room", "Mystery", "Horror",
        "Survival Horror", "Psychological Horror", "Story Rich", "Exploration",
        "Narrative", "Dark", "Open World", "Thriller", "Comedy",
        "Supernatural", "Detective", "Anime", "Sci-fi", "Fantasy"
    ],
    "Casual": [
        "Puzzle", "Hidden Object", "Idle", "Clicker", "Match 3",
        "Relaxing", "Mini Games", "Word Game", "Trivia", "Cozy",
        "Music", "Anime", "Cute", "Board Game", "Card Game",
        "Family Friendly", "2D", "Cooking", "Rhythm", "Typing"
    ],
    "Indie": [
        "Roguelike", "Roguelite", "Metroidvania", "Pixel Art", "Narrative",
        "Experimental", "Atmospheric", "Cozy", "Retro", "Cyberpunk",
        "Steampunk", "Dark Fantasy", "Horror", "Survival", "2D",
        "Platformer", "Open World", "Cute", "Anime", "Story Rich",
        "Puzzle", "Exploration", "Dark", "Fantasy", "Sci-fi",
        "Hand-drawn", "Top-Down", "Mystery", "Psychological", "Comedy"
    ],
    "RPG": [
        "JRPG", "Action RPG", "Turn-Based RPG", "Dungeon Crawler", "Western RPG",
        "Tactical RPG", "Isometric RPG", "Dark Fantasy", "Deckbuilding RPG",
        "Creature Collector", "Open World", "Fantasy", "Sci-fi", "Anime",
        "Story Rich", "Co-op", "Character Customization", "Sandbox",
        "MMORPG", "Roguelike", "Strategy RPG", "Loot", "Party-Based RPG"
    ],
    "Simulation": [
        "City Builder", "Farming Sim", "Life Sim", "Management", "Tycoon",
        "Space Sim", "Flight Sim", "Train Sim", "Colony Sim",
        "Base Building", "Sandbox", "God Game", "Driving", "Cooking",
        "Fishing", "Automation", "Factory", "Hospital", "Business",
        "Naval", "Trucking", "Hunting", "Survival", "Physics"
    ],
    "Strategy": [
        "Turn-Based Strategy", "Real-Time Strategy", "4X", "Grand Strategy",
        "Tower Defense", "Card Game", "Deckbuilding", "Wargame",
        "Auto Battler", "Puzzle Strategy", "City Builder", "Resource Management",
        "Economic", "Space", "Military", "Political", "Base Building",
        "Roguelike", "Naval", "Survival", "Management", "Sandbox"
    ],
    "Sports": [
        "Soccer", "Basketball", "Baseball", "Golf", "Tennis", "Wrestling",
        "Fishing", "Skating", "Cycling", "Track and Field", "Boxing", "Snowboarding",
        "Football", "Hockey", "Rugby", "Cricket", "Volleyball",
        "Skateboarding", "Surfing", "BMX", "Extreme Sports", "Hunting", "Archery"
    ],
    "Racing": [
        "Open World", "Motorsport", "Motocross", "Cycling"
    ]
}

def _curated_subgenre_tags(genre=None):
    if genre:
        return set(STEAM_SUBGENRES.get(genre, [])) | set(groups_for_genre(genre).keys())
    tags = set()
    for values in STEAM_SUBGENRES.values():
        tags.update(values)
    tags.update(all_taxonomy_tags())
    return tags


_subgenre_cache = {}
_subgenre_cache_time = {}

@app.route("/api/subgenres/<genre>")
def get_subgenres(genre):
    """Return subgenres for a genre with counts. Cached for 1 hour."""
    import time as _time
    now = _time.time()
    if genre in _subgenre_cache and now - _subgenre_cache_time.get(genre, 0) < 3600:
        return jsonify(_subgenre_cache[genre])

    tags = STEAM_SUBGENRES.get(genre, [])
    available = []
    for tag in tags:
        query = build_virtual_tag_query(tag, genre=genre)
        if query is None:
            query = {
                "genres": genre,
                "tags": build_tag_matcher(tag),
                "delisted": {"$ne": True}
            }
            count = games_col.count_documents(query)
        else:
            docs = list(games_col.find(query, {"_id": 0, "title": 1, "tags": 1, "genres": 1}))
            count = sum(1 for doc in docs if game_matches_virtual_tag(doc, tag))
        if count >= 10:
            available.append({
                "tag": tag,
                "count": count,
                "children": children_for_subgenre(tag),
                "has_children": bool(children_for_subgenre(tag)),
            })

    _subgenre_cache[genre] = available
    _subgenre_cache_time[genre] = now
    return jsonify(available)


# ----------------------------
# AI Chat
# ----------------------------

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """No-cost data assistant. Does not call a paid LLM API."""

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    try:
        response = answer_without_llm(games_col, data["message"])
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------
# Health Check
# ----------------------------

@app.route("/api/health")
def health():
    """Quick check that the server is running and database is connected."""
    game_count = games_col.count_documents({})
    return jsonify({
        "status": "ok",
        "games_in_database": game_count
    })


if __name__ == "__main__":
    app.run(debug=True)
