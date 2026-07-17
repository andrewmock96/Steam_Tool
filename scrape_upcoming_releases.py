"""
Track upcoming Steam releases — future competitors and a release calendar.

Originally this hit Steam's storefront search endpoint directly. That turned
out to be unreliable: the "coming soon" search facet is dominated by
near-term/just-flipped listings, so by the time we fetched full details for
each result, essentially all of them had already launched (verified: 496/496
in a live run came back already-released). Not usable as a signal.

The fix: `expand_continuous.py` and `refresh_games.py` already crawl EVERY
Steam app via the same appdetails endpoint and store `coming_soon` +
`release_date` on every game in the `games` collection — including unreleased
ones. That data is already accurate and already being collected. This script
just snapshots it.

Each run upserts by steam_app_id into `upcoming_games`, keeping the ORIGINAL
first_seen timestamp ($setOnInsert). Once a game's coming_soon flag flips to
False in `games_col` (picked up by expand_continuous/refresh_games), this
script marks it launched here too — so over weeks of runs you build a real
answer to "how long was the store page live before launch": first_seen vs.
actual release_date.

Tag backfill: SteamSpy (our normal tag source, see steam_api.py) only has
community-voted tags for games with real owner/playtime data, so unreleased
games almost always come through with tags=[]. Steam's own store page still
shows a "Popular user-defined tags" list pre-release (developer-selected at
store setup, refined by early wishlisters), so for any coming-soon game with
empty tags, this script scrapes that block directly off the store page and
writes it back onto both games_col and upcoming_games — the same pattern
scrape_steam250.py already uses for steam250.com. Polite rate limited.

Usage:
    python scrape_upcoming_releases.py                # snapshot all coming_soon games
    python scrape_upcoming_releases.py --genre Indie   # only one genre
    python scrape_upcoming_releases.py --skip-tags     # skip the store-page tag backfill
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
import re
import sys
import time
import os
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
upcoming_col = db["upcoming_games"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SteamToolResearch/1.0)",
    "Cookie": "birthtime=568022401; lastagecheckage=1-January-1990",
}
TAG_BLOCK = re.compile(
    r'class="glance_tags popular_tags" data-appid="\d+">(.*?)<div class="app_tag add_button"',
    re.S,
)
TAG_NAME = re.compile(r'class="app_tag" style="display: none;">\s*([^<]+?)\s*</a>')
TAG_SLEEP = 1.5


def fetch_store_tags(app_id):
    """Scrape the pre-release tag list off a game's own Steam store page."""
    url = f"https://store.steampowered.com/app/{app_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.exceptions.RequestException as e:
        print(f"  app {app_id}: request failed ({e})")
        return None
    if r.status_code != 200:
        print(f"  app {app_id}: HTTP {r.status_code}")
        return None
    block = TAG_BLOCK.search(r.text)
    if not block:
        return []
    return TAG_NAME.findall(block.group(1))


def backfill_tags(upcoming_docs):
    """For coming-soon games with no tags yet, scrape and store real Steam tags."""
    needing_tags = [g for g in upcoming_docs if not g.get("tags")]
    print(f"Backfilling tags for {len(needing_tags)} coming-soon games with no tags yet...")

    updated = 0
    for g in needing_tags:
        app_id = g["steam_app_id"]
        tags = fetch_store_tags(app_id)
        if tags:
            games_col.update_one({"steam_app_id": app_id}, {"$set": {"tags": tags}})
            upcoming_col.update_one({"steam_app_id": app_id}, {"$set": {"tags": tags}})
            updated += 1
        time.sleep(TAG_SLEEP)

    print(f"  Backfilled tags for {updated} of {len(needing_tags)} games.")


def snapshot(genre=None, backfill=True):
    now = datetime.now(timezone.utc)

    query = {"coming_soon": True, "delisted": {"$ne": True}}
    if genre:
        query["genres"] = genre

    projection = {
        "_id": 0,
        "steam_app_id": 1,
        "title": 1,
        "release_date": 1,
        "genres": 1,
        "tags": 1,
        "developer": 1,
        "publisher": 1,
        "platforms": 1,
        "price": 1,
        "header_image_url": 1,
        "store_url": 1,
    }

    upcoming = list(games_col.find(query, projection))
    print(f"Found {len(upcoming)} games currently marked coming_soon in the database.")

    tracked = 0
    for g in upcoming:
        app_id = g["steam_app_id"]
        upcoming_col.update_one(
            {"steam_app_id": app_id},
            {
                "$set": {
                    "title": g.get("title", ""),
                    "release_date_raw": g.get("release_date", ""),
                    "coming_soon": True,
                    "launched_since_tracking": False,
                    "genres": g.get("genres", []),
                    "tags": g.get("tags", []),
                    "developer": g.get("developer", []),
                    "publisher": g.get("publisher", []),
                    "platforms": g.get("platforms", {}),
                    "price_current_usd": g.get("price", {}).get("current"),
                    "header_image_url": g.get("header_image_url", ""),
                    "store_url": g.get("store_url", ""),
                    "last_checked": now,
                },
                "$setOnInsert": {"first_seen": now},
            },
            upsert=True,
        )
        tracked += 1

    # Anything we're tracking that's no longer coming_soon in games_col has launched.
    tracked_ids = {g["steam_app_id"] for g in upcoming}
    previously_tracked = list(upcoming_col.find(
        {"launched_since_tracking": False},
        {"_id": 0, "steam_app_id": 1},
    ))
    newly_launched = 0
    for doc in previously_tracked:
        app_id = doc["steam_app_id"]
        if app_id in tracked_ids:
            continue
        game = games_col.find_one({"steam_app_id": app_id}, {"coming_soon": 1, "release_date": 1})
        if game and not game.get("coming_soon", True):
            upcoming_col.update_one(
                {"steam_app_id": app_id},
                {"$set": {
                    "coming_soon": False,
                    "launched_since_tracking": True,
                    "release_date_raw": game.get("release_date", ""),
                    "last_checked": now,
                }},
            )
            newly_launched += 1

    print(f"Tracked/updated {tracked} upcoming games.")
    print(f"Detected {newly_launched} games that launched since last snapshot.")
    print(f"upcoming_games collection now has {upcoming_col.count_documents({}):,} total documents "
          f"({upcoming_col.count_documents({'launched_since_tracking': False}):,} still upcoming).")

    if backfill:
        still_upcoming = list(upcoming_col.find(
            {"launched_since_tracking": False},
            {"_id": 0, "steam_app_id": 1, "tags": 1},
        ))
        backfill_tags(still_upcoming)


if __name__ == "__main__":
    genre = None
    backfill = "--skip-tags" not in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == "--genre" and i + 1 < len(sys.argv):
            genre = sys.argv[i + 1]
    snapshot(genre=genre, backfill=backfill)
    client.close()
