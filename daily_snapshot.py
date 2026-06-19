"""
Run once per day to record genre-level player counts.
Uses Steam Web API for live CCU when available, falls back to stored data.
Store results in genre_snapshots collection.
Safe to run multiple times — upserts by date+genre.
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
import time
import os

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db     = client["steam_tool"]
games_col     = db["games"]
snapshots_col = db["genre_snapshots"]

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
PLAYER_COUNT_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

GENRES = ["Action", "Adventure", "Casual", "Indie", "RPG",
          "Simulation", "Strategy", "Sports", "Racing"]


def get_live_ccu(app_id):
    if not STEAM_API_KEY:
        return None
    try:
        r = requests.get(PLAYER_COUNT_URL, params={
            "key": STEAM_API_KEY, "appid": app_id
        }, timeout=8)
        if r.status_code == 200:
            data = r.json().get("response", {})
            if data.get("result") == 1:
                return data.get("player_count", 0)
    except Exception:
        pass
    return None


today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
ops   = []

# If we have a Steam API key, refresh top games' CCU first
if STEAM_API_KEY:
    print("Refreshing live player counts for top 500 games...")
    top_games = list(games_col.aggregate([
        {"$match": {"delisted": {"$ne": True}}},
        {"$addFields": {"_s": {"$ifNull": ["$estimated_revenue.low", 0]}}},
        {"$sort": {"_s": -1}},
        {"$limit": 500},
        {"$project": {"steam_app_id": 1, "_id": 0}}
    ]))

    refreshed = 0
    for g in top_games:
        ccu = get_live_ccu(g["steam_app_id"])
        if ccu is not None:
            games_col.update_one(
                {"steam_app_id": g["steam_app_id"]},
                {"$set": {"players.current": ccu, "players.last_updated": datetime.now(timezone.utc)}}
            )
            refreshed += 1
        time.sleep(0.4)

    print(f"  Refreshed {refreshed} of {len(top_games)} games.\n")
else:
    print("No STEAM_API_KEY — using stored player counts.\n")

# Now aggregate per genre
for genre in GENRES:
    agg = list(games_col.aggregate([
        {"$match": {"genres": genre, "delisted": {"$ne": True}}},
        {"$group": {
            "_id":            None,
            "total_players":  {"$sum": "$players.current"},
            "total_games":    {"$sum": 1}
        }}
    ]))
    s = agg[0] if agg else {}
    total_players = s.get("total_players", 0)
    total_games   = s.get("total_games", 0)

    ops.append(UpdateOne(
        {"date": today, "genre": genre},
        {"$set": {
            "date":           today,
            "genre":          genre,
            "total_players":  total_players,
            "total_games":    total_games,
            "recorded_at":    datetime.now(timezone.utc)
        }},
        upsert=True
    ))
    print(f"  {genre}: {total_players:,} players across {total_games:,} games")

if ops:
    result = snapshots_col.bulk_write(ops)
    print(f"\nDone — {result.upserted_count} inserted, {result.modified_count} updated for {today}")
