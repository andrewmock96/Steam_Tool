import time as _time

from flask import Blueprint, Response, jsonify, request

from db import games_col
from helpers import GENRE_EXCLUSIONS, STEAM_SUBGENRES
from virtual_tags import build_tag_matcher, build_virtual_tag_query, game_matches_virtual_tag, is_virtual_tag

games_bp = Blueprint("games", __name__)


@games_bp.route("/api/games/search")
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


@games_bp.route("/api/games/<int:app_id>")
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


@games_bp.route("/api/export/genre/<genre>")
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


@games_bp.route("/api/games/genre/<genre>")
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


@games_bp.route("/api/games/tag/<tag>")
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


@games_bp.route("/api/overview")
def get_overview():
    """Genre player trend data from daily snapshots for the home screen chart."""
    from datetime import datetime, timedelta, timezone
    from db import db as mongo_db

    genres = ["Action", "Adventure", "Casual", "Indie", "RPG",
              "Simulation", "Strategy", "Sports", "Racing"]

    thirty_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    raw = list(mongo_db["genre_snapshots"].find(
        {"date": {"$gte": thirty_ago}},
        {"_id": 0, "date": 1, "genre": 1, "total_players": 1}
    ).sort("date", 1))

    # Pivot into {genre: [{date, players}]}
    trend = {g: [] for g in genres}
    for r in raw:
        if r["genre"] in trend:
            trend[r["genre"]].append({"date": r["date"], "players": r["total_players"]})

    return jsonify({"genres": genres, "trend": trend})


_subgenre_cache = {}
_subgenre_cache_time = {}


@games_bp.route("/api/subgenres/<genre>")
def get_subgenres(genre):
    """Return subgenres for a genre with counts. Cached for 1 hour."""
    from market_taxonomy import children_for_subgenre

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
