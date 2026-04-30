"""Seed demo data — runs once when the database is empty.

Creates:
  - 1 admin user
  - N hospitals around the configured city
  - M ambulances at hospital depots
"""
import random
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .core.logging import log
from .core.security import hash_password
from .models.ambulance import Ambulance, AmbulanceType
from .models.hospital import Hospital
from .models.user import User, UserRole


SPECIALTIES_POOL = ["cardiac", "stroke", "trauma", "pediatric", "burns", "general"]


def _make_hospitals(city_lat: float, city_lng: float, n: int) -> list[Hospital]:
    rng = random.Random(42)
    hospitals = []
    names = [
        "City Apex Hospital", "St. Mary's Medical Center",
        "Lifeline Multi-Speciality", "Sunrise General Hospital",
        "Aarogya Trauma Center", "Sahara Pediatric Hospital",
        "Heritage Cardiac Institute", "Metro Burns & Recovery",
        "Coastline Medical College", "Nirvana Wellness Hospital",
    ]
    for i in range(n):
        # spread roughly within ~10km of the city center
        lat = city_lat + rng.uniform(-0.06, 0.06)
        lng = city_lng + rng.uniform(-0.07, 0.07)
        # Random specialty mix biased to "general"
        n_specs = rng.randint(2, 4)
        specs = list(set(["general"] +
                         rng.sample(SPECIALTIES_POOL, n_specs)))
        h = Hospital(
            name=names[i % len(names)] + (f" #{i+1}" if i >= len(names) else ""),
            address=f"Building {i+1}, Sector {chr(65 + i % 8)}",
            lat=lat, lng=lng,
            phone=f"+91-22-{rng.randint(20000000, 29999999)}",
            emergency_phone=f"+91-22-{rng.randint(40000000, 49999999)}",
            specialties=specs,
            total_beds_general=rng.randint(80, 160),
            available_beds_general=rng.randint(10, 60),
            total_beds_icu=rng.randint(20, 50),
            available_beds_icu=rng.randint(2, 18),
            total_beds_trauma=rng.randint(8, 25),
            available_beds_trauma=rng.randint(1, 10),
            total_beds_pediatric=rng.randint(15, 35),
            available_beds_pediatric=rng.randint(2, 18),
            total_beds_burns=rng.randint(5, 14),
            available_beds_burns=rng.randint(0, 7),
            er_wait_minutes=rng.randint(5, 75),
            is_diversion=False,
            quality_rating=rng.randint(3, 5),
            # ~40% of facilities have a helipad — typical urban mix.
            has_helipad=rng.random() < 0.40,
        )
        hospitals.append(h)
    return hospitals


def _make_ambulances(hospitals: list[Hospital], n: int) -> list[Ambulance]:
    rng = random.Random(123)
    types_dist = ([AmbulanceType.BLS.value] * 12
                  + [AmbulanceType.ALS.value] * 6
                  + [AmbulanceType.ICU_MOBILE.value] * 2)
    ambulances = []
    paramedic_first = ["Rohit", "Priya", "Arjun", "Sneha", "Amit",
                       "Neha", "Vikram", "Kavya", "Ravi", "Anjali",
                       "Suresh", "Pooja", "Karthik", "Divya", "Manish",
                       "Sunita", "Rahul", "Isha", "Aditya", "Meena"]
    paramedic_last = ["Sharma", "Patel", "Iyer", "Nair", "Reddy",
                      "Khan", "Singh", "Joshi", "Verma", "Mehta"]
    for i in range(n):
        depot = rng.choice(hospitals)
        amb_type = rng.choice(types_dist)
        a = Ambulance(
            registration_number=f"AMB-{1000 + i}",
            ambulance_type=amb_type,
            current_lat=depot.lat,
            current_lng=depot.lng,
            home_station_lat=depot.lat,
            home_station_lng=depot.lng,
            home_station_name=depot.name,
            paramedic_name=f"{rng.choice(paramedic_first)} {rng.choice(paramedic_last)}",
            paramedic_phone=f"+91-9{rng.randint(100000000, 999999999)}",
            paramedic_certification={
                AmbulanceType.BLS.value: "EMT-Basic",
                AmbulanceType.ALS.value: "EMT-Paramedic",
                AmbulanceType.ICU_MOBILE.value: "ACLS",
            }[amb_type],
            equipment={
                AmbulanceType.BLS.value: ["oxygen", "AED", "first-aid"],
                AmbulanceType.ALS.value: ["oxygen", "AED", "ECG", "IV", "drugs"],
                AmbulanceType.ICU_MOBILE.value: ["oxygen", "AED", "ECG", "IV",
                                                  "ventilator", "monitor", "drugs"],
            }[amb_type],
        )
        ambulances.append(a)
    return ambulances


async def seed_database(db: AsyncSession, force: bool = False):
    """Idempotent: only seeds when the DB is empty (or force=True)."""
    has_data = (await db.scalar(select(Hospital))) is not None
    if has_data and not force:
        log.info("Seed: data already present — skipping.")
        return

    log.info("Seed: populating database with demo data...")

    # 1. Admin user
    existing_admin = await db.scalar(
        select(User).where(User.username == settings.admin_username)
    )
    if not existing_admin:
        db.add(User(
            username=settings.admin_username,
            email=settings.admin_email,
            full_name="System Administrator",
            hashed_password=hash_password(settings.admin_password),
            role=UserRole.ADMIN.value,
        ))
        log.success(f"Seed: admin user created — {settings.admin_username}/"
                    f"{settings.admin_password}")

    # 2. Hospitals
    hospitals = _make_hospitals(settings.seed_city_lat, settings.seed_city_lng,
                                 settings.seed_num_hospitals)
    db.add_all(hospitals)
    await db.commit()
    log.success(f"Seed: {len(hospitals)} hospitals created")

    # 3. Ambulances (need hospitals committed to use them as depots)
    await db.refresh(hospitals[0])
    ambulances = _make_ambulances(hospitals, settings.seed_num_ambulances)
    db.add_all(ambulances)
    await db.commit()
    log.success(f"Seed: {len(ambulances)} ambulances created")
