# scripts/kalshi_client.py
import time
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_RATE_LIMIT_DELAY = 0.25  # seconds between requests; stay well under API rate limit


class KalshiClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {api_key}",
            "Accept": "application/json",
        })
        self._last_request = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict:
        elapsed = time.time() - self._last_request
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params)
        self._last_request = time.time()
        resp.raise_for_status()
        return resp.json()

    def get_series(self, series_ticker: str) -> dict:
        """Fetch series metadata. Works without auth (public endpoint)."""
        return self._get(f"/series/{series_ticker}")

    def get_markets(self, series_ticker: str, status: str = "finalized",
                    min_ts: int | None = None, max_ts: int | None = None) -> list[dict]:
        """
        Fetch all markets for a series. Paginates automatically.
        Returns a flat list of market objects.
        """
        markets = []
        cursor = None
        while True:
            params = {"series_ticker": series_ticker, "status": status, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            if min_ts:
                params["min_close_ts"] = min_ts
            if max_ts:
                params["max_close_ts"] = max_ts
            data = self._get("/markets", params)
            batch = data.get("markets", [])
            markets.extend(batch)
            cursor = data.get("cursor")
            if not cursor or not batch:
                break
        return markets

    def get_candlesticks(self, ticker: str, start_ts: int, end_ts: int,
                         period_interval: int = 60) -> list[dict]:
        """
        Fetch OHLCV candlesticks for a specific market ticker.
        period_interval: candle width in minutes (60 = hourly).
        """
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval,
        }
        data = self._get(f"/markets/{ticker}/candlesticks", params)
        return data.get("candlesticks", [])
