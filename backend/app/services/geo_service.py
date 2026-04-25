"""Geographic helpers — distance, zone mapping, simple route encoding."""
import math
from typing import List, Tuple

from ..config import settings

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in km."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_zone_id(lat: float, lng: float, n_zones: int = 12) -> int:
    """Map a lat/lng to one of N synthetic city zones.

    We use a simple offset-from-city-center grid. Good enough for a hackathon.
    """
    dlat = lat - settings.seed_city_lat
    dlng = lng - settings.seed_city_lng
    # Quantize into a 4x3 grid centered on the city
    row = max(0, min(2, int((dlat + 0.05) / 0.04)))
    col = max(0, min(3, int((dlng + 0.06) / 0.04)))
    return (row * 4 + col) % n_zones


def simple_route(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float,
    n_points: int = 20,
) -> List[Tuple[float, float]]:
    """Linear interpolation between two points — pseudo-route for the simulator."""
    return [
        (start_lat + (end_lat - start_lat) * t,
         start_lng + (end_lng - start_lng) * t)
        for t in [i / (n_points - 1) for i in range(n_points)]
    ]
