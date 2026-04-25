"""GPS Simulator — drives the ambulance fleet for the demo.

Behaviour:
  • Idle ambulances wander randomly within ~6 km of their depot.
  • When an ambulance is set to EN_ROUTE, the simulator interpolates its
    position toward the active emergency (read from /dispatches/active).
  • On scene → wait briefly → TRANSPORTING toward the assigned hospital.
  • On hospital arrival → mark ARRIVED_HOSPITAL → wait → RETURNING → AVAILABLE.

  All updates use the public REST API. Backend pushes Socket.IO events
  automatically as a side-effect of the PATCH calls.
"""
import argparse
import asyncio
import random
import sys
from datetime import datetime
from typing import Dict, Optional, Tuple

import httpx


# ---- Config (CLI overrides) ----
DEFAULT_BACKEND = "http://localhost:8000"
TICK_SECONDS = 2.0          # one simulator step
SPEED_KMH = 45.0            # average ambulance speed in the sim
WANDER_RADIUS_KM = 6.0
ON_SCENE_DWELL_S = 12       # hold "on_scene" before transporting
HOSPITAL_DWELL_S = 18       # hold "arrived_hospital" before returning


# ---- Geo helpers (duplicated to keep simulator standalone) ----
import math
EARTH_R_KM = 6371.0088


def haversine(lat1, lng1, lat2, lng2) -> float:
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1); dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def step_toward(cur_lat, cur_lng, dst_lat, dst_lng, max_km) -> Tuple[float, float]:
    """Move from current toward destination by at most max_km. Returns new lat/lng."""
    d = haversine(cur_lat, cur_lng, dst_lat, dst_lng)
    if d <= max_km or d < 0.005:
        return dst_lat, dst_lng
    t = max_km / d
    return cur_lat + (dst_lat - cur_lat) * t, cur_lng + (dst_lng - cur_lng) * t


# ---- Per-ambulance simulation state (lives in the simulator process only) ----
class AmbState:
    """In-memory state for one ambulance — beyond what the API tracks."""
    __slots__ = ("dwell_until", "wander_target", "active_dispatch_id", "phase")

    def __init__(self):
        self.dwell_until: Optional[datetime] = None
        self.wander_target: Optional[Tuple[float, float]] = None
        self.active_dispatch_id: Optional[int] = None
        self.phase: str = "idle"   # idle / to_scene / on_scene / to_hospital / arrived / returning


class Simulator:
    def __init__(self, backend_url: str):
        self.base = backend_url.rstrip("/")
        self.client: Optional[httpx.AsyncClient] = None
        self.state: Dict[int, AmbState] = {}     # ambulance_id -> AmbState

    # ────── Backend API helpers ──────
    async def get_ambulances(self):
        r = await self.client.get(f"{self.base}/ambulances", timeout=10)
        r.raise_for_status()
        return r.json()

    async def get_active_dispatches(self):
        r = await self.client.get(f"{self.base}/dispatches/active", timeout=10)
        r.raise_for_status()
        return r.json()

    async def get_emergency(self, eid: int):
        r = await self.client.get(f"{self.base}/emergencies/{eid}", timeout=10)
        r.raise_for_status()
        return r.json()

    async def get_hospital(self, hid: int):
        r = await self.client.get(f"{self.base}/hospitals/{hid}", timeout=10)
        r.raise_for_status()
        return r.json()

    async def patch_location(self, amb_id: int, lat: float, lng: float):
        await self.client.patch(
            f"{self.base}/ambulances/{amb_id}/location",
            json={"current_lat": lat, "current_lng": lng}, timeout=10,
        )

    async def patch_status(self, amb_id: int, status: str):
        await self.client.patch(
            f"{self.base}/ambulances/{amb_id}/status",
            json={"status": status}, timeout=10,
        )

    # ────── Per-ambulance step ──────
    async def step_ambulance(self, amb: dict, active_lookup: dict):
        amb_id = amb["id"]
        st = self.state.setdefault(amb_id, AmbState())

        # Dwell — waiting on scene / at hospital
        if st.dwell_until and datetime.utcnow() < st.dwell_until:
            return
        if st.dwell_until and datetime.utcnow() >= st.dwell_until:
            st.dwell_until = None
            if st.phase == "on_scene":
                # finished on-scene; switch to TRANSPORTING toward hospital
                await self.patch_status(amb_id, "transporting")
                st.phase = "to_hospital"
                return
            if st.phase == "arrived":
                # finished hospital handoff; head home
                await self.patch_status(amb_id, "returning")
                st.phase = "returning"
                return

        cur_lat, cur_lng = amb.get("current_lat"), amb.get("current_lng")
        if cur_lat is None or cur_lng is None:
            cur_lat, cur_lng = amb["home_station_lat"], amb["home_station_lng"]

        max_step_km = (SPEED_KMH / 3600.0) * TICK_SECONDS

        backend_status = amb["status"]
        # ── EN_ROUTE: drive to scene ──
        if backend_status == "en_route":
            disp = active_lookup.get(amb_id)
            if not disp:
                return                           # no active dispatch found yet
            st.active_dispatch_id = disp["id"]
            try:
                emergency = await self.get_emergency(disp["emergency_id"])
            except Exception:
                return
            new_lat, new_lng = step_toward(
                cur_lat, cur_lng,
                emergency["location_lat"], emergency["location_lng"],
                max_step_km,
            )
            await self.patch_location(amb_id, new_lat, new_lng)
            # Arrived?
            if haversine(new_lat, new_lng,
                          emergency["location_lat"], emergency["location_lng"]) < 0.05:
                await self.patch_status(amb_id, "on_scene")
                st.phase = "on_scene"
                st.dwell_until = datetime.utcnow().replace(microsecond=0)
                from datetime import timedelta
                st.dwell_until += timedelta(seconds=ON_SCENE_DWELL_S)
            return

        # ── TRANSPORTING: drive to assigned hospital ──
        if backend_status == "transporting":
            # Find the active dispatch (by ambulance id)
            disp = active_lookup.get(amb_id)
            if not disp:
                return
            try:
                hospital = await self.get_hospital(disp["hospital_id"])
            except Exception:
                return
            new_lat, new_lng = step_toward(
                cur_lat, cur_lng, hospital["lat"], hospital["lng"], max_step_km,
            )
            await self.patch_location(amb_id, new_lat, new_lng)
            if haversine(new_lat, new_lng, hospital["lat"], hospital["lng"]) < 0.05:
                await self.patch_status(amb_id, "out_of_service")  # at hospital handoff
                st.phase = "arrived"
                from datetime import timedelta
                st.dwell_until = datetime.utcnow() + timedelta(seconds=HOSPITAL_DWELL_S)
            return

        # ── RETURNING: drive home ──
        if backend_status == "returning":
            new_lat, new_lng = step_toward(
                cur_lat, cur_lng,
                amb["home_station_lat"], amb["home_station_lng"], max_step_km,
            )
            await self.patch_location(amb_id, new_lat, new_lng)
            if haversine(new_lat, new_lng,
                          amb["home_station_lat"], amb["home_station_lng"]) < 0.05:
                await self.patch_status(amb_id, "available")
                st.phase = "idle"
                st.wander_target = None
            return

        # ── AVAILABLE: gentle wandering for visual life ──
        if backend_status == "available":
            if st.wander_target is None or haversine(
                cur_lat, cur_lng, st.wander_target[0], st.wander_target[1]
            ) < 0.05:
                # pick a new wander point near the depot
                home_lat = amb["home_station_lat"]; home_lng = amb["home_station_lng"]
                dlat = random.uniform(-WANDER_RADIUS_KM/111, WANDER_RADIUS_KM/111)
                dlng = random.uniform(-WANDER_RADIUS_KM/95, WANDER_RADIUS_KM/95)
                st.wander_target = (home_lat + dlat, home_lng + dlng)
            new_lat, new_lng = step_toward(
                cur_lat, cur_lng, st.wander_target[0], st.wander_target[1],
                max_step_km * 0.4,    # wander slower than emergency drive
            )
            await self.patch_location(amb_id, new_lat, new_lng)
            return

    # ────── Main loop ──────
    async def run(self):
        async with httpx.AsyncClient() as self.client:
            print(f"[sim] connecting to {self.base}")
            # Warm up: wait for backend
            for _ in range(30):
                try:
                    r = await self.client.get(f"{self.base}/health", timeout=3)
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                print("[sim] backend not ready, retrying in 2s...")
                await asyncio.sleep(2)
            else:
                print("[sim] backend never became available; exiting.")
                return

            print("[sim] running; press Ctrl-C to stop.")
            tick = 0
            while True:
                try:
                    ambulances = await self.get_ambulances()
                    actives = await self.get_active_dispatches()
                    active_lookup = {d["ambulance_id"]: d for d in actives}
                    await asyncio.gather(*[
                        self.step_ambulance(a, active_lookup) for a in ambulances
                    ])
                    if tick % 10 == 0:
                        states = {}
                        for a in ambulances:
                            states[a["status"]] = states.get(a["status"], 0) + 1
                        print(f"[sim] tick {tick}: {states}")
                    tick += 1
                except httpx.HTTPError as e:
                    print(f"[sim] HTTP error: {e}")
                except Exception as e:
                    print(f"[sim] error: {e}")
                await asyncio.sleep(TICK_SECONDS)


def main():
    parser = argparse.ArgumentParser(description="Ambulance GPS simulator")
    parser.add_argument("--backend", default=DEFAULT_BACKEND,
                        help=f"Backend URL (default: {DEFAULT_BACKEND})")
    args = parser.parse_args()

    sim = Simulator(args.backend)
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        print("\n[sim] stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
