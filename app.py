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
