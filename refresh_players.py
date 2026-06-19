"""
Refresh current player counts using the Steam Web API.
Uses GetNumberOfCurrentPlayers for real-time CCU per game.
Run daily for top games, weekly for all.

Usage:
    python refresh_players.py              # top 1000 by revenue
    python refresh_players.py --all        # all games
    python refresh_players.py --limit 500  # custom limit
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
import time
import sys
import os

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
if not STEAM_API_KEY:
    print("ERROR: STEAM_API_KEY not set in .env")
    sys.exit(1)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
player_snapshots_col = db["player_snapshots"]

PLAYER_COUNT_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"


def get_live_player_count(app_id):
    try:
        r = requests.get(PLAYER_COUNT_URL, params={
            "key": STEAM_API_KEY,
            "appid": app_id
        }, timeout=10)
        if r.status_code == 200:
            data = r.json().get("response", {})
            if data.get("result") == 1:
                return data.get("player_count", 0)
        return None
    except Exception:
        return None


def refresh(limit=1000, all_games=False):
    if all_games:
        cursor = games_col.find(
            {"delisted": {"$ne": True}},
            {"steam_app_id": 1, "title": 1, "_id": 0}
        )
        games = list(cursor)
    else:
        pipeline = [
            {"$match": {"delisted": {"$ne": True}}},
            {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
            {"$sort": {"_sort": -1}},
            {"$limit": limit},
            {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}}
        ]
        games = list(games_col.aggregate(pipeline))

    print(f"Refreshing player counts for {len(games)} games...\n")

    updated = 0
    failed = 0
    ops = []
    now = datetime.now(timezone.utc)

    for i, g in enumerate(games):
        aid = g["steam_app_id"]
        count = get_live_player_count(aid)

        if count is not None:
            ops.append(UpdateOne(
                {"steam_app_id": aid},
                {"$set": {
                    "players.current": count,
                    "players.last_updated": now
                }}
            ))

            player_snapshots_col.insert_one({
                "steam_app_id": aid,
                "timestamp": now,
                "current_players": count
            })

            updated += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0:
            if ops:
                games_col.bulk_write(ops)
                ops = []
            print(f"  ...{i + 1}/{len(games)} ({updated} updated, {failed} failed)")

        time.sleep(0.5)

    if ops:
        games_col.bulk_write(ops)

    print(f"\nDone. {updated} updated, {failed} failed.")


if __name__ == "__main__":
    do_all = "--all" in sys.argv
    limit = 1000
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    refresh(limit=limit, all_games=do_all)
    client.close()
