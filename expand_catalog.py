"""
Expand game coverage by fetching ALL games from Steam's GetAppList,
then syncing details for ones we don't have yet.

This is a long-running script — ~150K apps on Steam, rate limited.
Estimated time: 3-5 days for full catalog.
Safe to interrupt and resume (skips games already in DB).

Usage:
    python expand_catalog.py                # start/resume full expansion
    python expand_catalog.py --limit 1000   # only fetch N new games then stop
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from steam_api import get_steam_game_details, get_steamspy_details, parse_game
import requests
import time
import sys
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
expansion_log = db["expansion_log"]


def get_all_steam_apps():
    """Fetch the full list of Steam app IDs via IStoreService (paginated)."""
    api_key = os.getenv("STEAM_API_KEY")
    if not api_key:
        print("ERROR: STEAM_API_KEY not set in .env")
        return []

    print("Fetching full Steam app list...")
    apps = []
    last_appid = 0

    while True:
        try:
            r = requests.get("https://api.steampowered.com/IStoreService/GetAppList/v1/", params={
                "key": api_key, "max_results": 50000, "last_appid": last_appid
            }, timeout=30)
            if r.status_code != 200:
                break
            data = r.json().get("response", {})
            apps.extend(data.get("apps", []))
            if not data.get("have_more_results"):
                break
            last_appid = data.get("last_appid", 0)
            time.sleep(1)
        except Exception:
            break

    print(f"Found {len(apps):,} apps on Steam.")
    return apps


def get_existing_ids():
    """Get all steam_app_ids already in our database."""
    ids = set()
    for doc in games_col.find({}, {"steam_app_id": 1, "_id": 0}):
        ids.add(doc["steam_app_id"])
    return ids


def expand(max_new=None):
    all_apps = get_all_steam_apps()
    existing = get_existing_ids()

    # Filter to apps we don't have yet
    new_apps = [a for a in all_apps if a["appid"] not in existing]
    print(f"Already have {len(existing):,} games. {len(new_apps):,} new apps to check.\n")

    if max_new:
        new_apps = new_apps[:max_new]
        print(f"Limiting to {max_new} new apps this run.\n")

    added = 0
    skipped = 0
    not_game = 0

    for i, app in enumerate(new_apps):
        app_id = app["appid"]
        app_name = app.get("name", f"App {app_id}")

        # Skip if already processed (but not saved — was non-game)
        if expansion_log.count_documents({"app_id": app_id}, limit=1):
            skipped += 1
            continue

        try:
            steam_data = get_steam_game_details(app_id)

            if not steam_data:
                expansion_log.insert_one({"app_id": app_id, "status": "no_data", "checked_at": datetime.now(timezone.utc)})
                skipped += 1
                time.sleep(1.5)
                continue

            # Only save actual games (skip DLC, soundtracks, tools, etc.)
            app_type = steam_data.get("type", "")
            if app_type != "game":
                expansion_log.insert_one({"app_id": app_id, "type": app_type, "status": "not_game", "checked_at": datetime.now(timezone.utc)})
                not_game += 1
                time.sleep(1.5)
                continue

            spy_data = get_steamspy_details(app_id)
            game = parse_game(steam_data, spy_data or {})

            if not game:
                expansion_log.insert_one({"app_id": app_id, "status": "parse_failed", "checked_at": datetime.now(timezone.utc)})
                skipped += 1
                time.sleep(1.5)
                continue

            game["last_updated"] = datetime.now(timezone.utc)
            games_col.update_one({"steam_app_id": app_id}, {"$set": game}, upsert=True)
            expansion_log.insert_one({"app_id": app_id, "status": "added", "checked_at": datetime.now(timezone.utc)})
            added += 1

        except Exception as e:
            print(f"  Error on {app_name}: {e}")
            expansion_log.insert_one({"app_id": app_id, "status": "error", "error": str(e), "checked_at": datetime.now(timezone.utc)})

        if (i + 1) % 100 == 0:
            total_processed = added + skipped + not_game
            print(f"  ...{total_processed}/{len(new_apps)} processed ({added} added, {not_game} non-games, {skipped} skipped)")

        time.sleep(2.5)

    print(f"\nDone. {added} new games added, {not_game} non-games skipped, {skipped} skipped/no data.")


if __name__ == "__main__":
    max_new = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            max_new = int(sys.argv[i + 1])
    expand(max_new=max_new)
    client.close()
