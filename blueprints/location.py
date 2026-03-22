"""
WSAS Location Blueprint
Handles: Live location updates, history, unsafe zone checks.
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import LocationHistory, UnsafeZone
from ai.risk_engine import haversine_distance

location_bp = Blueprint("location", __name__)
logger = logging.getLogger(__name__)


@location_bp.route("/update", methods=["POST"])
@jwt_required()
def update_location():
    """Record a new location point from user's device."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return jsonify({"error": "latitude and longitude required"}), 422

    # Check if in unsafe zone
    zones = UnsafeZone.query.filter_by(is_active=True).all()
    is_unsafe = False
    risk_level = "low"

    for zone in zones:
        dist = haversine_distance(float(lat), float(lon), zone.latitude, zone.longitude)
        if dist <= zone.radius_meters:
            is_unsafe = True
            risk_level = "high" if zone.crime_score >= 70 else "medium"
            break

    loc = LocationHistory(
        user_id    = user_id,
        latitude   = float(lat),
        longitude  = float(lon),
        accuracy   = data.get("accuracy"),
        speed      = data.get("speed"),
        is_unsafe  = is_unsafe,
        risk_level = risk_level
    )
    db.session.add(loc)
    db.session.commit()

    return jsonify({
        "message": "Location recorded",
        "is_unsafe": is_unsafe,
        "risk_level": risk_level
    }), 200


@location_bp.route("/history", methods=["GET"])
@jwt_required()
def location_history():
    """Return last 24h of location trail."""
    user_id = int(get_jwt_identity())
    since = datetime.utcnow() - timedelta(hours=24)
    locs = LocationHistory.query.filter(
        LocationHistory.user_id == user_id,
        LocationHistory.recorded_at >= since
    ).order_by(LocationHistory.recorded_at.asc()).all()

    return jsonify({
        "trail": [l.to_dict() for l in locs]
    }), 200


@location_bp.route("/unsafe-zones", methods=["GET"])
@jwt_required()
def get_unsafe_zones():
    """Return all active unsafe zones for map display."""
    zones = UnsafeZone.query.filter_by(is_active=True).all()
    return jsonify({"zones": [z.to_dict() for z in zones]}), 200
