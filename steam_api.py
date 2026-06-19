import requests
import time

STEAM_STORE_URL = "https://store.steampowered.com/api/appdetails"
STEAMSPY_URL = "https://steamspy.com/api.php"


STEAM_GENRES = [
    "Action", "Adventure", "Casual", "Indie", "Massively Multiplayer",
    "Racing", "RPG", "Simulation", "Sports", "Strategy", "Early Access"
]

STEAM_SUBGENRES = {
    "Action": [
        "Shooter", "First-Person Shooter", "Third-Person Shooter", "Top-Down Shooter",
        "Bullet Hell", "Platformer", "Precision Platformer", "Side Scroller", "Run and Gun",
        "Fighting", "Hack and Slash", "Beat 'em Up", "Brawler", "Stealth",
        "Soulslike", "Battle Royale", "Tower Defense", "Action Roguelike", "Rhythm",
        "Open World", "Survival", "Looter Shooter", "Military", "Co-op",
        "Parkour", "Space", "Sci-fi", "Arena Shooter", "2D", "Metroidvania"
    ],
    "Adventure": [
        "Point & Click", "Visual Novel", "Walking Simulator", "Puzzle Platformer",
        "Interactive Fiction", "Escape Room", "Mystery", "Horror",
        "Survival Horror", "Psychological Horror", "Story Rich", "Exploration",
        "Narrative", "Dark", "Open World", "Thriller", "Comedy",
        "Supernatural", "Detective", "Anime", "Sci-fi", "Fantasy"
    ],
    "Casual": [
        "Puzzle", "Hidden Object", "Idle", "Clicker", "Match 3",
        "Relaxing", "Mini Games", "Word Game", "Trivia", "Cozy",
        "Music", "Anime", "Cute", "Board Game", "Card Game",
        "Family Friendly", "2D", "Cooking", "Rhythm", "Typing"
    ],
    "Indie": [
        "Roguelike", "Roguelite", "Metroidvania", "Pixel Art", "Narrative",
        "Experimental", "Atmospheric", "Cozy", "Retro", "Cyberpunk",
        "Steampunk", "Dark Fantasy", "Horror", "Survival", "2D",
        "Platformer", "Open World", "Cute", "Anime", "Story Rich",
        "Puzzle", "Exploration", "Dark", "Fantasy", "Sci-fi",
        "Hand-drawn", "Top-Down", "Mystery", "Psychological", "Comedy"
    ],
    "RPG": [
        "JRPG", "Action RPG", "Turn-Based RPG", "Dungeon Crawler", "Western RPG",
        "Tactical RPG", "Isometric RPG", "Dark Fantasy", "Deckbuilding RPG",
        "Creature Collector", "Open World", "Fantasy", "Sci-fi", "Anime",
        "Story Rich", "Co-op", "Character Customization", "Sandbox",
        "MMORPG", "Roguelike", "Strategy RPG", "Loot", "Party-Based RPG"
    ],
    "Simulation": [
        "City Builder", "Farming Sim", "Life Sim", "Management", "Tycoon",
        "Space Sim", "Flight Sim", "Train Sim", "Colony Sim",
        "Base Building", "Sandbox", "God Game", "Driving", "Cooking",
        "Fishing", "Automation", "Factory", "Hospital", "Business",
        "Naval", "Trucking", "Hunting", "Survival", "Physics"
    ],
    "Strategy": [
        "Turn-Based Strategy", "Real-Time Strategy", "4X", "Grand Strategy",
        "Tower Defense", "Card Game", "Deckbuilding", "Wargame",
        "Auto Battler", "Puzzle Strategy", "City Builder", "Resource Management",
        "Economic", "Space", "Military", "Political", "Base Building",
        "Roguelike", "Naval", "Survival", "Management", "Sandbox"
    ],
    "Sports": [
        "Soccer", "Basketball", "Baseball", "Golf", "Tennis", "Wrestling",
        "Fishing", "Skating", "Cycling", "Track and Field", "Boxing", "Snowboarding",
        "Football", "Hockey", "Rugby", "Cricket", "Volleyball",
        "Skateboarding", "Surfing", "BMX", "Extreme Sports", "Hunting", "Archery"
    ],
    "Racing": [
        "Arcade Racing", "Simulation Racing", "Kart Racing",
        "Off-Road", "Motocross", "Drag Racing",
        "Street Racing", "Rally", "Open World", "Bikes", "Formula Racing"
    ]
}


def get_steamspy_top_games():
    """Fetch the top ~100 games by players in the last 2 weeks from SteamSpy."""
    response = requests.get(STEAMSPY_URL, params={"request": "top100in2weeks"})
    if response.status_code == 200:
        return response.json()
    return {}


def get_steamspy_by_genre(genre):
    """Fetch top games for a specific genre from SteamSpy."""
    response = requests.get(STEAMSPY_URL, params={"request": "genre", "genre": genre})
    if response.status_code == 200:
        return response.json()
    return {}


def get_steamspy_by_tag(tag):
    """Fetch top games for a specific tag/subgenre from SteamSpy."""
    response = requests.get(STEAMSPY_URL, params={"request": "tag", "tag": tag})
    if response.status_code == 200:
        return response.json()
    return {}


def get_steamspy_details(app_id):
    """Fetch estimated owners and revenue data for a game from SteamSpy."""
    response = requests.get(STEAMSPY_URL, params={"request": "appdetails", "appid": app_id})
    if response.status_code == 200:
        try:
            return response.json()
        except Exception:
            return {}
    return {}


def get_steam_game_details(app_id, retries=3):
    """Fetch full game details from the Steam Store API. Retries on connection errors."""
    for attempt in range(retries):
        try:
            response = requests.get(STEAM_STORE_URL, params={"appids": app_id, "cc": "us", "l": "en"}, timeout=10)
            if response.status_code != 200:
                return {}
            data = response.json().get(str(app_id), {})
            if not data.get("success"):
                return {}
            return data.get("data", {})
        except requests.exceptions.ConnectionError:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  Connection error, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Failed after {retries} attempts, skipping.")
                return {}
        except requests.exceptions.RequestException:
            return {}


def parse_categories(categories):
    """Convert Steam's category list into boolean feature flags."""
    ids = {c.get("id") for c in categories}
    return {
        "is_single_player":         2  in ids,
        "has_multiplayer":          1  in ids,
        "has_co_op":                9  in ids or 36 in ids,
        "has_pvp":                  49 in ids or 47 in ids,
        "has_achievements":         22 in ids,
        "has_cloud_saves":          23 in ids,
        "has_leaderboards":         25 in ids,
        "has_trading_cards":        29 in ids,
        "has_workshop":             30 in ids,
        "has_full_controller":      28 in ids,
        "has_partial_controller":   18 in ids or 32 in ids,
        "has_vr_support":           31 in ids or 53 in ids,
        "has_remote_play":          41 in ids,
    }


def parse_languages(raw):
    """Strip HTML tags from Steam's supported languages string."""
    import re
    clean = re.sub(r"<[^>]+>", "", raw or "")
    return [l.strip() for l in clean.split(",") if l.strip()]


def parse_game(steam_data, spy_data):
    """Combine Steam and SteamSpy data into our schema format."""
    if not steam_data:
        return None

    # --- Price ---
    price_info = steam_data.get("price_overview", {})
    price = {
        "currency": price_info.get("currency", "USD"),
        "initial":          price_info.get("initial", 0) / 100,
        "current":          price_info.get("final", 0) / 100,
        "discount_percent": price_info.get("discount_percent", 0)
    }

    # --- Reviews ---
    pos = spy_data.get("positive", 0)
    neg = spy_data.get("negative", 0)
    total = pos + neg
    reviews = {
        "total_reviews":    total,
        "positive_reviews": pos,
        "negative_reviews": neg,
        "positive_percent": round((pos / total) * 100, 1) if total > 0 else 0,
        "score_description": steam_data.get("review_score_desc", "")
    }

    # --- Estimated owners & revenue ---
    owners_raw = spy_data.get("owners", "0 .. 0").split(" .. ")
    owner_low  = int(owners_raw[0].replace(",", ""))
    owner_high = int(owners_raw[1].replace(",", ""))

    initial_price = price["initial"]
    current_price = price["current"]
    # Use historical low from ITAD if available (set by enrich_pricing.py)
    hist_low = spy_data.get("_price_history_low")
    if hist_low is not None and initial_price > 0:
        avg_price = (initial_price * 0.35) + (current_price * 0.35) + (hist_low * 0.30)
    elif initial_price > 0:
        avg_price = (initial_price + current_price) / 2
    else:
        avg_price = current_price
    if avg_price == 0:
        avg_price = current_price

    # Steam's tiered revenue share: 30% up to $10M, 25% to $50M, 20% above
    def _steam_dev_share(gross):
        if gross <= 10_000_000:
            return gross * 0.70
        elif gross <= 50_000_000:
            return 10_000_000 * 0.70 + (gross - 10_000_000) * 0.75
        else:
            return 10_000_000 * 0.70 + 40_000_000 * 0.75 + (gross - 50_000_000) * 0.80

    gross_low  = owner_low  * avg_price
    gross_high = owner_high * avg_price
    estimated_revenue = {
        "low":  round(_steam_dev_share(gross_low)),
        "high": round(_steam_dev_share(gross_high))
    }

    # --- Genres, tags, platforms ---
    genres = [g["description"] for g in steam_data.get("genres", [])]
    tags   = list(spy_data.get("tags", {}).keys())
    platforms_raw = steam_data.get("platforms", {})
    platforms = {
        "windows": platforms_raw.get("windows", False),
        "mac":     platforms_raw.get("mac", False),
        "linux":   platforms_raw.get("linux", False)
    }

    # --- Steam feature flags from categories ---
    features = parse_categories(steam_data.get("categories", []))

    # --- Publishing info (needed for launch checklist + AI assistant) ---
    screenshots = steam_data.get("screenshots", [])
    movies      = steam_data.get("movies", [])
    dlc         = steam_data.get("dlc", [])
    metacritic  = steam_data.get("metacritic", {})

    # --- Playtime from SteamSpy (minutes) ---
    playtime = {
        "avg_forever":    spy_data.get("average_forever", 0),
        "avg_2weeks":     spy_data.get("average_2weeks", 0),
        "median_forever": spy_data.get("median_forever", 0),
        "median_2weeks":  spy_data.get("median_2weeks", 0),
    }

    return {
        # Core identity
        "steam_app_id":   steam_data.get("steam_appid"),
        "type":           steam_data.get("type", "game"),
        "title":          steam_data.get("name", ""),
        "description":    steam_data.get("short_description", ""),
        "full_description": steam_data.get("detailed_description", ""),
        "website":        steam_data.get("website", ""),

        # Classification
        "genres":         genres,
        "tags":           tags,
        "is_early_access": "Early Access" in genres,
        "is_free":        steam_data.get("is_free", False),
        "required_age":   steam_data.get("required_age", 0),

        # Team
        "developer":  steam_data.get("developers", []),
        "publisher":  steam_data.get("publishers", []),

        # Release
        "release_date":        steam_data.get("release_date", {}).get("date", ""),
        "coming_soon":         steam_data.get("release_date", {}).get("coming_soon", False),

        # Platforms & languages
        "platforms":           platforms,
        "supported_languages": parse_languages(steam_data.get("supported_languages", "")),

        # Pricing
        "price": price,

        # Reviews
        "review_summary": reviews,
        "metacritic": {
            "score": metacritic.get("score", None),
            "url":   metacritic.get("url", "")
        },
        "score_rank": spy_data.get("score_rank", ""),

        # Players & engagement
        "players": {
            "current":      spy_data.get("ccu", 0),
            "peak_alltime": spy_data.get("peak_ccu", 0)
        },
        "playtime": playtime,

        # Market estimates
        "estimated_owners":  {"low": owner_low,  "high": owner_high},
        "estimated_revenue": estimated_revenue,

        # Steam features (for publishing checklist & AI)
        "features": features,

        # Publishing indicators
        "screenshot_count": len(screenshots),
        "has_trailer":      len(movies) > 0,
        "dlc_count":        len(dlc),

        # Media
        "header_image_url": steam_data.get("header_image", ""),
        "screenshots":      [s.get("path_full", "") for s in screenshots[:5]],
        "store_url":        f"https://store.steampowered.com/app/{steam_data.get('steam_appid')}",

        # Content info
        "content_descriptors": steam_data.get("content_descriptors", {}).get("notes", ""),
    }
