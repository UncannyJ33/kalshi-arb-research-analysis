# scripts/iem_client.py
"""
Iowa Environmental Mesonet GFS-MOS archive client.

IEM archives GFS-MOS forecast guidance by ICAO station and model runtime.
We pull the 12Z run from day D-1 (available ~8 AM ET, before market open at 10 AM ET).

API docs: https://mesonet.agron.iastate.edu/api/1/mos.json
"""
import logging
import requests

logger = logging.getLogger(__name__)

IEM_URL = "https://mesonet.agron.iastate.edu/api/1/mos.json"


def fetch_mos(station: str, runtime_iso: str) -> dict | None:
    """
    Fetch GFS-MOS forecast issued at runtime_iso for the given station.

    runtime_iso: ISO format UTC string, e.g. "2026-04-16T12:00:00Z"
    Returns the raw IEM API response dict, or None if unavailable.
    """
    params = {"station": station, "runtime": runtime_iso, "model": "GFS"}
    try:
        resp = requests.get(IEM_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # IEM returns {"forecasts": [...]} or {"error": "..."}
        if "error" in data:
            logger.warning(f"IEM error for {station} at {runtime_iso}: {data['error']}")
            return None
        return data
    except requests.RequestException as e:
        logger.warning(f"IEM request failed for {station} at {runtime_iso}: {e}")
        return None


def extract_daily_forecast(mos_data: dict, weather_date_str: str) -> dict | None:
    """
    Extract the high/low temperature forecast for weather_date_str (YYYY-MM-DD)
    from a GFS-MOS response.

    GFS-MOS provides forecasts at 6-hour intervals. Daily high = max(N18, N00, N06, N12)
    across the weather date's valid times (00Z through 18Z of weather_date).
    Returns {"t_high": float, "t_low": float, "sigma": float | None} or None.
    """
    forecasts = mos_data.get("forecasts", [])
    if not forecasts:
        return None

    # Each forecast entry has "valid" (ISO timestamp) and temperature fields
    # Filter to entries valid on the weather date
    day_temps = []
    for entry in forecasts:
        valid = entry.get("valid", "")
        if valid.startswith(weather_date_str):
            t = entry.get("tmp")  # temperature in °F
            if t is not None:
                day_temps.append(float(t))

    if not day_temps:
        return None

    t_high = max(day_temps)
    t_low = min(day_temps)

    # MOS spread: use "std" field if present for sigma; else None (caller falls back to 2.5)
    sigma_values = [
        float(entry["std"]) for entry in forecasts
        if entry.get("valid", "").startswith(weather_date_str) and entry.get("std") is not None
    ]
    sigma = sum(sigma_values) / len(sigma_values) if sigma_values else None

    return {"t_high": t_high, "t_low": t_low, "sigma": sigma}
