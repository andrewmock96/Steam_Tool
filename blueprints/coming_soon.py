from flask import Blueprint, jsonify, request

from db import upcoming_games_col
from helpers import STEAM_SUBGENRES
from market_insights import (
    upcoming_games_page,
    upcoming_genre_counts,
    upcoming_subgenre_children_counts,
    upcoming_subgenre_counts,
)
from market_taxonomy import children_for_subgenre

coming_soon_bp = Blueprint("coming_soon", __name__)


@coming_soon_bp.route("/api/coming-soon/genres")
def get_coming_soon_genres():
    """Count of tracked coming-soon games per top-level genre."""
    return jsonify({"genres": upcoming_genre_counts(upcoming_games_col)})


@coming_soon_bp.route("/api/coming-soon/subgenres/<genre>")
def get_coming_soon_subgenres(genre):
    """Subgenre tag counts for coming-soon games within a genre. Mirrors /api/subgenres/<genre>."""
    tags = STEAM_SUBGENRES.get(genre, [])
    return jsonify(upcoming_subgenre_counts(upcoming_games_col, genre, tags))


@coming_soon_bp.route("/api/coming-soon/subgenre-children")
def get_coming_soon_subgenre_children():
    """Child tag counts under a broad subgenre, restricted to coming-soon games."""
    genre = request.args.get("genre") or None
    parent = request.args.get("subgenre") or request.args.get("parent")

    if not parent:
        return jsonify({"error": "Provide subgenre or parent"}), 400

    children = children_for_subgenre(parent)
    if not children:
        return jsonify({
            "parent_subgenre": parent,
            "children_found": [],
            "message": "No child taxonomy is defined for this subgenre yet.",
        })

    return jsonify({
        "parent_subgenre": parent,
        "children_found": upcoming_subgenre_children_counts(upcoming_games_col, children, genre=genre),
    })


@coming_soon_bp.route("/api/coming-soon/games")
def get_coming_soon_games():
    """Paginated, soonest-release-first list of coming-soon games, optionally filtered by genre/tag."""
    genre = request.args.get("genre") or None
    tag = request.args.get("tag") or None
    page = max(0, int(request.args.get("page", 0)))
    limit = min(150, max(1, int(request.args.get("limit", 50))))

    results, total = upcoming_games_page(upcoming_games_col, genre=genre, tag=tag, page=page, limit=limit)
    return jsonify({"games": results, "total": total, "page": page, "limit": limit})
