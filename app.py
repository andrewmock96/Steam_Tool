"""
Flask application entry point.

This file only wires up the app: all actual routes live in blueprints/,
split by concern —
  pages        static page routes (index, brief loader page, etc.)
  games        single-game lookups and the paginated game grid API
  market       genre/tag market browsing, compare, taxonomy nav
  insights     the AI-brief pipeline (payload building, prompt assembly,
               question-answerability checks) — see blueprints/insights.py
  chat         the in-app chat widget
  coming_soon  the "Coming Soon" future-competitors browsing UI

Run directly with `python app.py` for local dev (Flask's debug reloader).
In production this would be served via a WSGI server instead of app.run().
"""
from flask import Flask

from blueprints.chat import chat_bp
from blueprints.coming_soon import coming_soon_bp
from blueprints.games import games_bp
from blueprints.insights import insights_bp
from blueprints.market import market_bp
from blueprints.pages import pages_bp

app = Flask(__name__)

app.register_blueprint(pages_bp)
app.register_blueprint(games_bp)
app.register_blueprint(market_bp)
app.register_blueprint(insights_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(coming_soon_bp)


if __name__ == "__main__":
    app.run(debug=True)
