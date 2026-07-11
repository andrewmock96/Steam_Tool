"""
Scrape curated rankings from steam250.com — an independent Steam rankings site
(Bayesian-adjusted review score, not owned by Valve). Pulls:
  - Yearly Top 250 lists (steam250.com/<year>)
  - Hidden Gems (steam250.com/hidden_gems) — smaller/indie-leaning, closest
    proxy we have to "well-received indie games"
  - Most Played (steam250.com/most_played)

For each entry, the page already exposes: rank, title, release date,
steam250 score, review vote count, rating %, and price — all parsed
straight out of the HTML, no interpretation needed.

Stores results in the `curated_lists` collection, keyed by (list_name, year,
steam_app_id), so re-running just refreshes rank/score movement over time.

This is read-only scraping of public pages at a polite rate (1 request per
~2s). Steam250 has no public API; if they add one later, prefer that.

Usage:
    python scrape_steam250.py                      # top250 + hidden_gems + most_played, last 5 years
    python scrape_steam250.py --years 2018-2026     # custom year range for yearly lists
    python scrape_steam250.py --lists hidden_gems   # only specific list(s)
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
import re
import sys
import time
import os

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
curated_col = db["curated_lists"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SteamToolResearch/1.0)"}
SLEEP_BETWEEN = 2.0

# Each list page (e.g. steam250.com/2024, /hidden_gems) renders one row per
# game as `<div id=<rank>>...</div>`, verified against live HTML. Splitting on
# that wrapper first, then extracting fields from within each row, is far more
# robust than one long sequential regex across the whole page.
ROW_SPLIT = re.compile(r"<div id=\d+>")

APP_ID_TITLE = re.compile(r"club\.steam250\.com/app/(?P<app_id>\d+)\s+title=(?P<title>[^>]+?)>")
DATE_PATTERN = re.compile(r'<span title="(?P<date>[^"]+)">')
SCORE_PATTERN = re.compile(r"<span>(?P<score>\d\.\d+)</span>")
VOTES_PATTERN = re.compile(r"<span class=votes>(?P<votes>[\d,]+)</span>")
RATING_PCT_PATTERN = re.compile(r"width:\s*(?P<pct>\d+)%")
PRICE_PATTERN = re.compile(r"<span>\s*\$(?P<price>[\d.]+)\s*</span>")


def _clean_title(raw):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw.strip()


def _parse_row(chunk, rank):
    app_match = APP_ID_TITLE.search(chunk)
    if not app_match:
        return None
    date_match = DATE_PATTERN.search(chunk)
    score_match = SCORE_PATTERN.search(chunk)
    votes_match = VOTES_PATTERN.search(chunk)
    pct_match = RATING_PCT_PATTERN.search(chunk)
    price_match = PRICE_PATTERN.search(chunk)

    return {
        "rank": rank,
        "steam_app_id": int(app_match.group("app_id")),
        "title": _clean_title(app_match.group("title")),
        "release_date_raw": date_match.group("date") if date_match else None,
        "steam250_score": float(score_match.group("score")) if score_match else None,
        "review_votes": int(votes_match.group("votes").replace(",", "")) if votes_match else None,
        "rating_pct": int(pct_match.group("pct")) if pct_match else None,
        "price_usd": float(price_match.group("price")) if price_match else None,
    }


def fetch_list(path):
    url = f"https://steam250.com/{path}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"  {url} -> HTTP {r.status_code}")
            return ""
        return r.text
    except requests.exceptions.RequestException as e:
        print(f"  {url} -> error: {e}")
        return ""


def parse_rows(html):
    chunks = ROW_SPLIT.split(html)[1:]
    rows = []
    for i, chunk in enumerate(chunks):
        row = _parse_row(chunk, rank=i + 1)
        if row:
            rows.append(row)
    return rows


def save_list(list_name, year, rows):
    now = datetime.now(timezone.utc)
    for row in rows:
        curated_col.update_one(
            {"list_name": list_name, "year": year, "steam_app_id": row["steam_app_id"]},
            {"$set": {
                **row,
                "list_name": list_name,
                "year": year,
                "fetched_at": now,
                "source": "steam250.com",
            }},
            upsert=True,
        )
    print(f"  Saved {len(rows)} entries for {list_name} (year={year})")


def scrape_yearly(year_range):
    for year in year_range:
        print(f"Fetching Top 250 for {year}...")
        html = fetch_list(str(year))
        rows = parse_rows(html)
        if not rows:
            print(f"  No rows parsed for {year} (page structure may have changed, or year has no data yet)")
        else:
            save_list("top250_yearly", year, rows)
        time.sleep(SLEEP_BETWEEN)


def scrape_named_list(path, list_name):
    print(f"Fetching {list_name}...")
    html = fetch_list(path)
    rows = parse_rows(html)
    if not rows:
        print(f"  No rows parsed for {list_name} (page structure may have changed)")
    else:
        save_list(list_name, None, rows)
    time.sleep(SLEEP_BETWEEN)


NAMED_LISTS = {
    "hidden_gems": "hidden_gems",
    "most_played": "most_played",
    "top250": "top250",
    "bottom100": "bottom100",
}


def run(year_range=None, lists=None):
    lists = lists or list(NAMED_LISTS.keys()) + ["yearly"]

    if "yearly" in lists:
        year_range = year_range or range(datetime.now(timezone.utc).year - 4, datetime.now(timezone.utc).year + 1)
        scrape_yearly(year_range)

    for key in lists:
        if key == "yearly":
            continue
        path = NAMED_LISTS.get(key)
        if not path:
            print(f"Unknown list '{key}', skipping. Known: {list(NAMED_LISTS.keys())}")
            continue
        scrape_named_list(path, key)

    total = curated_col.count_documents({})
    print(f"\nDone. curated_lists collection now has {total:,} documents.")


if __name__ == "__main__":
    year_range = None
    lists = None
    for i, arg in enumerate(sys.argv):
        if arg == "--years" and i + 1 < len(sys.argv):
            start, end = sys.argv[i + 1].split("-")
            year_range = range(int(start), int(end) + 1)
        if arg == "--lists" and i + 1 < len(sys.argv):
            lists = sys.argv[i + 1].split(",")
    run(year_range=year_range, lists=lists)
    client.close()
