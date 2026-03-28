"""
WSAS Authentication Blueprint
Handles: Register, Login, Refresh Token, Logout, Profile
Security: bcrypt passwords, JWT tokens, input validation
"""

import re
import logging
import random
import smtplib
import ssl
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def validate_email(email):
    return re.match(r"^[\w.+\-]+@[\w\-]+\.[a-z]{2,}$", email.lower())

def validate_phone(phone):
    return re.match(r"^\+?[1-9]\d{7,14}$", phone)

def validate_password(password):
    """Min 8 chars, 1 uppercase, 1 digit, 1 special char."""
    return (len(password) >= 8 and
            re.search(r"[A-Z]", password) and
            re.search(r"\d", password) and
            re.search(r"[!@#$%^&*(),.?\":{}|<>]", password))

def send_otp_email(receiver_email, otp_code):
    """Send OTP via SMTP."""
    try:
        smtp_server = current_app.config["MAIL_SERVER"]
        smtp_port = current_app.config["MAIL_PORT"]
        sender_email = current_app.config["MAIL_USERNAME"]
        password = current_app.config["MAIL_PASSWORD"]
        sender_display = current_app.config.get("MAIL_DEFAULT_SENDER", sender_email)

        if not sender_email or not password:
            logger.error("SMTP credentials not configured.")
            return False

        message = MIMEMultipart("alternative")
        message["Subject"] = f"{otp_code} is your WSAS verification code"
        message["From"] = sender_display
        message["To"] = receiver_email

        text = f"Your WSAS verification code is: {otp_code}. It expires in 10 minutes."
        html = f"""
        <html>
        <body>
            <div style="font-family: sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 10px; max-width: 500px;">
                <h2 style="color: #db2777;">WSAS Verification</h2>
                <p>Hello,</p>
                <p>Your one-time password (OTP) for registration is:</p>
                <div style="font-size: 32px; font-weight: bold; color: #db2777; margin: 20px 0;">{otp_code}</div>
                <p style="color: #666; font-size: 14px;">This code will expire in 10 minutes. If you didn't request this, please ignore this email.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #999;">Women Safety Alert System (WSAS)</p>
            </div>
        </body>
        </html>
        """
        message.attach(MIMEText(text, "plain"))
        message.attach(MIMEText(html, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if current_app.config.get("MAIL_USE_TLS", True):
                server.starttls(context=context)
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        
        logger.info(f"OTP sent to {receiver_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


# ─── Register ─────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    name     = str(data.get("name", "")).strip()
    email    = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    phone    = str(data.get("phone", "")).strip()

    errors = {}
    if not name or len(name) < 2:
        errors["name"] = "Name must be at least 2 characters"
    if not validate_email(email):
        errors["email"] = "Invalid email address"
    if not validate_password(password):
        errors["password"] = "Password: 8+ chars, uppercase, digit, special"
    
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    user = User.query.filter_by(email=email).first()
    if user:
        if user.is_email_verified:
            return jsonify({"error": "Email already registered and verified"}), 409
        # Reuse unverified account
    else:
        user = User(name=name, email=email, phone=phone)
        user.set_password(password)
        db.session.add(user)

    # Generate OTP
    otp = f"{random.randint(100000, 999999)}"
    user.otp_code = otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    user.is_email_verified = False # Ensure false for new/reuse
    db.session.commit()

    if send_otp_email(email, otp):
        return jsonify({"message": "OTP sent to email", "email": email}), 200
    else:
        return jsonify({"error": "Could not send OTP email. Please try again."}), 500


# ─── Google Login/Register ────────────────────────────────────────────────────
@auth_bp.route("/google-login", methods=["POST"])
def google_login():
    data = request.get_json(silent=True) or {}
    token = data.get("credential") # Google ID Token
    if not token:
        return jsonify({"error": "No Google credential provided"}), 400

    try:
        # Verify token with Google API directly to avoid heavy google-auth lib
        resp = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
        if resp.status_code != 200:
            return jsonify({"error": "Invalid Google token"}), 401
        
        info = resp.json()
        if info.get("aud") != current_app.config["GOOGLE_CLIENT_ID"]:
             return jsonify({"error": "Invalid Audience"}), 401

        email = info.get("email").lower()
        name = info.get("name")
        google_id = info.get("sub")
        picture = info.get("picture")

        user = User.query.filter((User.email == email) | (User.google_id == google_id)).first()

        if not user:
            # Create new user via Google
            user = User(name=name, email=email, google_id=google_id, profile_photo=picture)
            user.is_email_verified = False # Still needs OTP for first time registration
            db.session.add(user)
            db.session.commit()

        if not user.is_email_verified:
            # Send OTP for registration completion
            otp = f"{random.randint(100000, 999999)}"
            user.otp_code = otp
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            if send_otp_email(email, otp):
                return jsonify({"message": "Verification required", "email": email, "new_user": True}), 200
            else:
                return jsonify({"error": "Could not send OTP"}), 500

        # Existing verified user - Login directly
        user.last_login = datetime.utcnow()
        db.session.commit()

        access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
        refresh_token = create_refresh_token(identity=str(user.id))

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Google login error: {e}")
        return jsonify({"error": "Authentication failed"}), 500


# ─── Verify OTP ──────────────────────────────────────────────────────────────
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    code = data.get("otp", "").strip()

    if not email or not code:
        return jsonify({"error": "Email and OTP required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.otp_code != code:
        return jsonify({"error": "Invalid OTP code"}), 400

    if user.otp_expiry < datetime.utcnow():
        return jsonify({"error": "OTP expired"}), 400

    # Success
    user.is_email_verified = True
    user.otp_code = None
    user.otp_expiry = None
    user.last_login = datetime.utcnow()
    db.session.commit()

    access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "message": "Email verified and logged in",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200


# ─── Login ───────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    email    = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        logger.warning(f"Failed login attempt for: {email}")
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"error": "Account deactivated. Contact admin."}), 403

    if not user.is_email_verified:
        # Re-send OTP if not verified
        otp = f"{random.randint(100000, 999999)}"
        user.otp_code = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()
        send_otp_email(email, otp)
        return jsonify({"error": "Email not verified. OTP sent again.", "email": email, "needs_verification": True}), 401

    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()

    access_token  = create_access_token(identity=str(user.id),
                                         additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    logger.info(f"User logged in: {email}")
    return jsonify({
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    if not user:
        return jsonify({"error": "User not found"}), 404

    new_token = create_access_token(
        identity=identity,
        additional_claims={"role": user.role}
    )
    return jsonify({"access_token": new_token}), 200


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict()), 200


@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    if "name" in data and len(str(data["name"]).strip()) >= 2:
        user.name = str(data["name"]).strip()
    if "phone" in data and validate_phone(str(data["phone"])):
        user.phone = str(data["phone"]).strip()
    
    if "alternate_phone" in data:
        ap = str(data["alternate_phone"]).strip()
        user.alternate_phone = ap if ap else None
    
    if "address" in data:
        ad = str(data["address"]).strip()
        user.address = ad if ad else None

    if "profile_photo" in data:
        pp = str(data["profile_photo"]).strip()
        user.profile_photo = pp if pp else None

    db.session.commit()
    return jsonify({"message": "Profile updated", "user": user.to_dict()}), 200


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    old_pw = str(data.get("old_password", ""))
    new_pw = str(data.get("new_password", ""))

    if not user.password_hash:
        return jsonify({"error": "OAuth users cannot change password directly"}), 422

    if not user.check_password(old_pw):
        return jsonify({"error": "Current password incorrect"}), 401

    if not validate_password(new_pw):
        return jsonify({"error": "New password does not meet requirements"}), 422

    user.set_password(new_pw)
    db.session.commit()
    logger.info(f"Password changed for user {user_id}")
    return jsonify({"message": "Password updated successfully"}), 200
