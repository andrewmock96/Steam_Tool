"""
"Virtual tags": subgenre tags that don't exist as a clean SteamSpy
community tag, or whose plain tag doesn't reliably mean what the label
implies — so they're computed from a rule (title patterns, genre,
include/exclude tag combinations) instead of a simple `tags` field match.

Example problems this solves:
  - "First-Person Shooter" isn't itself a common SteamSpy tag; games are
    tagged "Shooter" + "First-Person" separately, so a plain tag query for
    "First-Person Shooter" would return almost nothing.
  - "Cycling" as a raw tag catches management sims, delivery games, and
    unrelated titles that happen to share the tag — the rule instead
    matches by title patterns (real cycling game names) and excludes
    obvious false positives (tycoon/manager games, motorsport titles).

Every consumer that needs to match games against a tag should check
is_virtual_tag() first: if true, use build_virtual_tag_query() to fetch a
candidate set from Mongo, then filter it in Python with
game_matches_virtual_tag() (the match logic here — regex title patterns,
tag exclusions — can't be expressed as a single Mongo query). If false,
it's just a normal tag and build_tag_matcher()/a plain `tags` filter works.
"""
import re


# Plain-tag synonyms — a search for "First-Person Shooter" should also match
# games only tagged "Shooter" once combined with other signals; see
# build_tag_matcher, which is for REAL tags (not virtual ones — virtual tags
# use VIRTUAL_TAG_RULES's include_any_tags instead).
TAG_ALIASES = {
    "First-Person Shooter": ["Shooter"],
    "Bikes": ["Cycling"],
}


# Rule shape (all keys optional except "genre"):
#   genre                    default genre to scope the query to
#   include_any_tags         game matches if it has ANY of these tags
#   include_title_patterns   game matches if title matches ANY of these regexes
#   exclude_tags              game is excluded if it has ALL of these tags
#   exclude_any_tags          game is excluded if it has ANY of these tags
#   exclude_title_patterns    game is excluded if title matches ANY of these regexes
# See game_matches_virtual_tag() for how these combine per-tag (some tags,
# like Motorsport, have extra bespoke logic beyond the generic rule fields).
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
    """True if this tag needs the virtual-tag rule/filter path instead of a plain Mongo tag query."""
    return tag in VIRTUAL_TAG_RULES


def build_tag_matcher(tag):
    """Case-insensitive exact-match $in query for a real tag, including any TAG_ALIASES."""
    tags = [tag] + TAG_ALIASES.get(tag, [])
    return {"$in": [re.compile(f"^{re.escape(value)}$", re.IGNORECASE) for value in tags]}


def _compile_patterns(patterns):
    """Combine a list of regex fragments into one case-insensitive alternation pattern."""
    if not patterns:
        return None
    return re.compile("|".join(patterns), re.IGNORECASE)


def _lower_set(values):
    return {str(value).strip().lower() for value in (values or []) if value}


def _title_matches(title, patterns):
    return bool(_compile_patterns(patterns).search(title or "")) if patterns else False


def game_matches_virtual_tag(game, tag):
    """Python-side (not Mongo-query-side) check for whether a game document
    actually satisfies a virtual tag's rule. Called after
    build_virtual_tag_query() has already narrowed the candidate set from
    Mongo — this does the part of the matching that can't be expressed as a
    query (regex title matching, tag-combination logic)."""
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
    """Best-effort Mongo query to narrow candidates for a virtual tag before
    the precise Python-side filter (game_matches_virtual_tag) runs. This is
    intentionally a superset — it can't perfectly express the rule (e.g.
    include_title_patterns regex can be pushed into the query, but the
    per-tag bespoke logic in game_matches_virtual_tag can't), so results
    still need the Python filter applied afterward. Returns None for a
    non-virtual tag, signaling callers to use the normal tag-query path."""
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
