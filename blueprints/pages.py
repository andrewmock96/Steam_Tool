from flask import Blueprint, jsonify, render_template, send_from_directory

from db import games_col

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    return render_template("index.html")


@pages_bp.route("/branding/<path:filename>")
def branding_file(filename):
    return send_from_directory("branding", filename)


@pages_bp.route("/api/health")
def health():
    """Quick check that the server is running and database is connected."""
    game_count = games_col.count_documents({})
    return jsonify({
        "status": "ok",
        "games_in_database": game_count
    })
