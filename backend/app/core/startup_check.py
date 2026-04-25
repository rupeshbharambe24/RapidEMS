"""Startup checks: verifies model files, dependencies, etc.

If anything is missing, prints clear actionable instructions instead of crashing.
"""
from pathlib import Path
from typing import List, Tuple

from ..config import settings
from .logging import log


REQUIRED_MODEL_FILES = [
    ("severity_classifier.pkl", "Severity Classifier (Notebook 1)"),
    ("severity_scaler.pkl",     "Severity feature scaler"),
    ("severity_feature_cols.pkl", "Severity feature column order"),
    ("eta_xgb.pkl",             "ETA Predictor (Notebook 2)"),
    ("eta_scaler.pkl",          "ETA feature scaler"),
    ("eta_feature_cols.pkl",    "ETA feature column order"),
    ("hospital_recommender.pkl","Hospital Recommender (Notebook 3)"),
    ("hospital_scaler.pkl",     "Hospital feature scaler"),
    ("hospital_feature_cols.pkl","Hospital feature column order"),
    ("traffic_predictor.pkl",   "Traffic Predictor (Notebook 4)"),
    ("traffic_scaler.pkl",      "Traffic feature scaler"),
    ("traffic_feature_cols.pkl","Traffic feature column order"),
    ("hotspot_lstm.keras",      "LSTM Hotspot Forecaster (Notebook 5)"),
    ("hotspot_count_scaler.pkl","Hotspot count scaler"),
]


def check_models() -> Tuple[List[str], List[str]]:
    """Return (present_files, missing_files)."""
    models_dir = Path(settings.models_dir)
    present, missing = [], []
    for fname, _desc in REQUIRED_MODEL_FILES:
        p = models_dir / fname
        if p.exists() and p.stat().st_size > 0:
            present.append(fname)
        else:
            missing.append(fname)
    return present, missing


def print_model_status():
    present, missing = check_models()
    log.info(f"Model files: {len(present)}/{len(REQUIRED_MODEL_FILES)} present in {settings.models_dir}")
    if missing:
        log.warning("Missing model files — heuristic fallbacks will be used:")
        for fname in missing:
            log.warning(f"  • {fname}")
        log.warning("To train the real models:")
        log.warning("  Option A) Run notebooks 1-5 in the notebooks/ folder (full quality)")
        log.warning("  Option B) Run: python -m backend.app.ai.quick_train (lightweight, ~90s)")
        if not settings.allow_heuristic_fallback:
            log.error("ALLOW_HEURISTIC_FALLBACK=false — dispatch endpoint will return errors!")
    else:
        log.success("All ML models loaded ✓")


def run_startup_checks():
    log.info("Running startup checks...")
    print_model_status()
    log.info("Startup checks complete.")
