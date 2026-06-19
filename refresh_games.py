"""
Re-fetch SteamSpy + Steam Store data for existing games.
Updates: owner estimates, reviews, playtime, price, tags, player counts.
Run weekly to keep data fresh.

Usage:
    python refresh_games.py              # top 2000 by revenue
    python refresh_games.py --all        # all games
    python refresh_games.py --limit 500  # custom limit
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from steam_api import get_steam_game_details, get_steamspy_details, parse_game
import sys
import time
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]

def refresh(limit=2000, all_games=False):
    if all_games:
        games = list(games_col.find(
            {"delisted": {"$ne": True}},
            {"steam_app_id": 1, "title": 1, "_id": 0}
        ))
    else:
        pipeline = [
            {"$match": {"delisted": {"$ne": True}}},
            {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
            {"$sort": {"_sort": -1}},
            {"$limit": limit},
            {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}}
        ]
        games = list(games_col.aggregate(pipeline))

    print(f"Refreshing data for {len(games)} games...\n")

    updated = 0
    skipped = 0
    errors = 0

    for i, g in enumerate(games):
        aid = g["steam_app_id"]
        title = g.get("title", f"App {aid}")

        try:
            steam_data = get_steam_game_details(aid)
            spy_data = get_steamspy_details(aid)

            if not steam_data:
                skipped += 1
                if (i + 1) % 100 == 0:
                    print(f"  ...{i + 1}/{len(games)} ({updated} updated)")
                time.sleep(1.5)
                continue

            parsed = parse_game(steam_data, spy_data or {})
            if not parsed:
                skipped += 1
                time.sleep(1.5)
                continue

            parsed["last_updated"] = datetime.now(timezone.utc)
            games_col.update_one({"steam_app_id": aid}, {"$set": parsed})
            updated += 1

        except Exception as e:
            errors += 1
            print(f"  Error on {title}: {e}")

        if (i + 1) % 100 == 0:
            print(f"  ...{i + 1}/{len(games)} ({updated} updated, {skipped} skipped, {errors} errors)")

        time.sleep(2.5)

    print(f"\nDone. {updated} updated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    do_all = "--all" in sys.argv
    limit = 2000
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    refresh(limit=limit, all_games=do_all)
    client.close()
