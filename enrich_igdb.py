"""
Enrich games with metadata from IGDB (via Twitch API).
Adds: themes, game modes, critic ratings, similar games.
Rate limit: 4 requests/sec.

Usage:
    python enrich_igdb.py              # top 2000 by revenue
    python enrich_igdb.py --all        # all games
    python enrich_igdb.py --limit 500  # custom limit
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import requests
import time
import sys
import os

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
    print("ERROR: TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set in .env")
    sys.exit(1)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]

IGDB_URL = "https://api.igdb.com/v4"


def get_twitch_token():
    r = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    if r.status_code == 200:
        return r.json().get("access_token")
    print(f"Failed to get Twitch token: {r.status_code} {r.text}")
    sys.exit(1)


def igdb_query(endpoint, body, token):
    try:
        r = requests.post(f"{IGDB_URL}/{endpoint}", headers={
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }, data=body, timeout=15)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            print("  Rate limited — pausing 5s...")
            time.sleep(5)
            return igdb_query(endpoint, body, token)
    except Exception as e:
        print(f"  IGDB error: {e}")
    return []


def enrich(limit=2000, all_games=False):
    token = get_twitch_token()
    print(f"Got Twitch token.\n")

    # Pre-fetch theme and game mode names
    themes_raw = igdb_query("themes", "fields name; limit 500;", token)
    theme_map = {t["id"]: t["name"] for t in themes_raw}
    time.sleep(0.3)

    modes_raw = igdb_query("game_modes", "fields name; limit 50;", token)
    mode_map = {m["id"]: m["name"] for m in modes_raw}
    time.sleep(0.3)

    if all_games:
        games = list(games_col.find(
            {"delisted": {"$ne": True}, "igdb": {"$exists": False}},
            {"steam_app_id": 1, "title": 1, "_id": 0}
        ))
    else:
        pipeline = [
            {"$match": {"delisted": {"$ne": True}, "igdb": {"$exists": False}}},
            {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
            {"$sort": {"_sort": -1}},
            {"$limit": limit},
            {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}}
        ]
        games = list(games_col.aggregate(pipeline))

    print(f"Enriching {len(games)} games from IGDB...\n")

    enriched = 0
    not_found = 0

    for i, g in enumerate(games):
        aid = g["steam_app_id"]
        title = g.get("title", f"App {aid}")

        # Search IGDB by Steam app ID via external games
        results = igdb_query("external_games",
            f'fields game; where uid = "{aid}" & category = 1; limit 1;',
            token
        )

        if not results:
            games_col.update_one(
                {"steam_app_id": aid},
                {"$set": {"igdb": {"found": False}}}
            )
            not_found += 1
            time.sleep(0.3)
            continue

        igdb_id = results[0].get("game")
        if not igdb_id:
            not_found += 1
            time.sleep(0.3)
            continue

        # Fetch full game details from IGDB
        game_data = igdb_query("games",
            f"fields name, themes, game_modes, aggregated_rating, "
            f"aggregated_rating_count, similar_games, total_rating, "
            f"total_rating_count; where id = {igdb_id};",
            token
        )

        if not game_data:
            not_found += 1
            time.sleep(0.3)
            continue

        gd = game_data[0]
        igdb_entry = {
            "found": True,
            "igdb_id": igdb_id,
            "themes": [theme_map.get(t, str(t)) for t in gd.get("themes", [])],
            "game_modes": [mode_map.get(m, str(m)) for m in gd.get("game_modes", [])],
            "critic_rating": round(gd["aggregated_rating"], 1) if gd.get("aggregated_rating") else None,
            "critic_rating_count": gd.get("aggregated_rating_count"),
            "total_rating": round(gd["total_rating"], 1) if gd.get("total_rating") else None,
            "total_rating_count": gd.get("total_rating_count"),
            "similar_game_ids": gd.get("similar_games", [])[:10],
        }

        games_col.update_one(
            {"steam_app_id": aid},
            {"$set": {"igdb": igdb_entry}}
        )
        enriched += 1

        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(games)} ({enriched} enriched, {not_found} not found)")

        time.sleep(0.3)

    print(f"\nDone. {enriched} enriched, {not_found} not on IGDB.")


if __name__ == "__main__":
    do_all = "--all" in sys.argv
    limit = 2000
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    enrich(limit=limit, all_games=do_all)
    client.close()
