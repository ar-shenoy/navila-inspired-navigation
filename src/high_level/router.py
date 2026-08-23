"""
Open-source routing via public OSRM server.
Returns real road geometry.
"""

from typing import List, Tuple, Optional
import requests

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

def get_osrm_route(start_lat: float, start_lon: float,
                   end_lat: float, end_lon: float,
                   max_waypoints: int = 80) -> Optional[List[Tuple[float, float]]]:
    """
    Returns list of (lat, lon) waypoints along real roads, or None on failure.
    """
    try:
        url = OSRM_URL.format(lon1=start_lon, lat1=start_lat, lon2=end_lon, lat2=end_lat)
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false"
        }
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != "Ok":
            return None
        coords = data["routes"][0]["geometry"]["coordinates"]  # [lon, lat]
        # Convert to (lat, lon) and downsample if very long
        waypoints = [(c[1], c[0]) for c in coords]
        if len(waypoints) > max_waypoints:
            step = max(1, len(waypoints) // max_waypoints)
            waypoints = waypoints[::step]
            # ensure last point is included
            if waypoints[-1] != (coords[-1][1], coords[-1][0]):
                waypoints.append((coords[-1][1], coords[-1][0]))
        return waypoints
    except Exception:
        return None
