# scripts/pull_forecasts.py
"""
Pull GFS-MOS 12Z forecast data for each city × weather day in the dataset.

For weather day D, we pull the 12Z run from day D-1. The 12Z run (8 AM ET)
was available to market participants before the 10 AM ET market open.

Writes: data/forecasts/{city_id}_{YYYY-MM-DD}.json per city per weather day.

Run: python scripts/pull_forecasts.py
"""
import sys
import json
import logging
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES
from iem_client import fetch_mos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
FORECASTS_DIR = DATA_DIR / "forecasts"


def dates_in_window(lookback_days: int = 60) -> list[str]:
    """Return list of YYYY-MM-DD strings for the past lookback_days."""
    today = datetime.now(timezone.utc).date()
    return [
        (today - timedelta(days=i)).isoformat()
        for i in range(1, lookback_days + 1)
    ]


def mos_runtime_for_date(weather_date_str: str) -> str:
    """Return the 12Z runtime ISO string for day D-1 given weather date YYYY-MM-DD."""
    d = date.fromisoformat(weather_date_str) - timedelta(days=1)
    return f"{d.isoformat()}T12:00:00Z"


def main():
    FORECASTS_DIR.mkdir(parents=True, exist_ok=True)
    weather_dates = dates_in_window(lookback_days=60)

    for city_id, city_cfg in CITIES.items():
        station = city_cfg["mos_station"]
        logger.info(f"{city_cfg['name']} ({station}): pulling {len(weather_dates)} days")
        fetched = skipped = missing = 0

        for weather_date in weather_dates:
            cache_path = FORECASTS_DIR / f"{city_id}_{weather_date}.json"
            if cache_path.exists():
                skipped += 1
                continue

            runtime = mos_runtime_for_date(weather_date)
            data = fetch_mos(station, runtime)
            if data is None:
                missing += 1
                continue

            out = {**data, "_meta": {"city_id": city_id, "weather_date": weather_date, "runtime": runtime}}
            with open(cache_path, "w") as f:
                json.dump(out, f)
            fetched += 1
            time.sleep(0.5)  # be gentle with IEM's public API

        logger.info(f"  fetched={fetched} skipped={skipped} missing={missing}")

    logger.info("Forecast pull complete.")


if __name__ == "__main__":
    main()
