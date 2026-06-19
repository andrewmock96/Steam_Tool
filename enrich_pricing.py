"""
Enrich games with historical pricing data from IsThereAnyDeal.
Fetches historical low prices and stores them for better revenue estimation.
Rate limit: 1000 requests per 5 minutes.

Usage:
    python enrich_pricing.py              # top 2000 by revenue
    python enrich_pricing.py --all        # all games
    python enrich_pricing.py --limit 500  # custom limit
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import requests
import time
import sys
import os

load_dotenv()

ITAD_API_KEY = os.getenv("ITAD_API_KEY")
if not ITAD_API_KEY:
    print("ERROR: ITAD_API_KEY not set in .env")
    sys.exit(1)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]

ITAD_BASE = "https://api.isthereanydeal.com"


def lookup_itad_id(steam_app_id):
    """Convert a Steam app ID to an ITAD game ID."""
    try:
        r = requests.get(f"{ITAD_BASE}/games/lookup/v1", params={
            "key": ITAD_API_KEY,
            "appid": steam_app_id
        }, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("found"):
                return data.get("game", {}).get("id")
    except Exception:
        pass
    return None


def get_historical_low(itad_id):
    """Get the historical lowest price for a game on Steam."""
    try:
        r = requests.post(f"{ITAD_BASE}/games/storelow/v2", params={
            "key": ITAD_API_KEY
        }, json=[itad_id], timeout=10)
        if r.status_code == 200:
            data = r.json()
            for entry in data:
                if entry.get("id") == itad_id:
                    lows = entry.get("lows", [])
                    for low in lows:
                        if low.get("shop", {}).get("id") == 61:  # Steam shop ID
                            return {
                                "amount": low.get("price", {}).get("amount"),
                                "cut": low.get("cut"),
                                "timestamp": low.get("timestamp")
                            }
    except Exception:
        pass
    return None


def enrich(limit=2000, all_games=False):
    if all_games:
        games = list(games_col.find(
            {"delisted": {"$ne": True}, "price_history": {"$exists": False}},
            {"steam_app_id": 1, "title": 1, "_id": 0}
        ))
    else:
        pipeline = [
            {"$match": {"delisted": {"$ne": True}, "price_history": {"$exists": False}}},
            {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
            {"$sort": {"_sort": -1}},
            {"$limit": limit},
            {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}}
        ]
        games = list(games_col.aggregate(pipeline))

    print(f"Enriching pricing for {len(games)} games...\n")

    enriched = 0
    not_found = 0
    errors = 0
    request_count = 0

    for i, g in enumerate(games):
        aid = g["steam_app_id"]
        title = g.get("title", f"App {aid}")

        itad_id = lookup_itad_id(aid)
        request_count += 1

        if not itad_id:
            not_found += 1
            games_col.update_one(
                {"steam_app_id": aid},
                {"$set": {"price_history": {"source": "itad", "found": False}}}
            )
        else:
            low = get_historical_low(itad_id)
            request_count += 1

            if low:
                games_col.update_one(
                    {"steam_app_id": aid},
                    {"$set": {"price_history": {
                        "source": "itad",
                        "found": True,
                        "itad_id": itad_id,
                        "steam_historical_low": low.get("amount"),
                        "steam_best_discount": low.get("cut"),
                        "fetched_at": time.time()
                    }}}
                )
                enriched += 1
            else:
                games_col.update_one(
                    {"steam_app_id": aid},
                    {"$set": {"price_history": {"source": "itad", "found": True, "itad_id": itad_id}}}
                )

        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(games)} ({enriched} enriched, {not_found} not found)")

        # Rate limiting: 1000 requests per 5 min = ~3.3 req/sec
        if request_count % 900 == 0:
            print("  Approaching rate limit — pausing 60s...")
            time.sleep(60)
        else:
            time.sleep(0.4)

    print(f"\nDone. {enriched} enriched, {not_found} not on ITAD, {errors} errors.")


if __name__ == "__main__":
    do_all = "--all" in sys.argv
    limit = 2000
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    enrich(limit=limit, all_games=do_all)
    client.close()
