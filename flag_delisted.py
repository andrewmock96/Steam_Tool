"""
Check all games against the Steam Store API and flag delisted ones.
A game is delisted if Steam returns success=false for its app ID.
Run once, then periodically to catch newly delisted games.
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import requests
import time
import os

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]

games = list(games_col.find(
    {"delisted": {"$ne": True}},
    {"steam_app_id": 1, "title": 1, "_id": 0}
))

print(f"Checking {len(games)} games against Steam Store API...\n")

flagged = 0
checked = 0
errors = 0

for g in games:
    aid = g["steam_app_id"]
    title = g.get("title", f"App {aid}")

    try:
        r = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": aid},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get(str(aid), {})
            if not data.get("success", False):
                games_col.update_one(
                    {"steam_app_id": aid},
                    {"$set": {"delisted": True}}
                )
                flagged += 1
                print(f"  DELISTED: {title} ({aid})")
        elif r.status_code == 429:
            print(f"  Rate limited — pausing 30s...")
            time.sleep(30)
            continue
        else:
            errors += 1
    except Exception as e:
        errors += 1
        print(f"  Error checking {title}: {e}")

    checked += 1
    if checked % 100 == 0:
        print(f"  ...checked {checked}/{len(games)} ({flagged} delisted so far)")

    time.sleep(1.5)

print(f"\nDone. Checked {checked}, flagged {flagged} as delisted, {errors} errors.")
client.close()
