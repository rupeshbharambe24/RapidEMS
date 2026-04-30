"""Admin endpoints — user management, audit-log viewer, system overview.

All routes require role=admin. The dispatcher / clinical / paramedic /
hospital-staff roles already have their own scoped routers; admin is the
only role that can create or alter other users and read the audit trail.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.policy import enforce as policy_enforce, list_policy, reload_policy
from ..core.security import hash_password
from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..models.audit_log import AuditLog
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..models.user import User, UserRole
from ..schemas.user import UserOut
from ..services.audit_chain import verify_chain
from .deps import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Schemas ────────────────────────────────────────────────────────────────
class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    full_name: Optional[str] = None
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default=UserRole.DISPATCHER.value)


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    assigned_hospital_id: Optional[int] = None


class AdminUserOut(UserOut):
    assigned_hospital_id: Optional[int] = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    details: Optional[dict] = None


class RoleCount(BaseModel):
    role: str
    count: int


class OverviewOut(BaseModel):
    user_counts: List[RoleCount]
    total_users: int
    total_ambulances: int
    available_ambulances: int
    busy_ambulances: int
    total_hospitals: int
    hospitals_on_diversion: int
    pending_emergencies: int
    active_dispatches: int
    dispatches_today: int


class AmbulanceAssignIn(BaseModel):
    user_id: Optional[int] = Field(default=None,
        description="Set None to release the unit.")


# ── Users ──────────────────────────────────────────────────────────────────
@router.get("/users", response_model=List[AdminUserOut])
async def list_users(
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    stmt = select(User).order_by(User.id.asc())
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    rows = (await db.scalars(stmt)).all()
    return [AdminUserOut.model_validate(u) for u in rows]


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    valid_roles = {r.value for r in UserRole}
    if payload.role not in valid_roles:
        raise HTTPException(400,
            detail=f"role must be one of {sorted(valid_roles)}")
    existing = await db.scalar(
        select(User).where(User.username == payload.username))
    if existing:
        raise HTTPException(409, detail="Username already exists.")
    u = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return AdminUserOut.model_validate(u)


@router.patch("/users/{uid}", response_model=AdminUserOut)
async def update_user(
    uid: int,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    u = await db.scalar(select(User).where(User.id == uid))
    if not u:
        raise HTTPException(404, detail="User not found.")
    data = payload.model_dump(exclude_unset=True)

    if "role" in data:
        valid_roles = {r.value for r in UserRole}
        if data["role"] not in valid_roles:
            raise HTTPException(400, detail=f"role must be one of {sorted(valid_roles)}")
    if "password" in data and data["password"]:
        u.hashed_password = hash_password(data.pop("password"))
    else:
        data.pop("password", None)

    for k, v in data.items():
        setattr(u, k, v)
    await db.commit()
    await db.refresh(u)
    return AdminUserOut.model_validate(u)


@router.delete("/users/{uid}", status_code=204)
async def deactivate_user(
    uid: int,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(require_role("admin")),
):
    """Soft-delete: flips is_active=False. Hard-deletion would orphan
    audit rows and break dispatch history."""
    if uid == me.id:
        raise HTTPException(409, detail="Cannot deactivate yourself.")
    u = await db.scalar(select(User).where(User.id == uid))
    if not u:
        raise HTTPException(404, detail="User not found.")
    u.is_active = False
    await db.commit()


# ── Audit log ──────────────────────────────────────────────────────────────
class AuditVerifyOut(BaseModel):
    ok: bool
    first_bad_id: Optional[int] = None
    rows_checked: int


class PolicyRow(BaseModel):
    sub: str
    obj: str
    act: str
    eft: str = "allow"


class PolicyTestIn(BaseModel):
    role: str
    obj: str
    act: str


class PolicyTestOut(BaseModel):
    role: str
    obj: str
    act: str
    allowed: bool


@router.get("/policy", response_model=List[PolicyRow])
async def get_policy(_: User = Depends(require_role("admin"))):
    """Read the seeded RBAC + ABAC policy (casbin)."""
    rows = list_policy()
    return [PolicyRow(sub=r[0], obj=r[1], act=r[2],
                      eft=r[3] if len(r) > 3 else "allow")
            for r in rows]


@router.post("/policy/reload", status_code=204)
async def reload_policy_route(_: User = Depends(require_role("admin"))):
    """Re-read core/policy.csv from disk without a backend restart."""
    reload_policy()


@router.post("/policy/test", response_model=PolicyTestOut)
async def test_policy(
    payload: PolicyTestIn,
    _: User = Depends(require_role("admin")),
):
    """Quick check 'can ROLE perform ACT on OBJ?' for ad-hoc auditing."""
    return PolicyTestOut(
        role=payload.role, obj=payload.obj, act=payload.act,
        allowed=policy_enforce(payload.role, payload.obj, payload.act),
    )


@router.get("/audit-log/verify", response_model=AuditVerifyOut)
async def verify_audit_chain(
    limit: Optional[int] = Query(None, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """Re-walk the SHA-256 chain over audit_log. Reports whether every
    stored row_hash still matches its computed value, and (if not) the id
    where the chain first broke."""
    ok, first_bad, n = await verify_chain(db, limit=limit)
    return AuditVerifyOut(ok=ok, first_bad_id=first_bad, rows_checked=n)


@router.get("/audit-log", response_model=List[AuditLogOut])
async def audit_log(
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    rows = (await db.scalars(stmt.limit(limit))).all()
    return [AuditLogOut.model_validate(r) for r in rows]


# ── Overview / system snapshot ─────────────────────────────────────────────
@router.get("/overview", response_model=OverviewOut)
async def overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    today = datetime.utcnow() - timedelta(hours=24)

    role_rows = (await db.execute(
        select(User.role, func.count(User.id)).group_by(User.role)
    )).all()
    user_counts = [RoleCount(role=r, count=c) for r, c in role_rows]
    total_users = sum(rc.count for rc in user_counts)

    total_amb = await db.scalar(select(func.count(Ambulance.id))) or 0
    avail = await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    ) or 0
    busy = await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status != AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    ) or 0

    total_h = await db.scalar(select(func.count(Hospital.id))) or 0
    on_div = await db.scalar(
        select(func.count(Hospital.id))
        .where(Hospital.is_diversion == True, Hospital.is_active == True)
    ) or 0

    pending_em = await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.status == "pending")
    ) or 0
    active_dispatch = await db.scalar(
        select(func.count(Dispatch.id))
        .where(Dispatch.status.in_(
            ["dispatched", "en_route", "on_scene", "transporting"]))
    ) or 0
    dispatches_today = await db.scalar(
        select(func.count(Dispatch.id))
        .where(Dispatch.dispatched_at >= today)
    ) or 0

    return OverviewOut(
        user_counts=user_counts,
        total_users=int(total_users),
        total_ambulances=int(total_amb),
        available_ambulances=int(avail),
        busy_ambulances=int(busy),
        total_hospitals=int(total_h),
        hospitals_on_diversion=int(on_div),
        pending_emergencies=int(pending_em),
        active_dispatches=int(active_dispatch),
        dispatches_today=int(dispatches_today),
    )


# ── Fleet / hospital admin convenience ─────────────────────────────────────
@router.patch("/ambulances/{amb_id}/assign", status_code=204)
async def assign_paramedic(
    amb_id: int,
    payload: AmbulanceAssignIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """Force-assign a paramedic User to an Ambulance (or release).
    Lets admin set up the demo without each paramedic having to /driver/claim."""
    amb = await db.scalar(select(Ambulance).where(Ambulance.id == amb_id))
    if not amb:
        raise HTTPException(404, detail="Ambulance not found.")

    if payload.user_id is not None:
        user = await db.scalar(select(User).where(User.id == payload.user_id))
        if not user:
            raise HTTPException(404, detail="User not found.")
        if user.role not in ("paramedic", "admin"):
            raise HTTPException(409,
                detail="Only paramedic or admin users can be assigned to a unit.")
        # Release any previous claim that user had.
        prev = await db.scalar(
            select(Ambulance).where(Ambulance.assigned_user_id == user.id))
        if prev and prev.id != amb.id:
            prev.assigned_user_id = None

    amb.assigned_user_id = payload.user_id
    await db.commit()
