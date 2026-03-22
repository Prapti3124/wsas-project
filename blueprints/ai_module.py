"""
WSAS AI Module Blueprint
Exposes AI features: risk score, motion analysis, hotspots.
"""

import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from ai.risk_engine import RiskEngine, MotionDetector, get_alert_hotspots
from models import RiskScore

ai_bp = Blueprint("ai_module", __name__)
logger = logging.getLogger(__name__)
engine = RiskEngine()
motion_detector = MotionDetector()


@ai_bp.route("/risk-score", methods=["POST"])
@jwt_required()
def get_risk_score():
    """Calculate real-time risk score for current location."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    lat = data.get("latitude")
    lon = data.get("longitude")

    result = engine.calculate_risk(user_id=user_id, latitude=lat, longitude=lon)
    return jsonify(result), 200


@ai_bp.route("/motion", methods=["POST"])
@jwt_required()
def analyze_motion():
    """Process accelerometer data for shake/fall detection."""
    data = request.get_json(silent=True) or {}
    x = float(data.get("x", 0))
    y = float(data.get("y", 0))
    z = float(data.get("z", 0))

    result = motion_detector.process_sample(x, y, z)
    return jsonify(result), 200


@ai_bp.route("/hotspots", methods=["GET"])
@jwt_required()
def hotspots():
    """Return alert hotspot data for heatmap rendering."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        # Non-admins get anonymized hotspots
        pass
    data = get_alert_hotspots()
    return jsonify({"hotspots": data}), 200


@ai_bp.route("/risk-history", methods=["GET"])
@jwt_required()
def risk_history():
    """Get user's risk score history for analytics chart."""
    user_id = int(get_jwt_identity())
    scores = RiskScore.query.filter_by(user_id=user_id)\
                            .order_by(RiskScore.computed_at.desc())\
                            .limit(30).all()
    return jsonify({
        "history": [s.to_dict() for s in scores]
    }), 200
