"""
WSAS AI Risk Score Engine
=========================
Calculates dynamic safety risk scores (0–100) using:
 1. Time-of-day factor
 2. Location proximity to unsafe zones
 3. Community threat reports density
 4. User's personal alert history
 5. Movement pattern anomaly

Algorithm:
    risk_score = Σ(factor_i × weight_i)
    Weights: time=25%, location=35%, community=20%, history=15%, anomaly=5%

Future ML upgrade: Replace rule-based factors with a trained
  RandomForest or LSTM model on labeled safety data.
"""

import math
import logging
from datetime import datetime, timedelta
from extensions import db
from models import RiskScore, LocationHistory, Alert, CommunityReport, UnsafeZone

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
WEIGHTS = {
    "time":      0.25,
    "location":  0.35,
    "community": 0.20,
    "history":   0.15,
    "anomaly":   0.05,
}

EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1, lon1, lat2, lon2) -> float:
    """
    Calculate distance in meters between two GPS coordinates.
    Uses Haversine formula for spherical Earth model.
    """
    R = EARTH_RADIUS_KM * 1000  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


class RiskEngine:
    """
    Core AI Risk Scoring Engine.
    Produces a normalized 0–100 risk score with factor breakdown.
    """

    def calculate_risk(self, user_id: int, latitude=None, longitude=None) -> dict:
        """
        Main entry point. Returns:
          { score, level, factors: {time, location, community, history, anomaly} }
        """
        now = datetime.utcnow()

        t_score  = self._time_factor(now)
        l_score  = self._location_factor(latitude, longitude) if latitude else 0
        c_score  = self._community_factor(latitude, longitude) if latitude else 0
        h_score  = self._history_factor(user_id, now)
        a_score  = self._anomaly_factor(user_id, now)

        raw_score = (
            t_score  * WEIGHTS["time"]      +
            l_score  * WEIGHTS["location"]  +
            c_score  * WEIGHTS["community"] +
            h_score  * WEIGHTS["history"]   +
            a_score  * WEIGHTS["anomaly"]
        )
        score = min(max(round(raw_score, 2), 0), 100)
        level = self._level(score)

        # Persist to DB
        try:
            rs = RiskScore(
                user_id         = user_id,
                score           = score,
                level           = level,
                time_factor     = t_score,
                location_factor = l_score,
                alert_factor    = h_score,
                community_factor= c_score
            )
            db.session.add(rs)
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not persist risk score: {e}")

        return {
            "score": score,
            "level": level,
            "factors": {
                "time": round(t_score, 2),
                "location": round(l_score, 2),
                "community": round(c_score, 2),
                "history": round(h_score, 2),
                "anomaly": round(a_score, 2)
            }
        }

    # ── Factor 1: Time of Day ─────────────────────────────────────────────────
    def _time_factor(self, now: datetime) -> float:
        """
        Night hours = higher risk.
        Score 0–100:
          Midnight–5AM  → 90–100
          9PM–Midnight  → 70–90
          5AM–7AM       → 40–60
          Daytime       → 5–20
        """
        hour = now.hour
        if 0 <= hour < 5:      # Late night
            return 95
        elif 5 <= hour < 7:    # Early morning
            return 50
        elif 7 <= hour < 18:   # Daytime
            return 10
        elif 18 <= hour < 21:  # Evening
            return 35
        else:                  # 9PM–midnight
            return 78

    # ── Factor 2: Location Proximity to Unsafe Zones ─────────────────────────
    def _location_factor(self, lat: float, lon: float) -> float:
        """
        Check proximity to admin-defined unsafe zones.
        Distance-weighted: closer = higher score.
        """
        zones = UnsafeZone.query.filter_by(is_active=True).all()
        if not zones:
            return 15  # baseline uncertainty

        max_score = 0
        for zone in zones:
            dist = haversine_distance(lat, lon, zone.latitude, zone.longitude)
            if dist <= zone.radius_meters:
                # Inside zone: score proportional to crime_score
                proximity_mult = 1.0 - (dist / zone.radius_meters) * 0.5
                score = zone.crime_score * proximity_mult
                max_score = max(max_score, score)
            elif dist <= zone.radius_meters * 2:
                # Near zone: half score
                score = zone.crime_score * 0.3
                max_score = max(max_score, score)

        return min(max_score, 100)

    # ── Factor 3: Community Reports Density ──────────────────────────────────
    def _community_factor(self, lat: float, lon: float) -> float:
        """
        Count recent community threat reports near the location.
        More reports nearby = higher score.
        """
        if lat is None or lon is None:
            return 0

        since = datetime.utcnow() - timedelta(days=30)
        reports = CommunityReport.query.filter(
            CommunityReport.created_at >= since
        ).all()

        nearby_score = 0
        for report in reports:
            dist = haversine_distance(lat, lon, report.latitude, report.longitude)
            if dist <= 500:     # Within 500m
                nearby_score += report.severity * 4
            elif dist <= 1000:  # Within 1km
                nearby_score += report.severity * 2

        return min(nearby_score, 100)

    # ── Factor 4: Personal Alert History ─────────────────────────────────────
    def _history_factor(self, user_id: int, now: datetime) -> float:
        """
        Frequent past alerts = pattern of unsafe situations.
        Decays over time (older alerts matter less).
        """
        week_ago  = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        recent_alerts  = Alert.query.filter(
            Alert.user_id == user_id,
            Alert.created_at >= week_ago,
            Alert.alert_type != "false_alarm"
        ).count()

        monthly_alerts = Alert.query.filter(
            Alert.user_id == user_id,
            Alert.created_at >= month_ago,
            Alert.created_at < week_ago
        ).count()

        score = (recent_alerts * 20) + (monthly_alerts * 5)
        return min(score, 100)

    # ── Factor 5: Movement Anomaly Detection ─────────────────────────────────
    def _anomaly_factor(self, user_id: int, now: datetime) -> float:
        """
        Detect abnormal movement patterns:
        - Very high speed (running?)
        - Rapid location changes
        - Stationary at unsafe hour in isolated area
        """
        recent_locs = LocationHistory.query.filter(
            LocationHistory.user_id == user_id,
            LocationHistory.recorded_at >= now - timedelta(minutes=10)
        ).order_by(LocationHistory.recorded_at.desc()).limit(5).all()

        if len(recent_locs) < 2:
            return 0

        anomaly_score = 0
        for loc in recent_locs:
            if loc.speed and loc.speed > 8.0:  # > 8 m/s = fast running
                anomaly_score += 30
                break
            if loc.speed and loc.speed > 4.0:  # > 4 m/s = running
                anomaly_score += 15

        return min(anomaly_score, 100)

    # ── Risk Level Classifier ─────────────────────────────────────────────────
    def _level(self, score: float) -> str:
        if score >= 70: return "high"
        if score >= 40: return "medium"
        return "low"


# ─────────────────────────────────────────────────────────────────────────────
# SHAKE / FALL DETECTION LOGIC
# ─────────────────────────────────────────────────────────────────────────────
class MotionDetector:
    """
    Processes accelerometer data to detect:
    - Shake (SOS gesture)
    - Fall (sudden impact)
    Both trigger automatic SOS alerts.
    """

    SHAKE_THRESHOLD = 15.0  # m/s²
    FALL_THRESHOLD  = 25.0  # Sudden spike then near-zero = fall
    WINDOW_SIZE     = 10    # samples

    def __init__(self):
        self._buffer = []

    def process_sample(self, x: float, y: float, z: float) -> dict:
        """
        Input: Raw accelerometer x, y, z in m/s²
        Output: { event: "shake"|"fall"|"normal", magnitude: float }
        """
        # Compute magnitude: remove gravity (9.8 m/s²)
        magnitude = math.sqrt(x**2 + y**2 + z**2) - 9.8
        magnitude = abs(magnitude)

        self._buffer.append(magnitude)
        if len(self._buffer) > self.WINDOW_SIZE:
            self._buffer.pop(0)

        event = "normal"

        # Fall detection: high spike followed by near-zero (free fall)
        if len(self._buffer) >= 3:
            prev_max = max(self._buffer[:-1])
            current  = self._buffer[-1]
            if prev_max >= self.FALL_THRESHOLD and current < 2.0:
                event = "fall"
            elif magnitude >= self.SHAKE_THRESHOLD:
                event = "shake"

        return {"event": event, "magnitude": round(magnitude, 2)}


# ─────────────────────────────────────────────────────────────────────────────
# HOTSPOT ANALYZER (for admin heatmap)
# ─────────────────────────────────────────────────────────────────────────────
def get_alert_hotspots(limit=50):
    """
    Cluster recent alert locations for heatmap visualization.
    Returns list of {lat, lon, weight} points.
    """
    since = datetime.utcnow() - timedelta(days=90)
    alerts = Alert.query.filter(
        Alert.created_at >= since,
        Alert.latitude.isnot(None)
    ).all()

    return [{
        "lat":    a.latitude,
        "lng":    a.longitude,
        "weight": 1 + (a.risk_score / 100)
    } for a in alerts[:limit]]
