# scripts/pull_actuals.py
"""
Pull observed daily high/low temperatures from Open-Meteo for each city.

Writes: data/actuals/{city_id}.json — full response with daily temps.

Run: python scripts/pull_actuals.py
"""
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES
from openmeteo_client import fetch_observed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ACTUALS_DIR = DATA_DIR / "actuals"


def main():
    ACTUALS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=61)).isoformat()
    end_date = (today - timedelta(days=1)).isoformat()

    for city_id, city_cfg in CITIES.items():
        cache_path = ACTUALS_DIR / f"{city_id}.json"
        if cache_path.exists():
            logger.info(f"{city_cfg['name']}: using cached actuals")
            continue

        logger.info(f"{city_cfg['name']}: pulling {start_date} → {end_date}")
        data = fetch_observed(
            lat=city_cfg["lat"],
            lon=city_cfg["lon"],
            start_date=start_date,
            end_date=end_date,
        )
        if data is None:
            logger.error(f"{city_cfg['name']}: pull failed")
            continue

        data["_meta"] = {"city_id": city_id}
        with open(cache_path, "w") as f:
            json.dump(data, f)
        logger.info(f"{city_cfg['name']}: {len(data['daily']['time'])} days")

    logger.info("Actuals pull complete.")


if __name__ == "__main__":
    main()
