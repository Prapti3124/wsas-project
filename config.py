"""
WSAS Configuration Module
All sensitive values loaded from environment variables.
Never hardcode secrets!
"""

import os
from datetime import timedelta


class Config:
    # ── Flask Core ────────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-wsas-2024")
    DEBUG = False
    TESTING = False

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite for development; swap DATABASE_URL for PostgreSQL in production
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///wsas.db"
    ).replace("postgres://", "postgresql://")  # Heroku fix
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-wsas-change-me")
    JWT_ACCESS_TOKEN_EXPIRES  = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # ── Twilio ────────────────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID",  "").strip()
    TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN",   "").strip()
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

    # ── Google OAuth ──────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID    = os.getenv("GOOGLE_CLIENT_ID",    "")
    GOOGLE_CLIENT_SECRET= os.getenv("GOOGLE_CLIENT_SECRET", "")

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    MAIL_SERVER         = os.getenv("MAIL_SERVER",         "smtp.gmail.com")
    MAIL_PORT           = int(os.getenv("MAIL_PORT",       587))
    MAIL_USE_TLS        = os.getenv("MAIL_USE_TLS",        "true").lower() == "true"
    MAIL_USERNAME       = os.getenv("MAIL_USERNAME",       "")
    MAIL_PASSWORD       = os.getenv("MAIL_PASSWORD",       "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # ── AI / Risk Engine ──────────────────────────────────────────────────────
    RISK_THRESHOLD_HIGH    = 70   # Score >= 70 → High Risk
    RISK_THRESHOLD_MEDIUM  = 40   # Score >= 40 → Medium Risk
    SHAKE_THRESHOLD        = 15   # Accelerometer magnitude threshold
    UNSAFE_HOUR_START      = 21   # 9 PM
    UNSAFE_HOUR_END        = 5    # 5 AM

    # ── App Settings ──────────────────────────────────────────────────────────
    MAX_CONTACTS           = 5    # Max emergency contacts per user
    ALERT_COOLDOWN_SECONDS = 60   # Prevent alert spam


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/wsas")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
