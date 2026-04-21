# scripts/openmeteo_client.py
"""
Open-Meteo historical weather archive client.

Fetches daily high/low temperatures in °F for a lat/lon and date range.
Free public API — no key required.

API docs: https://open-meteo.com/en/docs/historical-weather-api
"""
import logging
import requests

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_observed(lat: float, lon: float, start_date: str, end_date: str,
                   timezone: str = "America/New_York") -> dict | None:
    """
    Fetch daily high/low temperatures for a location over a date range.

    Returns the raw Open-Meteo response dict with a "daily" key containing
    "time", "temperature_2m_max", "temperature_2m_min" lists.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": timezone,
    }
    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Open-Meteo request failed for ({lat},{lon}): {e}")
        return None
