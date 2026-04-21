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
