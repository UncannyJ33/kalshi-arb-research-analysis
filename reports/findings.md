# Kalshi Weather Tail Mispricing — Research Findings

**Generated:** 2026-04-21
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
| Total observations | 2,782 |
| Tail-bucket observations | 869 |
| Positive-EV tail opportunities | 400 |
| Date range | 2026-02-20 → 2026-04-20 |

---

## Middle-Bucket Calibration Sanity Check

Before trusting tail findings, we verify the forecast model is well-calibrated on
middle buckets (20–80%), where markets are assumed efficient.

**Result:** ❌ FAIL — RMSE 5.44pp exceeds 5pp threshold. Tail results invalid.

![Calibration plot — middle buckets](figures/calibration_middle.png)

---

## Sigma Fallback Rate

⚠️ **Sigma fallback rate is 100.0%, exceeding the 30% threshold.** A fixed σ=2.5°F was used for the majority of observations. Tail edge estimates should be treated as approximate.

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
| 1 | ≥30 positive-EV tail opportunities | ✅ PASS — actual: 400 (threshold: 30) |
| 2 | Average edge ≥2 percentage points | ✅ PASS — actual: 0.0633 (threshold: 0.02) |
| 3 | Positive-EV opps in ≥5 cities | ✅ PASS — actual: 10 (threshold: 5) |
| 4 | Simulated P&L net positive after fees | ❌ FAIL — actual: -5.86 (threshold: 0.0) |

---

## Recommendation

**DO NOT PROCEED.** See failed criteria below.

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
