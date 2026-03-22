"""
WSAS Authentication Blueprint
Handles: Register, Login, Refresh Token, Logout, Profile
Security: bcrypt passwords, JWT tokens, input validation
"""

import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
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

    # Input validation
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
        errors["password"] = "Password needs 8+ chars, uppercase, digit, special char"
    if not validate_phone(phone):
        errors["phone"] = "Invalid phone number"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(name=name, email=email, phone=phone)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info(f"New user registered: {email}")
    return jsonify({"message": "Registration successful", "user": user.to_dict()}), 201


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


# ─── Refresh Token ───────────────────────────────────────────────────────────
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


# ─── Get Profile ─────────────────────────────────────────────────────────────
@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict()), 200


# ─── Update Profile ───────────────────────────────────────────────────────────
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
        # Accept base64 string or URL
        user.profile_photo = pp if pp else None

    db.session.commit()
    return jsonify({"message": "Profile updated", "user": user.to_dict()}), 200


# ─── Change Password ─────────────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    old_pw = str(data.get("old_password", ""))
    new_pw = str(data.get("new_password", ""))

    if not user.check_password(old_pw):
        return jsonify({"error": "Current password incorrect"}), 401

    if not validate_password(new_pw):
        return jsonify({"error": "New password does not meet requirements"}), 422

    user.set_password(new_pw)
    db.session.commit()
    logger.info(f"Password changed for user {user_id}")
    return jsonify({"message": "Password updated successfully"}), 200
