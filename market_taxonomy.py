"""
Hand-curated genre -> subgenre-group -> child-tag taxonomy.

This is the "confirmed" side of the AI brief's confidence framework: a tag
that shows up in here as a genre's child is treated as a real, defined
niche (confirmed_child_tag: true in helpers._annotate_niche_candidates);
anything else is "adjacent_or_unconfirmed" — a tag that correlates with a
market but isn't a verified subgenre of it. It's necessarily incomplete
(hundreds of SteamSpy community tags exist; only the useful/common ones are
curated here), which is exactly why most niche recommendations in a brief
carry the "adjacent, not confirmed" caveat — expanding this tree directly
reduces how often that caveat has to apply.

SUBGENRE_CHILDREN: subgenre -> its narrower child tags (e.g. "Shooter" ->
["First-Person Shooter", "Battle Royale", ...]). Reused across multiple
genres below since a subgenre like "Horror" can appear under more than one
genre grouping.

GENRE_SUBGENRE_GROUPS: top-level genre -> named groups of subgenres, for
building the sidebar's genre -> subgenre -> child-tag nav tree.
"""
SUBGENRE_CHILDREN = {
    "Shooter": [
        "First-Person Shooter",
        "Third-Person Shooter",
        "Top-Down Shooter",
        "Arena Shooter",
        "Looter Shooter",
        "Run and Gun",
        "Battle Royale",
        "Extraction Shooter",
        "Bullet Hell",
    ],
    "Platformer": [
        "Precision Platformer",
        "Puzzle Platformer",
        "Side Scroller",
        "2D Platformer",
        "3D Platformer",
        "Metroidvania",
    ],
    "RPG": [
        "JRPG",
        "Action RPG",
        "Turn-Based RPG",
        "Tactical RPG",
        "Strategy RPG",
        "Western RPG",
        "Dungeon Crawler",
        "Isometric RPG",
        "Party-Based RPG",
        "Deckbuilding RPG",
        "Creature Collector",
        "MMORPG",
    ],
    "Horror": [
        "Survival Horror",
        "Psychological Horror",
        "Lovecraftian",
        "Supernatural",
        "Dark",
    ],
    "Puzzle": [
        "Puzzle Platformer",
        "Hidden Object",
        "Escape Room",
        "Match 3",
        "Word Game",
        "Trivia",
        "Puzzle Strategy",
    ],
    "Simulation": [
        "City Builder",
        "Farming Sim",
        "Life Sim",
        "Management",
        "Tycoon",
        "Colony Sim",
        "Space Sim",
        "Flight Sim",
        "Train Sim",
        "Driving",
        "Cooking",
        "Fishing",
        "Automation",
        "Factory",
        "Hospital",
        "Business",
        "Trucking",
        "Hunting",
    ],
    "Strategy": [
        "Turn-Based Strategy",
        "Real-Time Strategy",
        "Grand Strategy",
        "4X",
        "Tower Defense",
        "Wargame",
        "Auto Battler",
        "Puzzle Strategy",
        "Resource Management",
        "Economic",
        "Political",
    ],
    "Card Game": [
        "Deckbuilding",
        "Deckbuilding RPG",
        "Roguelike Deckbuilder",
        "Collectible Card Game",
    ],
    "Racing": [
        "Arcade Racing",
        "Simulation Racing",
        "Kart Racing",
        "Off-Road",
        "Motocross",
        "Drag Racing",
        "Street Racing",
        "Rally",
        "Cycling",
        "Formula Racing",
    ],
    "Sports": [
        "Soccer",
        "Basketball",
        "Baseball",
        "Golf",
        "Tennis",
        "Wrestling",
        "Football",
        "Hockey",
        "Rugby",
        "Cricket",
        "Volleyball",
        "Skateboarding",
        "Snowboarding",
        "BMX",
        "Cycling",
        "Boxing",
        "Fishing",
        "Hunting",
    ],
    "Cozy": [
        "Farming Sim",
        "Life Sim",
        "Cooking",
        "Fishing",
        "Cute",
        "Relaxing",
        "Wholesome",
        "Family Friendly",
    ],
    "Survival": [
        "Open World Survival Craft",
        "Survival Horror",
        "Base Building",
        "Crafting",
        "Sandbox",
    ],
    "Management": [
        "City Builder",
        "Colony Sim",
        "Tycoon",
        "Resource Management",
        "Automation",
        "Factory",
        "Business",
        "Hospital",
    ],
}


GENRE_SUBGENRE_GROUPS = {
    "Action": {
        "Shooter": SUBGENRE_CHILDREN["Shooter"],
        "Platformer": SUBGENRE_CHILDREN["Platformer"],
        "Combat": ["Fighting", "Hack and Slash", "Beat 'em Up", "Brawler", "Soulslike"],
        "Action Roguelike": ["Roguelike", "Roguelite", "Action Roguelike", "Bullet Hell"],
        "Movement": ["Parkour", "Precision Platformer", "Side Scroller"],
    },
    "Adventure": {
        "Horror": SUBGENRE_CHILDREN["Horror"],
        "Puzzle": ["Point & Click", "Puzzle Platformer", "Escape Room", "Mystery", "Detective"],
        "Narrative": ["Visual Novel", "Interactive Fiction", "Walking Simulator", "Story Rich", "Narrative"],
    },
    "Casual": {
        "Puzzle": SUBGENRE_CHILDREN["Puzzle"],
        "Cozy": SUBGENRE_CHILDREN["Cozy"],
        "Tabletop": ["Board Game", "Card Game", "Trivia"],
        "Light Skill": ["Rhythm", "Typing", "Mini Games"],
    },
    "Indie": {
        "Cozy": SUBGENRE_CHILDREN["Cozy"],
        "Horror": SUBGENRE_CHILDREN["Horror"],
        "Platformer": SUBGENRE_CHILDREN["Platformer"],
        "Roguelike": ["Roguelike", "Roguelite", "Action Roguelike", "Deckbuilding"],
        "Style": ["Pixel Art", "Hand-drawn", "Retro", "Experimental"],
    },
    "RPG": {
        "RPG Format": SUBGENRE_CHILDREN["RPG"],
        "RPG Theme": ["Dark Fantasy", "Fantasy", "Sci-fi", "Anime"],
        "RPG Systems": ["Character Customization", "Loot", "Co-op", "Sandbox"],
    },
    "Simulation": {
        "Builder/Management": SUBGENRE_CHILDREN["Management"],
        "Life/Cozy": ["Farming Sim", "Life Sim", "Cooking", "Fishing"],
        "Vehicle/Profession": ["Space Sim", "Flight Sim", "Train Sim", "Driving", "Trucking"],
        "Systems": ["Automation", "Factory", "Physics", "God Game"],
    },
    "Strategy": {
        "Strategy Format": SUBGENRE_CHILDREN["Strategy"],
        "Card Strategy": SUBGENRE_CHILDREN["Card Game"],
        "Builder Strategy": ["City Builder", "Base Building", "Resource Management", "Economic"],
    },
    "Sports": {
        "Team Sports": ["Soccer", "Basketball", "Baseball", "Football", "Hockey", "Rugby", "Cricket", "Volleyball"],
        "Individual Sports": ["Golf", "Tennis", "Boxing", "Wrestling", "Fishing", "Hunting"],
        "Extreme Sports": ["Skateboarding", "Snowboarding", "BMX", "Cycling", "Surfing"],
    },
    "Racing": {
        "Racing Format": SUBGENRE_CHILDREN["Racing"],
    },
}


def all_taxonomy_tags():
    """Every tag name that appears anywhere in the taxonomy (subgenre keys,
    child tags, and group names) — used as the "known tag" allowlist for
    free-text genre/tag inference (see market_insights.infer_market_context)."""
    tags = set(SUBGENRE_CHILDREN)
    for children in SUBGENRE_CHILDREN.values():
        tags.update(children)
    for groups in GENRE_SUBGENRE_GROUPS.values():
        for parent, children in groups.items():
            tags.add(parent)
            tags.update(children)
    return tags


def children_for_subgenre(subgenre):
    """Child tags for a subgenre, or [] if it's a leaf (no further children defined)."""
    return SUBGENRE_CHILDREN.get(subgenre, [])


def groups_for_genre(genre):
    """Named subgenre groups for a genre, or {} if the genre isn't in the taxonomy."""
    return GENRE_SUBGENRE_GROUPS.get(genre, {})


def genre_for_tag(tag):
    """Best-guess parent genre for a subgenre/child tag, e.g. 'Metroidvania' -> 'Action'.

    Used to scope cross-market sections (smaller_subgenres, opportunities,
    prominence) near a resolved tag when no genre was given alongside it —
    without this, those sections default to scanning every genre, surfacing
    thematically unrelated niches (Rugby, Cricket, ...) next to a brief
    about a specific subgenre. A tag can appear under multiple genres (e.g.
    Metroidvania sits under both Action and Indie); the first match is used
    as a reasonable single scope, not a claim of exclusive ownership.
    """
    if not tag:
        return None
    for genre, groups in GENRE_SUBGENRE_GROUPS.items():
        if tag in groups:
            return genre
        for children in groups.values():
            if tag in children:
                return genre
    return None
