from flask import Blueprint, jsonify, request

from db import games_col, upcoming_games_col
from helpers import build_compare_data
from market_insights import summarize_market, upcoming_competitors

market_bp = Blueprint("market", __name__)


@market_bp.route("/api/market/genre/<genre>")
def get_market_overview(genre):
    """Compute TAM and outlier-adjusted benchmarks for a genre."""
    summary = summarize_market(games_col, genre=genre)
    if not summary:
        return jsonify({"error": "No games found for this genre"}), 404

    return jsonify({
        "genre": genre,
        "total_games": summary["total_games"],
        "paid_games": summary["paid_games"],
        "avg_review_score": summary["avg_review_score_pct"],
        "avg_price": summary["avg_price_usd"],
        "TAM": {**summary["TAM"], "description": summary["TAM"]["label"]},
        "SOM": {**summary["SOM"], "description": summary["SOM"]["label"]},
        "realistic_revenue_target": summary["realistic_revenue_target"],
        "performance_benchmarks": summary["performance_benchmarks"],
        "confidence": summary["confidence"],
        "source_confidence": summary["source_confidence"],
        "sample_notes": summary["sample_notes"],
        "revenue_concentration_top_10_pct": summary["revenue_concentration_top_10_pct"],
        "disclaimer": summary["disclaimer"],
    })


@market_bp.route("/api/market/tag/<tag>")
def get_market_by_tag(tag):
    """Compute SAM/SOM and outlier-adjusted benchmarks for a tag."""
    genre = request.args.get("genre") or None
    summary = summarize_market(games_col, genre=genre, tag=tag)
    if not summary:
        return jsonify({"error": "No games found for this tag"}), 404

    return jsonify({
        "tag": tag,
        "genre": genre,
        "total_games": summary["total_games"],
        "paid_games": summary["paid_games"],
        "avg_review_score": summary["avg_review_score_pct"],
        "avg_price": summary["avg_price_usd"],
        "TAM": {**summary["TAM"], "description": summary["TAM"]["label"]},
        "SAM": {**summary["SAM"], "description": summary["SAM"]["label"]},
        "SOM": {**summary["SOM"], "description": summary["SOM"]["label"]},
        "realistic_revenue_target": summary["realistic_revenue_target"],
        "performance_benchmarks": summary["performance_benchmarks"],
        "confidence": summary["confidence"],
        "source_confidence": summary["source_confidence"],
        "sample_notes": summary["sample_notes"],
        "revenue_concentration_top_10_pct": summary["revenue_concentration_top_10_pct"],
        "disclaimer": summary["disclaimer"],
    })


@market_bp.route("/api/market/competitors")
def get_competitors():
    """Get competitor analysis for a genre or tag."""
    genre = request.args.get("genre", "")
    tag = request.args.get("tag", "")

    if not genre and not tag:
        return jsonify({"error": "Provide a genre or tag parameter"}), 400

    query = {}
    if genre:
        query["genres"] = {"$regex": genre, "$options": "i"}
    if tag:
        query["tags"] = {"$regex": tag, "$options": "i"}

    results = list(games_col.find(query, {"_id": 0})
        .sort("estimated_owners.high", -1)
        .limit(20))

    return jsonify(results)


@market_bp.route("/api/market/upcoming")
def get_upcoming_competitors():
    """Future competitors currently in Steam's coming-soon queue for a genre/tag."""
    genre = request.args.get("genre", "") or None
    tag = request.args.get("tag", "") or None
    limit = request.args.get("limit", 12)

    if not genre and not tag:
        return jsonify({"error": "Provide a genre or tag parameter"}), 400

    results = upcoming_competitors(upcoming_games_col, genre=genre, tag=tag, limit=limit)
    return jsonify({
        "genre": genre,
        "tag": tag,
        "count": len(results),
        "upcoming": results,
        "source": "Steam store data (games currently marked coming_soon)",
    })


@market_bp.route("/api/insights/compare")
def compare_markets():
    left_type = request.args.get("left_type", "genre")
    left_value = request.args.get("left") or ""
    left_genre = left_value if left_type == "genre" else request.args.get("left_genre") or None
    left_tag = left_value if left_type == "tag" else None

    right_type = request.args.get("right_type", "genre")
    right_value = request.args.get("right") or ""
    right_genre = right_value if right_type == "genre" else request.args.get("right_genre") or None
    right_tag = right_value if right_type == "tag" else None

    if not left_value or not right_value:
        return jsonify({"error": "Provide both markets to compare"}), 400

    comparison = build_compare_data(
        games_col,
        left_genre=left_genre,
        left_tag=left_tag,
        right_genre=right_genre,
        right_tag=right_tag,
    )
    if not comparison:
        return jsonify({"error": "Could not compare one or both markets"}), 404
    return jsonify(comparison)
