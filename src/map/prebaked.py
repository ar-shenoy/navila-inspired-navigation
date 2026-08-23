"""
Instant prebaked local obstacle packs for demo spawn locations.
No network — first paint is immediate.
Live OSM can still expand <100m around the robot as it moves.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

# (lat, lon) must match app LOCATIONS keys
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
    """List of (north_m, east_m, width_m, height_m) building boxes."""
    if name == "Open Field":
        return [(40, 40, 12, 8), (-50, 30, 10, 10), (35, -55, 15, 8)]
    if name == "Taipei 101":
        return [
            (25, 10, 45, 45),
            (-30, 40, 28, 20),
            (50, -35, 22, 18),
            (-55, -20, 30, 16),
            (15, -60, 18, 14),
            (70, 20, 20, 12),
            (-20, 70, 16, 22),
            (40, 55, 14, 14),
            (-70, 50, 18, 10),
            (60, -70, 12, 20),
        ]
    if "Station" in name:
        return [
            (20, 0, 50, 20),
            (0, 40, 18, 35),
            (-40, -10, 25, 18),
            (45, -40, 20, 15),
            (-30, 50, 15, 15),
            (55, 30, 12, 22),
            (-55, 25, 20, 12),
            (10, -55, 30, 12),
            (-20, -45, 14, 18),
        ]
    if "University" in name:
        return [
            (30, 25, 35, 20),
            (-25, 35, 22, 30),
            (40, -30, 28, 16),
            (-45, -20, 18, 22),
            (15, 55, 20, 14),
            (-55, 10, 16, 16),
            (55, 40, 14, 18),
            (0, -50, 40, 12),
            (-30, -55, 15, 15),
            (50, -55, 12, 12),
        ]
    if "Bangalore" in name:
        cells = [
            (20, 20), (20, -20), (-20, 20), (-20, -20),
            (45, 10), (45, -35), (-45, 15), (-40, -40),
            (10, 50), (-15, 55), (55, 45), (-55, -15),
            (30, 60), (-60, 30), (0, -60), (60, 0),
        ]
        return [(n, e, 14 + (i % 5) * 2, 10 + (i % 4) * 2) for i, (n, e) in enumerate(cells)]
    # Kaohsiung / Tainan
    return [
        (25, 25, 22, 16),
        (-25, 30, 18, 20),
        (35, -25, 20, 14),
        (-40, -20, 16, 16),
        (50, 15, 14, 18),
        (-15, 50, 24, 12),
        (20, -50, 18, 12),
        (-50, 5, 12, 22),
        (18, 12, 8, 8),
    ]


def get_prebaked(name: str) -> dict:
    """
    Return map_data dict compatible with osm_loader / controller.
    Instant — no network.
    """
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
            # ring is [lat, lon] → shapely wants (lon, lat)
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
