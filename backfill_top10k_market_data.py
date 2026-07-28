"""
One-time backfill: re-fetch Steam Store + SteamSpy data for the top 10,000
games by estimated revenue, so older DB records pick up fields the detail
panel now shows (peak players, playtime, Metacritic score, DLC count, etc.)
that parse_game() already extracts but older records were written before
those fields existed.

This is the same fetch/parse path as refresh_games.py, just scoped to a
fixed top-10k-by-revenue slice with clearer progress output for a one-off
watched run.

Usage:
    python backfill_top10k_market_data.py
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
from steam_api import get_steam_game_details, get_steamspy_details, parse_game
import sys
import time
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]

LIMIT = 10000


def backfill():
    pipeline = [
        {"$match": {"delisted": {"$ne": True}}},
        {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
        {"$sort": {"_sort": -1}},
        {"$limit": LIMIT},
        {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}},
    ]
    games = list(games_col.aggregate(pipeline))
    total = len(games)
    print(f"Backfilling market data for top {total} games by revenue...\n")

    updated = 0
    skipped = 0
    errors = 0
    started = time.time()

    for i, g in enumerate(games):
        aid = g["steam_app_id"]
        title = g.get("title", f"App {aid}")

        try:
            steam_data = get_steam_game_details(aid)
            spy_data = get_steamspy_details(aid) or {}

            if not steam_data:
                skipped += 1
                time.sleep(1.5)
                continue

            # Pass ITAD historical low into spy_data so parse_game can use it
            existing = games_col.find_one({"steam_app_id": aid}, {"price_history": 1, "_id": 0})
            if existing and existing.get("price_history", {}).get("steam_historical_low"):
                spy_data["_price_history_low"] = existing["price_history"]["steam_historical_low"]

            parsed = parse_game(steam_data, spy_data)
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

        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - started
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total - (i + 1)) / rate if rate > 0 else 0
            pct = (i + 1) / total * 100
            print(
                f"  ...{i + 1}/{total} ({pct:.1f}%) — "
                f"{updated} updated, {skipped} skipped, {errors} errors — "
                f"~{remaining / 60:.0f} min remaining"
            )

        time.sleep(2.5)

    print(f"\nDone. {updated} updated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    backfill()
    client.close()
