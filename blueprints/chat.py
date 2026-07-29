"""
The in-app chat widget's backend.

Separate from the AI-brief system in blueprints/insights.py — this answers
simple questions instantly with canned, data-driven responses
(answer_without_llm in market_insights.py does keyword matching against the
question and formats a reply from real numbers), rather than handing off to
an external AI tool. No paid API calls happen here.
"""
from flask import Blueprint, jsonify, request

from db import games_col
from market_insights import answer_without_llm

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """No-cost data assistant. Does not call a paid LLM API."""

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    try:
        response = answer_without_llm(games_col, data["message"])
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
