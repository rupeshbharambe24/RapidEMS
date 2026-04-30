"""End-to-end smoke tests.

The session-scoped ``_bootstrap_test_db`` fixture in ``conftest.py``
takes care of creating + seeding the test database before any test
module runs.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_list_hospitals(client):
    r = client.get("/hospitals")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_list_ambulances(client):
    r = client.get("/ambulances")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_create_emergency_and_dispatch(client):
    payload = {
        "patient_name": "Test Patient",
        "patient_age": 55, "patient_gender": "male",
        "phone": "+91-9123456789",
        "location_lat": 19.07, "location_lng": 72.87,
        "location_address": "Test Road",
        "symptoms": ["chest_pain", "shortness_of_breath"],
        "chief_complaint": "Crushing chest pain",
        "pulse_rate": 130, "blood_pressure_systolic": 95,
        "blood_pressure_diastolic": 60,
        "respiratory_rate": 28, "spo2": 88, "gcs_score": 13,
    }
    r = client.post("/emergencies", json=payload)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]

    # Trigger dispatch
    r = client.post(f"/emergencies/{eid}/dispatch")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["severity_level"] in (1, 2)         # should be Critical or Serious
    assert plan["predicted_eta_seconds"] > 0
    assert plan["hospital_id"] > 0


def test_ai_triage_endpoint(client):
    r = client.post("/ai/triage", json={
        "age": 65, "gender": "male",
        "gcs_score": 6, "spo2": 80, "pulse_rate": 160,
        "respiratory_rate": 34,
        "blood_pressure_systolic": 75, "blood_pressure_diastolic": 50,
        "symptoms": ["cardiac_arrest", "unconscious"],
    })
    assert r.status_code == 200
    assert r.json()["severity_level"] == 1  # Critical


def test_ai_eta_endpoint(client):
    r = client.post("/ai/eta", json={
        "distance_km": 5.0, "congestion": 0.3,
        "hour": 10, "day_of_week": 2,
    })
    assert r.status_code == 200
    assert r.json()["eta_seconds"] > 0


def test_login_admin(client):
    r = client.post("/auth/login",
                    json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_kpis_endpoint(client):
    r = client.get("/analytics/kpis")
    assert r.status_code == 200
    assert "available_ambulances" in r.json()
