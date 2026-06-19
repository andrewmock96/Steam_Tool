"""
Continuously expand the game catalog by fetching ALL games from Steam.
Designed to run 24/7 until every game on Steam is in the database.
Safe to stop and restart — picks up where it left off.

Handles rate limits, connection errors, and Steam API throttling.
Logs progress so you can see how far along it is.

Usage:
    python expand_continuous.py
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from steam_api import get_steam_game_details, get_steamspy_details, parse_game
import requests
import time
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
expansion_log = db["expansion_log"]

BATCH_SIZE = 100
SLEEP_BETWEEN = 2.0
SLEEP_ON_RATE_LIMIT = 60
SLEEP_BETWEEN_BATCHES = 10
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), ".expand_progress")


def get_all_steam_apps():
    """Fetch full Steam app list using IStoreService (paginated, requires API key)."""
    api_key = os.getenv("STEAM_API_KEY")
    if not api_key:
        print("ERROR: STEAM_API_KEY not set in .env")
        return []

    print("Fetching full Steam app list (paginated)...")
    apps = []
    last_appid = 0
    page = 0

    while True:
        try:
            r = requests.get("https://api.steampowered.com/IStoreService/GetAppList/v1/", params={
                "key": api_key,
                "max_results": 50000,
                "last_appid": last_appid
            }, timeout=30)

            if r.status_code != 200:
                print(f"  Failed on page {page}: {r.status_code}")
                break

            data = r.json().get("response", {})
            batch = data.get("apps", [])
            apps.extend(batch)
            page += 1

            if not data.get("have_more_results"):
                break

            last_appid = data.get("last_appid", 0)
            time.sleep(1)

        except Exception as e:
            print(f"  Error fetching app list: {e}")
            break

    print(f"Steam has {len(apps):,} apps total ({page} pages).")
    return apps


def get_already_processed():
    existing = set()
    for doc in games_col.find({}, {"steam_app_id": 1, "_id": 0}):
        existing.add(doc["steam_app_id"])
    for doc in expansion_log.find({}, {"app_id": 1, "_id": 0}):
        existing.add(doc["app_id"])
    return existing


def process_app(app_id, app_name):
    try:
        steam_data = get_steam_game_details(app_id)

        if not steam_data:
            expansion_log.insert_one({
                "app_id": app_id,
                "status": "no_data",
                "checked_at": datetime.now(timezone.utc)
            })
            return "no_data"

        app_type = steam_data.get("type", "")
        if app_type != "game":
            expansion_log.insert_one({
                "app_id": app_id,
                "type": app_type,
                "status": "not_game",
                "checked_at": datetime.now(timezone.utc)
            })
            return "not_game"

        spy_data = get_steamspy_details(app_id) or {}
        game = parse_game(steam_data, spy_data)

        if not game:
            expansion_log.insert_one({
                "app_id": app_id,
                "status": "parse_failed",
                "checked_at": datetime.now(timezone.utc)
            })
            return "parse_failed"

        game["last_updated"] = datetime.now(timezone.utc)
        games_col.update_one({"steam_app_id": app_id}, {"$set": game}, upsert=True)
        expansion_log.insert_one({
            "app_id": app_id,
            "status": "added",
            "checked_at": datetime.now(timezone.utc)
        })
        return "added"

    except requests.exceptions.ConnectionError:
        return "connection_error"
    except Exception as e:
        expansion_log.insert_one({
            "app_id": app_id,
            "status": "error",
            "error": str(e)[:200],
            "checked_at": datetime.now(timezone.utc)
        })
        return "error"


def run():
    all_apps = get_all_steam_apps()
    if not all_apps:
        print("Could not fetch app list. Retrying in 5 minutes...")
        time.sleep(300)
        return run()

    processed = get_already_processed()
    remaining = [a for a in all_apps if a["appid"] not in processed]
    total_remaining = len(remaining)
    total_on_steam = len(all_apps)
    already_done = len(processed)

    print(f"Already processed: {already_done:,}")
    print(f"Remaining: {total_remaining:,}")
    print(f"Starting continuous expansion...\n")
    print("=" * 60)

    added = 0
    not_game = 0
    no_data = 0
    errors = 0
    batch_num = 0
    start_time = time.time()

    for i, app in enumerate(remaining):
        app_id = app["appid"]
        app_name = app.get("name", f"App {app_id}")

        result = process_app(app_id, app_name)

        if result == "added":
            added += 1
        elif result == "not_game":
            not_game += 1
        elif result == "no_data" or result == "parse_failed":
            no_data += 1
        elif result == "connection_error":
            print(f"  Connection error on {app_name} — pausing 30s...")
            time.sleep(30)
            errors += 1
            continue
        else:
            errors += 1

        processed_count = i + 1

        if processed_count % BATCH_SIZE == 0:
            batch_num += 1
            elapsed = time.time() - start_time
            rate = processed_count / (elapsed / 3600) if elapsed > 0 else 0
            eta_hours = (total_remaining - processed_count) / rate if rate > 0 else 0

            total_in_db = already_done + processed_count
            print(f"  Batch {batch_num} | "
                  f"Checked: {processed_count:,}/{total_remaining:,} | "
                  f"Added: {added:,} | "
                  f"Non-games: {not_game:,} | "
                  f"Skipped: {no_data:,} | "
                  f"Errors: {errors:,} | "
                  f"Rate: {rate:,.0f}/hr | "
                  f"ETA: {eta_hours:.1f}h | "
                  f"DB total: {total_in_db:,}/{total_on_steam:,}")

            time.sleep(SLEEP_BETWEEN_BATCHES)
        else:
            time.sleep(SLEEP_BETWEEN)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"COMPLETE in {elapsed/3600:.1f} hours")
    print(f"  Added: {added:,}")
    print(f"  Non-games: {not_game:,}")
    print(f"  No data: {no_data:,}")
    print(f"  Errors: {errors:,}")
    print(f"  Total in DB: {games_col.count_documents({}):,}")


if __name__ == "__main__":
    print("=" * 60)
    print("  STEAM CATALOG EXPANSION — CONTINUOUS MODE")
    print("  Press Ctrl+C to stop (safe to restart anytime)")
    print("=" * 60 + "\n")

    try:
        run()
    except KeyboardInterrupt:
        total = games_col.count_documents({})
        print(f"\n\nStopped by user. {total:,} games in database.")
        print("Run again anytime to continue where you left off.")
    finally:
        client.close()
