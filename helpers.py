"""Shared helpers used by more than one blueprint."""
import re

from market_insights import (
    infer_market_context,
    market_opportunities,
    smaller_subgenre_report,
    summarize_market,
    top_competitors,
)
from market_taxonomy import all_taxonomy_tags, groups_for_genre

# External AI tools the brief can hand off to (see get_ai_handoff_tool()
# and the "brief-loader" flow in blueprints/insights.py / brief_loader.html).
AI_HANDOFF_TOOLS = {
    "chatgpt": {"label": "ChatGPT", "url": "https://chatgpt.com/"},
    "claude": {"label": "Claude", "url": "https://claude.ai/"},
    "gemini": {"label": "Gemini", "url": "https://gemini.google.com/"},
    "perplexity": {"label": "Perplexity", "url": "https://www.perplexity.ai/"},
    "copilot": {"label": "Microsoft Copilot", "url": "https://copilot.microsoft.com/"},
    "grok": {"label": "Grok", "url": "https://grok.com/"},
    "poe": {"label": "Poe", "url": "https://poe.com/"},
    "phind": {"label": "Phind", "url": "https://phindai.org/phind-chat/"},
    "lechat": {"label": "Mistral Le Chat", "url": "https://chat.mistral.ai/chat"},
    "you": {"label": "You.com", "url": "https://you.com/?chatMode=default"},
    "deepseek": {"label": "DeepSeek", "url": "https://chat.deepseek.com/"},
}
DEFAULT_AI_TOOL = "claude"

# Each mode's "instruction" line gets inserted into the AI prompt (see
# build_chatgpt_prompt in blueprints/insights.py) to steer response length
# and focus. The frontend also auto-detects one of these from keywords in
# the user's question — see MODE_KEYWORDS in static/app.js.
BRIEF_MODES = {
    "general": {
        "label": "Market Deep Dive",
        "instruction": "Give a rounded market read: demand, competition, pricing, risk, and opportunity for a small indie team.",
    },
    "quick": {
        "label": "Quick Answer",
        "instruction": "Answer directly and briefly. Prioritize the user's question and the 3-5 most decision-useful data points.",
    },
    "competition": {
        "label": "Competitor Analysis",
        "instruction": "Focus on competitor shape, benchmark titles, market crowding, and where a new game could differentiate.",
    },
    "pricing": {
        "label": "Pricing and Launch",
        "instruction": "Focus on pricing, review-score expectations, wishlist/readiness signals, and launch-positioning implications.",
    },
}

# Sports and Racing share several tags (Cycling, Motocross, ...), so without
# this a game tagged both ways would double-count in each genre's totals.
GENRE_EXCLUSIONS = {
    "Sports": ["Racing"],
    "Racing": ["Sports"],
}

# Curated per-genre subgenre tag lists shown in the sidebar/filter UI. This
# is hand-picked (not "every tag that exists"), to keep the subgenre nav
# focused on tags that are actually useful for browsing rather than every
# SteamSpy community tag. See market_taxonomy.py for the deeper
# genre -> subgenre-group -> child-tag tree used by the AI brief system.
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
        "Open World", "Motorsport", "Motocross", "Cycling"
    ]
}


# Known-tag allowlist used to keep free-text genre/tag inference (see
# market_insights.infer_market_context) from matching on random SteamSpy
# community tags — only tags we've curated into STEAM_SUBGENRES or the
# market_taxonomy tree are eligible matches.
def _curated_subgenre_tags(genre=None):
    if genre:
        return set(STEAM_SUBGENRES.get(genre, [])) | set(groups_for_genre(genre).keys())
    tags = set()
    for values in STEAM_SUBGENRES.values():
        tags.update(values)
    tags.update(all_taxonomy_tags())
    return tags


# Return a supported AI handoff destination.
def get_ai_handoff_tool(tool_id=None):
    key = (tool_id or DEFAULT_AI_TOOL).lower()
    if key not in AI_HANDOFF_TOOLS:
        key = DEFAULT_AI_TOOL
    return {"id": key, **AI_HANDOFF_TOOLS[key]}


# Look up a brief mode by id, falling back to "general" for anything unrecognized.
def get_brief_mode(mode_id=None):
    key = (mode_id or "general").lower()
    if key not in BRIEF_MODES:
        key = "general"
    return {"id": key, **BRIEF_MODES[key]}


# Generate the suggested-question chips shown after a market/concept result
# loads. Built from templates rather than an LLM call, since this app has
# no paid AI API — see blueprints/insights.py's module docstring.
def build_follow_up_prompts(question="", genre=None, tag=None, summary=None, include_concept=False):
    market_name = tag or genre or (summary or {}).get("market") or "this market"
    market_label = f"{market_name} on Steam"
    prompts = [
        f"What makes {market_label} attractive for a small indie team?",
        f"What risks stand out in the {market_name} market right now?",
        f"Which competitors should I study before entering {market_name}?",
        f"What price range looks most credible in {market_name}?",
        f"What tags overlap most with the audience for {market_name}?",
    ]
    if tag:
        prompts.extend([
            f"Should I position this as {tag} first or lead with the broader {genre or 'genre'}?",
            f"What sub-subgenres inside {tag} look least crowded?",
        ])
    if genre and not tag:
        prompts.extend([
            f"Which subgenres inside {genre} feel most indie-friendly?",
            f"What kind of game concept has the best chance in {genre} right now?",
        ])
    if include_concept:
        prompts.extend([
            "Which audience would most likely buy this concept on Steam?",
            "What tags should this concept probably lead with on Steam?",
        ])
    if question:
        prompts.append(f"Based on this question, what should I ask next: {question}")

    deduped = []
    seen = set()
    for prompt in prompts:
        if prompt not in seen:
            seen.add(prompt)
            deduped.append(prompt)
    return deduped[:8]


# Take a free-text game description (the "Describe Your Game Concept" box)
# and infer a likely genre/tag market for it, then return the same shape of
# market data a resolved genre/tag brief would get.
def analyze_concept(games_col, description):
    text = (description or "").strip()
    inferred = infer_market_context(
        games_col,
        text,
        known_tags=_curated_subgenre_tags() | all_taxonomy_tags(),
    )
    genre = inferred.get("genre")
    tag = inferred.get("tag")
    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    smaller = smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=6,
        curated_tags=_curated_subgenre_tags(genre),
    )
    opportunities = market_opportunities(games_col, genre=genre, limit=5)
    competitors = top_competitors(games_col, genre=genre, tag=tag, limit=5) if (genre or tag) else []
    return {
        "description": text,
        "inferred_context": inferred,
        "likely_market": summary,
        "opportunities": opportunities,
        "smaller_subgenres": smaller,
        "top_competitors": competitors,
        "follow_up_prompts": build_follow_up_prompts(
            question=text,
            genre=genre,
            tag=tag,
            summary=summary,
            include_concept=True,
        ),
    }


# Summarize two markets side by side (the 'Compare Markets' feature) and
# compute the percent deltas between them. The two summarize_market() calls
# are independent and each does its own DB work, so they run in parallel
# threads rather than sequentially.
def build_compare_data(games_col, left_genre=None, left_tag=None, right_genre=None, right_tag=None):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as ex:
        fl = ex.submit(summarize_market, games_col, left_genre, left_tag)
        fr = ex.submit(summarize_market, games_col, right_genre, right_tag)
        left, right = fl.result(), fr.result()
    if not left or not right:
        return None

    # Percent difference of `a` relative to `b`, or None if either side is missing/zero.
    def pct_diff(a, b):
        if not a or not b:
            return None
        return round(((a - b) / b) * 100, 1)

    return {
        "left": left,
        "right": right,
        "delta": {
            "estimated_revenue_high_pct": pct_diff(left.get("estimated_revenue_high"), right.get("estimated_revenue_high")),
            "avg_review_score_pct": round(left.get("avg_review_score_pct", 0) - right.get("avg_review_score_pct", 0), 1),
            "total_games_pct": pct_diff(left.get("total_games"), right.get("total_games")),
            "som_high_pct": pct_diff(left.get("SOM", {}).get("high"), right.get("SOM", {}).get("high")),
        },
        "follow_up_prompts": [
            f"Which of these two markets looks better for a small indie team: {left['market']} or {right['market']}?",
            f"What is the biggest risk difference between {left['market']} and {right['market']}?",
            f"Which market gives a better pricing and launch setup: {left['market']} or {right['market']}?",
        ],
    }


# Collapse whitespace so downstream keyword checks aren't tripped up by
# extra spaces/newlines a user pasted in.
def _normalize_question(text):
    return " ".join((text or "").strip().split())


# True if the question both mentions a year (e.g. "2024") and phrases like
# "how many games released in" — this dataset has no release-year
# distribution to answer that with, so it's flagged as unsupported rather
# than letting the AI guess a count from a handful of example games.
def _question_mentions_release_year_count(question):
    text = (question or "").lower()
    has_year = bool(re.search(r"\b(19|20)\d{2}\b", text))
    year_count_phrases = (
        "how many games",
        "how many were published",
        "how many were released",
        "games published in",
        "games released in",
        "released in ",
        "published in ",
        "launches in ",
        "launched in ",
    )
    return has_year and any(phrase in text for phrase in year_count_phrases)


# Decide upfront whether the brief payload actually supports answering the
# user's question, and say so explicitly in the payload itself
# (can_answer_directly, missing_requirements, limitations) — this is what
# the prompt instructions in build_chatgpt_prompt() point the AI at, so it
# says "I can't answer this from the data" instead of guessing a number
# when e.g. no genre/tag resolved from the question text.
def _build_question_answerability(question="", inferred=None, summary=None, momentum=None, competitors=None):
    normalized_question = _normalize_question(question)
    inferred = inferred or {}
    summary = summary or {}
    competitors = competitors or []
    resolved_market = bool(inferred.get("genre") or inferred.get("tag"))

    result = {
        "question": normalized_question,
        "resolved_market": {
            "genre": inferred.get("genre"),
            "tag": inferred.get("tag"),
            "is_resolved": resolved_market,
        },
        "can_answer_directly": True,
        "confidence": "medium",
        "primary_evidence": [],
        "missing_requirements": [],
        "limitations": [],
        "recommended_response_mode": "full_market_analysis",
    }

    if normalized_question:
        result["primary_evidence"] = [
            "market_summary",
            "brief_diagnostics",
            "smaller_subgenres",
            "opportunities",
            "top_competitors",
        ]

    if not resolved_market and normalized_question:
        result["limitations"].append(
            "No specific genre or tag was resolved from the question, so broad-market conclusions may be unavailable."
        )
        result["confidence"] = "low"

    if normalized_question and not summary:
        result["can_answer_directly"] = False
        result["recommended_response_mode"] = "explain_missing_market_data"
        result["missing_requirements"].append("A resolved genre or tag with populated market_summary data.")

    if _question_mentions_release_year_count(normalized_question):
        result["can_answer_directly"] = False
        result["confidence"] = "high"
        result["recommended_response_mode"] = "explain_unsupported_dimension"
        result["primary_evidence"] = ["data_available", "top_competitors"]
        result["missing_requirements"] = [
            "A full game-level release-date dataset or a precomputed release-year distribution for the market."
        ]
        result["limitations"].append(
            "This payload does not include a market-wide release-year breakdown or a full list of matching games with release dates."
        )
        result["limitations"].append(
            "Do not infer yearly publication counts from top_competitors or a handful of example games."
        )

    if momentum and (momentum.get("confidence") or "").lower() == "low":
        result["limitations"].append(
            "Momentum exists but is low-confidence, so it should not be treated as strong evidence of growth or decline."
        )

    if competitors and len(competitors) < 3:
        result["limitations"].append(
            "Top competitor coverage is thin in this payload, so competitor examples may be incomplete."
        )

    if not result["limitations"]:
        result["limitations"].append(
            "Use aggregate market metrics as the main evidence and treat competitor examples as supporting context."
        )

    return result


# Sample-size-based confidence label for a niche row — thin samples (Rugby,
# Volleyball, ...) get flagged "low" so the AI prompt knows to suppress
# their revenue-per-game figures rather than treat a couple of breakout
# hits as a representative average.
def _niche_reliability_label(item):
    total_games = (item or {}).get("total_games") or 0
    paid_games = (item or {}).get("paid_games") or 0
    if total_games < 40 or paid_games < 30:
        return "low"
    if total_games < 120 or paid_games < 80:
        return "medium"
    return "higher"


# yes/caution/no verdict for a niche — only a confirmed child tag with
# non-low reliability clears the bar for "yes"; everything else is at best
# a validated hypothesis, not a direct recommendation.
def _recommendation_flag(reliability, confirmed_child_tag):
    if reliability == "low":
        return "caution"
    if confirmed_child_tag:
        return "yes"
    if reliability == "higher":
        return "caution"
    return "caution"


# Attach the reliability/confidence framework (data_reliability,
# confirmed_child_tag, market_relationship, use_for_recommendation,
# reliability_note, revenue_metric_guidance) to a list of niche/market
# rows, so the AI prompt has a consistent way to judge every niche list in
# the payload (smaller_subgenres, opportunities, and — since these
# otherwise lacked it — doing_well/less_prominent) rather than treating
# some as more trustworthy just because they happen to carry metadata.
def _annotate_niche_candidates(items, confirmed_children=None):
    confirmed = set(confirmed_children or [])
    annotated = []
    for item in items or []:
        row = dict(item)
        reliability = _niche_reliability_label(row)
        confirmed_child_tag = row.get("market") in confirmed if row.get("market") else False
        recommendation_flag = _recommendation_flag(reliability, confirmed_child_tag)
        row["data_reliability"] = reliability
        row["confirmed_child_tag"] = confirmed_child_tag
        row["market_relationship"] = "confirmed_child" if confirmed_child_tag else "adjacent_or_unconfirmed"
        row["use_for_recommendation"] = recommendation_flag
        row["raw_revenue_per_game_estimate"] = row.get("revenue_per_game_estimate")
        if reliability == "low":
            row["reliability_note"] = (
                "Small sample. Revenue-per-game and opportunity signals may be skewed by one or two breakout hits."
            )
            row["revenue_per_game_estimate"] = None
            row["revenue_metric_guidance"] = (
                "Suppressed for recommendation use because this niche is low reliability. "
                "Use broad-market outlier-adjusted benchmarks and direct competitor checks instead."
            )
        elif reliability == "medium":
            row["reliability_note"] = (
                "Moderate sample. Treat niche upside as directional and validate against direct competitors."
            )
            row["revenue_metric_guidance"] = (
                "Directional only. Validate against direct competitors before using this as a planning anchor."
            )
        else:
            row["reliability_note"] = (
                "Larger sample than most niche tags here, but still directional rather than guaranteed."
            )
            row["revenue_metric_guidance"] = (
                "More decision-useful than tiny-sample niches, but still not a guaranteed outcome."
            )
        if confirmed_child_tag:
            row["recommendation_note"] = (
                "Confirmed child tag in the current taxonomy context. Safer to discuss as an FPS-specific niche."
            )
        elif reliability == "higher":
            row["recommendation_note"] = (
                "Adjacent opportunity with a stronger sample, but not confirmed as a child tag in the current taxonomy."
            )
        else:
            row["recommendation_note"] = (
                "Use as a hypothesis to validate, not as a final recommendation."
            )
        annotated.append(row)
    return annotated


# Build the brief_diagnostics section: decision rules, red flags, and the
# annotated niche_validation tables the AI prompt is told to lean on. This
# is where per-payload red flags get raised (thin taxonomy support,
# low-confidence momentum, suspicious SOM legacy-capture figures) so the
# prompt instructions in blueprints/insights.py can point the AI at them
# instead of the AI having to infer data quality on its own.
def _build_brief_diagnostics(summary=None, momentum=None, smaller=None, opportunities=None, taxonomy=None, prominence=None):
    diagnostics = {
        "decision_rules": [
            "Prefer outlier-adjusted per-game benchmarks over raw TAM/SAM when judging indie feasibility.",
            "Treat broad-market size as context, not proof that a small team can win there.",
            "Use top competitors as examples, not the main evidence base.",
            "Downweight any niche with low data_reliability or missing taxonomy support.",
        ],
        "red_flags": [],
        "niche_reliability_guide": {
            "higher": "Larger niche sample; still directional, but more decision-useful than tiny-sample niches.",
            "medium": "Usable for exploration, but validate with direct competitor reads.",
            "low": "Thin-sample niche; do not treat large revenue-per-game numbers as realistic targets.",
        },
    }

    if summary:
        sample_notes = summary.get("sample_notes") or {}
        diagnostics["benchmark_preference"] = {
            "prefer": "realistic_revenue_target and performance_benchmarks.per_game_revenue_estimate",
            "avoid_overweighting": "TAM, SAM, and raw niche revenue-per-game values when making indie go/no-go calls",
            "reason": sample_notes.get("outlier_handling"),
        }
        legacy_low = ((summary.get("SOM") or {}).get("legacy_percent_capture_low")) or 0
        som_high = ((summary.get("SOM") or {}).get("high")) or 0
        if legacy_low and som_high and legacy_low > som_high * 50:
            diagnostics["red_flags"].append(
                "Ignore SOM legacy_percent_capture fields for decision-making; they can dwarf the outlier-adjusted SOM range."
            )

    if momentum:
        if (momentum.get("confidence") or "").lower() == "low":
            diagnostics["red_flags"].append(
                "Momentum is low-confidence. Do not use it as evidence of market growth or decline."
            )
        if momentum.get("sample_coverage_pct") is not None:
            diagnostics["momentum_reading_rule"] = {
                "sample_coverage_pct": momentum.get("sample_coverage_pct"),
                "confidence": momentum.get("confidence"),
                "instruction": "Only use momentum directionally when confidence is not low and coverage is reasonably broad.",
            }

    taxonomy_context = taxonomy or {}
    has_child_report = bool((taxonomy_context.get("child_report") or {}).get("children_found"))
    has_child_tags = bool(taxonomy_context.get("children_for_detected_tag"))
    confirmed_children = set(taxonomy_context.get("children_for_detected_tag") or [])
    confirmed_children.update(
        row.get("market")
        for row in ((taxonomy_context.get("child_report") or {}).get("children_found") or [])
        if row.get("market")
    )
    if not has_child_report and not has_child_tags:
        diagnostics["red_flags"].append(
            "Taxonomy support is thin for this market. Some niche recommendations may be adjacent tags rather than confirmed child tags."
        )

    # doing_well/less_prominent otherwise carry none of the reliability
    # framework (data_reliability, confirmed_child_tag, use_for_recommendation)
    # that smaller_subgenres/opportunities get below — which can push an AI
    # reading this payload to ignore the most on-topic data (e.g. the actual
    # less_prominent list for a "what's underserved" question) in favor of
    # unrelated niches purely because those are the only ones annotated.
    if prominence:
        prominence["doing_well"] = _annotate_niche_candidates(
            prominence.get("doing_well"), confirmed_children=confirmed_children
        )
        prominence["less_prominent"] = _annotate_niche_candidates(
            prominence.get("less_prominent"), confirmed_children=confirmed_children
        )

    diagnostics["recommendation_flag_guide"] = {
        "yes": "Reasonable to recommend directly, assuming the rest of the evidence is supportive.",
        "caution": "Interesting, but validate with direct competitors and treat upside as directional.",
        "no": "Do not recommend directly from this dataset alone.",
    }
    diagnostics["niche_validation"] = {
        "strongest_small_subgenres": _annotate_niche_candidates(
            (smaller or {}).get("strongest_small_subgenres"),
            confirmed_children=confirmed_children,
        ),
        "less_prominent_small_subgenres": _annotate_niche_candidates(
            (smaller or {}).get("less_prominent_small_subgenres"),
            confirmed_children=confirmed_children,
        ),
        "opportunities": _annotate_niche_candidates(
            opportunities,
            confirmed_children=confirmed_children,
        ),
    }
    diagnostics["niche_reading_rule"] = (
        "Prefer niches that have both stronger data_reliability and a clear qualitative signal. "
        "If a niche has low reliability, present it as a hypothesis to validate, not as a recommendation with firm upside."
    )
    return diagnostics
