import re


TAG_ALIASES = {
    "First-Person Shooter": ["Shooter"],
    "Bikes": ["Cycling"],
}


VIRTUAL_TAG_RULES = {
    "First-Person Shooter": {
        "genre": "Action",
        "include_any_tags": ["Shooter", "FPS", "First-Person", "First-Person Shooter"],
        "exclude_title_patterns": [],
    },
    "Third-Person Shooter": {
        "genre": "Action",
        "include_any_tags": ["Shooter", "Third Person", "Third-Person Shooter"],
        "exclude_title_patterns": [],
    },
    "Top-Down Shooter": {
        "genre": "Action",
        "include_any_tags": ["Shooter", "Top-Down", "Top-Down Shooter"],
        "exclude_title_patterns": [],
    },
    "Motorsport": {
        "genre": "Racing",
        "include_any_tags": ["Automobile Sim", "Realistic", "Motorbike"],
        "include_title_patterns": [
            r"\bmotogp(?:\s*\d+)?\b",
            r"^ride(?:\s+\d+)?\b",
            r"\btt isle of man\b",
            r"\btrials\b",
        ],
        "exclude_tags": ["Open World", "Motocross", "Bikes", "Cycling"],
        "exclude_any_tags": ["Management", "Building", "Flight", "BMX"],
        "exclude_title_patterns": [
            r"\bmanager\b",
            r"\btycoon\b",
            r"\bdrone\b",
            r"\btruck\b",
            r"\brider\b",
        ],
    },
    "Cycling": {
        "genre": "Racing",
        "include_any_tags": ["Cycling", "BMX"],
        "include_title_patterns": [
            r"\bdescenders\b",
            r"\bdownhill\b",
            r"\btour de france\b",
            r"\bcycling manager\b",
            r"\blive cycling manager\b",
            r"\bbikeout\b",
            r"\bbike of the wild\b",
            r"\bmagnytour\b",
            r"\bpedalverse\b",
            r"\bwattgames\b",
            r"\bbmx\b",
            r"\bgravel\b",
            r"\bbicycle\b",
            r"\bking of dirt\b",
            r"\bbananitro\b",
        ],
        "exclude_tags": ["Motocross"],
        "exclude_any_tags": ["Motorbike"],
        "exclude_title_patterns": [
            r"\bmotogp\b",
            r"^ride(?:\s+\d+)?\b",
            r"\bisle of man\b",
            r"\bmotorcycle\b",
            r"\bmoto racer\b",
            r"\btrials\b",
            r"\bkart\b",
            r"\bdrift\b",
            r"\boutrun\b",
            r"\bscooter\b",
            r"\bdelivery\b",
            r"\bstorm chase\b",
            r"\bhighway\b",
            r"\bsynthwave\b",
            r"\bsports collection\b",
            r"\bsummer games\b",
            r"\btennis manager\b",
            r"\bpuzzle\b",
            r"\bparcel corps\b",
            r"\btraction control\b",
            r"\bsol cycling\b",
        ],
    },
}


VIRTUAL_TAG_RULES["Bikes"] = VIRTUAL_TAG_RULES["Cycling"]


def is_virtual_tag(tag):
    return tag in VIRTUAL_TAG_RULES


def build_tag_matcher(tag):
    tags = [tag] + TAG_ALIASES.get(tag, [])
    return {"$in": [re.compile(f"^{re.escape(value)}$", re.IGNORECASE) for value in tags]}


def _compile_patterns(patterns):
    if not patterns:
        return None
    return re.compile("|".join(patterns), re.IGNORECASE)


def _lower_set(values):
    return {str(value).strip().lower() for value in (values or []) if value}


def _title_matches(title, patterns):
    return bool(_compile_patterns(patterns).search(title or "")) if patterns else False


def game_matches_virtual_tag(game, tag):
    rule = VIRTUAL_TAG_RULES.get(tag)
    if not rule:
        return False

    title = game.get("title", "") or ""
    tags = _lower_set(game.get("tags"))
    genres = _lower_set(game.get("genres"))

    if any(excluded.lower() in tags for excluded in rule.get("exclude_tags", [])):
        return False
    if any(excluded.lower() in tags for excluded in rule.get("exclude_any_tags", [])):
        return False
    if _title_matches(title, rule.get("exclude_title_patterns")):
        return False

    if tag in {"Cycling", "Bikes"}:
        return _title_matches(title, rule.get("include_title_patterns"))

    if tag == "First-Person Shooter":
        return (
            "shooter" in tags
            and ("first-person" in tags or "fps" in tags or "first-person shooter" in tags)
        )

    if tag == "Third-Person Shooter":
        return (
            "shooter" in tags
            and ("third person" in tags or "third-person shooter" in tags)
        )

    if tag == "Top-Down Shooter":
        return (
            "shooter" in tags
            and ("top-down" in tags or "top-down shooter" in tags)
        )

    if tag == "Motorsport":
        if _title_matches(title, rule.get("include_title_patterns")):
            return True
        if "automobile sim" not in tags:
            return False
        if {"combat racing", "vehicular combat", "destruction"} & tags:
            return False
        return bool({"simulation", "sports"} & genres or {"simulation", "sports", "driving"} & tags)

    return (
        bool(tags & _lower_set(rule.get("include_any_tags")))
        or _title_matches(title, rule.get("include_title_patterns"))
    )


def build_virtual_tag_query(tag, genre=None):
    rule = VIRTUAL_TAG_RULES.get(tag)
    if not rule:
        return None

    query = {"delisted": {"$ne": True}, "genres": rule["genre"]}
    if genre:
        query["genres"] = genre

    include_parts = []
    if rule.get("include_any_tags"):
        include_parts.append({
            "tags": {
                "$in": [re.compile(f"^{re.escape(value)}$", re.IGNORECASE) for value in rule["include_any_tags"]]
            }
        })
    title_include = _compile_patterns(rule.get("include_title_patterns"))
    if title_include:
        include_parts.append({"title": {"$regex": title_include}})
    if include_parts:
        query["$or"] = include_parts

    exclude_parts = []
    if rule.get("exclude_tags"):
        exclude_parts.append({
            "tags": {
                "$nin": [re.compile(f"^{re.escape(value)}$", re.IGNORECASE) for value in rule["exclude_tags"]]
            }
        })
    if rule.get("exclude_any_tags"):
        exclude_parts.append({
            "tags": {
                "$nin": [re.compile(f"^{re.escape(value)}$", re.IGNORECASE) for value in rule["exclude_any_tags"]]
            }
        })
    if exclude_parts:
        query["$and"] = exclude_parts

    title_exclude = _compile_patterns(rule.get("exclude_title_patterns"))
    if title_exclude:
        query["title"] = {"$not": title_exclude}

    return query
