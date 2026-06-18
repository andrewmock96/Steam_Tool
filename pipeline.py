from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from datetime import datetime, timezone
from steam_api import get_steamspy_by_genre, get_steamspy_by_tag, get_steamspy_details, get_steam_game_details, parse_game, STEAM_GENRES, STEAM_SUBGENRES
import os
import time

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["steam_tool"]
games_col = db["games"]
review_snapshots_col = db["review_snapshots"]
player_snapshots_col = db["player_snapshots"]
sync_log_col = db["sync_log"]


def already_synced(app_id):
    """Check if a game is already in the database."""
    return games_col.count_documents({"steam_app_id": app_id}, limit=1) > 0


def genre_already_completed(genre):
    """Check if a genre has been fully synced before."""
    return sync_log_col.count_documents({"genre": genre, "status": "complete"}, limit=1) > 0


def mark_genre_complete(genre, saved, skipped):
    """Record that a genre sync finished successfully."""
    sync_log_col.update_one(
        {"genre": genre},
        {"$set": {
            "genre": genre,
            "status": "complete",
            "saved": saved,
            "skipped": skipped,
            "completed_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )


def save_game(app_id, spy_data):
    """Fetch full details for one game and save it to MongoDB."""
    steam_data = get_steam_game_details(app_id)

    # Genre endpoint doesn't include tags — fetch full details to get them
    full_spy_data = get_steamspy_details(app_id)
    if full_spy_data:
        spy_data = {**spy_data, **full_spy_data}

    game = parse_game(steam_data, spy_data)

    if not game:
        return False

    game["last_updated"] = datetime.now(timezone.utc)

    try:
        games_col.update_one({"steam_app_id": app_id}, {"$set": game}, upsert=True)
    except DuplicateKeyError:
        games_col.update_one({"steam_app_id": app_id}, {"$set": game})

    review_snapshots_col.insert_one({
        "steam_app_id": app_id,
        "timestamp": datetime.now(timezone.utc),
        **game["review_summary"]
    })

    player_snapshots_col.insert_one({
        "steam_app_id": app_id,
        "timestamp": datetime.now(timezone.utc),
        "current_players": game["players"]["current"],
        "peak_alltime": game["players"]["peak_alltime"]
    })

    return True


def sync_by_genre(genre):
    """Fetch games for a genre and save only ones we don't already have."""
    if genre_already_completed(genre):
        print(f"\nSkipping {genre} — already completed.")
        return

    print(f"\nSyncing genre: {genre}")
    games = get_steamspy_by_genre(genre)

    if not games:
        print(f"  No data returned for {genre}")
        return

    saved = 0
    skipped_duplicate = 0
    skipped_no_data = 0

    for app_id, spy_data in games.items():
        app_id = int(app_id)
        title = spy_data.get("name", f"App {app_id}")

        # Skip games we already have — no need to hit Steam API again
        if already_synced(app_id):
            print(f"  Already have: {title}, skipping.")
            skipped_duplicate += 1
            continue

        print(f"  Syncing: {title}")
        result = save_game(app_id, spy_data)

        if result:
            saved += 1
        else:
            skipped_no_data += 1
            print(f"    Skipped (no data)")

        time.sleep(2.5)

    mark_genre_complete(genre, saved, skipped_duplicate + skipped_no_data)
    print(f"  Genre complete: {saved} new, {skipped_duplicate} already had, {skipped_no_data} no data.")


def sync_by_tag(tag):
    """Fetch games for a subgenre tag and save only ones we don't already have."""
    tag_key = f"tag:{tag}"

    if genre_already_completed(tag_key):
        print(f"  Skipping tag '{tag}' — already completed.")
        return

    print(f"  Syncing tag: {tag}")
    games = get_steamspy_by_tag(tag)

    if not games:
        print(f"    No data returned for tag '{tag}'")
        mark_genre_complete(tag_key, 0, 0)
        return

    saved = 0
    skipped_duplicate = 0
    skipped_no_data = 0

    for app_id, spy_data in games.items():
        app_id = int(app_id)
        title = spy_data.get("name", f"App {app_id}")

        if already_synced(app_id):
            skipped_duplicate += 1
            continue

        print(f"    Syncing: {title}")
        result = save_game(app_id, spy_data)

        if result:
            saved += 1
        else:
            skipped_no_data += 1

        time.sleep(2.5)

    mark_genre_complete(tag_key, saved, skipped_duplicate + skipped_no_data)
    print(f"    Tag complete: {saved} new, {skipped_duplicate} already had, {skipped_no_data} no data.")


def sync_all_genres():
    """Loop through every genre and subgenre. Skips anything already completed."""
    total_tags = sum(len(tags) for tags in STEAM_SUBGENRES.values())
    print(f"Starting sync across {len(STEAM_GENRES)} genres and {total_tags} subgenres...\n")

    for genre in STEAM_GENRES:
        sync_by_genre(genre)

        if genre in STEAM_SUBGENRES:
            print(f"  Syncing subgenres for {genre}...")
            for tag in STEAM_SUBGENRES[genre]:
                sync_by_tag(tag)

    print("\nAll genres and subgenres synced.")
    client.close()


if __name__ == "__main__":
    import sys
    if "--force" in sys.argv:
        print("Force mode: clearing sync log to re-fetch all genres/tags.\n")
        sync_log_col.delete_many({})
    sync_all_genres()
