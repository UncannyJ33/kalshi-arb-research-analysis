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
            "actual": int(n_opportunities),
            "pass": bool(n_opportunities >= CRITERIA["min_positive_ev_tail_opportunities"]),
        },
        "avg_edge_pct_points": {
            "threshold": CRITERIA["min_avg_edge_pct_points"],
            "actual": round(float(avg_edge), 4),
            "pass": bool(avg_edge >= CRITERIA["min_avg_edge_pct_points"]),
        },
        "cities_with_positive_ev": {
            "threshold": CRITERIA["min_cities_with_positive_ev"],
            "actual": int(n_cities),
            "pass": bool(n_cities >= CRITERIA["min_cities_with_positive_ev"]),
        },
        "simulated_pnl_positive": {
            "threshold": 0.0,
            "actual": round(float(pnl), 2),
            "pass": bool(pnl > 0),
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
        # Soft-stop: continue to produce all outputs so findings.md has full context,
        # but the final recommendation gates on calibration_passed.

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
