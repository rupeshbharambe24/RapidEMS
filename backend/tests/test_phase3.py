"""End-to-end smoke tests for the Phase 3 surfaces.

The seeded test database is built by the session-scoped fixture in
``conftest.py``, so tests here only need to authenticate and exercise
the endpoint contracts.

Coverage:
  * /dispatches/staging/preview      LSTM-driven pre-positioning
  * /admin/chaos/{inject,clear}      fault-injection round trip
  * /drones, /drones/dispatch        manual recon launch
  * /insurance/verify, /payers       EDI-271 covered / denied paths
  * /copilot/voice  (transcript)     reuses /ask via the same shape
  * /ar/turn-by-turn/{dispatch_id}   waypoint payload shape
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ── Auth helpers ──────────────────────────────────────────────────────────
def _bearer(client: TestClient, username: str = "admin",
            password: str = "admin123") -> dict:
    r = client.post("/auth/login",
                    json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Predictive staging (Phase 3.2) ────────────────────────────────────────
def test_staging_preview(client):
    h = _bearer(client)
    r = client.get("/dispatches/staging/preview",
                   params={"horizon_hours": 2}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["horizon_hours"] == 2
    # Empty proposals list is valid (e.g. no idle ambulances) — we just
    # verify the response shape so the contract is locked in.
    assert isinstance(body["proposals"], list)
    for p in body["proposals"]:
        assert {"ambulance_id", "ambulance_registration", "zone_id",
                "predicted_demand", "distance_km"} <= p.keys()


# ── Chaos lab (Phase 3.10) ────────────────────────────────────────────────
def test_chaos_dispatch_failure_round_trip(client):
    h = _bearer(client)

    # Clear anything left from a previous run so the test is hermetic.
    client.post("/admin/chaos/clear", headers=h)

    # Inject 100% dispatch failure and confirm it's listed.
    r = client.post("/admin/chaos/inject", headers=h, json={
        "scenario": "dispatch_failure_rate", "rate": 1.0,
    })
    assert r.status_code == 201, r.text
    assert r.json()["rate"] == 1.0

    state = client.get("/admin/chaos", headers=h).json()
    assert any(s["scenario"] == "dispatch_failure_rate" for s in state["active"])

    # Create an emergency + try to dispatch — should 409 with chaos: prefix.
    e = client.post("/emergencies", json={
        "patient_age": 50, "pulse_rate": 110,
        "location_lat": 19.07, "location_lng": 72.87,
        "symptoms": ["chest_pain"], "chief_complaint": "chest pain",
    })
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    d = client.post(f"/emergencies/{eid}/dispatch")
    assert d.status_code == 409
    assert "chaos" in (d.json().get("detail") or "").lower()

    # Clear and confirm a follow-up dispatch succeeds.
    cleared = client.post("/admin/chaos/clear", headers=h)
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] >= 1
    d2 = client.post(f"/emergencies/{eid}/dispatch")
    # 200 = dispatched; 409 with non-chaos detail is acceptable too (e.g.
    # the emergency is already in dispatched state from a re-run).
    if d2.status_code == 409:
        assert "chaos" not in (d2.json().get("detail") or "").lower()
    else:
        assert d2.status_code == 200, d2.text


# ── Drones (Phase 3.6) ────────────────────────────────────────────────────
def test_drones_roster_and_dispatch(client):
    h = _bearer(client)

    # Roster of 3 in-memory drones, all available.
    r = client.get("/drones", headers=h)
    assert r.status_code == 200, r.text
    drones = r.json()
    assert len(drones) == 3
    assert all(d["status"] in ("available", "en_route", "on_scene", "returning")
               for d in drones)

    # Manually dispatch one to a fresh emergency.
    e = client.post("/emergencies", json={
        "patient_age": 35, "pulse_rate": 120,
        "location_lat": 19.10, "location_lng": 72.88,
        "symptoms": ["trauma"], "chief_complaint": "MVC",
        "is_multi_casualty": True, "casualty_count": 3,
    }).json()
    r = client.post("/drones/dispatch", headers=h,
                    json={"emergency_id": e["id"]})
    # Auto-dispatch may have already grabbed a bird via the multi-casualty
    # heuristic. Either: 201 with our manual pick, or 503 fleet-busy.
    assert r.status_code in (201, 503), r.text
    if r.status_code == 201:
        body = r.json()
        assert body["emergency_id"] == e["id"]
        assert body["eta_seconds"] > 0
        assert body["drone_registration"].startswith("DRONE-")


# ── Insurance verification (Phase 3.9) ────────────────────────────────────
def test_insurance_verify_covered_and_denied(client):
    h = _bearer(client)

    payers = client.get("/insurance/payers", headers=h)
    assert payers.status_code == 200
    assert len(payers.json()) == 4   # stub registry has four payers

    # Any non-DENY card is covered.
    covered = client.post("/insurance/verify", headers=h, json={
        "card_number": "HDFC-PROD-99412",
        "patient_name": "Asha K",
    }).json()
    assert covered["covered"] is True
    assert covered["payer_code"]
    assert isinstance(covered["in_network_hospital_ids"], list)
    assert covered["effective_through"]

    # DENY- prefix returns uncovered with a structured reason.
    denied = client.post("/insurance/verify", headers=h, json={
        "card_number": "DENY-LAPSED-001",
    }).json()
    assert denied["covered"] is False
    assert denied["reason"] == "policy_inactive"

    # Determinism: same card → same payer + same expiry across calls.
    a = client.post("/insurance/verify", headers=h,
                    json={"card_number": "STABLE-XY-001"}).json()
    b = client.post("/insurance/verify", headers=h,
                    json={"card_number": "STABLE-XY-001"}).json()
    assert a["payer_code"] == b["payer_code"]
    assert a["effective_through"] == b["effective_through"]


# ── Voice copilot (Phase 3.4 transcript path) ─────────────────────────────
def test_copilot_voice_transcript_path(client):
    """Skips the audio upload (would need a real Whisper key); the
    transcript path exercises the same /ask machinery and verifies the
    response shape regardless of whether GROQ_API_KEY is set — when it
    isn't, the backend returns provider='disabled' with a clean error,
    not a 5xx."""
    h = _bearer(client)
    r = client.post("/copilot/voice", headers=h,
                    data={"transcript":
                          "How many ambulances are available right now?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"].startswith("How many ambulances")
    # provider is 'groq' when configured, 'disabled' otherwise.
    assert body["provider"] in ("groq", "disabled")
    # Empty body is still a 400 (validation).
    bad = client.post("/copilot/voice", headers=h, data={})
    assert bad.status_code == 400


# ── AR turn-by-turn (Phase 3.5) ───────────────────────────────────────────
def test_ar_turn_by_turn_after_dispatch(client):
    h = _bearer(client)

    # Clear chaos in case a previous test left it active.
    client.post("/admin/chaos/clear", headers=h)

    e = client.post("/emergencies", json={
        "patient_age": 60, "pulse_rate": 105,
        "location_lat": 19.085, "location_lng": 72.875,
        "symptoms": ["chest_pain"], "chief_complaint": "AR test",
    }).json()
    d = client.post(f"/emergencies/{e['id']}/dispatch")
    if d.status_code != 200:
        pytest.skip(f"dispatch unavailable for AR test: {d.text}")
    dispatch_id = d.json()["dispatch_id"]

    r = client.get(f"/ar/turn-by-turn/{dispatch_id}", headers=h)
    assert r.status_code == 200, r.text
    overlay = r.json()
    assert overlay["dispatch_id"] == dispatch_id
    assert overlay["destination"]["lat"] is not None
    # has_polyline is False under haversine fallback (no provider keys
    # in the test env). Either way, waypoints is a list and the schema
    # is intact.
    assert isinstance(overlay["waypoints"], list)
    if overlay["has_polyline"]:
        first = overlay["waypoints"][0]
        last = overlay["waypoints"][-1]
        assert first["anchor"] == "origin"
        assert first["turn_cue"] == "depart"
        assert last["anchor"] == "destination"
        assert last["turn_cue"] == "arrive"


# ── 404 sanity ────────────────────────────────────────────────────────────
def test_ar_turn_by_turn_unknown_dispatch(client):
    h = _bearer(client)
    r = client.get("/ar/turn-by-turn/999999", headers=h)
    assert r.status_code == 404
