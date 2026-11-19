
import os
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from extensions import db
from routes.chat import chat_bp
import models

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def create_app():
    app = Flask(__name__)

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from environment variables.")

    # Support PostgreSQL connection URLs from hosting providers
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql://", 1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True
    }

    CORS(app)

    db.init_app(app)

    app.register_blueprint(chat_bp)

    # Create database tables
    with app.app_context():
        db.create_all()

    @app.route("/", methods=["GET"])
    def home():
        return jsonify({
            "success": True,
            "message": "Autoflick AI backend is running!",
            "application": "Autoflick AI Chatbot"
        })

    @app.route("/api/health", methods=["GET"])
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))

            return jsonify({
                "status": "healthy",
                "service": "Autoflick AI API",
                "database": "connected"
            }), 200

        except Exception:
            app.logger.exception("Database health check failed.")

            return jsonify({
                "status": "unhealthy",
                "database": "disconnected"
            }), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
