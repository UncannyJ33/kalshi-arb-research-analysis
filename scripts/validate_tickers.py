"""
Validate that every Kalshi series ticker in CITIES resolves to a real series.
Uses the public series endpoint — no API key required.

Run: python scripts/validate_tickers.py
"""
import sys
import time
import logging
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import get_series_tickers

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def validate_ticker(ticker: str) -> tuple[bool, str]:
    """Return (ok, message) for a single series ticker."""
    try:
        resp = requests.get(f"{BASE_URL}/series/{ticker}", timeout=10)
        if resp.status_code == 200:
            title = resp.json().get("series", {}).get("title", "unknown")
            return True, title
        return False, f"HTTP {resp.status_code}"
    except requests.RequestException as e:
        return False, str(e)


def main():
    tickers = get_series_tickers()
    logger.info(f"Validating {len(tickers)} series tickers...\n")

    passed, failed = [], []
    for ticker in tickers:
        ok, detail = validate_ticker(ticker)
        status = "PASS" if ok else "FAIL"
        logger.info(f"  [{status}] {ticker:<18} {detail}")
        (passed if ok else failed).append(ticker)
        time.sleep(0.2)

    logger.info(f"\nResult: {len(passed)}/{len(tickers)} tickers valid")
    if failed:
        logger.error(f"FAILED tickers: {failed}")
        sys.exit(1)
    else:
        logger.info("All tickers validated. Safe to proceed.")


if __name__ == "__main__":
    main()
