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
