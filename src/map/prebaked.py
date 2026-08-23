"""
Instant prebaked local obstacle packs for demo spawn locations.
No network — first paint is immediate.
Live OSM can still expand <100m around the robot as it moves.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

SPAWN_COORDS: Dict[str, Tuple[float, float]] = {
    "Taipei 101": (25.0339, 121.5640),
    "National Taiwan University": (25.0170, 121.5375),
    "Taipei Main Station": (25.0478, 121.5170),
    "Kaohsiung": (22.6275, 120.3010),
    "Tainan": (23.0005, 120.2270),
    "Bangalore MG Road": (12.9760, 77.6060),
    "Open Field": (25.0510, 121.5810),
}

PREBAKED_RADIUS_M = 100


def _m_to_deg(lat: float, north_m: float, east_m: float):
    dlat = north_m / 111320.0
    dlon = east_m / (111320.0 * max(0.25, abs(math.cos(math.radians(lat)))))
    return dlat, dlon


def _rect(lat: float, lon: float, cx_n: float, cx_e: float, w_m: float, h_m: float):
    dlat_c, dlon_c = _m_to_deg(lat, cx_n, cx_e)
    dlat_h, dlon_w = _m_to_deg(lat, h_m / 2.0, w_m / 2.0)
    clat, clon = lat + dlat_c, lon + dlon_c
    return [
        [clat - dlat_h, clon - dlon_w],
        [clat - dlat_h, clon + dlon_w],
        [clat + dlat_h, clon + dlon_w],
        [clat + dlat_h, clon - dlon_w],
        [clat - dlat_h, clon - dlon_w],
    ]


def _offsets_for(name: str) -> List[Tuple[float, float, float, float]]:
    """(north_m, east_m, width_m, height_m) — denser packs for a convincing demo."""
    if name == "Open Field":
        return [
            (35, 40, 14, 10), (-45, 35, 12, 12), (40, -50, 16, 10),
            (-55, -30, 10, 14), (60, 15, 12, 8),
        ]
    if name == "Taipei 101":
        return [
            (28, 12, 50, 48), (-32, 42, 30, 22), (52, -38, 24, 20),
            (-58, -22, 32, 18), (18, -62, 20, 16), (72, 22, 22, 14),
            (-22, 72, 18, 24), (42, 58, 16, 16), (-72, 52, 20, 12),
            (62, -72, 14, 22), (8, 35, 18, 14), (-40, -55, 16, 18),
            (55, 8, 14, 20), (-15, -75, 22, 12), (75, -25, 12, 16),
            (-65, 15, 15, 15), (30, 80, 12, 12), (-80, -40, 14, 10),
        ]
    if "Station" in name:
        return [
            (22, 5, 55, 22), (5, 42, 20, 38), (-42, -12, 28, 20),
            (48, -42, 22, 16), (-32, 52, 16, 16), (58, 32, 14, 24),
            (-58, 28, 22, 14), (12, -58, 32, 14), (-22, -48, 16, 20),
            (35, 60, 14, 14), (-50, -40, 18, 12), (70, -10, 12, 18),
            (-70, 5, 15, 15), (0, 70, 25, 12), (40, -70, 15, 15),
        ]
    if "University" in name:
        return [
            (32, 28, 38, 22), (-28, 38, 24, 32), (42, -32, 30, 18),
            (-48, -22, 20, 24), (18, 58, 22, 16), (-58, 12, 18, 18),
            (58, 42, 16, 20), (5, -52, 42, 14), (-32, -58, 16, 16),
            (52, -58, 14, 14), (-15, 70, 20, 12), (70, -15, 12, 20),
            (-70, -35, 15, 15), (25, 75, 14, 14), (-45, 55, 18, 12),
            (60, 20, 12, 16),
        ]
    if "Bangalore" in name:
        cells = []
        for n in range(-70, 75, 22):
            for e in range(-70, 75, 22):
                if abs(n) < 12 and abs(e) < 12:
                    continue  # keep spawn clear
                cells.append((float(n), float(e), 12.0, 10.0))
        return cells[:28]
    # Kaohsiung / Tainan
    return [
        (28, 28, 24, 18), (-28, 32, 20, 22), (38, -28, 22, 16),
        (-42, -22, 18, 18), (52, 18, 16, 20), (-18, 52, 26, 14),
        (22, -52, 20, 14), (-52, 8, 14, 24), (18, 15, 10, 10),
        (65, -40, 14, 14), (-60, -45, 16, 12), (45, 55, 12, 18),
        (-35, 65, 18, 12), (70, 30, 12, 12), (-70, 40, 14, 10),
    ]


def get_prebaked(name: str) -> dict:
    if name not in SPAWN_COORDS:
        return {
            "buildings": [],
            "building_coords": [],
            "road_graph": None,
            "road_lines": [],
            "success": False,
            "error": f"No prebaked pack for {name}",
            "from_cache": False,
            "center": None,
            "radius": 0,
            "source": "none",
        }

    lat, lon = SPAWN_COORDS[name]
    rings = [_rect(lat, lon, n, e, w, h) for (n, e, w, h) in _offsets_for(name)]

    buildings = []
    try:
        from shapely.geometry import Polygon

        for ring in rings:
            poly = Polygon([(p[1], p[0]) for p in ring])
            if poly.is_valid and not poly.is_empty:
                buildings.append(poly)
    except Exception:
        buildings = []

    return {
        "buildings": buildings,
        "building_coords": rings,
        "road_graph": None,
        "road_lines": [],
        "success": True,
        "error": None,
        "from_cache": True,
        "center": (lat, lon),
        "radius": PREBAKED_RADIUS_M,
        "source": "prebaked",
    }
