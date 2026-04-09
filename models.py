"""
WSAS Database Models
All tables with relationships, indexes, and constraints.
Designed for SQLite now, PostgreSQL-ready for production.
"""

from datetime import datetime
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash


# ─────────────────────────────────────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash= db.Column(db.String(256), nullable=True) # Nullable for Google users
    phone        = db.Column(db.String(20), nullable=True) # Nullable initially
    google_id    = db.Column(db.String(150), unique=True, nullable=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    otp_code     = db.Column(db.String(10), nullable=True)
    otp_expiry   = db.Column(db.DateTime, nullable=True)
    alternate_phone = db.Column(db.String(20), nullable=True)
    address      = db.Column(db.Text, nullable=True)
    profile_photo= db.Column(db.Text, nullable=True)
    role         = db.Column(db.String(20), default="user")   # "user" | "admin"
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_login   = db.Column(db.DateTime, nullable=True)

    # Relationships
    contacts     = db.relationship("EmergencyContact", backref="user", lazy=True, cascade="all, delete")
    alerts       = db.relationship("Alert",            backref="user", lazy=True, cascade="all, delete")
    locations    = db.relationship("LocationHistory",  backref="user", lazy=True, cascade="all, delete")
    risk_scores  = db.relationship("RiskScore",        backref="user", lazy=True, cascade="all, delete")
    reports      = db.relationship("CommunityReport",  backref="user", lazy=True, cascade="all, delete")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "email": self.email, "phone": self.phone,
            "alternate_phone": self.alternate_phone,
            "address": self.address,
            "profile_photo": self.profile_photo,
            "role": self.role, "is_active": self.is_active,
            "created_at": self.created_at.isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# EMERGENCY CONTACT MODEL
# ─────────────────────────────────────────────────────────────────────────────
class EmergencyContact(db.Model):
    __tablename__ = "emergency_contacts"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name         = db.Column(db.String(100), nullable=False)
    phone        = db.Column(db.String(20), nullable=False)
    relation     = db.Column(db.String(50))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "phone": self.phone, "relation": self.relation
        }


# ─────────────────────────────────────────────────────────────────────────────
# ALERT MODEL
# ─────────────────────────────────────────────────────────────────────────────
class Alert(db.Model):
    __tablename__ = "alerts"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    alert_type   = db.Column(db.String(50), default="manual")
    # Types: "manual" | "voice" | "shake" | "fall" | "chatbot" | "auto_risk"
    latitude     = db.Column(db.Float, nullable=True)
    longitude    = db.Column(db.Float, nullable=True)
    address      = db.Column(db.String(255), nullable=True)
    message      = db.Column(db.Text, nullable=True)
    risk_score   = db.Column(db.Float, default=0.0)
    status       = db.Column(db.String(20), default="active")
    # Status: "active" | "resolved" | "false_alarm"
    notified_contacts = db.Column(db.Text, nullable=True)  # JSON list of notified phones
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id,
            "alert_type": self.alert_type,
            "latitude": self.latitude, "longitude": self.longitude,
            "address": self.address, "message": self.message,
            "risk_score": self.risk_score, "status": self.status,
            "created_at": self.created_at.isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# LOCATION HISTORY MODEL
# ─────────────────────────────────────────────────────────────────────────────
class LocationHistory(db.Model):
    __tablename__ = "location_history"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    latitude     = db.Column(db.Float, nullable=False)
    longitude    = db.Column(db.Float, nullable=False)
    accuracy     = db.Column(db.Float, nullable=True)
    speed        = db.Column(db.Float, nullable=True)   # m/s
    is_unsafe    = db.Column(db.Boolean, default=False)
    risk_level   = db.Column(db.String(10), default="low")
    recorded_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id, "latitude": self.latitude,
            "longitude": self.longitude, "speed": self.speed,
            "is_unsafe": self.is_unsafe, "risk_level": self.risk_level,
            "recorded_at": self.recorded_at.isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# RISK SCORE MODEL
# ─────────────────────────────────────────────────────────────────────────────
class RiskScore(db.Model):
    __tablename__ = "risk_scores"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    score           = db.Column(db.Float, nullable=False)          # 0–100
    level           = db.Column(db.String(10), nullable=False)     # low/medium/high
    time_factor     = db.Column(db.Float, default=0.0)
    location_factor = db.Column(db.Float, default=0.0)
    alert_factor    = db.Column(db.Float, default=0.0)
    community_factor= db.Column(db.Float, default=0.0)
    computed_at     = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "score": round(self.score, 2),
            "level": self.level,
            "factors": {
                "time": self.time_factor,
                "location": self.location_factor,
                "alerts": self.alert_factor,
                "community": self.community_factor
            },
            "computed_at": self.computed_at.isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# COMMUNITY REPORT MODEL
# ─────────────────────────────────────────────────────────────────────────────
class CommunityReport(db.Model):
    __tablename__ = "community_reports"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    latitude     = db.Column(db.Float, nullable=False)
    longitude    = db.Column(db.Float, nullable=False)
    category     = db.Column(db.String(50))
    # Categories: "harassment" | "theft" | "assault" | "suspicious" | "lighting" | "other"
    description  = db.Column(db.Text)
    severity     = db.Column(db.Integer, default=3)   # 1–5
    verified     = db.Column(db.Boolean, default=False)
    upvotes      = db.Column(db.Integer, default=0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id, "latitude": self.latitude,
            "longitude": self.longitude, "category": self.category,
            "description": self.description, "severity": self.severity,
            "verified": self.verified, "upvotes": self.upvotes,
            "created_at": self.created_at.isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# UNSAFE ZONE MODEL (Admin-managed)
# ─────────────────────────────────────────────────────────────────────────────
class UnsafeZone(db.Model):
    __tablename__ = "unsafe_zones"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100))
    latitude     = db.Column(db.Float, nullable=False)
    longitude    = db.Column(db.Float, nullable=False)
    radius_meters= db.Column(db.Float, default=500.0)
    crime_score  = db.Column(db.Float, default=50.0)   # 0–100
    category     = db.Column(db.String(50))
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "latitude": self.latitude, "longitude": self.longitude,
            "radius_meters": self.radius_meters,
            "crime_score": self.crime_score, "category": self.category
        }


# ─────────────────────────────────────────────────────────────────────────────
# CHAT LOG MODEL
# ─────────────────────────────────────────────────────────────────────────────
class ChatLog(db.Model):
    __tablename__ = "chat_logs"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user_message = db.Column(db.Text)
    bot_response = db.Column(db.Text)
    intent       = db.Column(db.String(50))
    triggered_sos= db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

# ─────────────────────────────────────────────────────────────────────────────
# TRACKING SESSION MODEL (Follow Me)
# ─────────────────────────────────────────────────────────────────────────────
class TrackingSession(db.Model):
    __tablename__ = "tracking_sessions"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token        = db.Column(db.String(64), unique=True, nullable=False, index=True)
    is_active    = db.Column(db.Boolean, default=True)
    expires_at   = db.Column(db.DateTime, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat()
        }
