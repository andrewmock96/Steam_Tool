"""
Shared MongoDB connection and collection handles.

Every blueprint and standalone script imports from here instead of opening
its own MongoClient, so the whole app talks to one connection pool and one
set of collection names. MONGO_URI comes from the .env file (see
db.py's load_dotenv() call) and is never hardcoded.
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]

# Core Steam game records (metadata, pricing, reviews, revenue estimates —
# see steam_api.py's parse_game() for the full schema written into this).
games_col = db["games"]

# Precomputed per-genre market rollups (used by the "Player Trends" home
# chart and other summary views that don't need to scan `games` directly).
genre_aggregates_col = db["genre_aggregates"]

# Snapshots of currently coming-soon games, tracked over time so we can
# answer "how long was this store page live before launch" — see
# scrape_upcoming_releases.py, which is what writes to this collection.
upcoming_games_col = db["upcoming_games"]
