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
