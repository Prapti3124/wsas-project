"""
WSAS Admin Blueprint
Role-protected routes for admin dashboard:
- User management, alert analytics, unsafe zone CRUD, heatmap data
"""

import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from extensions import db
from models import User, Alert, CommunityReport, UnsafeZone, LocationHistory

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)


# ─── Admin-only decorator ────────────────────────────────────────────────────
def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if claims.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ─── Dashboard Stats ──────────────────────────────────────────────────────────
@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    """Summary statistics for admin dashboard."""
    today = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)

    stats = {
        "users": {
            "total": User.query.filter_by(role="user").count(),
            "active_today": User.query.filter(
                User.last_login >= datetime.combine(today, datetime.min.time())
            ).count()
        },
        "alerts": {
            "total": Alert.query.count(),
            "this_week": Alert.query.filter(Alert.created_at >= week_ago).count(),
            "active": Alert.query.filter_by(status="active").count(),
            "by_type": db.session.query(
                Alert.alert_type, db.func.count(Alert.id)
            ).group_by(Alert.alert_type).all()
        },
        "community_reports": {
            "total": CommunityReport.query.count(),
            "unverified": CommunityReport.query.filter_by(verified=False).count()
        },
        "unsafe_zones": UnsafeZone.query.filter_by(is_active=True).count()
    }

    # Convert SQLAlchemy tuples to dicts
    stats["alerts"]["by_type"] = [
        {"type": t, "count": c} for t, c in stats["alerts"]["by_type"]
    ]

    return jsonify(stats), 200


# ─── Alert Analytics ──────────────────────────────────────────────────────────
@admin_bp.route("/analytics/alerts", methods=["GET"])
@admin_required
def alert_analytics():
    """Daily alert counts for the past 30 days (chart data)."""
    days = []
    for i in range(29, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        start = datetime.combine(day, datetime.min.time())
        end   = datetime.combine(day, datetime.max.time())
        count = Alert.query.filter(
            Alert.created_at >= start,
            Alert.created_at <= end
        ).count()
        days.append({"date": day.isoformat(), "count": count})

    return jsonify({"daily_alerts": days}), 200


# ─── User Management ──────────────────────────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    page = request.args.get("page", 1, type=int)
    users = User.query.filter_by(role="user")\
                      .paginate(page=page, per_page=20, error_out=False)
    return jsonify({
        "users": [u.to_dict() for u in users.items],
        "total": users.total,
        "pages": users.pages
    }), 200


@admin_bp.route("/users/<int:user_id>/toggle", methods=["PUT"])
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    action = "activated" if user.is_active else "deactivated"
    return jsonify({"message": f"User {action}", "is_active": user.is_active}), 200


# ─── Unsafe Zone Management ──────────────────────────────────────────────────
@admin_bp.route("/unsafe-zones", methods=["POST"])
@admin_required
def create_unsafe_zone():
    data = request.get_json(silent=True) or {}
    zone = UnsafeZone(
        name          = data.get("name", "Unnamed Zone"),
        latitude      = float(data["latitude"]),
        longitude     = float(data["longitude"]),
        radius_meters = float(data.get("radius_meters", 500)),
        crime_score   = float(data.get("crime_score", 50)),
        category      = data.get("category", "general")
    )
    db.session.add(zone)
    db.session.commit()
    return jsonify({"message": "Unsafe zone created", "zone": zone.to_dict()}), 201


@admin_bp.route("/unsafe-zones/<int:zone_id>", methods=["DELETE"])
@admin_required
def delete_unsafe_zone(zone_id):
    zone = UnsafeZone.query.get_or_404(zone_id)
    zone.is_active = False
    db.session.commit()
    return jsonify({"message": "Zone deactivated"}), 200


# ─── Community Reports Management ────────────────────────────────────────────
@admin_bp.route("/reports", methods=["GET"])
@admin_required
def list_reports():
    reports = CommunityReport.query.order_by(
        CommunityReport.created_at.desc()
    ).limit(100).all()
    return jsonify({"reports": [r.to_dict() for r in reports]}), 200


@admin_bp.route("/reports/<int:report_id>/verify", methods=["PUT"])
@admin_required
def verify_report(report_id):
    report = CommunityReport.query.get_or_404(report_id)
    report.verified = True
    db.session.commit()
    return jsonify({"message": "Report verified"}), 200
