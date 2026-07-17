import json

from flask import Blueprint, jsonify, render_template, request

from db import db, games_col
from helpers import (
    AI_HANDOFF_TOOLS,
    BRIEF_MODES,
    DEFAULT_AI_TOOL,
    _build_brief_diagnostics,
    _build_question_answerability,
    _curated_subgenre_tags,
    analyze_concept,
    build_compare_data,
    build_follow_up_prompts,
    get_ai_handoff_tool,
    get_brief_mode,
)
from market_insights import (
    DATA_POINT_CATALOG,
    SOURCE_CONFIDENCE,
    child_subgenre_report,
    infer_market_context,
    market_momentum,
    market_opportunities,
    prominence_report,
    rank_genre_markets,
    rank_tag_markets,
    smaller_subgenre_report,
    summarize_market,
    top_competitors,
)
from market_taxonomy import (
    GENRE_SUBGENRE_GROUPS,
    SUBGENRE_CHILDREN,
    all_taxonomy_tags,
    children_for_subgenre,
    groups_for_genre,
)

insights_bp = Blueprint("insights", __name__)


@insights_bp.route("/api/insights/data-points")
def get_data_points():
    """Structured catalog of facts and derived metrics the product can expose."""
    return jsonify({
        "data_points": DATA_POINT_CATALOG,
        "disclaimer": "Revenue, owner, and market sizing figures are estimates based on SteamSpy and public Steam data."
    })


@insights_bp.route("/api/ai-tools")
def get_ai_tools():
    """Supported external AI tools for no-cost prompt handoff."""
    return jsonify({
        "default": DEFAULT_AI_TOOL,
        "tools": [
            {"id": tool_id, "label": meta["label"]}
            for tool_id, meta in AI_HANDOFF_TOOLS.items()
        ],
    })


@insights_bp.route("/api/brief-modes")
def get_brief_modes():
    return jsonify({
        "default": "general",
        "modes": [
            {"id": mode_id, "label": meta["label"]}
            for mode_id, meta in BRIEF_MODES.items()
        ],
    })


@insights_bp.route("/api/insights/accuracy")
def get_accuracy_model():
    """Explain source confidence and estimate methodology."""
    return jsonify({
        "source_confidence": SOURCE_CONFIDENCE,
        "estimate_methodology": {
            "market_size": "Summed SteamSpy owner/revenue ranges across matching games.",
            "realistic_indie_target": "Paid-game revenue percentiles from comparable games, with the top 1% trimmed when sample size allows.",
            "confidence_score": "Based on comparable sample size, paid sample size, and top-10 revenue concentration.",
            "outlier_policy": "Top hits remain in total market size, but are trimmed from per-game target benchmarks.",
        },
        "recommended_language": "Say 'estimated' for owners, revenue, TAM, SAM, and SOM. Steam does not publish official sales for all games.",
    })


@insights_bp.route("/api/insights/market")
def get_market_insight():
    """Tool-ready market summary for a genre and/or tag."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None

    if not genre and not tag:
        return jsonify({"error": "Provide genre or tag"}), 400

    summary = summarize_market(games_col, genre=genre, tag=tag)
    if not summary:
        return jsonify({"error": "No games found for this market"}), 404

    limit = min(25, max(1, request.args.get("limit", default=10, type=int)))
    return jsonify({
        "summary": summary,
        "top_competitors": top_competitors(games_col, genre=genre, tag=tag, limit=limit),
    })


@insights_bp.route("/api/insights/momentum")
def get_market_momentum():
    """Player-snapshot momentum for a genre or tag."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    days = min(365, max(2, request.args.get("days", default=30, type=int)))

    if not genre and not tag:
        return jsonify({"error": "Provide genre or tag"}), 400

    return jsonify(market_momentum(games_col, db, genre=genre, tag=tag, days=days))


@insights_bp.route("/api/insights/markets")
def get_ranked_markets():
    """Rank genres or tags by estimated market size."""
    market_type = request.args.get("type", "genres")
    genre = request.args.get("genre") or None
    limit = min(100, max(1, request.args.get("limit", default=25, type=int)))

    if market_type == "tags":
        markets = rank_tag_markets(games_col, genre=genre, limit=limit)
    else:
        markets = sorted(
            rank_genre_markets(games_col),
            key=lambda m: m.get("estimated_revenue_high", 0),
            reverse=True,
        )[:limit]

    return jsonify({
        "type": market_type,
        "genre": genre,
        "markets": markets,
        "disclaimer": "Revenue figures are SteamSpy estimates, not official Steam data."
    })


@insights_bp.route("/api/insights/opportunities")
def get_opportunities():
    """Rank markets with strong demand signals and comparatively addressable competition."""
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=12, type=int)))
    return jsonify({
        "genre": genre,
        "opportunities": market_opportunities(games_col, genre=genre, limit=limit),
        "disclaimer": "Opportunity score is directional and should be validated against direct competitors."
    })


@insights_bp.route("/api/insights/smaller-subgenres")
def get_smaller_subgenres():
    """Find smaller, more niche subgenres while filtering broad umbrella tags."""
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=15, type=int)))
    min_games = min(500, max(5, request.args.get("min_games", default=25, type=int)))
    max_games = min(5000, max(min_games, request.args.get("max_games", default=750, type=int)))
    raw_tags = request.args.get("raw_tags", "").lower() in {"1", "true", "yes"}
    return jsonify(smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=limit,
        min_games=min_games,
        max_games=max_games,
        curated_tags=None if raw_tags else _curated_subgenre_tags(genre),
    ))


@insights_bp.route("/api/taxonomy")
def get_taxonomy():
    """Return the curated genre -> subgenre -> child tag taxonomy."""
    genre = request.args.get("genre") or None
    if genre:
        return jsonify({
            "genre": genre,
            "groups": groups_for_genre(genre),
            "note": "Not every subgenre needs child tags; only broad categories are expanded.",
        })
    return jsonify({
        "groups_by_genre": GENRE_SUBGENRE_GROUPS,
        "children_by_subgenre": SUBGENRE_CHILDREN,
        "note": "Not every subgenre needs child tags; only broad categories are expanded.",
    })


@insights_bp.route("/api/insights/subgenre-children")
def get_subgenre_children():
    """Compare child tags for a broad subgenre such as Shooter or RPG."""
    parent = request.args.get("subgenre") or request.args.get("parent")
    genre = request.args.get("genre") or None
    limit = min(50, max(1, request.args.get("limit", default=20, type=int)))

    if not parent:
        return jsonify({"error": "Provide subgenre or parent"}), 400

    children = children_for_subgenre(parent)
    if not children:
        return jsonify({
            "parent_subgenre": parent,
            "children_found": [],
            "message": "No child taxonomy is defined for this subgenre yet.",
        })

    return jsonify(child_subgenre_report(
        games_col,
        parent,
        children,
        genre=genre,
        limit=limit,
    ))


@insights_bp.route("/api/insights/prominence")
def get_prominence():
    """Show markets doing well and markets that are currently less prominent."""
    genre = request.args.get("genre") or None
    limit = min(25, max(1, request.args.get("limit", default=10, type=int)))
    return jsonify(prominence_report(games_col, genre=genre, limit=limit))


@insights_bp.route("/api/insights/follow-ups")
def get_follow_ups():
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    return jsonify({
        "prompts": build_follow_up_prompts(question=question, genre=genre, tag=tag, summary=summary),
    })


@insights_bp.route("/api/insights/concept", methods=["POST"])
def concept_insight():
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "Provide a game description"}), 400
    return jsonify(analyze_concept(games_col, description))


def build_chatgpt_brief_payload(question="", genre=None, tag=None, brief_mode="general", compare=None, concept_description=""):
    """Build the market data bundle used by both the JSON API and loader page."""
    inferred = None
    mode = get_brief_mode(brief_mode)

    if question and not (genre or tag):
        inferred = infer_market_context(
            games_col,
            question,
            known_tags=_curated_subgenre_tags() | all_taxonomy_tags(),
        )
        genre = inferred.get("genre")
        tag = inferred.get("tag")

    summary = summarize_market(games_col, genre=genre, tag=tag) if (genre or tag) else None
    momentum = market_momentum(games_col, db, genre=genre, tag=tag) if (genre or tag) else None
    child_report = None
    if tag and children_for_subgenre(tag):
        child_report = child_subgenre_report(games_col, tag, children_for_subgenre(tag), genre=genre, limit=12)
    comparison = None
    if compare:
        comparison = build_compare_data(
            games_col,
            left_genre=genre if not tag else genre,
            left_tag=tag,
            right_genre=compare.get("genre"),
            right_tag=compare.get("tag"),
        )
    concept_analysis = analyze_concept(games_col, concept_description) if concept_description else None
    taxonomy_context = {
        "genre_groups": groups_for_genre(genre) if genre else None,
        "child_report": child_report,
        "children_for_detected_tag": children_for_subgenre(tag) if tag else [],
    }
    prominence = prominence_report(games_col, genre=genre, limit=8)
    smaller = smaller_subgenre_report(
        games_col,
        genre=genre,
        limit=10,
        curated_tags=_curated_subgenre_tags(genre),
    )
    opportunities = market_opportunities(games_col, genre=genre, limit=8)
    competitors = top_competitors(games_col, genre=genre, tag=tag, limit=8) if (genre or tag) else []
    brief_diagnostics = _build_brief_diagnostics(
        summary=summary,
        momentum=momentum,
        smaller=smaller,
        opportunities=opportunities,
        taxonomy=taxonomy_context,
    )
    # `inferred` only gets populated when genre/tag were guessed from free text.
    # When the caller passes genre/tag explicitly, resolved_market must still
    # reflect that a market was resolved, or the brief tells the AI "no market
    # was found" right next to a fully populated market_summary for one.
    resolved_context = inferred if inferred is not None else (
        {"genre": genre, "tag": tag} if (genre or tag) else None
    )
    question_answerability = _build_question_answerability(
        question=question,
        inferred=resolved_context,
        summary=summary,
        momentum=momentum,
        competitors=competitors,
    )

    return {
        "brief_mode": mode,
        "instruction": (
            "Paste this JSON into ChatGPT and ask it to reason from the provided Steam market data only. "
            "Treat all revenue and owner figures as estimates, not official Steam data."
        ),
        "user_question": question,
        "question_answerability": question_answerability,
        "inferred_context": inferred,
        "market_summary": summary,
        "market_momentum": momentum,
        "taxonomy_context": taxonomy_context,
        "top_competitors": competitors,
        "source_confidence": SOURCE_CONFIDENCE,
        "doing_well_and_less_prominent": prominence,
        "smaller_subgenres": smaller,
        "opportunities": opportunities,
        "brief_diagnostics": brief_diagnostics,
        "comparison": comparison,
        "concept_analysis": concept_analysis,
        "follow_up_prompts": build_follow_up_prompts(question=question, genre=genre, tag=tag, summary=summary),
        "data_available": DATA_POINT_CATALOG,
    }


def build_chatgpt_prompt(payload, user_question="", brief_mode="general"):
    """Convert a brief payload into the pasteable ChatGPT prompt."""
    mode = get_brief_mode(brief_mode)
    lines = [
        "You are helping an indie game developer analyze Steam market data.",
        "Use only the JSON below as your data source.",
        "Treat all revenue and owner figures as SteamSpy-based estimates, not official Steam data.",
        "Optimize for a solo developer or small indie team, not a AAA studio or publisher-backed team.",
        mode["instruction"],
        "Do not rely mainly on top competitor anecdotes. Use aggregate market metrics as the primary evidence and use competitor examples only to support a point.",
        "If confidence is weak or sample coverage is thin, say so clearly and reduce certainty.",
        "If the broad market looks crowded, identify narrower subgenres, child tags, or adjacent niches from the JSON that may be more promising.",
        "Avoid generic advice unless it is directly justified by the provided data.",
        "If a flashy niche metric conflicts with a reliability warning, trust the reliability warning.",
        "If a niche has use_for_recommendation set to caution, present it as a hypothesis to validate rather than a confident recommendation.",
        "Check question_answerability before making claims. If can_answer_directly is false, say the dataset cannot answer the question directly and explain which required data is missing.",
        "Never infer market-wide year counts, release distributions, or other unsupported dimensions from top_competitors or a few example games.",
        "If no genre or tag was resolved, do not pretend the payload represents a defined market.",
    ]
    if user_question:
        lines.append(f"User question: {user_question}")
    lines.extend([
        "",
        "Your answer must follow this exact structure:",
        "1. Short answer",
        "2. Verdict",
        "3. Demand",
        "4. Competition",
        "5. Pricing",
        "6. Risks",
        "7. Best niche opportunities",
        "8. Data confidence and weak spots",
        "9. Recommendation for a small team",
        "",
        "Requirements for the analysis:",
        "- Start by checking question_answerability and align the response mode to it.",
        "- Cite the most decision-useful metrics from the JSON, especially market_summary, performance_benchmarks, revenue_concentration_top_10_pct, confidence, brief_diagnostics, smaller_subgenres, opportunities, taxonomy_context, and market_momentum when reliable.",
        "- Distinguish between broad-market conclusions and niche/subgenre conclusions.",
        "- Do not treat low-confidence momentum data as strong evidence.",
        "- If a field is missing, thin, or low-confidence, say that directly instead of filling the gap with assumptions.",
        "- Every recommendation should be tied to a specific metric, market pattern, or named niche from the JSON.",
        "- Prefer outlier-adjusted benchmarks over raw TAM/SAM or raw niche revenue-per-game figures when recommending what a small team should pursue.",
        "- If taxonomy support is thin, say whether a niche is a confirmed child tag or only an adjacent opportunity.",
        "- In niche analysis, explicitly use confirmed_child_tag, market_relationship, data_reliability, and use_for_recommendation.",
        "- If revenue_per_game_estimate is suppressed or null for a niche, do not reconstruct it from other fields or treat raw_revenue_per_game_estimate as a planning target.",
        "- If question_answerability.can_answer_directly is false, the Short answer must explicitly say the question is not answerable from this payload and must not guess a number.",
        "",
        "In the Verdict section, include these labels on separate lines:",
        "- Market Size:",
        "- Competition:",
        "- Saturation:",
        "- Barrier to Entry:",
        "- Commercial Opportunity:",
        "",
        "In Best niche opportunities, name up to 3 specific niches and explain why each looks better or worse than the broad market.",
        "In Data confidence and weak spots, explicitly list any red flags from brief_diagnostics.",
    ])
    lines.extend(["", json.dumps(payload, indent=2, sort_keys=True, default=str)])
    return "\n".join(lines)


@insights_bp.route("/api/insights/chatgpt-brief")
def get_chatgpt_brief():
    """Bundle a compact data brief users can paste into ChatGPT."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    brief_mode = request.args.get("mode") or "general"
    compare_type = request.args.get("compare_type") or None
    compare_value = request.args.get("compare_value") or None
    compare_genre = request.args.get("compare_genre") or None
    concept_description = request.args.get("concept") or ""
    compare = None
    if compare_type and compare_value:
        compare = {
            "genre": compare_value if compare_type == "genre" else compare_genre,
            "tag": compare_value if compare_type == "tag" else None,
        }
    return jsonify(build_chatgpt_brief_payload(
        question=question,
        genre=genre,
        tag=tag,
        brief_mode=brief_mode,
        compare=compare,
        concept_description=concept_description,
    ))


@insights_bp.route("/api/insights/chatgpt-prompt")
def get_chatgpt_prompt():
    """Return the prepared AI handoff prompt."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    question = request.args.get("q") or ""
    brief_mode = request.args.get("mode") or "general"
    compare_type = request.args.get("compare_type") or None
    compare_value = request.args.get("compare_value") or None
    compare_genre = request.args.get("compare_genre") or None
    concept_description = request.args.get("concept") or ""
    compare = None
    if compare_type and compare_value:
        compare = {
            "genre": compare_value if compare_type == "genre" else compare_genre,
            "tag": compare_value if compare_type == "tag" else None,
        }
    payload = build_chatgpt_brief_payload(
        question=question,
        genre=genre,
        tag=tag,
        brief_mode=brief_mode,
        compare=compare,
        concept_description=concept_description,
    )
    return jsonify({
        "prompt": build_chatgpt_prompt(payload, user_question=question, brief_mode=brief_mode),
    })


@insights_bp.route("/chatgpt-brief-loader")
def chatgpt_brief_loader():
    """Open a dedicated handoff page that copies the brief, then sends the tab to an AI tool."""
    ai_tool = get_ai_handoff_tool(request.args.get("ai_tool"))
    return render_template(
        "brief_loader.html",
        ai_tool=ai_tool,
        loader_query=request.args.to_dict(flat=True),
    )
