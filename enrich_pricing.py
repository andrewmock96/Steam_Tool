"""
Enrich games with historical-low pricing from IsThereAnyDeal (ITAD).
Feeds steam_api.parse_game()'s revenue model via price_history.steam_historical_low
(already wired in refresh_games.py) — a game's realistic average sale price is a
much better revenue-estimate input than list price alone.

Note: ITAD's bulk historylow endpoint returns the lowest price seen across
ALL stores it tracks (Microsoft Store, EA Store, GOG, etc.), not Steam
specifically — verified live: Forza Horizon 5's low came back as a Microsoft
Store price, Battlefield V's as an EA Store price. Feeding a non-Steam price
into a Steam-specific revenue model would make estimates worse, not better.
So this script only writes `steam_historical_low` when ITAD's low.shop.id is
61 (Steam). Non-Steam lows are kept separately as `market_low_price` /
`market_low_shop` for reference/transparency, but do NOT feed the revenue
model. This trades some coverage for correctness — deliberately.

A version of this script ran once already (2,351 games) and was deleted as a
one-time script, but it used the wrong HTTP method (POST) on the lookup
endpoint, silently failing on ~350 of those. This version uses ITAD's real
bulk endpoints (verified against live API):
  - POST /lookup/id/shop/61/v1   — up to 200 Steam appids -> ITAD ids per call
  - POST /games/historylow/v1    — up to 200 ITAD ids -> historical low per call
Two requests covers up to 200 games. ITAD's rate limit is 1000 req/5min, so
this is nowhere close to the ceiling even at --all scale.

Usage:
    python enrich_pricing.py              # top 3000 by revenue, skips already-enriched
    python enrich_pricing.py --all        # all games, skips already-enriched
    python enrich_pricing.py --limit 500  # custom limit
    python enrich_pricing.py --refresh    # re-check games already enriched (prices change)
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
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

ITAD_API_KEY = os.getenv("ITAD_API_KEY")
ITAD_URL = "https://api.isthereanydeal.com"
CHUNK_SIZE = 150  # under ITAD's 200 batch cap, leaves margin
SLEEP_BETWEEN_CHUNKS = 1.0

if not ITAD_API_KEY:
    print("ERROR: ITAD_API_KEY must be set in .env")
    sys.exit(1)


def lookup_itad_ids(app_ids):
    """Resolve Steam appids -> ITAD game IDs. Returns {appid: itad_id or None}."""
    body = [f"app/{aid}" for aid in app_ids]
    try:
        r = requests.post(f"{ITAD_URL}/lookup/id/shop/61/v1", params={"key": ITAD_API_KEY}, json=body, timeout=20)
        if r.status_code != 200:
            print(f"  lookup failed: HTTP {r.status_code}")
            return {}
        data = r.json()
        result = {}
        for aid in app_ids:
            itad_id = data.get(f"app/{aid}")
            result[aid] = itad_id
        return result
    except requests.exceptions.RequestException as e:
        print(f"  lookup error: {e}")
        return {}


def fetch_historical_lows(itad_ids):
    """Fetch historical low prices for a batch of ITAD ids. Returns {itad_id: entry}."""
    if not itad_ids:
        return {}
    try:
        r = requests.post(
            f"{ITAD_URL}/games/historylow/v1",
            params={"key": ITAD_API_KEY, "country": "US"},
            json=itad_ids,
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  historylow failed: HTTP {r.status_code}")
            return {}
        return {entry["id"]: entry for entry in r.json()}
    except requests.exceptions.RequestException as e:
        print(f"  historylow error: {e}")
        return {}


def enrich(limit=3000, all_games=False, refresh=False):
    match = {"delisted": {"$ne": True}}
    if not refresh:
        match["price_history"] = {"$exists": False}

    if all_games:
        games = list(games_col.find(match, {"steam_app_id": 1, "title": 1, "_id": 0}))
    else:
        pipeline = [
            {"$match": match},
            {"$addFields": {"_sort": {"$ifNull": ["$estimated_revenue.low", 0]}}},
            {"$sort": {"_sort": -1}},
            {"$limit": limit},
            {"$project": {"steam_app_id": 1, "title": 1, "_id": 0}},
        ]
        games = list(games_col.aggregate(pipeline))

    print(f"Enriching pricing for {len(games)} games from ITAD (chunks of {CHUNK_SIZE})...\n")

    enriched = 0
    not_found = 0

    for i in range(0, len(games), CHUNK_SIZE):
        chunk = games[i:i + CHUNK_SIZE]
        app_ids = [g["steam_app_id"] for g in chunk]

        id_map = lookup_itad_ids(app_ids)
        found_ids = {aid: itad_id for aid, itad_id in id_map.items() if itad_id}

        lows = fetch_historical_lows(list(found_ids.values())) if found_ids else {}

        for g in chunk:
            aid = g["steam_app_id"]
            itad_id = id_map.get(aid)
            now = datetime.now(timezone.utc).timestamp()

            if not itad_id:
                games_col.update_one(
                    {"steam_app_id": aid},
                    {"$set": {"price_history": {"source": "itad", "found": False, "fetched_at": now}}},
                )
                not_found += 1
                continue

            low_entry = lows.get(itad_id)
            if not low_entry or not low_entry.get("low"):
                games_col.update_one(
                    {"steam_app_id": aid},
                    {"$set": {"price_history": {
                        "source": "itad", "found": False, "itad_id": itad_id, "fetched_at": now,
                    }}},
                )
                not_found += 1
                continue

            low = low_entry["low"]
            is_steam_low = low.get("shop", {}).get("id") == 61

            entry = {
                "source": "itad",
                "found": is_steam_low,
                "itad_id": itad_id,
                "market_low_price": low.get("price", {}).get("amount"),
                "market_low_shop": low.get("shop", {}).get("name"),
                "fetched_at": now,
            }
            if is_steam_low:
                entry["steam_historical_low"] = low.get("price", {}).get("amount")
                entry["steam_best_discount"] = low.get("cut")

            games_col.update_one({"steam_app_id": aid}, {"$set": {"price_history": entry}})
            if is_steam_low:
                enriched += 1
            else:
                not_found += 1

        done = min(i + CHUNK_SIZE, len(games))
        print(f"  ...{done}/{len(games)} ({enriched} enriched, {not_found} not found)")
        time.sleep(SLEEP_BETWEEN_CHUNKS)

    print(f"\nDone. {enriched} enriched, {not_found} not found on ITAD.")
    print("Run refresh_games.py afterward to fold these historical lows into revenue estimates.")


if __name__ == "__main__":
    do_all = "--all" in sys.argv
    refresh = "--refresh" in sys.argv
    limit = 3000
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    enrich(limit=limit, all_games=do_all, refresh=refresh)
    client.close()
