"""AI inference service.

Loads all 5 ML models on startup as a singleton, exposes one method per model.
Every method has a heuristic fallback so the system stays functional even when
the trained .pkl/.keras files are missing — useful for first-run, demos, and dev.
"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import joblib
import numpy as np

from ..config import settings
from ..core.logging import log


# These match the symptom one-hot order used in Notebook 1.
SYMPTOMS_POOL = [
    "cardiac_arrest", "unconscious", "severe_burns", "spinal_injury",
    "anaphylaxis", "major_bleeding",
    "stroke_symptoms", "chest_pain", "shortness_of_breath", "seizure",
    "head_trauma", "diabetic_emergency",
    "fracture", "moderate_bleeding", "abdominal_pain", "high_fever",
    "vomiting", "dizziness", "minor_cut", "sprain", "headache",
]
SEVERITY_LABELS = {1: "Critical", 2: "Serious", 3: "Moderate",
                   4: "Minor", 5: "Non-Emergency"}

# Symptoms → patient type mapping (used by the hospital recommender)
SYMPTOM_TO_PATIENT_TYPE = {
    "cardiac_arrest": "cardiac", "chest_pain": "cardiac",
    "stroke_symptoms": "stroke",
    "head_trauma": "trauma", "spinal_injury": "trauma", "fracture": "trauma",
    "major_bleeding": "trauma", "moderate_bleeding": "trauma",
    "severe_burns": "burns",
    "seizure": "general", "anaphylaxis": "general",
    "diabetic_emergency": "general", "shortness_of_breath": "general",
}


class AIService:
    """Singleton holding all 5 trained models in memory."""

    def __init__(self):
        self.models_dir: Path = Path(settings.models_dir)
        self.severity_model = None
        self.severity_scaler = None
        self.severity_feature_cols: Optional[List[str]] = None

        self.eta_model = None
        self.eta_scaler = None
        self.eta_feature_cols: Optional[List[str]] = None

        self.hospital_model = None
        self.hospital_scaler = None
        self.hospital_feature_cols: Optional[List[str]] = None

        self.traffic_model = None
        self.traffic_scaler = None
        self.traffic_feature_cols: Optional[List[str]] = None

        self.hotspot_model = None
        self.hotspot_count_scaler = None

        self._load_all()

    # ─────────────────────────────────────────────────────
    # Loading
    # ─────────────────────────────────────────────────────
    def _safe_load(self, fname: str):
        path = self.models_dir / fname
        if not path.exists():
            log.warning(f"AIService: model file missing → {path}")
            return None
        try:
            return joblib.load(path)
        except Exception as e:
            log.error(f"AIService: failed to load {fname}: {e}")
            return None

    def _load_all(self):
        log.info(f"AIService: loading models from {self.models_dir}")

        self.severity_model        = self._safe_load("severity_classifier.pkl")
        self.severity_scaler       = self._safe_load("severity_scaler.pkl")
        self.severity_feature_cols = self._safe_load("severity_feature_cols.pkl")

        self.eta_model        = self._safe_load("eta_xgb.pkl")
        self.eta_scaler       = self._safe_load("eta_scaler.pkl")
        self.eta_feature_cols = self._safe_load("eta_feature_cols.pkl")

        self.hospital_model        = self._safe_load("hospital_recommender.pkl")
        self.hospital_scaler       = self._safe_load("hospital_scaler.pkl")
        self.hospital_feature_cols = self._safe_load("hospital_feature_cols.pkl")

        self.traffic_model        = self._safe_load("traffic_predictor.pkl")
        self.traffic_scaler       = self._safe_load("traffic_scaler.pkl")
        self.traffic_feature_cols = self._safe_load("traffic_feature_cols.pkl")

        self.hotspot_count_scaler = self._safe_load("hotspot_count_scaler.pkl")

        # Keras model needs special loading
        keras_path = self.models_dir / "hotspot_lstm.keras"
        if keras_path.exists():
            try:
                from tensorflow import keras
                self.hotspot_model = keras.models.load_model(keras_path)
                log.success(f"AIService: loaded LSTM hotspot model")
            except Exception as e:
                log.error(f"AIService: failed to load LSTM: {e}")

    # ─────────────────────────────────────────────────────
    # 1. Severity Classifier
    # ─────────────────────────────────────────────────────
    def predict_severity(
        self, age: int, gender: str,
        gcs: Optional[int] = None,
        spo2: Optional[float] = None,
        pulse: Optional[int] = None,
        resp_rate: Optional[int] = None,
        bp_systolic: Optional[int] = None,
        bp_diastolic: Optional[int] = None,
        symptoms: Optional[List[str]] = None,
    ) -> dict:
        symptoms = symptoms or []
        # Sensible defaults for missing vitals (assume average healthy adult)
        gcs = gcs if gcs is not None else 15
        spo2 = spo2 if spo2 is not None else 98.0
        pulse = pulse if pulse is not None else 80
        resp_rate = resp_rate if resp_rate is not None else 16
        bp_systolic = bp_systolic if bp_systolic is not None else 120
        bp_diastolic = bp_diastolic if bp_diastolic is not None else 80

        if (self.severity_model is None or self.severity_scaler is None
                or self.severity_feature_cols is None):
            return self._heuristic_severity(symptoms, gcs, spo2, pulse, resp_rate,
                                            bp_systolic)

        try:
            row = {c: 0 for c in self.severity_feature_cols}
            row.update({
                "age": age,
                "gender": 1 if gender == "male" else 0,
                "gcs": float(gcs), "spo2": float(spo2),
                "pulse": int(pulse), "resp_rate": int(resp_rate),
                "bp_systolic": int(bp_systolic),
                "bp_diastolic": int(bp_diastolic),
            })
            for s in symptoms:
                key = f"sym_{s}"
                if key in row:
                    row[key] = 1

            x = np.array([[row[c] for c in self.severity_feature_cols]], dtype=float)
            x_scaled = self.severity_scaler.transform(x)
            pred = int(self.severity_model.predict(x_scaled)[0]) + 1  # 0-idx → 1-5

            confidence = 0.85
            if hasattr(self.severity_model, "predict_proba"):
                proba = self.severity_model.predict_proba(x_scaled)[0]
                confidence = float(proba.max())

            return {
                "severity_level": pred,
                "severity_label": SEVERITY_LABELS[pred],
                "confidence": confidence,
                "used_fallback": False,
            }
        except Exception as e:
            log.error(f"Severity model inference failed: {e} — falling back")
            return self._heuristic_severity(symptoms, gcs, spo2, pulse, resp_rate,
                                            bp_systolic)

    @staticmethod
    def _heuristic_severity(symptoms, gcs, spo2, pulse, resp_rate, bp_sys) -> dict:
        """Simple rule-based triage when the model is missing."""
        critical_symptoms = {"cardiac_arrest", "unconscious", "severe_burns",
                             "spinal_injury", "anaphylaxis", "major_bleeding"}
        serious_symptoms = {"stroke_symptoms", "chest_pain", "shortness_of_breath",
                            "seizure", "head_trauma", "diabetic_emergency"}
        moderate_symptoms = {"fracture", "moderate_bleeding", "abdominal_pain",
                             "high_fever"}

        symset = set(symptoms or [])

        # Vital-driven escalation
        if gcs <= 8 or spo2 < 85 or pulse > 150 or pulse < 40 or bp_sys < 80:
            level = 1
        elif gcs <= 12 or spo2 < 92 or pulse > 130 or bp_sys < 95:
            level = 2
        elif gcs == 15 and spo2 >= 96 and 60 <= pulse <= 100:
            level = 5
        else:
            level = 3

        # Symptom-driven escalation
        if symset & critical_symptoms:
            level = min(level, 1)
        elif symset & serious_symptoms:
            level = min(level, 2)
        elif symset & moderate_symptoms:
            level = min(level, 3)
        elif symset and not (symset & critical_symptoms):
            level = min(level, 4)

        return {
            "severity_level": int(level),
            "severity_label": SEVERITY_LABELS[level],
            "confidence": 0.70,
            "used_fallback": True,
        }

    # ─────────────────────────────────────────────────────
    # 2. ETA Predictor
    # ─────────────────────────────────────────────────────
    def predict_eta(
        self, distance_km: float, congestion: float, hour: int, day_of_week: int,
        weather: int = 0, ambulance_type: int = 0, road_type: int = 0,
    ) -> dict:
        if (self.eta_model is None or self.eta_scaler is None
                or self.eta_feature_cols is None):
            return self._heuristic_eta(distance_km, congestion, weather)

        try:
            base_speed = [35, 80, 55][road_type]
            row = {
                "distance_km": distance_km, "congestion": congestion,
                "hour": hour, "day_of_week": day_of_week,
                "is_weekend": int(day_of_week >= 5),
                "is_rush_hour": int(day_of_week < 5 and
                                    ((8 <= hour <= 10) or (17 <= hour <= 20))),
                "is_night": int(hour >= 23 or hour <= 5),
                "weather": weather,
                "ambulance_type": ambulance_type, "road_type": road_type,
                "base_speed_kmh": base_speed,
                "est_free_flow_s": (distance_km / base_speed) * 3600,
                "distance_x_congestion": distance_km * congestion,
                "log_distance": float(np.log1p(distance_km)),
            }
            x = np.array([[row.get(c, 0) for c in self.eta_feature_cols]], dtype=float)
            x_scaled = self.eta_scaler.transform(x)
            eta_s = float(self.eta_model.predict(x_scaled)[0])
            return {
                "eta_seconds": max(30.0, eta_s),
                "eta_minutes": max(0.5, eta_s / 60.0),
                "used_fallback": False,
            }
        except Exception as e:
            log.error(f"ETA inference failed: {e} — falling back")
            return self._heuristic_eta(distance_km, congestion, weather)

    @staticmethod
    def _heuristic_eta(distance_km, congestion, weather) -> dict:
        # Average urban ambulance speed adjusted for congestion + weather
        eff_speed = 35 * (1 - 0.6 * congestion)
        eff_speed *= [1.0, 1.10, 1.25, 1.55][weather]
        eff_speed = max(8.0, eff_speed)
        eta_s = (distance_km / eff_speed) * 3600 + 60  # +60s dispatch overhead
        return {
            "eta_seconds": eta_s,
            "eta_minutes": eta_s / 60.0,
            "used_fallback": True,
        }

    # ─────────────────────────────────────────────────────
    # 3. Hospital Recommender
    # ─────────────────────────────────────────────────────
    def score_hospital(
        self, patient_type: str, hospital, distance_km: float,
    ) -> dict:
        from ..models.hospital import Hospital as HospitalModel  # avoid circular
        h: HospitalModel = hospital

        bed_kind = {
            "cardiac": "icu", "stroke": "icu", "trauma": "trauma",
            "pediatric": "pediatric", "burns": "burns", "general": "general",
        }.get(patient_type, "general")
        avail = getattr(h, f"available_beds_{bed_kind}", 0)
        total = getattr(h, f"total_beds_{bed_kind}", 0)
        relevant_util = (avail / total) if total > 0 else 0.0
        spec_match = int(patient_type in (h.specialties or []))

        if (self.hospital_model is None or self.hospital_scaler is None
                or self.hospital_feature_cols is None):
            return self._heuristic_hospital(spec_match, relevant_util, distance_km,
                                            h.er_wait_minutes, h.is_diversion,
                                            h.quality_rating)

        try:
            row = {
                "patient_type_id": ["cardiac","trauma","stroke","pediatric",
                                    "burns","general"].index(patient_type),
                "specialty_match": spec_match,
                "distance_km": distance_km,
                "er_wait_minutes": h.er_wait_minutes,
                "is_diversion": int(h.is_diversion),
                "quality_rating": h.quality_rating,
                "available_general": h.available_beds_general,
                "total_general": h.total_beds_general,
                "available_icu": h.available_beds_icu,
                "total_icu": h.total_beds_icu,
                "available_trauma": h.available_beds_trauma,
                "total_trauma": h.total_beds_trauma,
                "available_pediatric": h.available_beds_pediatric,
                "total_pediatric": h.total_beds_pediatric,
                "available_burns": h.available_beds_burns,
                "total_burns": h.total_beds_burns,
                "relevant_bed_utilisation": relevant_util,
            }
            x = np.array([[row.get(c, 0) for c in self.hospital_feature_cols]], dtype=float)
            x_scaled = self.hospital_scaler.transform(x)
            score = float(self.hospital_model.predict(x_scaled)[0])
            return {"score": float(np.clip(score, 0, 1)), "used_fallback": False}
        except Exception as e:
            log.error(f"Hospital score inference failed: {e} — falling back")
            return self._heuristic_hospital(spec_match, relevant_util, distance_km,
                                            h.er_wait_minutes, h.is_diversion,
                                            h.quality_rating)

    @staticmethod
    def _heuristic_hospital(spec_match, relevant_util, distance_km,
                            wait_min, is_diversion, quality_rating) -> dict:
        bed_score = float(np.clip((relevant_util - 0.05) * 1.4, 0, 1))
        prox_score = float(np.exp(-distance_km / 8))
        wait_score = float(np.exp(-wait_min / 60))
        qual_score = quality_rating / 5.0
        score = (0.30 * spec_match + 0.25 * bed_score + 0.20 * prox_score
                 + 0.15 * wait_score + 0.10 * qual_score)
        if is_diversion:
            score *= 0.20
        return {"score": float(np.clip(score, 0, 1)), "used_fallback": True}

    # ─────────────────────────────────────────────────────
    # 4. Traffic Predictor
    # ─────────────────────────────────────────────────────
    def predict_congestion(
        self, zone_id: int, hour: int, day_of_week: int, month: int,
        weather: int = 0, is_holiday: int = 0,
        zone_density: float = 0.6, lat: float = 0.0, lng: float = 0.0,
    ) -> dict:
        if (self.traffic_model is None or self.traffic_scaler is None
                or self.traffic_feature_cols is None):
            return self._heuristic_congestion(hour, day_of_week, month, weather,
                                              is_holiday, zone_density)

        try:
            row = {
                "zone_id": zone_id, "zone_density": zone_density,
                "lat": lat, "lng": lng,
                "hour": hour, "day_of_week": day_of_week, "month": month,
                "is_weekend": int(day_of_week >= 5),
                "is_rush_hour": int(day_of_week < 5 and
                                    ((8 <= hour <= 10) or (17 <= hour <= 20))),
                "is_night": int(hour >= 23 or hour <= 5),
                "is_monsoon": int(6 <= month <= 9),
                "is_holiday": is_holiday,
                "is_school_day": int(day_of_week < 5 and is_holiday == 0),
                "weather": weather,
                "hour_sin": float(np.sin(2 * np.pi * hour / 24)),
                "hour_cos": float(np.cos(2 * np.pi * hour / 24)),
                "month_sin": float(np.sin(2 * np.pi * month / 12)),
                "month_cos": float(np.cos(2 * np.pi * month / 12)),
                "dow_sin": float(np.sin(2 * np.pi * day_of_week / 7)),
                "dow_cos": float(np.cos(2 * np.pi * day_of_week / 7)),
            }
            x = np.array([[row.get(c, 0) for c in self.traffic_feature_cols]], dtype=float)
            x_scaled = self.traffic_scaler.transform(x)
            cong = float(self.traffic_model.predict(x_scaled)[0])
            return {"congestion": float(np.clip(cong, 0, 1)), "used_fallback": False}
        except Exception as e:
            log.error(f"Traffic inference failed: {e} — falling back")
            return self._heuristic_congestion(hour, day_of_week, month, weather,
                                              is_holiday, zone_density)

    @staticmethod
    def _heuristic_congestion(hour, day_of_week, month, weather, is_holiday,
                              zone_density) -> dict:
        morn_peak = float(np.exp(-((hour - 9) ** 2) / 4.0))
        eve_peak = float(np.exp(-((hour - 18) ** 2) / 4.5))
        base = (morn_peak + eve_peak) * 0.55 + 0.05
        if day_of_week >= 5:
            base *= 0.55
        if is_holiday:
            base *= 0.50
        if 6 <= month <= 9:
            base *= 1.10
        weather_mult = [1.0, 1.10, 1.30, 1.60][weather]
        cong = float(np.clip(base * zone_density * weather_mult, 0, 1))
        return {"congestion": cong, "used_fallback": True}

    # ─────────────────────────────────────────────────────
    # 5. Hotspot Forecaster
    # ─────────────────────────────────────────────────────
    def forecast_hotspots(
        self, recent_counts: List[float], zone_id: int = 0, steps: int = 24,
    ) -> dict:
        """Forecast next `steps` hours of incident counts.

        recent_counts: last 48 hourly counts (we'll pad/truncate as needed)
        """
        if self.hotspot_model is None or self.hotspot_count_scaler is None:
            return self._heuristic_hotspots(recent_counts, steps)

        try:
            from datetime import timedelta
            SEQ_LEN = 48
            counts = list(recent_counts)
            if len(counts) < SEQ_LEN:
                counts = [0.0] * (SEQ_LEN - len(counts)) + counts
            else:
                counts = counts[-SEQ_LEN:]

            cur_dt = datetime.utcnow()
            window = []
            for i, c in enumerate(counts):
                t = cur_dt - timedelta(hours=SEQ_LEN - i)
                window.append([
                    c,
                    float(np.sin(2 * np.pi * t.hour / 24)),
                    float(np.cos(2 * np.pi * t.hour / 24)),
                    float(np.sin(2 * np.pi * t.weekday() / 7)),
                    float(np.cos(2 * np.pi * t.weekday() / 7)),
                ])
            window = np.array(window, dtype=float)

            preds = []
            for step in range(steps):
                win_in = window.copy().astype(np.float32)
                win_in[:, 0] = self.hotspot_count_scaler.transform(
                    win_in[:, 0].reshape(-1, 1)).flatten()
                p = float(self.hotspot_model.predict(win_in[None, :, :], verbose=0)[0, 0])
                p = max(0.0, p)
                preds.append(p)
                # roll
                cur_dt = cur_dt + timedelta(hours=1)
                new_row = np.array([
                    p,
                    float(np.sin(2 * np.pi * cur_dt.hour / 24)),
                    float(np.cos(2 * np.pi * cur_dt.hour / 24)),
                    float(np.sin(2 * np.pi * cur_dt.weekday() / 7)),
                    float(np.cos(2 * np.pi * cur_dt.weekday() / 7)),
                ])
                window = np.vstack([window[1:], new_row])

            return {"zone_id": zone_id, "next_24h": preds, "used_fallback": False}
        except Exception as e:
            log.error(f"Hotspot inference failed: {e} — falling back")
            return self._heuristic_hotspots(recent_counts, steps)

    @staticmethod
    def _heuristic_hotspots(recent_counts, steps) -> dict:
        avg = float(np.mean(recent_counts)) if recent_counts else 1.0
        # Gentle diurnal modulation around the average
        now_hour = datetime.utcnow().hour
        out = []
        for s in range(steps):
            h = (now_hour + s) % 24
            mult = 0.4 + 1.6 * (np.exp(-((h - 9) ** 2) / 4) +
                                 np.exp(-((h - 18) ** 2) / 4)) / 2
            out.append(round(avg * mult, 3))
        return {"zone_id": 0, "next_24h": out, "used_fallback": True}

    # ─────────────────────────────────────────────────────
    # Helper: pick a patient type from symptoms
    # ─────────────────────────────────────────────────────
    @staticmethod
    def infer_patient_type(symptoms: List[str], age: Optional[int] = None) -> str:
        if age is not None and age < 16:
            return "pediatric"
        for s in (symptoms or []):
            if s in SYMPTOM_TO_PATIENT_TYPE:
                return SYMPTOM_TO_PATIENT_TYPE[s]
        return "general"


# Singleton instance — created once at app startup
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def reset_ai_service():
    """Force-reload all models (useful after retraining)."""
    global _ai_service
    _ai_service = None
    return get_ai_service()
