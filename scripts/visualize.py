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
