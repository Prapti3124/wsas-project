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
    user_name = user.name if user else "a SAKHI User"

    # Rate limiting: prevent alert spam
    cooldown = current_app.config.get("ALERT_COOLDOWN_SECONDS", 60)
    recent = Alert.query.filter(
        Alert.user_id == user_id,
        Alert.created_at >= datetime.utcnow() - timedelta(seconds=cooldown),
        Alert.status == "active"
    ).first()
    if recent:
        return jsonify({"error": "Alert cooldown active. Please wait."}), 429

    # Create alert record immediately with placeholder risk
    alert = Alert(
        user_id    = user_id,
        alert_type = data.get("alert_type", "manual"),
        latitude   = data.get("latitude"),
        longitude  = data.get("longitude"),
        address    = data.get("address", ""),
        message    = data.get("message", "I need help!"),
        risk_score = 0.0, # Will be updated in background
        status     = "active"
    )
    db.session.add(alert)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create alert record: {e}")
        return jsonify({"error": "Failed to trigger SOS on server."}), 500

    # Start background processing for AI and Notifications
    # We pass the app object to the thread to reconstruct context
    app = current_app._get_current_object()
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(process_sos_background, app, alert.id, data)

    logger.info(f"SOS Alert #{alert.id} accepted for processing for user {user_id}.")

    return jsonify({
        "message": "SOS Alert triggered and processing in background.",
        "alert": alert.to_dict(),
        "status": "processing"
    }), 201


def process_sos_background(app, alert_id, data):
    """Background task to run AI engine and notify contacts."""
    with app.app_context():
        alert = Alert.query.get(alert_id)
        if not alert: return
        
        user_id = alert.user_id
        user = User.query.get(user_id)
        user_name = user.name if user else "a SAKHI User"
        
        # 1. Background AI Risk Calculation
        try:
            from ai.risk_engine import RiskEngine
            engine = RiskEngine()
            risk_data = engine.calculate_risk(
                user_id=user_id,
                latitude=alert.latitude,
                longitude=alert.longitude
            )
            alert.risk_score = risk_data["score"]
            db.session.add(alert)
            db.session.commit()
            logger.info(f"Background risk score updated for Alert #{alert_id}: {alert.risk_score}")
        except Exception as e:
            logger.warning(f"Background risk engine error for Alert #{alert_id}: {e}")

        # 2. Parallel Notifications
        contacts = EmergencyContact.query.filter_by(user_id=user_id).all()
        if not contacts:
            logger.info(f"No contacts to notify for Alert #{alert_id}")
            return

        twilio_config = {
            "account_sid": app.config["TWILIO_ACCOUNT_SID"],
            "auth_token":  app.config["TWILIO_AUTH_TOKEN"],
            "from_number": app.config["TWILIO_PHONE_NUMBER"]
        }

        if not twilio_config["account_sid"] or not twilio_config["auth_token"]:
            logger.error(f"Twilio not configured for background Alert #{alert_id}")
            return

        def dispatch_alert(contact, method="sms"):
            """Thread-safe worker to send SMS or Call."""
            phone = "".join(contact.phone.split())
            try:
                from twilio.rest import Client
                client = Client(twilio_config["account_sid"], twilio_config["auth_token"])
                from_num = twilio_config["from_number"]
                
                if method == "sms":
                    # Smart Location Formatting: Handle missing GPS
                    if alert.latitude and alert.longitude:
                        lat_str = f"{alert.latitude:.7f}"
                        lon_str = f"{alert.longitude:.7f}"
                        accuracy = data.get("accuracy")
                        acc_str = f" (Accuracy: {round(accuracy)}m)" if accuracy else ""
                        maps_url = f"https://maps.google.com/?q={lat_str},{lon_str}{acc_str}"
                    else:
                        maps_url = "⚠️ Location Unavailable (Signal weak or blocked)"
                    
                    # Exact format requested by user
                    body = (f"🆘 SOS! {user_name} is in danger!\n"
                            f"Location: {maps_url}\n"
                            f"Time: {datetime.utcnow().strftime('%H:%M')} UTC\n"
                            f"Msg: {alert.message}")
                    
                    logger.info(f"Sending SOS SMS to {phone}: {body}")
                    client.messages.create(body=body, from_=from_num, to=phone)
                    logger.info(f"Parallel SMS sent to {phone}")
                else:
                    twiml = f"<Response><Say>SOS! Emergency alert from {user_name}. Check your phone for location.</Say></Response>"
                    client.calls.create(twiml=twiml, to=phone, from_=from_num)
                    logger.info(f"Parallel Call initiated for {phone}")
                return phone
            except Exception as e:
                logger.error(f"Background {method} failed for {phone}: {e}")
                return None

        # Fan-out: Every notification (SMS and Voice) for Every contact runs in its own thread
        notified = []
        with ThreadPoolExecutor(max_workers=len(contacts)*2) as notify_exec:
            # Schedule SMS and Calls separately for maximum parallelism
            futures = []
            for c in contacts:
                futures.append(notify_exec.submit(dispatch_alert, c, "sms"))
                futures.append(notify_exec.submit(dispatch_alert, c, "call"))
            
            for future in futures:
                res = future.result()
                if res: notified.append(res)

        alert.notified_contacts = json.dumps(list(set(notified)))
        db.session.commit()
        logger.info(f"SOS Alert #{alert_id} notifications completed. Notified: {len(set(notified))} ids.")


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
