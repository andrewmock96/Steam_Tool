from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
genre_aggregates_col = db["genre_aggregates"]
upcoming_games_col = db["upcoming_games"]
