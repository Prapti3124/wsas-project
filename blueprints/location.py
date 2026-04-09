"""
WSAS Location Blueprint
Handles: Live location updates, history, unsafe zone checks, safe route planning.
"""

import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import LocationHistory, UnsafeZone, CommunityReport
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


# ─── Safe Route Planning ──────────────────────────────────────────────────────
@location_bp.route("/safe-route", methods=["POST"])
@jwt_required()
def safe_route():
    """
    Find up to 3 alternative routes from origin to destination.
    Score each route's waypoints against unsafe zones and recent reports.
    Returns routes sorted safest-first.
    """
    data = request.get_json(silent=True) or {}
    olat = data.get("origin_lat")
    olon = data.get("origin_lon")
    dlat = data.get("dest_lat")
    dlon = data.get("dest_lon")

    if None in (olat, olon, dlat, dlon):
        return jsonify({"error": "origin_lat, origin_lon, dest_lat, dest_lon required"}), 422

    try:
        olat, olon, dlat, dlon = float(olat), float(olon), float(dlat), float(dlon)
    except (TypeError, ValueError):
        return jsonify({"error": "Coordinates must be numeric"}), 422

    # Fetch up to 3 alternative routes from OSRM public router (walking + driving)
    routes = []
    for profile in ["foot", "car"]:
        try:
            url = (
                f"https://router.project-osrm.org/route/v1/{profile}/"
                f"{olon},{olat};{dlon},{dlat}"
                f"?overview=full&geometries=geojson&alternatives=true&steps=false"
            )
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            osrm_data = resp.json()

            if osrm_data.get("code") == "Ok":
                for r in osrm_data.get("routes", [])[:2]:  # max 2 per profile
                    coords = r["geometry"]["coordinates"]  # [[lon, lat], ...]
                    routes.append({
                        "profile": profile,
                        "distance_km": round(r["distance"] / 1000, 2),
                        "duration_min": round(r["duration"] / 60, 1),
                        "waypoints": [[c[1], c[0]] for c in coords[::max(1, len(coords)//20)]],
                        "full_geometry": [[c[1], c[0]] for c in coords]
                    })
        except Exception as e:
            logger.warning(f"OSRM {profile} routing failed: {e}")

    if not routes:
        return jsonify({"error": "Could not fetch routes. Check connectivity or try again."}), 503

    # Load risk data for scoring
    zones = UnsafeZone.query.filter_by(is_active=True).all()
    since_48h = datetime.utcnow() - timedelta(hours=48)
    reports = CommunityReport.query.filter(
        CommunityReport.created_at >= since_48h
    ).all()

    def score_route(waypoints):
        """Compute 0–100 risk score for a route based on proximity to danger."""
        total = 0.0
        for lat, lon in waypoints:
            pt_score = 0.0
            # Check unsafe zones (radius-based)
            for z in zones:
                d = haversine_distance(lat, lon, z.latitude, z.longitude)
                if d < z.radius_meters + 100:          # within zone + 100m buffer
                    contrib = (z.crime_score / 100) * max(0, 1 - d / (z.radius_meters + 100))
                    pt_score += contrib * 40            # zone contributes up to 40pts
            # Check community reports within 300m
            for rep in reports:
                d = haversine_distance(lat, lon, rep.latitude, rep.longitude)
                if d < 300:
                    sev_weight = rep.severity / 5.0     # 0.2 – 1.0
                    proximity  = 1 - d / 300
                    pt_score  += sev_weight * proximity * 15  # report contributes up to 15pts
            total += min(100, pt_score)
        return round(total / max(1, len(waypoints)), 1)

    scored = []
    for i, r in enumerate(routes[:4]):               # cap at 4 routes total
        risk = score_route(r["waypoints"])
        label_idx = i + 1
        scored.append({
            "route_id":     label_idx,
            "profile":      r["profile"],
            "distance_km":  r["distance_km"],
            "duration_min": r["duration_min"],
            "risk_score":   risk,
            "risk_level":   "low" if risk < 25 else "medium" if risk < 55 else "high",
            "geometry":     r["full_geometry"]
        })

    # Sort: safest first
    scored.sort(key=lambda x: x["risk_score"])
    scored[0]["label"] = "✅ Recommended (Safest)"
    for route in scored[1:]:
        route["label"] = "⚠️ Alternative"

    return jsonify({"routes": scored}), 200
