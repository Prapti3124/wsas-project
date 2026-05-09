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
        user.is_email_verified = True
        user.is_active = True
        user.set_password(password)
    else:
        # Create a brand-new user record
        logger.info(f"Creating new user account: {email}")
        user = User(name=name, email=email, phone=phone, is_email_verified=True, is_active=True)
        user.set_password(password)
        db.session.add(user)

    try:
        db.session.commit()
        logger.info(f"User registered successfully: {email} (ID: {user.id})")
    except Exception as e:
        db.session.rollback()
        logger.error(f"DB commit failed during register for {email}: {e}")
        return jsonify({"error": "Internal server error. Please try again."}), 500

    access_token  = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "message": "Registration successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200


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

