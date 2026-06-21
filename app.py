from flask import Flask, jsonify, request, render_template, Response
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

try:
    from ai_assistant import chat as ai_chat
    AI_AVAILABLE = True
except Exception as _ai_err:
    AI_AVAILABLE = False
    print(f"AI assistant unavailable: {_ai_err}")

app = Flask(__name__)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
genre_aggregates_col = db["genre_aggregates"]


# ----------------------------
# Frontend
# ----------------------------

@app.route("/")
def index():
    return render_template("index.html")


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
        {"_id": 0}
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


def _sorted_games_pipeline(match_query, page, limit, sort_by="revenue"):
    """
    Aggregation pipeline with configurable sort.
    Uses estimated_revenue.low directly for revenue sort (indexed)
    instead of a computed field, for better performance on deep pages.
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
        {"$project": {"_id": 0}}
    ]

    results = list(games_col.aggregate(pipeline, allowDiskUse=True))
    total   = _cached_count(match_query)
    return results, total


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


@app.route("/api/games/genre/<genre>")
def get_games_by_genre(genre):
    page    = max(0, int(request.args.get("page", 0)))
    limit   = min(150, max(1, int(request.args.get("limit", 50))))
    sort_by = request.args.get("sort", "revenue")
    query   = {"genres": genre, "delisted": {"$ne": True}, **_parse_filters(request.args)}
    results, total = _sorted_games_pipeline(query, page, limit, sort_by)
    return jsonify({"games": results, "total": total, "page": page, "limit": limit})


@app.route("/api/games/tag/<tag>")
def get_games_by_tag(tag):
    genre   = request.args.get("genre", "")
    page    = max(0, int(request.args.get("page", 0)))
    limit   = min(150, max(1, int(request.args.get("limit", 50))))
    sort_by = request.args.get("sort", "revenue")
    query   = {"tags": {"$regex": f"^{tag}$", "$options": "i"}, "delisted": {"$ne": True}, **_parse_filters(request.args)}
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
    """Compute TAM for a genre from games in the database."""
    games = list(games_col.find(
        {"genres": genre, "delisted": {"$ne": True}},
        {"_id": 0, "estimated_revenue": 1, "price": 1, "review_summary": 1, "is_free": 1}
    ))

    if not games:
        return jsonify({"error": "No games found for this genre"}), 404

    tam_low = sum(g.get("estimated_revenue", {}).get("low", 0) for g in games)
    tam_high = sum(g.get("estimated_revenue", {}).get("high", 0) for g in games)

    paid_games = [g for g in games if not g.get("is_free") and g.get("price", {}).get("current", 0) > 0]
    scores = [g["review_summary"]["positive_percent"] for g in games if g.get("review_summary", {}).get("positive_percent")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    prices = [g["price"]["current"] for g in paid_games if g.get("price", {}).get("current")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0

    return jsonify({
        "genre": genre,
        "total_games": len(games),
        "paid_games": len(paid_games),
        "avg_review_score": avg_score,
        "avg_price": avg_price,
        "TAM": {
            "description": "Total estimated lifetime revenue across all games in this genre on Steam",
            "low": tam_low,
            "high": tam_high
        }
    })


@app.route("/api/market/tag/<tag>")
def get_market_by_tag(tag):
    """Compute SAM/SOM for a subgenre tag, optionally filtered by parent genre."""
    genre = request.args.get("genre", "")
    query = {"tags": {"$regex": f"^{tag}$", "$options": "i"}, "delisted": {"$ne": True}}
    if genre:
        query["genres"] = genre
    games = list(games_col.find(
        query,
        {"_id": 0, "estimated_revenue": 1, "price": 1, "review_summary": 1, "is_free": 1}
    ))

    if not games:
        return jsonify({"error": "No games found for this tag"}), 404

    paid_games = [g for g in games if not g.get("is_free") and g.get("price", {}).get("current", 0) > 0]

    # SAM = total revenue of all games in this subgenre
    sam_low = sum(g.get("estimated_revenue", {}).get("low", 0) for g in games)
    sam_high = sum(g.get("estimated_revenue", {}).get("high", 0) for g in games)

    # SOM = 1–10% of SAM (realistic capture for a new indie game)
    som_low = round(sam_low * 0.01)
    som_high = round(sam_high * 0.10)

    scores = [g["review_summary"]["positive_percent"] for g in games if g.get("review_summary", {}).get("positive_percent")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    prices = [g["price"]["current"] for g in paid_games if g.get("price", {}).get("current")]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0

    return jsonify({
        "tag": tag,
        "total_games": len(games),
        "paid_games": len(paid_games),
        "avg_review_score": avg_score,
        "avg_price": avg_price,
        "SAM": {
            "description": "Total estimated revenue of all games in this subgenre",
            "low": sam_low,
            "high": sam_high
        },
        "SOM": {
            "description": "Your realistic capture: 1–10% of the subgenre market",
            "low": som_low,
            "high": som_high
        }
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
        "Arcade Racing", "Simulation Racing", "Kart Racing",
        "Off-Road", "Motocross", "Drag Racing",
        "Street Racing", "Rally", "Open World", "Bikes", "Formula Racing"
    ]
}

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
        count = games_col.count_documents({
            "genres": genre,
            "tags": {"$regex": f"^{tag}$", "$options": "i"},
            "delisted": {"$ne": True}
        })
        if count >= 10:
            available.append({"tag": tag, "count": count})

    _subgenre_cache[genre] = available
    _subgenre_cache_time[genre] = now
    return jsonify(available)


# ----------------------------
# AI Chat
# ----------------------------

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """Chat with the AI market research assistant."""
    if not AI_AVAILABLE:
        return jsonify({"error": "AI assistant not configured. Add ANTHROPIC_API_KEY to .env."}), 503

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    try:
        response = ai_chat(data["message"])
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
