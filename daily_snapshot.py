"""
Run once per day to record genre-level player counts.
Store results in genre_snapshots collection.
Safe to run multiple times — upserts by date+genre.
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from datetime import datetime, timezone
import os

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db     = client["steam_tool"]
games_col     = db["games"]
snapshots_col = db["genre_snapshots"]

GENRES = ["Action", "Adventure", "Casual", "Indie", "RPG",
          "Simulation", "Strategy", "Sports", "Racing"]

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
ops   = []

for genre in GENRES:
    agg = list(games_col.aggregate([
        {"$match": {"genres": genre}},
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
