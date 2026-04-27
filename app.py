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
    os.makedirs("logs", exist_ok=True)  # Ensure logs dir exists (e.g. on Render)
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

    # ── API Error Handlers ──────────────────────────────────────────────────
    @app.errorhandler(500)
    def handle_500(e):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Internal server error. Our team has been notified."}), 500
        return "Internal Server Error", 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log the full exception
        app.logger.error(f"Unhandled Exception: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({"error": str(e) if app.debug else "An unexpected error occurred."}), 500
        return "An unexpected error occurred.", 500

    # ── Create DB Tables ─────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _seed_admin()

    return app


def _seed_admin():
    """Create owner admin account on every startup if not already present."""
    from models import User
    from extensions import db
    from werkzeug.security import generate_password_hash

    admin_email = os.getenv("ADMIN_EMAIL", "praptitembhe07@gmail.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "Prapti@2004")
    admin_name = os.getenv("ADMIN_NAME", "Prapti")

    existing = User.query.filter_by(email=admin_email).first()
    if existing:
        # Ensure the account is always admin, even after accidental role changes
        if existing.role != "admin":
            existing.role = "admin"
            db.session.commit()
            print(f"[SEED] Admin role restored for {admin_email}")
        return

    admin = User(
        name=admin_name,
        email=admin_email,
        password_hash=generate_password_hash(admin_password),
        phone="+919999999999",
        role="admin",
        is_active=True,
        is_email_verified=True
    )
    db.session.add(admin)
    db.session.commit()
    print(f"[SEED] Admin account created: {admin_email}")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    app = create_app()
    app.run(host="0.0.0.0", debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", port=5000)
