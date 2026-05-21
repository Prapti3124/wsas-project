"""
WSAS Alerts Blueprint
Handles: SOS trigger, alert history, Twilio SMS/call notifications,
         status updates, emergency contacts CRUD.
"""
# pylint: disable=line-too-long, logging-fstring-interpolation, broad-exception-caught
# flake8: noqa


import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests as req_lib
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from twilio.rest import Client

from extensions import db
from models import Alert, User, EmergencyContact
from ai.risk_engine import RiskEngine

alerts_bp = Blueprint("alerts", __name__)
logger = logging.getLogger(__name__)


# ─── Trigger SOS Alert ────────────────────────────────────────────────────────
@alerts_bp.route("/sos", methods=["POST"])
@jwt_required()
def trigger_sos():
    """Trigger an SOS alert for the current user."""
    user_id = int(get_jwt_identity())
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

    # Check how many contacts will be notified — include in response for frontend feedback
    contacts_count = EmergencyContact.query.filter_by(user_id=user_id).count()

    # Create alert record immediately with placeholder risk
    alert = Alert(
        user_id=user_id,
        alert_type=data.get("alert_type", "manual"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        address=data.get("address", ""),
        message=data.get("message", "I need help!"),
        risk_score=0.0,  # Will be updated in background
        status="active"
    )
    db.session.add(alert)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create alert record: {e}")
        return jsonify({"error": "Failed to trigger SOS on server."}), 500

    if contacts_count == 0:
        logger.warning(f"SOS Alert #{alert.id} created for user {user_id} but NO emergency contacts are configured — no SMS/call will be sent.")

    # Start background processing for AI and Notifications
    # We pass the app object to the thread to reconstruct context
    app = current_app._get_current_object()
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(process_sos_background, app, alert.id, data)

    logger.info(f"SOS Alert #{alert.id} accepted for processing for user {user_id}. Contacts to notify: {contacts_count}")

    return jsonify({
        "message": "SOS Alert triggered and processing in background.",
        "alert": alert.to_dict(),
        "status": "processing",
        "contacts_count": contacts_count  # Immediate count so frontend can warn if 0
    }), 201


def process_sos_background(app, alert_id, data):
    """Background task to run AI engine and notify contacts."""
    with app.app_context():
        alert = Alert.query.get(alert_id)
        if not alert:
            return

        user_id = alert.user_id
        user = User.query.get(user_id)
        user_name = user.name if user else "a SAKHI User"

        # 1. Background AI Risk Calculation
        try:
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

        def to_gsm7(text):
            """Filter text to strictly contain only standard GSM-7 characters to prevent UCS-2 encoding."""
            if not text:
                return ""
            gsm7_chars = (
                "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
            )
            gsm7_ext = "^{}\\[~]|€"
            all_gsm7 = gsm7_chars + gsm7_ext
            return "".join(c for c in text if c in all_gsm7)

        def dispatch_alert(contact, method="sms"):
            """Thread-safe worker to send SMS or Call."""
            phone = "".join(contact.phone.split())
            try:
                body = ""
                twiml = ""
                if method == "sms":
                    # Smart Location Formatting: Handle missing GPS
                    if alert.latitude and alert.longitude:
                        lat_str = f"{alert.latitude:.7f}"
                        lon_str = f"{alert.longitude:.7f}"
                        maps_url = f"https://maps.google.com/?q={lat_str},{lon_str}"
                        accuracy = data.get("accuracy")
                        acc_line = f"Accuracy: {round(accuracy)}m\n" if accuracy else ""

                        # Reverse geocode to get human-readable address
                        readable_addr = ""
                        try:
                            geo_resp = req_lib.get(
                                "https://nominatim.openstreetmap.org/reverse",
                                params={"lat": alert.latitude, "lon": alert.longitude, "format": "json"},
                                headers={"User-Agent": "SAKHI-Safety-App/1.0"},
                                timeout=5
                            )
                            if geo_resp.status_code == 200:
                                geo_data = geo_resp.json()
                                addr = geo_data.get("address", {})
                                parts = []
                                if addr.get("suburb"):
                                    parts.append(addr["suburb"])
                                if addr.get("city") or addr.get("town") or addr.get("village"):
                                    parts.append(addr.get("city") or addr.get("town") or addr.get("village"))
                                if addr.get("state"):
                                    parts.append(addr["state"])
                                if addr.get("country"):
                                    parts.append(addr["country"])
                                readable_addr = ", ".join(parts)
                        except Exception as geo_err:
                            logger.warning(f"Reverse geocoding failed: {geo_err}")

                        # Limit address size to keep message within GSM-7 segment limits
                        addr_part = ""
                        if readable_addr:
                            clean_addr = to_gsm7(readable_addr)
                            if len(clean_addr) > 50:
                                clean_addr = clean_addr[:47] + "..."
                            addr_part = f"Addr: {clean_addr}\n"

                        location_line = f"Loc: {maps_url}\n{addr_part}{acc_line}"
                    else:
                        location_line = "Loc: Unavailable (No GPS signal)\n"

                    # IST time (UTC+5:30)
                    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
                    time_str = ist.strftime('%H:%M IST')

                    # Clean custom message
                    msg_part = ""
                    if alert.message and alert.message != "I need help!":
                        clean_msg = to_gsm7(alert.message)
                        if len(clean_msg) > 30:
                            clean_msg = clean_msg[:27] + "..."
                        msg_part = f"\nMsg: {clean_msg}"

                    # Clean user name
                    clean_name = to_gsm7(user_name)

                    body = (f"SOS! {clean_name} is in danger!\n"
                            f"{location_line}"
                            f"Time: {time_str}"
                            f"{msg_part}")

                    # Final validation to ensure pure GSM-7 body
                    body = to_gsm7(body)

                    logger.info(f"Prepared SOS SMS to {phone}: {body}")
                else:
                    # Clean user name for voice call synthesis
                    clean_name = to_gsm7(user_name)
                    twiml = f"<Response><Say>SOS! Emergency alert from {clean_name}. Check your phone for location.</Say></Response>"

                if not twilio_config["account_sid"] or not twilio_config["auth_token"]:
                    logger.warning(f"Twilio not configured. [DEV MODE] Simulated {method} to {phone}:\n{body if method == 'sms' else twiml}")
                    print(f"\n==========\n[DEV MODE] Simulated {method.upper()} to {phone}:\n{body if method == 'sms' else twiml}\n==========\n")
                    return phone

                # client = Client(...) already imported at top level
                client = Client(twilio_config["account_sid"], twilio_config["auth_token"])
                from_num = twilio_config["from_number"]

                if method == "sms":
                    msg_obj = client.messages.create(body=body, from_=from_num, to=phone)
                    logger.info(f"Parallel SMS sent to {phone}. SID: {msg_obj.sid}, Status: {msg_obj.status}")
                else:
                    call_obj = client.calls.create(twiml=twiml, to=phone, from_=from_num)
                    logger.info(f"Parallel Call initiated for {phone}. SID: {call_obj.sid}, Status: {call_obj.status}")
                return phone
            except Exception as e:
                logger.error(f"Background {method} failed for {phone}: {e}")
                if hasattr(e, 'code'):
                    logger.error(f"Twilio Error Code: {e.code} - {getattr(e, 'msg', '')}")
                print(f"\n==========\n[TWILIO FAILURE] Simulated {method.upper()} to {phone}:\n{body if method == 'sms' else 'VOICE CALL'}\n==========\n")
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
                if res:
                    notified.append(res)

        alert.notified_contacts = json.dumps(list(set(notified)))
        db.session.commit()
        logger.info(f"SOS Alert #{alert_id} notifications completed. Notified: {len(set(notified))} ids.")


# ─── Get Alert History ────────────────────────────────────────────────────────
@alerts_bp.route("/history", methods=["GET"])
@jwt_required()
def alert_history():
    """Retrieve history of alerts for the current user."""
    user_id = int(get_jwt_identity())
    page = request.args.get("page", 1, type=int)
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
    """Update the status of an existing alert."""
    user_id = int(get_jwt_identity())
    alert = Alert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    data = request.get_json(silent=True) or {}
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
    """Get emergency contacts for the current user."""
    user_id = int(get_jwt_identity())
    contacts = EmergencyContact.query.filter_by(user_id=user_id).all()
    return jsonify({"contacts": [c.to_dict() for c in contacts]}), 200


@alerts_bp.route("/contacts", methods=["POST"])
@jwt_required()
def add_contact():
    """Add a new emergency contact for the current user."""
    user_id = int(get_jwt_identity())
    max_contacts = current_app.config.get("MAX_CONTACTS", 5)

    existing = EmergencyContact.query.filter_by(user_id=user_id).count()
    if existing >= max_contacts:
        return jsonify({"error": f"Maximum {max_contacts} contacts allowed"}), 400

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not name or not phone:
        return jsonify({"error": "Name and phone required"}), 422

    contact = EmergencyContact(
        user_id=user_id,
        name=name,
        phone=phone,
        relation=data.get("relation", "")
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({"message": "Contact added", "contact": contact.to_dict()}), 201


@alerts_bp.route("/contacts/<int:contact_id>", methods=["DELETE"])
@jwt_required()
def delete_contact(contact_id):
    """Delete an emergency contact."""
    user_id = int(get_jwt_identity())
    contact = EmergencyContact.query.filter_by(id=contact_id, user_id=user_id).first()
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    db.session.delete(contact)
    db.session.commit()
    return jsonify({"message": "Contact deleted"}), 200
