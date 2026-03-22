"""
Women Safety Alert System (WSAS) - AI Enhanced Version
Main Application Entry Point
Author: BCA Final Year Project
"""

import os
import logging
from flask import Flask
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from dotenv import load_dotenv

from config import Config
from extensions import db
from blueprints.auth import auth_bp
from blueprints.alerts import alerts_bp
from blueprints.location import location_bp
from blueprints.admin import admin_bp
from blueprints.chatbot import chatbot_bp
from blueprints.community import community_bp
from blueprints.ai_module import ai_bp

# Load environment variables
load_dotenv()

def create_app(config_class=Config):
    """Application factory pattern for scalability."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Extensions ──────────────────────────────────────────────────────────
    db.init_app(app)
    jwt = JWTManager(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["5000 per day", "1000 per hour"],
        storage_uri="memory://"
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("logs/wsas.log"),
            logging.StreamHandler()
        ]
    )
    app.logger.info("WSAS Application Starting...")

    # ── Register Blueprints ──────────────────────────────────────────────────
    app.register_blueprint(auth_bp,      url_prefix="/api/auth")
    app.register_blueprint(alerts_bp,    url_prefix="/api/alerts")
    app.register_blueprint(location_bp,  url_prefix="/api/location")
    app.register_blueprint(admin_bp,     url_prefix="/api/admin")
    app.register_blueprint(chatbot_bp,   url_prefix="/api/chatbot")
    app.register_blueprint(community_bp, url_prefix="/api/community")
    app.register_blueprint(ai_bp,        url_prefix="/api/ai")

    # ── Serve Frontend ───────────────────────────────────────────────────────
    from flask import send_from_directory
    @app.route("/")
    def index():
        return send_from_directory("frontend", "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory("frontend", filename)

    # ── JWT Error Handlers ───────────────────────────────────────────────────
    @jwt.unauthorized_loader
    def unauthorized_callback(reason):
        return {"error": "Missing or invalid token", "reason": reason}, 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        return {"error": "Token has expired"}, 401

    # ── Create DB Tables ─────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _seed_admin()

    return app


def _seed_admin():
    """Create default admin account if not exists."""
    from models import User
    from extensions import db
    from werkzeug.security import generate_password_hash
    if not User.query.filter_by(role="admin").first():
        admin = User(
            name="Admin",
            email="admin@wsas.com",
            password_hash=generate_password_hash("Admin@123"),
            phone="+910000000000",
            role="admin",
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print("[SEED] Default admin created: admin@wsas.com / Admin@123")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    app = create_app()
    app.run(host="0.0.0.0", debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", port=5000)
