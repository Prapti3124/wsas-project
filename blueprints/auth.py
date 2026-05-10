"""
WSAS Authentication Blueprint
Handles: Register, Login, Refresh Token, Logout, Profile
Security: bcrypt passwords, JWT tokens, input validation
"""

import re
import logging
import random
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
import smtplib
from email.message import EmailMessage
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

def send_otp_email(to_email, otp_code):
    try:
        sender_email = current_app.config.get("MAIL_USERNAME")
        sender_password = current_app.config.get("MAIL_PASSWORD")
        smtp_server = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
        smtp_port = int(current_app.config.get("MAIL_PORT", 587))
        
        if not sender_email or not sender_password:
            logger.warning(f"SMTP not configured. Mocking OTP {otp_code} for {to_email}")
            print(f"\n==========\n[DEV MODE] OTP for {to_email}: {otp_code}\n==========\n")
            return True

        msg = EmailMessage()
        msg['Subject'] = 'Your SAKHI Verification Code'
        msg['From'] = current_app.config.get("MAIL_DEFAULT_SENDER", sender_email)
        msg['To'] = to_email
        msg.set_content(f"Welcome to SAKHI!\n\nYour 6-digit verification code is: {otp_code}\n\nThis code will expire in 10 minutes.\nStay Safe!")

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=5)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        # Print for dev fallback
        print(f"\n==========\n[SMTP FAILURE] OTP for {to_email}: {otp_code}\n==========\n")
        return False

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

    # ── Input Validation ──────────────────────────────────────────────────────
    errors = {}
    if not name or len(name) < 2:
        errors["name"] = "Name must be at least 2 characters"
    if not validate_email(email):
        errors["email"] = "Invalid email address"
    if not validate_password(password):
        errors["password"] = "Password must be 8+ chars with uppercase, digit & special character"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    user = User.query.filter_by(email=email).first()

    if user:
        if user.is_email_verified:
            logger.warning(f"Registration attempt for already verified email: {email}")
            return jsonify({"error": "Email already registered and verified"}), 409

        # Update existing unverified account with fresh registration data
        logger.info(f"Re-registering existing unverified account: {email}")
        user.name = name
        user.phone = phone
        user.is_email_verified = False
        user.is_active = True
        user.set_password(password)
    else:
        # Create a brand-new user record
        logger.info(f"Creating new user account: {email}")
        user = User(name=name, email=email, phone=phone, is_email_verified=False, is_active=True)
        user.set_password(password)
        db.session.add(user)

    # Generate OTP
    otp_code = str(random.randint(100000, 999999))
    user.otp_code = otp_code
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)

    try:
        db.session.commit()
        logger.info(f"User OTP generated successfully: {email} (ID: {user.id})")
    except Exception as e:
        db.session.rollback()
        logger.error(f"DB commit failed during register for {email}: {e}")
        return jsonify({"error": "Internal server error. Please try again."}), 500

    send_otp_email(email, otp_code)

    return jsonify({
        "message": "OTP sent",
        "email": email
    }), 200

# ─── Verify OTP ───────────────────────────────────────────────────────────────
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    otp = str(data.get("otp", "")).strip()

    if not email or not otp:
        return jsonify({"error": "Email and OTP required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_email_verified:
        return jsonify({"error": "Email already verified"}), 400

    if user.otp_code != otp:
        return jsonify({"error": "Invalid OTP"}), 401

    if not user.otp_expiry or datetime.utcnow() > user.otp_expiry:
        return jsonify({"error": "OTP has expired"}), 401

    # Mark as verified
    user.is_email_verified = True
    user.otp_code = None
    user.otp_expiry = None
    db.session.commit()

    # Generate tokens
    access_token  = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    logger.info(f"User verified via OTP: {email}")
    return jsonify({
        "message": "Verification successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200

# ─── Resend OTP ───────────────────────────────────────────────────────────────
@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    if not email:
        return jsonify({"error": "Email required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.is_email_verified:
        return jsonify({"error": "Email already verified"}), 400

    otp_code = str(random.randint(100000, 999999))
    user.otp_code = otp_code
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()

    send_otp_email(email, otp_code)

    return jsonify({"message": "OTP resent"}), 200


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
            user.is_email_verified = True
            user.is_active = True
            db.session.add(user)
            db.session.commit()

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
        return jsonify({"error": "Please verify your email via OTP first."}), 403



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
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data and len(str(data["name"]).strip()) >= 2:
        user.name = str(data["name"]).strip()
    if "phone" in data:
        ph = str(data["phone"]).strip()
        if ph and validate_phone(ph):
            user.phone = ph
        elif not ph:
            user.phone = None
    
    if "alternate_phone" in data:
        ap = str(data["alternate_phone"]).strip()
        user.alternate_phone = ap if ap else None
    
    if "address" in data:
        ad = str(data["address"]).strip()
        user.address = ad if ad else None

    if "profile_photo" in data:
        pp = str(data["profile_photo"]).strip()
        user.profile_photo = pp if pp else None

    try:
        db.session.commit()
        logger.info(f"Profile updated for user {user_id}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update profile for user {user_id}: {e}")
        return jsonify({"error": "Failed to save profile. Please try again."}), 500

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


@auth_bp.route("/make-me-admin", methods=["POST"])
@jwt_required()
def make_me_admin():
    """Hidden endpoint to easily promote the current user to Admin (useful for Render ephemeral DBs)."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    user.role = "admin"
    db.session.commit()
    
    # Must re-issue tokens because 'role' is baked into the JWT claims
    access_token  = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))
    
    return jsonify({
        "message": "You are now an admin!",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200

