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
