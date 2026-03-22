"""
WSAS Chatbot Blueprint
Rule-based NLP chatbot for safety assistance.
Intent detection without external paid APIs.
"""

import requests
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import ChatLog

chatbot_bp = Blueprint("chatbot", __name__)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# INTENT DETECTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class IntentDetector:
    """
    Rule-based NLP using keyword matching + pattern scoring.
    No external API needed. Expandable to ML (future scope).
    """

    INTENTS = {
        "sos_emergency": {
            "keywords": ["help", "danger", "emergency", "sos", "scared", "afraid",
                         "attack", "hurt", "save me", "call police", "in trouble",
                         "unsafe", "threatening", "following me", "stalker"],
            "priority": 10,  # Highest — triggers SOS
            "response": (
                "🚨 EMERGENCY DETECTED! I'm triggering your SOS alert NOW.\n\n"
                "Stay calm. Your emergency contacts are being notified.\n"
                "• Try to reach a public, well-lit area\n"
                "• Make noise to attract attention\n"
                "• Call 100 (Police) or 112 (Emergency)\n\n"
                "You are NOT alone. Help is on the way! 💪"
            ),
            "trigger_sos": True
        },
        "find_police": {
            "keywords": ["police station", "nearest police", "cop", "law", "authorities",
                         "police number", "emergency number", "police"],
            "priority": 7,
            "response": (
                "📍 Emergency Numbers:\n\n"
                "🚔 Police: 100\n"
                "🚑 Ambulance: 108\n"
                "🔥 Fire: 101\n"
                "📞 All Emergencies: 112\n"
                "👩 Women Helpline: 1091\n"
                "🛡 CRPC Helpline: 181\n\n"
            ),
            "trigger_sos": False
        },
        "find_hospital": {
            "keywords": ["hospital", "clinic", "nearest hospital", "doctor", "medical",
                         "ambulance", "injured", "bleeding"],
            "priority": 7,
            "response": (
                "🏥 Medical Emergency Numbers:\n\n"
                "🚑 Ambulance: 108\n"
                "📞 All Emergencies: 112\n\n"
            ),
            "trigger_sos": False
        },
        "feeling_unsafe": {
            "keywords": ["unsafe", "feel unsafe", "not safe", "feel scared",
                         "worried", "nervous", "anxious", "unwell", "bad feeling"],
            "priority": 8,
            "response": (
                "💙 I hear you, and your feelings are valid.\n\n"
                "Here's what you can do right now:\n"
                "• Stay in a bright, crowded place\n"
                "• Text a trusted person your location\n"
                "• Keep your phone charged\n"
                "• Trust your instincts — if something feels wrong, ACT\n\n"
                "⚡ Say 'SOS' or tap the SOS button if you need immediate help.\n"
                "Shall I notify your emergency contacts that you feel unsafe?"
            ),
            "trigger_sos": False
        },
        "safety_tips": {
            "keywords": ["tips", "safety", "advice", "suggest", "how to be safe",
                         "precautions", "protection", "what should i do"],
            "priority": 3,
            "response": (
                "🛡 Personal Safety Tips:\n\n"
                "📍 Location:\n"
                "• Always share your live location with trusted contacts\n"
                "• Avoid poorly lit, isolated areas at night\n"
                "• Know your route before traveling\n\n"
                "📱 Technology:\n"
                "• Keep phone fully charged\n"
                "• Save emergency numbers on speed dial\n"
                "• Use WSAS voice detection feature\n\n"
                "🧠 Awareness:\n"
                "• Trust your instincts\n"
                "• Walk confidently and stay alert\n"
                "• If followed, enter a shop or public space\n\n"
                "Would you like to activate live safety monitoring?"
            ),
            "trigger_sos": False
        },
        "hello_greeting": {
            "keywords": ["hello", "hi", "hey", "good morning", "good evening", "howdy"],
            "priority": 1,
            "response": (
                "👋 Hello! I'm WSAS Safety Assistant.\n\n"
                "I'm here to help you stay safe. Here's what I can do:\n"
                "• 🚨 Trigger emergency SOS\n"
                "• 📍 Find nearby help (police, hospital)\n"
                "• 🛡 Share safety tips\n"
                "• 💬 Listen and support you\n\n"
                "How are you feeling right now? Type anything to get started."
            ),
            "trigger_sos": False
        },
        "location_sharing": {
            "keywords": ["share location", "track me", "send location", "where am i",
                         "live location", "gps"],
            "priority": 5,
            "response": (
                "📡 Location Services:\n\n"
                "Your live location can be shared automatically with emergency contacts.\n"
                "• Go to Dashboard → Enable Live Tracking\n"
                "• Your location updates every 30 seconds\n"
                "• Contacts can see you on a map\n\n"
                "⚡ During SOS, location is sent automatically.\n"
                "Shall I enable live tracking now?"
            ),
            "trigger_sos": False
        }
    }

    def detect_intent(self, user_message: str) -> dict:
        """
        Score each intent based on keyword matches.
        Returns best matching intent.
        """
        message = user_message.lower().strip()
        best_intent = None
        best_score = 0

        for intent_name, intent_data in self.INTENTS.items():
            score = 0
            for keyword in intent_data["keywords"]:
                if keyword in message:
                    # Exact phrase match scores higher
                    if keyword == message:
                        score += 10
                    elif f" {keyword} " in f" {message} ":
                        score += 5
                    else:
                        score += 2
            
            # Multiply by priority weight
            weighted_score = score * (intent_data["priority"] / 10)

            if weighted_score > best_score:
                best_score = weighted_score
                best_intent = intent_name

        if best_intent and best_score > 0:
            return {
                "intent": best_intent,
                "confidence": min(best_score / 10, 1.0),
                "response": self.INTENTS[best_intent]["response"],
                "trigger_sos": self.INTENTS[best_intent]["trigger_sos"]
            }
        
        # Default fallback response
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "response": (
                "I'm not sure how to help with that. Try saying:\n"
                "• 'I feel unsafe'\n"
                "• 'SOS' or 'Help me'\n"
                "• 'Safety tips'\n"
                "• 'Nearest police station'\n\n"
                "Or tap the SOS button if you're in immediate danger! 🆘"
            ),
            "trigger_sos": False
        }


# ─────────────────────────────────────────────────────────────────────────────
# OVERPASS API HELPER
# ─────────────────────────────────────────────────────────────────────────────
def get_nearby_facilities(lat, lon, amenity="hospital"):
    try:
        url = "http://overpass-api.de/api/interpreter"
        query = f"""
        [out:json][timeout:10];
        nwr["amenity"="{amenity}"](around:5000,{lat},{lon});
        out center 4;
        """
        response = requests.post(url, data=query, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                name = tags.get("name")
                if not name: continue
                # Try to build address
                addr = tags.get("addr:full", tags.get("addr:street", ""))
                addr_city = tags.get("addr:city", "")
                full_addr = f"{addr}, {addr_city}".strip(" ,")
                
                if full_addr:
                    results.append(f"• <b>{name}</b><br><span style='font-size: 0.85rem; opacity: 0.8;'>{full_addr}</span>")
                else:
                    results.append(f"• <b>{name}</b><br><span style='font-size: 0.85rem; opacity: 0.8;'>(Address unlisted)</span>")
            return results
    except Exception as e:
        logger.error(f"Overpass API error: {e}")
    return []

# ─────────────────────────────────────────────────────────────────────────────
# CHATBOT ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
detector = IntentDetector()

@chatbot_bp.route("/message", methods=["POST"])
@jwt_required()
def chat():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    lat = data.get("lat")
    lon = data.get("lon")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    if len(message) > 500:
        return jsonify({"error": "Message too long (max 500 chars)"}), 400

    # Detect intent
    result = detector.detect_intent(message)
    sos_triggered = False
    is_html = False
    
    # Inject Maps URL for location-based queries
    if result["intent"] in ["find_police", "find_hospital"]:
        is_html = True
        query = "police+station" if result["intent"] == "find_police" else "hospital"
        overpass_amenity = "police" if result["intent"] == "find_police" else "hospital"
        map_title = "Police Stations" if result["intent"] == "find_police" else "Hospitals"
        
        # Format response with HTML (since we will render as is_html)
        result["response"] = result["response"].replace("\n", "<br>")
        
        if lat and lon:
            # 1. Fetch real addresses
            facilities = get_nearby_facilities(lat, lon, overpass_amenity)
            if facilities:
                result["response"] += f"<br><br>🏨 <strong>Nearest {map_title} Found:</strong><br>"
                result["response"] += "<br>".join(facilities)
                
            # 2. Add GPS Link
            maps_link = f"https://www.google.com/maps/search/{query}/@{lat},{lon},15z"
            result["response"] += (
                f"<br><br>📍 <a href='{maps_link}' target='_blank' class='btn btn-sm btn-outline-pink mt-1'>"
                f"View All on Map <i class='fas fa-external-link-alt ms-1'></i></a>"
            )
        else:
            result["response"] += "<br><em>(Enable GPS location to receive nearby map links automatically)</em>"

    # Auto-trigger SOS if high-risk intent detected
    if result["trigger_sos"] and result["confidence"] > 0.3:
        try:
            from blueprints.alerts import trigger_sos
            # We'll flag it; the frontend will handle the SOS call
            sos_triggered = True
        except Exception as e:
            logger.error(f"Auto-SOS from chat failed: {e}")

    # Log conversation
    log = ChatLog(
        user_id      = user_id,
        user_message = message,
        bot_response = result["response"],
        intent       = result["intent"],
        triggered_sos= sos_triggered
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "response": result["response"],
        "intent": result["intent"],
        "confidence": round(result["confidence"], 2),
        "trigger_sos": sos_triggered,
        "is_html": is_html
    }), 200


@chatbot_bp.route("/history", methods=["GET"])
@jwt_required()
def chat_history():
    user_id = int(get_jwt_identity())
    logs = ChatLog.query.filter_by(user_id=user_id)\
                        .order_by(ChatLog.created_at.desc())\
                        .limit(50).all()
    return jsonify({
        "history": [{
            "user": l.user_message,
            "bot": l.bot_response,
            "intent": l.intent,
            "time": l.created_at.isoformat()
        } for l in logs]
    }), 200
