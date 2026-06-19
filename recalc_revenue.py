"""
Recalculate estimated revenue for games that have ITAD historical pricing.
Uses: avg(initial*0.35, current*0.35, hist_low*0.30) + tiered Steam cut.
No API calls — just recalculates from existing DB data.
"""
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]


def steam_dev_share(gross):
    if gross <= 10_000_000:
        return gross * 0.70
    elif gross <= 50_000_000:
        return 10_000_000 * 0.70 + (gross - 10_000_000) * 0.75
    else:
        return 10_000_000 * 0.70 + 40_000_000 * 0.75 + (gross - 50_000_000) * 0.80


games = list(games_col.find(
    {"price_history.found": True, "is_free": {"$ne": True}},
    {"steam_app_id": 1, "title": 1, "price": 1, "estimated_owners": 1,
     "price_history": 1, "estimated_revenue": 1, "_id": 0}
))

print(f"Recalculating revenue for {len(games)} games with ITAD data...\n")

ops = []
changed = 0

for g in games:
    initial = g.get("price", {}).get("initial", 0)
    current = g.get("price", {}).get("current", 0)
    hist_low = g.get("price_history", {}).get("steam_historical_low")
    owner_low = g.get("estimated_owners", {}).get("low", 0)
    owner_high = g.get("estimated_owners", {}).get("high", 0)

    if hist_low is not None and initial > 0:
        avg_price = (initial * 0.35) + (current * 0.35) + (hist_low * 0.30)
    elif initial > 0:
        avg_price = (initial + current) / 2
    else:
        avg_price = current

    if avg_price == 0:
        continue

    new_low = round(steam_dev_share(owner_low * avg_price))
    new_high = round(steam_dev_share(owner_high * avg_price))

    old_low = g.get("estimated_revenue", {}).get("low", 0)
    old_high = g.get("estimated_revenue", {}).get("high", 0)

    if new_low != old_low or new_high != old_high:
        ops.append(UpdateOne(
            {"steam_app_id": g["steam_app_id"]},
            {"$set": {
                "estimated_revenue.low": new_low,
                "estimated_revenue.high": new_high,
                "revenue_method": "itad_weighted"
            }}
        ))
        changed += 1

if ops:
    games_col.bulk_write(ops)

print(f"Done. {changed} games updated with improved revenue estimates.")
client.close()
