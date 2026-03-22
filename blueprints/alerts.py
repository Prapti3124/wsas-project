"""
WSAS Alerts Blueprint
Handles: SOS trigger, alert history, Twilio SMS/call notifications,
         status updates, emergency contacts CRUD.
"""

import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from concurrent.futures import ThreadPoolExecutor
from extensions import db
from models import Alert, User, EmergencyContact

alerts_bp = Blueprint("alerts", __name__)
logger = logging.getLogger(__name__)


# ─── Trigger SOS Alert ────────────────────────────────────────────────────────
@alerts_bp.route("/sos", methods=["POST"])
@jwt_required()
def trigger_sos():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    # Rate limiting: prevent alert spam
    cooldown = current_app.config.get("ALERT_COOLDOWN_SECONDS", 60)
    recent = Alert.query.filter(
        Alert.user_id == user_id,
        Alert.created_at >= datetime.utcnow() - timedelta(seconds=cooldown),
        Alert.status == "active"
    ).first()
    if recent:
        return jsonify({"error": "Alert cooldown active. Please wait."}), 429

    # Get risk score from AI module
    risk_score = 0.0
    try:
        from ai.risk_engine import RiskEngine
        engine = RiskEngine()
        risk_data = engine.calculate_risk(
            user_id=user_id,
            latitude=data.get("latitude"),
            longitude=data.get("longitude")
        )
        risk_score = risk_data["score"]
    except Exception as e:
        logger.warning(f"Risk engine error: {e}")

    # Create alert record
    alert = Alert(
        user_id    = user_id,
        alert_type = data.get("alert_type", "manual"),
        latitude   = data.get("latitude"),
        longitude  = data.get("longitude"),
        address    = data.get("address", ""),
        message    = data.get("message", "I need help!"),
        risk_score = risk_score,
        status     = "active"
    )
    db.session.add(alert)
    db.session.flush()  # Get alert ID before commit

    # Notify emergency contacts in parallel
    contacts = EmergencyContact.query.filter_by(user_id=user_id).all()
    notified = []
    errors = []
    
    if contacts:
        # We pass necessary config to avoid accessing current_app inside threads
        twilio_config = {
            "account_sid": current_app.config["TWILIO_ACCOUNT_SID"],
            "auth_token":  current_app.config["TWILIO_AUTH_TOKEN"],
            "from_number": current_app.config["TWILIO_PHONE_NUMBER"]
        }
        
        def notify_single_contact(contact):
            """Helper to send alert to one contact in a thread."""
            contact_success = {"sms": False, "call": False}
            contact_errors = []
            phone = "".join(contact.phone.split()) # Strip all whitespace
            
            try:
                from twilio.rest import Client
                account_sid = twilio_config["account_sid"]
                auth_token  = twilio_config["auth_token"]
                from_number = twilio_config["from_number"]
                
                if not account_sid or not auth_token:
                    return False, "Twilio credentials not configured.", contact.phone

                client = Client(account_sid, auth_token)
                maps_url = f"https://maps.google.com/?q={alert.latitude},{alert.longitude}" if alert.latitude else "Location unavailable"
                body = (
                    f"🆘 EMERGENCY ALERT from {user.name}!\n"
                    f"help me i am in danger.\n"
                    f"Location: {maps_url}\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"Please check on them immediately!"
                )
                
                # 1. Send SMS
                try:
                    client.messages.create(body=body, from_=from_number, to=phone)
                    contact_success["sms"] = True
                    logger.info(f"SMS sent successfully to {phone}")
                except Exception as sms_e:
                    logger.error(f"SMS failed for {phone}: {sms_e}")
                    contact_errors.append(f"SMS: {str(sms_e)}")
                
                # 2. Make Voice Call
                try:
                    twiml = f"<Response><Say>help me i am in danger. help me i am in danger. help me i am in danger.</Say></Response>"
                    client.calls.create(twiml=twiml, to=phone, from_=from_number)
                    contact_success["call"] = True
                    logger.info(f"Voice call initiated for {phone}")
                except Exception as call_e:
                    logger.error(f"Voice call failed for {phone}: {call_e}")
                    contact_errors.append(f"Call: {str(call_e)}")
                
                overall_success = contact_success["sms"] or contact_success["call"]
                err_msg = "; ".join(contact_errors)
                return overall_success, err_msg, contact.phone

            except Exception as e:
                logger.error(f"Critical thread error for {contact.phone}: {e}")
                return False, str(e), contact.phone

        # Use ThreadPoolExecutor to run notifications concurrently
        with ThreadPoolExecutor(max_workers=len(contacts)) as executor:
            results = list(executor.map(notify_single_contact, contacts))
            
        for success, err_msg, phone in results:
            if success:
                notified.append(phone)
            else:
                errors.append(f"{phone}: {err_msg}")

    alert.notified_contacts = json.dumps(notified)
    db.session.commit()

    logger.info(f"SOS Alert #{alert.id} triggered by user {user_id}. "
                f"Notified: {len(notified)} contacts. Errors: {len(errors)}. Risk: {risk_score}")

    return jsonify({
        "message": "SOS Alert triggered",
        "alert": alert.to_dict(),
        "notified_contacts": len(notified),
        "errors": errors,
        "risk_score": risk_score
    }), 201


# ─── Get Alert History ────────────────────────────────────────────────────────
@alerts_bp.route("/history", methods=["GET"])
@jwt_required()
def alert_history():
    user_id = int(get_jwt_identity())
    page  = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 10, type=int), 50)

    alerts = Alert.query.filter_by(user_id=user_id)\
                        .order_by(Alert.created_at.desc())\
                        .paginate(page=page, per_page=limit, error_out=False)

    return jsonify({
        "alerts": [a.to_dict() for a in alerts.items],
        "total": alerts.total,
        "pages": alerts.pages,
        "current_page": page
    }), 200


# ─── Update Alert Status ─────────────────────────────────────────────────────
@alerts_bp.route("/<int:alert_id>/status", methods=["PUT"])
@jwt_required()
def update_alert_status(alert_id):
    user_id = int(get_jwt_identity())
    alert = Alert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    data   = request.get_json(silent=True) or {}
    status = data.get("status", "resolved")
    if status not in ("active", "resolved", "false_alarm"):
        return jsonify({"error": "Invalid status"}), 422

    alert.status = status
    db.session.commit()
    return jsonify({"message": "Alert status updated", "alert": alert.to_dict()}), 200


# ─── Emergency Contacts CRUD ─────────────────────────────────────────────────
@alerts_bp.route("/contacts", methods=["GET"])
@jwt_required()
def get_contacts():
    user_id = int(get_jwt_identity())
    contacts = EmergencyContact.query.filter_by(user_id=user_id).all()
    return jsonify({"contacts": [c.to_dict() for c in contacts]}), 200


@alerts_bp.route("/contacts", methods=["POST"])
@jwt_required()
def add_contact():
    user_id = int(get_jwt_identity())
    max_contacts = current_app.config.get("MAX_CONTACTS", 5)

    existing = EmergencyContact.query.filter_by(user_id=user_id).count()
    if existing >= max_contacts:
        return jsonify({"error": f"Maximum {max_contacts} contacts allowed"}), 400

    data = request.get_json(silent=True) or {}
    name  = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not name or not phone:
        return jsonify({"error": "Name and phone required"}), 422

    contact = EmergencyContact(
        user_id  = user_id,
        name     = name,
        phone    = phone,
        relation = data.get("relation", "")
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({"message": "Contact added", "contact": contact.to_dict()}), 201


@alerts_bp.route("/contacts/<int:contact_id>", methods=["DELETE"])
@jwt_required()
def delete_contact(contact_id):
    user_id = int(get_jwt_identity())
    contact = EmergencyContact.query.filter_by(id=contact_id, user_id=user_id).first()
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    db.session.delete(contact)
    db.session.commit()
    return jsonify({"message": "Contact deleted"}), 200
