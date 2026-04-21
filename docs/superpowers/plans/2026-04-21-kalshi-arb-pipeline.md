# Kalshi Weather Tail Mispricing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that pulls 60 days of Kalshi weather market data + GFS-MOS forecasts + observed temperatures, computes forecast-implied EV for each tail bucket, and produces a calibration analysis and go/no-go trading recommendation.

**Architecture:** Five sequential data scripts (validate → pull_kalshi → pull_forecasts → pull_actuals → build_dataset) write cached JSON/parquet files to data/. Two analysis scripts (analyze + visualize) read the parquet and write plots + reports/findings.md. Shared logic lives in scripts/ev.py and scripts/cities.py. Scripts are idempotent — re-running skips already-cached files.

**Tech Stack:** Python 3.10+, requests, pandas, scipy, matplotlib, seaborn, pyarrow, pytest

---

## File Map

```
scripts/
  cities.py              — CITIES dict: ticker, MOS station, coords per city
  ev.py                  — taker_fee(), bucket_probability(), ev(), is_tail()
  kalshi_client.py       — KalshiClient: auth header, rate limiting, API methods
  iem_client.py          — fetch_mos(): pull IEM GFS-MOS by station + runtime
  openmeteo_client.py    — fetch_observed(): pull daily high/low from Open-Meteo
  validate_tickers.py    — hit every series ticker, log PASS/FAIL (no auth needed)
  pull_kalshi.py         — pull settled markets + 10 AM ET candlestick per market
  pull_forecasts.py      — pull GFS-MOS 12Z run for each city × day D-1
  pull_actuals.py        — pull observed daily high/low for each city × day
  build_dataset.py       — merge three sources → data/processed/dataset.parquet
  analyze.py             — EV, calibration stats, edge, falsification criteria
  visualize.py           — 4 plots + write reports/findings.md

tests/
  test_ev.py             — unit tests for fee formula, EV calc, bucket probability
  test_build_dataset.py  — tests for merge alignment and computed columns

config/
  settings.json          — gitignored; add your Kalshi API key here
  settings.example.json  — committed; shows required structure

data/                    — gitignored; all pulled data lives here
  kalshi/                — one JSON per series: list of settled markets
  kalshi_candles/        — one JSON per market ticker: candlestick at open
  forecasts/             — one JSON per city per date: MOS response
  actuals/               — one JSON per city: full Open-Meteo response
  processed/             — dataset.parquet (merged, analysis-ready)

reports/
  findings.md            — written by visualize.py; committed to repo
  figures/               — gitignored; plots written by visualize.py
```

---

## Task 1: Repo Scaffold

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `config/settings.example.json`
- Create: `reports/findings.md` (placeholder)
- Create: `README.md`
- Create all directories in the file map above

- [ ] **Step 1: Initialize git and create directories**

```bash
cd /Users/sj/Projects/GitHub/kalshi-arb-research-analysis
git init
mkdir -p scripts tests config data/kalshi data/kalshi_candles data/forecasts data/actuals data/processed reports/figures notebooks
touch scripts/__init__.py tests/__init__.py
```

- [ ] **Step 2: Create .gitignore**

```
venv/
data/
config/settings.json
__pycache__/
*.pyc
*.pyo
.DS_Store
reports/figures/
.pytest_cache/
*.egg-info/
dist/
build/
```

Write to `.gitignore`.

- [ ] **Step 3: Create requirements.txt**

```
requests>=2.31
pandas>=2.2
scipy>=1.12
matplotlib>=3.8
seaborn>=0.13
pyarrow>=15.0
pytest>=8.0
python-dateutil>=2.9
```

Write to `requirements.txt`.

- [ ] **Step 4: Create config/settings.example.json**

```json
{
  "kalshi_api_key": "your-api-key-here",
  "lookback_days": 60
}
```

Write to `config/settings.example.json`.

- [ ] **Step 5: Create config/settings.json from example**

```bash
cp config/settings.example.json config/settings.json
```

(User will fill in `kalshi_api_key` before running pull scripts.)

- [ ] **Step 6: Create README.md**

```markdown
# Kalshi Weather Tail Mispricing — Research Analysis

Historical analysis testing whether Kalshi daily weather markets systematically
misprice tail-probability buckets (≤5% and ≥95%).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Add your Kalshi API key to `config/settings.json` (copy from `settings.example.json`).

## Pipeline

Run scripts in order from the project root:

```bash
python scripts/validate_tickers.py      # confirm all series exist (no auth)
python scripts/pull_kalshi.py           # requires API key
python scripts/pull_forecasts.py        # no auth; hits IEM public API
python scripts/pull_actuals.py          # no auth; hits Open-Meteo public API
python scripts/build_dataset.py         # merges pulled data
python scripts/analyze.py               # computes EV + falsification criteria
python scripts/visualize.py             # writes reports/findings.md + figures/
```

## Fee Formula

Source: [Kalshi Fee Schedule Feb 2026](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
and [pm.wiki](https://pm.wiki/learn/kalshi-fees-explained)

> "Taker fee per contract = $0.07 × C × (1 − C). Where C = contract price from $0.01 to $0.99."

Charged at execution. Applies to both buyers and sellers regardless of outcome.

## Design

See `docs/superpowers/specs/2026-04-21-kalshi-arb-research-design.md`.
```

Write to `README.md`.

- [ ] **Step 7: Set up venv**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install cleanly.

- [ ] **Step 8: Initial commit**

```bash
git add .gitignore requirements.txt config/settings.example.json README.md \
        docs/superpowers/specs/2026-04-21-kalshi-arb-research-design.md \
        docs/superpowers/plans/2026-04-21-kalshi-arb-pipeline.md
git commit -m "feat: initial scaffold — spec, plan, config, requirements"
```

---

## Task 2: City Config (scripts/cities.py)

**Files:**
- Create: `scripts/cities.py`
- Create: `tests/test_cities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cities.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from cities import CITIES, get_series_tickers

def test_all_cities_have_required_keys():
    required = {"name", "mos_station", "lat", "lon", "series"}
    for city_id, cfg in CITIES.items():
        missing = required - cfg.keys()
        assert not missing, f"{city_id} missing keys: {missing}"

def test_each_series_has_ticker_and_market_type():
    for city_id, cfg in CITIES.items():
        for s in cfg["series"]:
            assert "ticker" in s, f"{city_id} series missing ticker"
            assert "market_type" in s, f"{city_id} series missing market_type"
            assert s["market_type"] in ("high", "low")

def test_chicago_has_only_low():
    chicago = CITIES["chicago"]
    types = [s["market_type"] for s in chicago["series"]]
    assert types == ["low"], "Chicago should have only a low-temp series"

def test_get_series_tickers_returns_all():
    tickers = get_series_tickers()
    assert "KXHIGHNY" in tickers
    assert "KXLOWTCHI" in tickers
    assert len(tickers) == 19  # 9 cities × 2 + Chicago × 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/sj/Projects/GitHub/kalshi-arb-research-analysis
source venv/bin/activate
pytest tests/test_cities.py -v
```

Expected: `ModuleNotFoundError: No module named 'cities'`

- [ ] **Step 3: Write cities.py**

```python
# scripts/cities.py

CITIES = {
    "nyc": {
        "name": "New York City",
        "mos_station": "KJFK",
        "lat": 40.71,
        "lon": -74.01,
        "series": [
            {"ticker": "KXHIGHNY",  "market_type": "high"},
            {"ticker": "KXLOWTNYC", "market_type": "low"},
        ],
    },
    "dallas": {
        "name": "Dallas",
        "mos_station": "KDFW",
        "lat": 32.90,
        "lon": -97.04,
        "series": [
            {"ticker": "KXHIGHTDAL", "market_type": "high"},
            {"ticker": "KXLOWTDAL",  "market_type": "low"},
        ],
    },
    "houston": {
        "name": "Houston",
        "mos_station": "KHOU",
        "lat": 29.65,
        "lon": -95.28,
        "series": [
            {"ticker": "KXHIGHTHOU", "market_type": "high"},
            {"ticker": "KXLOWTHOU",  "market_type": "low"},
        ],
    },
    "atlanta": {
        "name": "Atlanta",
        "mos_station": "KATL",
        "lat": 33.64,
        "lon": -84.43,
        "series": [
            {"ticker": "KXHIGHTATL", "market_type": "high"},
            {"ticker": "KXLOWTATL",  "market_type": "low"},
        ],
    },
    "phoenix": {
        "name": "Phoenix",
        "mos_station": "KPHX",
        "lat": 33.43,
        "lon": -112.01,
        "series": [
            {"ticker": "KXHIGHTPHX", "market_type": "high"},
            {"ticker": "KXLOWTPHX",  "market_type": "low"},
        ],
    },
    "seattle": {
        "name": "Seattle",
        "mos_station": "KSEA",
        "lat": 47.45,
        "lon": -122.31,
        "series": [
            {"ticker": "KXHIGHTSEA", "market_type": "high"},
            {"ticker": "KXLOWTSEA",  "market_type": "low"},
        ],
    },
    "dc": {
        "name": "Washington DC",
        "mos_station": "KDCA",
        "lat": 38.85,
        "lon": -77.04,
        "series": [
            {"ticker": "KXHIGHTDC", "market_type": "high"},
            {"ticker": "KXLOWTDC",  "market_type": "low"},
        ],
    },
    "sf": {
        "name": "San Francisco",
        "mos_station": "KSFO",
        "lat": 37.62,
        "lon": -122.38,
        "series": [
            {"ticker": "KXHIGHTSFO", "market_type": "high"},
            {"ticker": "KXLOWTSFO",  "market_type": "low"},
        ],
    },
    "las_vegas": {
        "name": "Las Vegas",
        "mos_station": "KLAS",
        "lat": 36.08,
        "lon": -115.15,
        "series": [
            {"ticker": "KXHIGHTLV", "market_type": "high"},
            {"ticker": "KXLOWTLV",  "market_type": "low"},
        ],
    },
    "chicago": {
        "name": "Chicago",
        "mos_station": "KORD",
        "lat": 41.98,
        "lon": -87.91,
        "series": [
            {"ticker": "KXLOWTCHI", "market_type": "low"},
        ],
    },
}


def get_series_tickers() -> list[str]:
    """Return all series tickers across all cities."""
    return [s["ticker"] for cfg in CITIES.values() for s in cfg["series"]]


def get_city_for_series(ticker: str) -> tuple[str, dict] | None:
    """Return (city_id, series_config) for a given series ticker."""
    for city_id, cfg in CITIES.items():
        for s in cfg["series"]:
            if s["ticker"] == ticker:
                return city_id, s
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cities.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/cities.py tests/test_cities.py
git commit -m "feat: add city config with validated ticker map"
```

---

## Task 3: EV Module (scripts/ev.py)

**Files:**
- Create: `scripts/ev.py`
- Create: `tests/test_ev.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ev.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from ev import taker_fee, bucket_probability, trade_ev, is_tail

def test_taker_fee_at_midpoint():
    # 0.07 × 0.50 × 0.50 = 0.0175
    assert abs(taker_fee(0.50) - 0.0175) < 1e-6

def test_taker_fee_at_tail_5pct():
    # 0.07 × 0.05 × 0.95 = 0.003325
    assert abs(taker_fee(0.05) - 0.003325) < 1e-6

def test_taker_fee_at_tail_1pct():
    # 0.07 × 0.01 × 0.99 = 0.000693
    assert abs(taker_fee(0.01) - 0.000693) < 1e-6

def test_taker_fee_symmetric():
    # fee(C) == fee(1-C)
    assert abs(taker_fee(0.10) - taker_fee(0.90)) < 1e-9

def test_bucket_probability_centered():
    # Gaussian centered at 72.5 with sigma=2.5
    # P(72 < x < 73) should be near the PDF peak value × 1°F width ≈ 15-17%
    p = bucket_probability(forecast=72.5, sigma=2.5, bucket_low=72.0, bucket_high=73.0)
    assert 0.14 < p < 0.18

def test_bucket_probability_tail():
    # bucket 5 sigma away from mean — near zero
    p = bucket_probability(forecast=72.5, sigma=2.5, bucket_low=85.0, bucket_high=86.0)
    assert p < 0.001

def test_bucket_probability_sums_to_one():
    # integrating over all 1-degree buckets from 20 to 130 should be ~1.0
    from functools import reduce
    total = sum(
        bucket_probability(72.5, 2.5, float(t), float(t + 1))
        for t in range(20, 130)
    )
    assert abs(total - 1.0) < 0.001

def test_ev_positive_when_forecast_above_breakeven():
    # market at 5%, forecast says 10% — should be positive EV
    ev = trade_ev(p_forecast=0.10, price=0.05)
    assert ev > 0

def test_ev_negative_when_fairly_priced():
    # market at 5%, forecast also says 5% — EV is negative (fees)
    ev = trade_ev(p_forecast=0.05, price=0.05)
    assert ev < 0

def test_is_tail_5pct():
    assert is_tail(0.05) is True
    assert is_tail(0.04) is True
    assert is_tail(0.96) is True
    assert is_tail(0.06) is False
    assert is_tail(0.94) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ev.py -v
```

Expected: `ModuleNotFoundError: No module named 'ev'`

- [ ] **Step 3: Write ev.py**

```python
# scripts/ev.py
from scipy.stats import norm


def taker_fee(price: float) -> float:
    """
    Kalshi taker fee per contract.

    Source: Kalshi Fee Schedule Feb 2026, https://kalshi.com/docs/kalshi-fee-schedule.pdf
    Formula: $0.07 × C × (1 − C) where C is the contract price.
    Charged at execution regardless of outcome. Applies to both buyers and sellers.
    """
    return 0.07 * price * (1.0 - price)


def bucket_probability(forecast: float, sigma: float, bucket_low: float, bucket_high: float) -> float:
    """
    P(daily temperature falls in [bucket_low, bucket_high]) given a Gaussian
    forecast distribution N(forecast, sigma).

    sigma comes from the MOS spread field when available; falls back to 2.5°F
    (published NWS 24h max temp MAE for major US cities).
    """
    return norm.cdf((bucket_high - forecast) / sigma) - norm.cdf((bucket_low - forecast) / sigma)


def trade_ev(p_forecast: float, price: float) -> float:
    """
    Expected value of buying one YES contract at `price`, given forecast
    probability `p_forecast` that the bucket resolves YES.

    EV = p_forecast × $1.00 − (price + taker_fee(price))
    """
    cost = price + taker_fee(price)
    return p_forecast * 1.00 - cost


def is_tail(price: float, threshold: float = 0.05) -> bool:
    """True if a market price falls in the tail (≤ threshold or ≥ 1-threshold)."""
    return price <= threshold or price >= (1.0 - threshold)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ev.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/ev.py tests/test_ev.py
git commit -m "feat: add EV module with fee formula and bucket probability"
```

---

## Task 4: Kalshi Client + Config Loader (scripts/kalshi_client.py)

**Files:**
- Create: `scripts/config_loader.py`
- Create: `scripts/kalshi_client.py`

- [ ] **Step 1: Write config_loader.py**

```python
# scripts/config_loader.py
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def load_config() -> dict:
    path = _ROOT / "config" / "settings.json"
    if not path.exists():
        raise FileNotFoundError(
            f"config/settings.json not found. Copy config/settings.example.json "
            f"and add your Kalshi API key."
        )
    with open(path) as f:
        return json.load(f)
```

- [ ] **Step 2: Write kalshi_client.py**

```python
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
```

- [ ] **Step 3: No automated test for the client** (it wraps an external API). Validation happens in the next task.

- [ ] **Step 4: Commit**

```bash
git add scripts/config_loader.py scripts/kalshi_client.py
git commit -m "feat: add Kalshi API client and config loader"
```

---

## Task 5: Ticker Validation Script (scripts/validate_tickers.py)

This script uses only the public `/series/{ticker}` endpoint — no API key required.

**Files:**
- Create: `scripts/validate_tickers.py`

- [ ] **Step 1: Write validate_tickers.py**

```python
# scripts/validate_tickers.py
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
from cities import CITIES, get_series_tickers

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
```

- [ ] **Step 2: Run the validator**

```bash
source venv/bin/activate
python scripts/validate_tickers.py
```

Expected output (one line per ticker, all PASS):
```
Validating 19 series tickers...

  [PASS] KXHIGHNY           Highest temperature in NYC
  [PASS] KXLOWTNYC          Lowest temperature in NYC
  [PASS] KXHIGHTDAL         Dallas Maximum Temperature
  ...
  [PASS] KXLOWTCHI          Lowest Temperature Chicago

Result: 19/19 tickers valid
All tickers validated. Safe to proceed.
```

If any ticker fails, stop and investigate before proceeding.

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_tickers.py
git commit -m "feat: add ticker validation script — all 19 tickers confirmed"
```

---

> **⏸ PAUSE — Add credentials before continuing**
>
> Edit `config/settings.json` and set `kalshi_api_key` to your actual API key.
> The remaining scripts require authenticated Kalshi API access.

---

## Task 6: Pull Kalshi Market Data (scripts/pull_kalshi.py)

Pulls two things per series: (1) all settled markets in the 60-day window (metadata
including result, floor_strike, cap_strike, expiration_value), and (2) the first
hourly candlestick after 10 AM ET on day D−1 for each market (our "market open price").

**Files:**
- Create: `scripts/pull_kalshi.py`

- [ ] **Step 1: Write pull_kalshi.py**

```python
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
import time
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
    markets = client.get_markets(series_ticker, status="finalized", min_ts=min_ts)
    logger.info(f"  {series_ticker}: got {len(markets)} markets")

    with open(cache_path, "w") as f:
        json.dump(markets, f)
    return markets


def pull_candle(client: KalshiClient, market: dict) -> dict | None:
    ticker = market["ticker"]
    cache_path = CANDLES_DIR / f"{ticker}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    close_ts = market.get("close_time", "")
    if not close_ts:
        return None

    weather_dt = weather_date_from_close_time(close_ts)
    start_ts, end_ts = market_open_window(weather_dt)

    candles = client.get_candlesticks(ticker, start_ts, end_ts, period_interval=60)
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
                result = pull_candle(client, market)
                if result:
                    total_candles += 1

    logger.info(f"\nDone. {total_markets} markets, {total_candles} candles pulled.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
python scripts/pull_kalshi.py
```

Expected: logs one line per series, then a done summary. Check `data/kalshi/` for JSON files.

```bash
ls data/kalshi/
# KXHIGHNY.json  KXLOWTNYC.json  KXHIGHTDAL.json ... (19 files)
```

- [ ] **Step 3: Commit**

```bash
git add scripts/pull_kalshi.py
git commit -m "feat: add Kalshi market + candlestick pull script"
```

---

## Task 7: IEM MOS Client + Forecast Pull (scripts/iem_client.py, scripts/pull_forecasts.py)

**Files:**
- Create: `scripts/iem_client.py`
- Create: `scripts/pull_forecasts.py`

- [ ] **Step 1: Write iem_client.py**

```python
# scripts/iem_client.py
"""
Iowa Environmental Mesonet GFS-MOS archive client.

IEM archives GFS-MOS forecast guidance by ICAO station and model runtime.
We pull the 12Z run from day D-1 (available ~8 AM ET, before market open at 10 AM ET).

API docs: https://mesonet.agron.iastate.edu/api/1/mos.json
"""
import time
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
```

- [ ] **Step 2: Write pull_forecasts.py**

```python
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
from datetime import datetime, timezone, timedelta
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
    from datetime import date
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

            data["_meta"] = {"city_id": city_id, "weather_date": weather_date, "runtime": runtime}
            with open(cache_path, "w") as f:
                json.dump(data, f)
            fetched += 1
            time.sleep(0.5)  # be gentle with IEM's public API

        logger.info(f"  fetched={fetched} skipped={skipped} missing={missing}")

    logger.info("Forecast pull complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script**

```bash
python scripts/pull_forecasts.py
```

Expected: one progress line per city, then "Forecast pull complete." Check `data/forecasts/` — should have ~600 files (10 cities × 60 days).

- [ ] **Step 4: Commit**

```bash
git add scripts/iem_client.py scripts/pull_forecasts.py
git commit -m "feat: add IEM GFS-MOS client and forecast pull script"
```

---

## Task 8: Open-Meteo Client + Actuals Pull (scripts/openmeteo_client.py, scripts/pull_actuals.py)

**Files:**
- Create: `scripts/openmeteo_client.py`
- Create: `scripts/pull_actuals.py`

- [ ] **Step 1: Write openmeteo_client.py**

```python
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
```

- [ ] **Step 2: Write pull_actuals.py**

```python
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
```

- [ ] **Step 3: Run the script**

```bash
python scripts/pull_actuals.py
```

Expected: 10 log lines (one per city), then "Actuals pull complete." Check `data/actuals/` — 10 JSON files.

- [ ] **Step 4: Commit**

```bash
git add scripts/openmeteo_client.py scripts/pull_actuals.py
git commit -m "feat: add Open-Meteo client and observed temperature pull"
```

---

## Task 9: Build Dataset (scripts/build_dataset.py)

Merges the three data sources into a single parquet file. Each row is one
(city, weather_date, bucket) observation with: market_open_price, floor_strike,
cap_strike, result, observed_high, observed_low, mos_forecast_high, mos_forecast_low,
sigma, and computed p_forecast.

**Files:**
- Create: `scripts/build_dataset.py`
- Create: `tests/test_build_dataset.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_build_dataset.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import pandas as pd
import pytest
from build_dataset import (
    extract_open_price,
    align_observed_temp,
    compute_sigma,
    DEFAULT_SIGMA,
)

def test_extract_open_price_returns_open_field():
    candle_data = {
        "ticker": "KXHIGHNY-26APR17-T72",
        "candle": {"open": 0.04, "high": 0.05, "low": 0.03, "close": 0.045, "volume": 100}
    }
    assert extract_open_price(candle_data) == pytest.approx(0.04)

def test_extract_open_price_missing_returns_none():
    assert extract_open_price(None) is None
    assert extract_open_price({}) is None

def test_align_observed_temp_returns_correct_day():
    actuals = {
        "daily": {
            "time": ["2026-04-16", "2026-04-17", "2026-04-18"],
            "temperature_2m_max": [68.0, 74.2, 71.0],
            "temperature_2m_min": [52.0, 58.1, 55.0],
        }
    }
    hi, lo = align_observed_temp(actuals, "2026-04-17")
    assert hi == pytest.approx(74.2)
    assert lo == pytest.approx(58.1)

def test_align_observed_temp_missing_date_returns_none():
    actuals = {"daily": {"time": ["2026-04-16"], "temperature_2m_max": [68.0], "temperature_2m_min": [52.0]}}
    assert align_observed_temp(actuals, "2026-04-20") == (None, None)

def test_compute_sigma_uses_mos_when_available():
    assert compute_sigma({"sigma": 3.1}) == pytest.approx(3.1)

def test_compute_sigma_falls_back_to_default():
    assert compute_sigma({"sigma": None}) == DEFAULT_SIGMA
    assert compute_sigma({}) == DEFAULT_SIGMA
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_build_dataset.py -v
```

Expected: `ModuleNotFoundError: No module named 'build_dataset'`

- [ ] **Step 3: Write build_dataset.py**

```python
# scripts/build_dataset.py
"""
Merge Kalshi markets + candlesticks + IEM MOS forecasts + Open-Meteo actuals
into a single analysis-ready parquet file.

Output: data/processed/dataset.parquet

Each row = one (series_ticker, market_ticker, weather_date, bucket) observation.

Key columns:
  series_ticker, market_ticker, city_id, market_type, weather_date
  floor_strike, cap_strike       — bucket bounds in °F
  market_open_price              — YES contract price at 10 AM ET open on D-1
  result                         — "yes" or "no" (from Kalshi settlement)
  expiration_value               — actual temperature from NWS CLI
  observed_high, observed_low    — from Open-Meteo
  mos_forecast_high, mos_forecast_low — from IEM GFS-MOS
  sigma                          — forecast uncertainty (MOS spread or 2.5°F fallback)
  sigma_source                   — "mos" or "fallback"
  p_forecast                     — bucket_probability(mos_forecast, sigma, floor, cap)

Run: python scripts/build_dataset.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES
from ev import bucket_probability
from iem_client import extract_daily_forecast

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
KALSHI_DIR = DATA_DIR / "kalshi"
CANDLES_DIR = DATA_DIR / "kalshi_candles"
FORECASTS_DIR = DATA_DIR / "forecasts"
ACTUALS_DIR = DATA_DIR / "actuals"
PROCESSED_DIR = DATA_DIR / "processed"

DEFAULT_SIGMA = 2.5  # °F — NWS published 24h max temp MAE for major US cities


def extract_open_price(candle_data: dict | None) -> float | None:
    """Extract the open price from a cached candlestick dict."""
    if not candle_data:
        return None
    candle = candle_data.get("candle", {})
    return candle.get("open")


def align_observed_temp(actuals: dict, weather_date: str) -> tuple[float | None, float | None]:
    """Return (observed_high, observed_low) for weather_date from Open-Meteo actuals dict."""
    daily = actuals.get("daily", {})
    times = daily.get("time", [])
    if weather_date not in times:
        return None, None
    idx = times.index(weather_date)
    hi = daily["temperature_2m_max"][idx]
    lo = daily["temperature_2m_min"][idx]
    return hi, lo


def compute_sigma(forecast: dict) -> float:
    """Return sigma from forecast dict, falling back to DEFAULT_SIGMA."""
    s = forecast.get("sigma")
    return float(s) if s is not None else DEFAULT_SIGMA


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def build_rows() -> list[dict]:
    rows = []
    sigma_sources = {"mos": 0, "fallback": 0}

    for city_id, city_cfg in CITIES.items():
        actuals = load_json(ACTUALS_DIR / f"{city_id}.json")
        if actuals is None:
            logger.warning(f"{city_id}: no actuals data, skipping")
            continue

        for series_cfg in city_cfg["series"]:
            series_ticker = series_cfg["ticker"]
            market_type = series_cfg["market_type"]
            markets = load_json(KALSHI_DIR / f"{series_ticker}.json")
            if not markets:
                logger.warning(f"{series_ticker}: no market data")
                continue

            for market in markets:
                ticker = market.get("ticker", "")
                close_time = market.get("close_time", "")
                if not close_time:
                    continue

                # Derive weather_date from close_time (11:59 PM ET on weather day)
                weather_date = datetime.fromisoformat(
                    close_time.replace("Z", "+00:00")
                ).strftime("%Y-%m-%d")

                # Load candlestick (market open price at 10 AM ET on D-1)
                candle_data = load_json(CANDLES_DIR / f"{ticker}.json")
                open_price = extract_open_price(candle_data)
                if open_price is None:
                    continue

                # Load MOS forecast
                forecast_data = load_json(FORECASTS_DIR / f"{city_id}_{weather_date}.json")
                if forecast_data is None:
                    continue
                daily_fc = extract_daily_forecast(forecast_data, weather_date)
                if daily_fc is None:
                    continue

                # Observed actuals
                obs_hi, obs_lo = align_observed_temp(actuals, weather_date)
                if obs_hi is None:
                    continue

                # Sigma
                sigma = compute_sigma(daily_fc)
                sigma_source = "mos" if daily_fc.get("sigma") is not None else "fallback"
                sigma_sources[sigma_source] += 1

                # Forecast temperature for this market type
                forecast_temp = daily_fc["t_high"] if market_type == "high" else daily_fc["t_low"]

                # Bucket bounds from Kalshi market object
                floor_strike = market.get("floor_strike")
                cap_strike = market.get("cap_strike")
                if floor_strike is None or cap_strike is None:
                    continue

                p_fc = bucket_probability(
                    forecast=forecast_temp,
                    sigma=sigma,
                    bucket_low=float(floor_strike),
                    bucket_high=float(cap_strike),
                )

                rows.append({
                    "series_ticker": series_ticker,
                    "market_ticker": ticker,
                    "city_id": city_id,
                    "city_name": city_cfg["name"],
                    "market_type": market_type,
                    "weather_date": weather_date,
                    "floor_strike": float(floor_strike),
                    "cap_strike": float(cap_strike),
                    "market_open_price": float(open_price),
                    "result": market.get("result"),
                    "expiration_value": market.get("expiration_value"),
                    "observed_high": obs_hi,
                    "observed_low": obs_lo,
                    "mos_forecast_high": daily_fc["t_high"],
                    "mos_forecast_low": daily_fc["t_low"],
                    "sigma": sigma,
                    "sigma_source": sigma_source,
                    "p_forecast": p_fc,
                })

    total = len(rows)
    fallback_pct = 100 * sigma_sources["fallback"] / max(total, 1)
    logger.info(f"Built {total} rows. Sigma fallback rate: {fallback_pct:.1f}%")
    if fallback_pct > 30:
        logger.warning(
            f"SIGMA FALLBACK RATE {fallback_pct:.1f}% EXCEEDS 30% THRESHOLD — "
            "flag this as a methodology caveat in findings.md"
        )
    return rows


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    if not rows:
        logger.error("No rows built. Check that all pull scripts ran successfully.")
        return

    df = pd.DataFrame(rows)
    out_path = PROCESSED_DIR / "dataset.parquet"
    df.to_parquet(out_path, index=False)
    logger.info(f"Wrote {len(df)} rows → {out_path}")
    logger.info(f"Columns: {list(df.columns)}")
    logger.info(f"Date range: {df['weather_date'].min()} → {df['weather_date'].max()}")
    logger.info(f"Cities: {sorted(df['city_id'].unique())}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_build_dataset.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the build script (after all pull scripts have run)**

```bash
python scripts/build_dataset.py
```

Expected output:
```
Built NNNNN rows. Sigma fallback rate: X.X%
Wrote NNNNN rows → data/processed/dataset.parquet
```

- [ ] **Step 6: Commit**

```bash
git add scripts/build_dataset.py tests/test_build_dataset.py
git commit -m "feat: add dataset builder — merges Kalshi + MOS + Open-Meteo"
```

---

## Task 10: Analysis (scripts/analyze.py)

Computes EV for every observation, runs the middle-bucket calibration sanity check,
measures sigma fallback frequency, and evaluates all four falsification criteria.
Writes a summary CSV for use by visualize.py.

**Files:**
- Create: `scripts/analyze.py`

- [ ] **Step 1: Write analyze.py**

```python
# scripts/analyze.py
"""
Compute EV, calibration stats, edge distribution, and falsification criteria.

Reads:  data/processed/dataset.parquet
Writes: data/processed/analysis.parquet   — dataset + computed EV columns
        data/processed/summary.json       — falsification criteria results

Run: python scripts/analyze.py
"""
import sys
import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ev import taker_fee, trade_ev, is_tail

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"

# Falsification thresholds (pre-registered in design spec)
CRITERIA = {
    "min_positive_ev_tail_opportunities": 30,
    "min_avg_edge_pct_points": 0.02,           # 2 percentage points
    "min_cities_with_positive_ev": 5,
    "pnl_must_be_positive": True,
}

MIDDLE_BUCKET_RMSE_STOP = 0.05  # 5 percentage points


def add_ev_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add fee, ev, edge, is_tail, and resolved_yes columns."""
    df = df.copy()
    df["fee"] = df["market_open_price"].apply(taker_fee)
    df["ev"] = df.apply(
        lambda r: trade_ev(r["p_forecast"], r["market_open_price"]), axis=1
    )
    df["edge"] = df["ev"]  # edge > 0 means tradeable
    df["is_tail"] = df["market_open_price"].apply(is_tail)
    df["resolved_yes"] = df["result"].str.lower() == "yes"
    return df


def calibration_rmse(df: pd.DataFrame, n_bins: int = 10) -> float:
    """
    Bin market_open_price into n_bins deciles, compute actual YES rate per bin,
    return RMSE vs. the 45-degree perfect-calibration line.
    """
    df = df.copy()
    df["price_bin"] = pd.cut(df["market_open_price"], bins=n_bins, labels=False)
    cal = df.groupby("price_bin").agg(
        mean_price=("market_open_price", "mean"),
        actual_rate=("resolved_yes", "mean"),
        count=("resolved_yes", "count"),
    ).dropna()
    rmse = math.sqrt(((cal["mean_price"] - cal["actual_rate"]) ** 2).mean())
    return rmse


def evaluate_falsification(df_tail: pd.DataFrame) -> dict:
    """
    Evaluate all four pre-registered falsification criteria.
    Returns a dict with criterion name → {threshold, actual, pass}.
    """
    positive_ev = df_tail[df_tail["ev"] > 0]
    n_opportunities = len(positive_ev)
    avg_edge = positive_ev["ev"].mean() if n_opportunities > 0 else 0.0
    n_cities = positive_ev["city_id"].nunique() if n_opportunities > 0 else 0

    # Simulated P&L: buy 1 contract on each positive-EV tail opportunity
    # Cost = market_open_price + fee; payout = 1.0 if resolved_yes else 0.0
    pnl = 0.0
    if n_opportunities > 0:
        costs = positive_ev["market_open_price"] + positive_ev["fee"]
        payouts = positive_ev["resolved_yes"].astype(float)
        pnl = float((payouts - costs).sum())

    return {
        "n_positive_ev_tail_opportunities": {
            "threshold": CRITERIA["min_positive_ev_tail_opportunities"],
            "actual": n_opportunities,
            "pass": n_opportunities >= CRITERIA["min_positive_ev_tail_opportunities"],
        },
        "avg_edge_pct_points": {
            "threshold": CRITERIA["min_avg_edge_pct_points"],
            "actual": round(avg_edge, 4),
            "pass": avg_edge >= CRITERIA["min_avg_edge_pct_points"],
        },
        "cities_with_positive_ev": {
            "threshold": CRITERIA["min_cities_with_positive_ev"],
            "actual": n_cities,
            "pass": n_cities >= CRITERIA["min_cities_with_positive_ev"],
        },
        "simulated_pnl_positive": {
            "threshold": 0.0,
            "actual": round(pnl, 2),
            "pass": pnl > 0,
        },
    }


def main():
    dataset_path = PROCESSED_DIR / "dataset.parquet"
    if not dataset_path.exists():
        logger.error("dataset.parquet not found — run build_dataset.py first")
        return

    df = pd.read_parquet(dataset_path)
    logger.info(f"Loaded {len(df)} rows")

    # Add EV columns
    df = add_ev_columns(df)

    # --- Middle-bucket calibration sanity check ---
    df_middle = df[(df["market_open_price"] >= 0.20) & (df["market_open_price"] <= 0.80)]
    if len(df_middle) < 50:
        logger.warning("Fewer than 50 middle-bucket observations — calibration check unreliable")
    middle_rmse = calibration_rmse(df_middle)
    logger.info(f"Middle-bucket calibration RMSE: {middle_rmse:.4f} ({middle_rmse*100:.2f} pp)")
    calibration_passed = middle_rmse <= MIDDLE_BUCKET_RMSE_STOP
    if not calibration_passed:
        logger.error(
            f"STOP: Middle-bucket calibration RMSE {middle_rmse*100:.2f}pp exceeds "
            f"5pp threshold. The Gaussian-MOS model is not well-calibrated. "
            f"Tail analysis results are not trustworthy."
        )

    # --- Sigma fallback rate ---
    sigma_fallback_rate = (df["sigma_source"] == "fallback").mean()
    logger.info(f"Sigma fallback rate: {sigma_fallback_rate*100:.1f}%")
    if sigma_fallback_rate > 0.30:
        logger.warning(
            f"Sigma fallback rate {sigma_fallback_rate*100:.1f}% exceeds 30% — "
            "flag as methodology caveat"
        )

    # --- Tail-bucket falsification criteria ---
    df_tail = df[df["is_tail"]]
    logger.info(f"Tail-bucket observations: {len(df_tail)}")
    criteria_results = evaluate_falsification(df_tail)
    for name, result in criteria_results.items():
        status = "PASS" if result["pass"] else "FAIL"
        logger.info(f"  [{status}] {name}: actual={result['actual']} threshold={result['threshold']}")

    # --- Write outputs ---
    df.to_parquet(PROCESSED_DIR / "analysis.parquet", index=False)

    summary = {
        "n_total_observations": len(df),
        "n_tail_observations": len(df_tail),
        "middle_bucket_calibration_rmse": round(middle_rmse, 4),
        "middle_bucket_calibration_passed": calibration_passed,
        "sigma_fallback_rate": round(sigma_fallback_rate, 4),
        "falsification_criteria": criteria_results,
        "all_criteria_pass": all(r["pass"] for r in criteria_results.values()),
    }
    with open(PROCESSED_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    overall = "PROCEED TO LIVE TRADING" if (
        calibration_passed and summary["all_criteria_pass"]
    ) else "DO NOT PROCEED — see findings.md for details"
    logger.info(f"\nRECOMMENDATION: {overall}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
python scripts/analyze.py
```

Expected: calibration RMSE logged, tail observation count, pass/fail for each criterion,
and a final recommendation line. Check `data/processed/summary.json` for the structured output.

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze.py
git commit -m "feat: add analysis script with EV, calibration, and falsification criteria"
```

---

## Task 11: Visualize + Write findings.md (scripts/visualize.py)

Generates four plots and writes the final `reports/findings.md` with all results filled in.

**Files:**
- Create: `scripts/visualize.py`
- Create: `reports/findings.md` (written by the script)

- [ ] **Step 1: Write visualize.py**

```python
# scripts/visualize.py
"""
Generate analysis plots and write reports/findings.md.

Reads:  data/processed/analysis.parquet
        data/processed/summary.json
Writes: reports/figures/calibration_full.png
        reports/figures/calibration_middle.png
        reports/figures/edge_distribution.png
        reports/figures/pnl_simulation.png
        reports/findings.md

Run: python scripts/visualize.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

sys.path.insert(0, str(Path(__file__).parent))
from ev import taker_fee

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

sns.set_theme(style="whitegrid", palette="muted")


def calibration_plot(df: pd.DataFrame, title: str, out_path: Path, n_bins: int = 10):
    """Plot market price (x) vs actual YES rate (y) vs perfect calibration."""
    df = df.copy()
    df["price_bin"] = pd.cut(df["market_open_price"], bins=n_bins, labels=False)
    cal = df.groupby("price_bin").agg(
        mean_price=("market_open_price", "mean"),
        actual_rate=("resolved_yes", "mean"),
        count=("resolved_yes", "count"),
    ).dropna()

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect calibration")
    ax.scatter(cal["mean_price"], cal["actual_rate"],
               s=cal["count"] / cal["count"].max() * 300,
               alpha=0.8, label="Observed (size ∝ n)")
    ax.set_xlabel("Market open price (implied probability)")
    ax.set_ylabel("Actual YES rate")
    ax.set_title(title)
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved {out_path.name}")


def edge_histogram(df: pd.DataFrame, out_path: Path):
    """Histogram of edge (EV) for tail vs non-tail buckets."""
    fig, ax = plt.subplots(figsize=(8, 5))
    tail = df[df["is_tail"]]["edge"]
    non_tail = df[~df["is_tail"]]["edge"]
    ax.hist(non_tail, bins=50, alpha=0.5, label=f"Non-tail (n={len(non_tail)})",
            density=True)
    ax.hist(tail, bins=50, alpha=0.7, label=f"Tail (n={len(tail)})", density=True)
    ax.axvline(0, color="red", linestyle="--", alpha=0.8, label="Break-even")
    ax.set_xlabel("Edge (EV per $1 contract)")
    ax.set_ylabel("Density")
    ax.set_title("Edge distribution: tail vs. non-tail buckets")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved {out_path.name}")


def pnl_simulation(df: pd.DataFrame, out_path: Path):
    """Cumulative P&L if trading $1/contract on every positive-EV tail opportunity."""
    positive_ev_tail = df[df["is_tail"] & (df["ev"] > 0)].copy()
    positive_ev_tail = positive_ev_tail.sort_values("weather_date")

    cost = positive_ev_tail["market_open_price"] + positive_ev_tail["fee"]
    payout = positive_ev_tail["resolved_yes"].astype(float)
    pnl_per_trade = payout - cost
    cumulative_pnl = pnl_per_trade.cumsum().reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(cumulative_pnl.index, cumulative_pnl.values, linewidth=1.5)
    ax.axhline(0, color="red", linestyle="--", alpha=0.6)
    ax.set_xlabel("Trade number (chronological)")
    ax.set_ylabel("Cumulative P&L ($)")
    ax.set_title(
        f"Simulated P&L — $1/contract on all positive-EV tail opportunities "
        f"(n={len(positive_ev_tail)})"
    )
    ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("$%.2f"))
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info(f"Saved {out_path.name}")


def write_findings(df: pd.DataFrame, summary: dict, out_path: Path):
    """Write the full findings report as Markdown."""
    today = datetime.today().strftime("%Y-%m-%d")
    criteria = summary["falsification_criteria"]

    def fmt_criterion(key: str) -> str:
        c = criteria[key]
        status = "✅ PASS" if c["pass"] else "❌ FAIL"
        return f"{status} — actual: {c['actual']} (threshold: {c['threshold']})"

    recommendation = (
        "**PROCEED to live trading.** All four falsification criteria passed and "
        "middle-bucket calibration is valid."
        if summary["all_criteria_pass"] and summary["middle_bucket_calibration_passed"]
        else "**DO NOT PROCEED.** See failed criteria below."
    )

    tail = df[df["is_tail"]]
    positive_ev_tail = tail[tail["ev"] > 0]

    sigma_pct = summary["sigma_fallback_rate"] * 100
    sigma_caveat = (
        f"⚠️ **Sigma fallback rate is {sigma_pct:.1f}%, exceeding the 30% threshold.** "
        "A fixed σ=2.5°F was used for the majority of observations. Tail edge estimates "
        "should be treated as approximate."
        if summary["sigma_fallback_rate"] > 0.30
        else f"Sigma fallback rate: {sigma_pct:.1f}% (below 30% threshold — acceptable)."
    )

    cal_rmse_pp = summary["middle_bucket_calibration_rmse"] * 100
    cal_status = (
        f"✅ PASS — RMSE {cal_rmse_pp:.2f}pp (threshold: ≤5pp)"
        if summary["middle_bucket_calibration_passed"]
        else f"❌ FAIL — RMSE {cal_rmse_pp:.2f}pp exceeds 5pp threshold. Tail results invalid."
    )

    md = f"""# Kalshi Weather Tail Mispricing — Research Findings

**Generated:** {today}
**Lookback window:** 60 days
**Cities:** NYC, Dallas, Houston, Atlanta, Phoenix, Seattle, DC, San Francisco, Las Vegas (high+low), Chicago (low only)

---

## Hypothesis

Kalshi daily weather temperature markets may systematically underprice tail buckets
(market price ≤5% or ≥95%) because the small absolute payout discourages arbitrageurs
from correcting small percentage mispricings, even when the edge in percentage terms
is large. This analysis tests that hypothesis using 60 days of historical data.

---

## Methodology

### Data Sources
- **Market prices:** Kalshi API candlestick at 10 AM ET on day D−1 (market open)
- **Forecast probabilities:** IEM GFS-MOS 12Z run from day D−1, modeled as
  Gaussian N(forecast_temp, σ) with p(bucket) = Φ((T+1−μ)/σ) − Φ((T−μ)/σ)
- **Observed actuals:** Open-Meteo historical archive API

### Fee Formula
Source: [Kalshi Fee Schedule Feb 2026](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
> "Taker fee per contract = $0.07 × C × (1 − C). Where C = contract price from $0.01 to $0.99."
Charged at execution; applies to both buyers and sellers regardless of outcome.

### EV Calculation
`EV = p_forecast × $1.00 − (market_price + fee)`

### Tail definition
Market open price ≤ 5% or ≥ 95%.

---

## Dataset Summary

| Metric | Value |
|---|---|
| Total observations | {summary['n_total_observations']:,} |
| Tail-bucket observations | {summary['n_tail_observations']:,} |
| Positive-EV tail opportunities | {len(positive_ev_tail):,} |
| Date range | {df['weather_date'].min()} → {df['weather_date'].max()} |

---

## Middle-Bucket Calibration Sanity Check

Before trusting tail findings, we verify the forecast model is well-calibrated on
middle buckets (20–80%), where markets are assumed efficient.

**Result:** {cal_status}

![Calibration plot — middle buckets](figures/calibration_middle.png)

---

## Sigma Fallback Rate

{sigma_caveat}

---

## Key Findings

### Calibration (full range)

![Calibration plot — all buckets](figures/calibration_full.png)

### Edge Distribution

![Edge distribution histogram](figures/edge_distribution.png)

### Simulated P&L

![P&L simulation](figures/pnl_simulation.png)

---

## Falsification Criteria Results

All four criteria must pass to recommend proceeding. These were pre-registered
before any data was pulled.

| # | Criterion | Result |
|---|---|---|
| 1 | ≥30 positive-EV tail opportunities | {fmt_criterion('n_positive_ev_tail_opportunities')} |
| 2 | Average edge ≥2 percentage points | {fmt_criterion('avg_edge_pct_points')} |
| 3 | Positive-EV opps in ≥5 cities | {fmt_criterion('cities_with_positive_ev')} |
| 4 | Simulated P&L net positive after fees | {fmt_criterion('simulated_pnl_positive')} |

---

## Recommendation

{recommendation}

---

## Caveats and Limitations

1. **Sample size:** 60 days × ~10 cities × 2 markets provides good statistical power
   for detecting systematic mispricing, but individual city results may lack significance.
2. **Forecast model:** Gaussian assumption for temperature uncertainty is standard but
   approximate. Actual temperature distributions can be skewed (e.g., summer heat waves).
3. **Market open price:** We use the first candlestick after 10 AM ET. Thin early markets
   may have wide bid-ask spreads; actual fill prices could differ.
4. **Survival bias:** Kalshi may have delisted poorly-performing or illiquid markets.
   Results reflect only active series.
5. **Selection bias:** This analysis looks at markets that existed and had volume. It
   cannot account for tail buckets that were never traded.
6. **These results do not prove forward-looking edge.** Market participants may adapt;
   the forecast model may degrade; Kalshi may change fee structure or market design.
"""

    out_path.write_text(md)
    logger.info(f"Wrote {out_path}")


def main():
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    analysis_path = PROCESSED_DIR / "analysis.parquet"
    summary_path = PROCESSED_DIR / "summary.json"
    if not analysis_path.exists() or not summary_path.exists():
        logger.error("Run analyze.py first.")
        return

    df = pd.read_parquet(analysis_path)
    with open(summary_path) as f:
        summary = json.load(f)

    calibration_plot(df, "Calibration — all buckets",
                     FIGURES_DIR / "calibration_full.png")
    df_mid = df[(df["market_open_price"] >= 0.20) & (df["market_open_price"] <= 0.80)]
    calibration_plot(df_mid, "Calibration — middle buckets (20%–80%)",
                     FIGURES_DIR / "calibration_middle.png")
    edge_histogram(df, FIGURES_DIR / "edge_distribution.png")
    pnl_simulation(df, FIGURES_DIR / "pnl_simulation.png")

    write_findings(df, summary, REPORTS_DIR / "findings.md")
    logger.info("Done. See reports/findings.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
python scripts/visualize.py
```

Expected: 4 plot files saved to `reports/figures/`, `reports/findings.md` written.

- [ ] **Step 3: Commit findings.md and scripts**

```bash
git add scripts/visualize.py reports/findings.md
git commit -m "feat: add visualization script and findings.md template"
```

---

## Task 12: Run Full Test Suite + Final Commit

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_cities.py::test_all_cities_have_required_keys PASSED
tests/test_cities.py::test_each_series_has_ticker_and_market_type PASSED
tests/test_cities.py::test_chicago_has_only_low PASSED
tests/test_cities.py::test_get_series_tickers_returns_all PASSED
tests/test_ev.py::test_taker_fee_at_midpoint PASSED
tests/test_ev.py::test_taker_fee_at_tail_5pct PASSED
tests/test_ev.py::test_taker_fee_at_tail_1pct PASSED
tests/test_ev.py::test_taker_fee_symmetric PASSED
tests/test_ev.py::test_bucket_probability_centered PASSED
tests/test_ev.py::test_bucket_probability_tail PASSED
tests/test_ev.py::test_bucket_probability_sums_to_one PASSED
tests/test_ev.py::test_ev_positive_when_forecast_above_breakeven PASSED
tests/test_ev.py::test_ev_negative_when_fairly_priced PASSED
tests/test_ev.py::test_is_tail_5pct PASSED
tests/test_build_dataset.py::test_extract_open_price_returns_open_field PASSED
tests/test_build_dataset.py::test_extract_open_price_missing_returns_none PASSED
tests/test_build_dataset.py::test_align_observed_temp_returns_correct_day PASSED
tests/test_build_dataset.py::test_align_observed_temp_missing_date_returns_none PASSED
tests/test_build_dataset.py::test_compute_sigma_uses_mos_when_available PASSED
tests/test_build_dataset.py::test_compute_sigma_falls_back_to_default PASSED

20 passed
```

- [ ] **Step 2: Final commit**

```bash
git add -A
git commit -m "chore: final scaffold — all 20 tests passing, pipeline ready for data pull"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task covering it |
|---|---|
| venv + requirements.txt | Task 1 |
| Pull Kalshi market + candlestick data | Task 6 |
| Pull NWS/MOS forecasts | Task 7 |
| Pull observed temperatures | Task 8 |
| Build merged dataset | Task 9 |
| Fee formula with citation | Tasks 3, 11 (README + findings.md) |
| EV calculation per bucket | Task 10 |
| Tail bucket definition (≤5%) | Task 3 |
| Middle-bucket calibration sanity check | Task 10, 11 |
| σ fallback frequency reporting | Task 9, 10, 11 |
| 4 visualizations | Task 11 |
| reports/findings.md with recommendation | Task 11 |
| Falsification criteria (pre-registered) | Task 10, 11 |
| Credentials in gitignored settings.json | Task 1 |
| settings.example.json committed | Task 1 |
| Ticker validation script | Task 5 |
| Data cached locally (idempotent pulls) | Tasks 6, 7, 8 |
| Sigma fallback >30% flagged | Tasks 9, 10 |
| Middle-bucket stop condition | Task 10 |

**All spec requirements covered.**
