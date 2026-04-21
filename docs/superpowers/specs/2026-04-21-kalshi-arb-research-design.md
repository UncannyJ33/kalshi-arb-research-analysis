# Kalshi Weather Market Tail Mispricing — Research Design

**Date:** 2026-04-21
**Status:** Approved, proceeding to implementation plan

---

## Hypothesis

Kalshi daily weather temperature markets price middle buckets (20–80% probability)
efficiently, because participants use NWS and ensemble model forecasts. Tail buckets
(market price ≤5% or ≥95%) may be systematically underpriced in absolute probability
terms because the small dollar payout discourages arbitrageurs from correcting small
percentage mispricings, even when the edge in percentage terms is large.

If this mispricing exists and is consistent, a systematic strategy of buying positive-EV
tail contracts at market open (10 AM ET the day before the weather day) could produce
positive expected value after fees.

---

## Data Sources

### Kalshi API
- **Base URL:** `https://api.elections.kalshi.com/trade-api/v2`
- **Auth:** API key in `config/settings.json` (gitignored)
- **What we pull:** Candlestick data for each market, specifically the first candlestick
  after 10 AM ET on day D−1 (market open). This is our "market price" — the price before
  the weather day begins, when the outcome is still genuinely uncertain.
- **Why not closing price:** Markets close at 11:59 PM ET on the actual weather day. By
  that point, METAR readings are available and the price reflects the near-certain outcome,
  not a prediction.
- **Endpoint for candlesticks:** `GET /markets/{ticker}/candlesticks`
- **Endpoint for settled markets:** `GET /markets?series_ticker={series}&status=settled`

### IEM GFS-MOS Forecast Archive
- **URL:** `https://mesonet.agron.iastate.edu/api/1/mos.json`
- **What we pull:** GFS-MOS 12Z run issued on day D−1 for the forecast valid on day D.
  The 12Z run (8 AM ET) is available before market open at 10 AM ET — it represents what
  forecast data was available to market participants at open.
- **Why MOS:** Archives the actual forecast *as issued*, unlike ERA5 reanalysis. MOS is
  the statistical guidance NWS forecasters use as their first-guess. Free, clean JSON API,
  keyed by ICAO station code.

### Open-Meteo Historical Archive
- **URL:** `https://archive-api.open-meteo.com/v1/archive`
- **What we pull:** Official observed daily high and low temperatures for each city.
- **Why Open-Meteo:** Free, simple REST API, aligns well with the NWS-reported actuals
  used by Kalshi for settlement. Cross-checked against Kalshi's `expiration_value` field.

---

## City and Ticker Map

All tickers live-validated against the Kalshi API on 2026-04-21.

| City | HIGH ticker | LOW ticker | MOS station | Note |
|---|---|---|---|---|
| New York City | `KXHIGHNY` | `KXLOWTNYC` | KJFK | |
| Dallas | `KXHIGHTDAL` | `KXLOWTDAL` | KDFW | |
| Houston | `KXHIGHTHOU` | `KXLOWTHOU` | KHOU | |
| Atlanta | `KXHIGHTATL` | `KXLOWTATL` | KATL | |
| Phoenix | `KXHIGHTPHX` | `KXLOWTPHX` | KPHX | |
| Seattle | `KXHIGHTSEA` | `KXLOWTSEA` | KSEA | |
| Washington DC | `KXHIGHTDC` | `KXLOWTDC` | KDCA | |
| San Francisco | `KXHIGHTSFO` | `KXLOWTSFO` | KSFO | |
| Las Vegas | `KXHIGHTLV` | `KXLOWTLV` | KLAS | |
| Chicago | *(none — no daily high market exists on Kalshi)* | `KXLOWTCHI` | KORD | LOW only |

Chicago added for climate variability despite having no high temp market.
Miami excluded — temperature too stable to generate tail opportunities.
Chicago/Miami/LA were confirmed to have no daily HIGH markets as of validation date.

---

## Fee Formula

**Source:** Kalshi Fee Schedule (February 2026), cited at
[kalshi.com/docs/kalshi-fee-schedule.pdf](https://kalshi.com/docs/kalshi-fee-schedule.pdf),
and confirmed by [pm.wiki/learn/kalshi-fees-explained](https://pm.wiki/learn/kalshi-fees-explained).

**Direct quote:** *"Every trade on Kalshi is governed by one formula...
Taker fee per contract = $0.07 × C × (1 − C). Where C = contract price from $0.01 to $0.99."*

**Full formula (rounded up to nearest cent):**
```
taker_fee = ⌈0.07 × C × (1 − C)⌉  per contract
maker_fee = ⌈0.0175 × C × (1 − C)⌉  per contract  (25% of taker)
```

- Charged at **trade execution**, not at settlement
- Applies to **both** buyers and sellers, regardless of outcome
- `fee_type: "quadratic"`, `fee_multiplier: 1` in the API series object
  (the `fee_multiplier` is a scaling factor on the 0.07 base rate; 1 = standard rate)
- S&P 500 / Nasdaq markets use an effective rate of 0.035 (reduced multiplier)

**Fee at tail prices:**

| Contract price | Taker fee |
|---|---|
| 50¢ | 1.75¢ |
| 10¢ / 90¢ | 0.63¢ |
| 5¢ / 95¢ | 0.33¢ |
| 1¢ / 99¢ | 0.07¢ |

---

## Forecast Probability Model

**Goal:** Compute P(daily high/low falls in 1°F bucket [T, T+1]) from the MOS point
forecast, to compare against market price C.

**Method:** Model the forecast distribution as Gaussian centered on the MOS point
forecast with standard deviation σ:

```
p_forecast(bucket) = Φ((T+1 − forecast) / σ) − Φ((T − forecast) / σ)
```

**σ selection (in priority order):**
1. Use the MOS temperature spread field if present in the IEM response
2. Fall back to σ = 2.5°F (published NWS 24h max temp MAE for major US cities)

The fallback rate (% of observations using σ = 2.5°F) will be tracked and reported.
If fallback usage exceeds 30% of observations, this will be flagged as a methodology
caveat in `reports/findings.md`.

---

## EV Calculation

For a YES contract on bucket [T, T+1] bought at market price C:

```
cost      = C + ⌈0.07 × C × (1 − C)⌉
payout    = $1.00  if outcome falls in bucket, else $0.00
EV        = p_forecast × 1.00 − cost
edge      = EV  (positive = tradeable)
```

Simplified break-even condition (ignoring ceiling rounding):
```
p_forecast > C × (1 + 0.07 × (1 − C))
```

**Tail bucket definition:** market price C ≤ 0.05 or C ≥ 0.95.

**At 5¢:** break-even is p_forecast > 5.33%. Low bar — any meaningful model probability
above the market price is exploitable.

---

## Middle-Bucket Calibration Sanity Check

Before trusting any tail finding, we verify the forecast model is well-calibrated on
middle buckets (20% ≤ C ≤ 80%), where markets are assumed efficient.

**Procedure:** Bin market prices into deciles. For each decile, compute the actual
frequency that the bucket resolved YES. Plot against the 45° perfect-calibration line.

**Stop condition:** If the middle-bucket calibration curve deviates materially from the
diagonal (e.g., RMSE > 5 percentage points across deciles), the Gaussian-MOS model is
broken. In that case, tail analysis results are invalid and the findings report will say
so explicitly rather than proceeding to a trading recommendation.

---

## Analysis Outputs

### Visualizations (saved to `reports/figures/`)
1. **Calibration plot — full range:** market price vs. actual hit rate, all buckets
2. **Calibration plot — middle buckets only (20–80%):** sanity check for model validity
3. **Edge distribution histogram:** distribution of `edge` for tail vs. non-tail buckets
4. **P&L simulation:** cumulative realized P&L trading $1/contract on every
   positive-EV tail opportunity at market open price

### `reports/findings.md`
Structured report covering: hypothesis, methodology, data sources, key findings,
σ fallback frequency, falsification criteria results (pass/fail), and recommendation.

---

## Falsification Criteria (Pre-Registered)

These criteria are pre-registered before any data is pulled. Proceed to live trading
**only if ALL FOUR pass.** If any one fails, the recommendation is pivot or abandon.

| # | Criterion | Pass threshold |
|---|---|---|
| 1 | Positive-EV tail opportunities in 60-day window | ≥ 30 |
| 2 | Average edge on positive-EV opportunities | ≥ 3 percentage points |
| 3 | Positive-EV opportunities distributed across cities | ≥ 5 of the 10 cities |
| 4 | Simulated P&L at $1/contract on all positive-EV tail opps | Net positive after fees |

The analysis script will evaluate each criterion and write the results table with
explicit PASS / FAIL per row into `reports/findings.md`.

---

## Project Structure

```
kalshi-arb-research-analysis/
├── venv/                          # gitignored
├── data/                          # gitignored
│   ├── kalshi/                    # raw Kalshi API responses (JSON)
│   ├── forecasts/                 # IEM MOS data (JSON)
│   ├── actuals/                   # Open-Meteo observed temps (JSON)
│   └── processed/                 # merged analysis-ready dataset (parquet/CSV)
├── config/
│   ├── settings.json              # gitignored — Kalshi API key goes here
│   └── settings.example.json      # committed — shows required keys
├── scripts/
│   ├── pull_kalshi.py             # step 1: pull candlestick + market metadata
│   ├── pull_forecasts.py          # step 2: pull IEM GFS-MOS 12Z forecast data
│   ├── pull_actuals.py            # step 3: pull Open-Meteo observed daily highs/lows
│   ├── build_dataset.py           # step 4: merge sources → processed/
│   ├── analyze.py                 # step 5: compute EV, calibration, edge stats
│   └── visualize.py               # step 6: plots + reports/findings.md
├── reports/
│   ├── findings.md                # final output (written by visualize.py)
│   └── figures/                   # plots
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-21-kalshi-arb-research-design.md  # this file
├── notebooks/                     # exploration only, not part of pipeline
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Key Design Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Market price timestamp | 10 AM ET open on day D−1 | Closing price = realized probability; open price is genuine prediction |
| Forecast source | IEM GFS-MOS 12Z run | Free, archives actual issued forecast, authoritative |
| Observed actuals source | Open-Meteo archive | Free, clean REST API, consistent with NWS CLI |
| σ for probability model | MOS spread field, fallback σ=2.5°F | Published NWS 24h MAE; MOS spread preferred when available |
| Tail definition | C ≤ 5% or C ≥ 95% | Balances "neglected" signal with having tradeable volume |
| Cities | 9 symmetric + Chicago LOW-only | Chicago adds variability; Miami excluded (too stable) |
| Lookback period | 60 days | ~5,000 tail bucket observations estimated; sufficient statistical power |
| Fee formula | ⌈0.07 × C × (1−C)⌉ at entry | Confirmed from Kalshi Feb 2026 fee schedule |
| Stop condition | Middle-bucket calibration RMSE > 5pp | Model must be valid before tail claims are trusted |
