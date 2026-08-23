"""
Simple Nominatim geocoder for landmark navigation.
"""

from typing import Optional, Tuple
import requests

def geocode(query: str, country_codes: str = "tw,in") -> Optional[Tuple[float, float]]:
    """
    Returns (lat, lon) or None.
    Uses OpenStreetMap Nominatim (free, rate-limited).
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": country_codes
        }
        headers = {"User-Agent": "NaVILA-Lite/1.0 (research demo)"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None
