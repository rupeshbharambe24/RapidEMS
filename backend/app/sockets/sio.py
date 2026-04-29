"""Socket.IO server — broadcasts live updates to connected clients.

Channels:
  ambulance:position        – pushed by simulator / mobile crew app
  ambulance:status_change   – status transitions (en_route → on_scene → ...)
  emergency:created         – new call alert for dispatcher dashboards
  emergency:dispatched      – assignment broadcast
  hospital:beds_updated     – bed availability changes
  traffic:snapshot          – periodic traffic updates
"""
import socketio

from ..core.logging import log


# AsyncServer so it plays nicely with FastAPI/uvicorn
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",   # CORS already enforced at FastAPI layer
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid, environ, auth=None):
    log.info(f"[sio] client connected: {sid}")
    await sio.emit("server:hello", {"sid": sid}, to=sid)


@sio.event
async def disconnect(sid):
    log.info(f"[sio] client disconnected: {sid}")


# ── Helpers used by the REST layer to push events ─────────────
async def emit_ambulance_position(amb_id: int, lat: float, lng: float, status: str):
    await sio.emit("ambulance:position", {
        "ambulance_id": amb_id, "lat": lat, "lng": lng, "status": status,
    })


async def emit_ambulance_status(amb_id: int, status: str):
    await sio.emit("ambulance:status_change", {
        "ambulance_id": amb_id, "status": status,
    })


async def emit_emergency_created(payload: dict):
    await sio.emit("emergency:created", payload)


async def emit_emergency_dispatched(payload: dict):
    await sio.emit("emergency:dispatched", payload)


async def emit_hospital_beds_updated(payload: dict):
    await sio.emit("hospital:beds_updated", payload)


async def emit_hospital_alert(payload: dict):
    """Pre-arrival alert pushed to hospital staff dashboards."""
    await sio.emit("hospital:alert", payload)


async def emit_hospital_alert_status(payload: dict):
    """Acknowledged / accepted / diverted — keeps dispatcher dashboards in sync."""
    await sio.emit("hospital:alert_status", payload)
