# scripts/pull_kalshi.py
"""
Pull settled Kalshi weather markets and 10 AM ET open-price candlesticks.

Writes:
  data/kalshi/{series_ticker}.json       — list of settled market objects
  data/kalshi_candles/{market_ticker}.json — candlestick at 10 AM ET open

Run: python scripts/pull_kalshi.py
"""
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES
from kalshi_client import KalshiClient
from config_loader import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
KALSHI_DIR = DATA_DIR / "kalshi"
CANDLES_DIR = DATA_DIR / "kalshi_candles"
ET = ZoneInfo("America/New_York")


def market_open_window(weather_date: datetime) -> tuple[int, int]:
    """
    Return (start_ts, end_ts) as Unix timestamps for the 10 AM–12 PM ET window
    on day D-1 (the day before the weather day). This is when the market opens.
    """
    day_before = weather_date.date() - timedelta(days=1)
    start = datetime(day_before.year, day_before.month, day_before.day,
                     10, 0, 0, tzinfo=ET)
    end = datetime(day_before.year, day_before.month, day_before.day,
                   12, 0, 0, tzinfo=ET)
    return int(start.timestamp()), int(end.timestamp())


def weather_date_from_close_time(close_ts: str) -> datetime:
    """Parse close_time (ISO string) to UTC datetime."""
    return datetime.fromisoformat(close_ts.replace("Z", "+00:00"))


def pull_series(client: KalshiClient, series_ticker: str, lookback_days: int) -> list[dict]:
    cache_path = KALSHI_DIR / f"{series_ticker}.json"
    if cache_path.exists():
        logger.info(f"  {series_ticker}: using cached markets")
        with open(cache_path) as f:
            return json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    min_ts = int(cutoff.timestamp())
    logger.info(f"  {series_ticker}: pulling settled markets since {cutoff.date()}")
    markets = client.get_markets(series_ticker, status="settled", min_ts=min_ts)
    logger.info(f"  {series_ticker}: got {len(markets)} markets")

    with open(cache_path, "w") as f:
        json.dump(markets, f)
    return markets


def pull_candle(client: KalshiClient, market: dict, series_ticker: str) -> dict | None:
    ticker = market["ticker"]
    cache_path = CANDLES_DIR / f"{ticker}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    close_ts = market.get("close_time", "")
    if not close_ts:
        logger.warning(f"  {ticker}: missing close_time, skipping")
        return None

    weather_dt = weather_date_from_close_time(close_ts)
    start_ts, end_ts = market_open_window(weather_dt)

    candles = client.get_candlesticks(series_ticker, ticker, start_ts, end_ts, period_interval=60)
    if not candles:
        logger.debug(f"  no candles for {ticker}")
        return None

    # Take the first candle after 10 AM ET — its open price is the market open price
    result = {"ticker": ticker, "candle": candles[0]}
    with open(cache_path, "w") as f:
        json.dump(result, f)
    return result


def main():
    cfg = load_config()
    client = KalshiClient(cfg["kalshi_api_key"])
    lookback = cfg.get("lookback_days", 60)

    KALSHI_DIR.mkdir(parents=True, exist_ok=True)
    CANDLES_DIR.mkdir(parents=True, exist_ok=True)

    total_markets = 0
    total_candles = 0

    for city_id, city_cfg in CITIES.items():
        for series in city_cfg["series"]:
            ticker = series["ticker"]
            logger.info(f"{city_cfg['name']} / {ticker}")

            markets = pull_series(client, ticker, lookback)
            total_markets += len(markets)

            for market in markets:
                result = pull_candle(client, market, ticker)
                if result:
                    total_candles += 1

    logger.info(f"\nDone. {total_markets} markets, {total_candles} candles pulled.")


if __name__ == "__main__":
    main()
