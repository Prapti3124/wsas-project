"""
WSAS Community Reports Blueprint
Users can report unsafe locations for community safety intelligence.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import CommunityReport

community_bp = Blueprint("community", __name__)

VALID_CATEGORIES = {"harassment", "theft", "assault", "suspicious", "lighting", "other"}


@community_bp.route("/report", methods=["POST"])
@jwt_required()
def submit_report():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return jsonify({"error": "Location required"}), 422

    category = data.get("category", "other")
    if category not in VALID_CATEGORIES:
        category = "other"

    severity = int(data.get("severity", 3))
    severity = max(1, min(5, severity))

    report = CommunityReport(
        user_id     = user_id,
        latitude    = float(lat),
        longitude   = float(lon),
        category    = category,
        description = str(data.get("description", ""))[:500],
        severity    = severity
    )
    db.session.add(report)
    db.session.commit()

    return jsonify({"message": "Report submitted. Thank you for keeping the community safe!", 
                    "report_id": report.id}), 201


@community_bp.route("/reports", methods=["GET"])
@jwt_required()
def get_reports():
    """Get recent verified community reports for map display."""
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=30)
    reports = CommunityReport.query.filter(
        CommunityReport.created_at >= since
    ).order_by(CommunityReport.created_at.desc()).limit(100).all()
    return jsonify({"reports": [r.to_dict() for r in reports]}), 200


@community_bp.route("/report/<int:report_id>/upvote", methods=["POST"])
@jwt_required()
def upvote_report(report_id):
    report = CommunityReport.query.get_or_404(report_id)
    report.upvotes += 1
    db.session.commit()
    return jsonify({"upvotes": report.upvotes}), 200
