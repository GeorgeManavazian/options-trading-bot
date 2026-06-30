# ACD Multi-Day Options Bot — Design Spec

**Date:** 2026-06-30
**Status:** Approved (design); pending implementation plan
**Strategy:** Mark Fisher's ACD method (see `strategies/ACD.md`)
**Bot #:** 3 (after 1DTE condor — shelved; ORB — first real edge)

---

## Purpose

Build a third trading bot that automates a v1 slice of Mark Fisher's ACD method on SPX,
expressed through options. The headline engineering question this bot answers:

> **Which option wrapper, riding the identical ACD signal, gives the best risk-adjusted return?**

We race three structurally-distinct wrappers on one fixed signal and crown a winner by a
pre-committed yardstick — avoiding the trap of unconsciously picking whatever wrapper
flatters whatever number we happen to glance at.

## Success criteria

- A working signal layer that emits, for each trading day, a directional decision + stop.
- Three wrapper builders that turn that decision into option legs.
- A backtest harness that runs all three on the *same* signal over our ~3-year window and
  reports, per wrapper: total return, max drawdown, **risk-adjusted = total return ÷ max
  drawdown** (primary), a Sharpe-like ratio (cross-check), win rate, trade count, a
  per-year regime breakdown, and slippage sensitivity.
- Each wrapper's metrics run through the `backtest-expert` skill for a robustness/overfitting verdict.

## Pre-committed decisions (from brainstorming, 2026-06-30)

| Decision | Choice | Notes |
|---|---|---|
| **Yardstick** | Risk-adjusted return (total return ÷ max drawdown) | Sharpe-like ratio as cross-check. Answers the ORB savage-drawdown lesson + small account. |
| **v1 setup** | Plain "A held" + pivot filter | More trades than "A through pivot" → cleaner wrapper comparison. |
| **Hold horizon** | Multi-day swing | Exit via Fisher's 3-day rolling pivot trailing stop. Faithful to the book. |
| **Data** | Keep IVolatility live | Need dated chains + daily marks; the July 5 trial-cancel is **reversed**. |
| **Wrappers raced** | Long option, debit spread, credit spread | Span the theta spectrum: against you → neutral → for you. |

---

## Architecture — two layers + a seam

The same decoupling that lets `build_condor` / `build_orb` eat live, historical, or fake
chains. The signal is computed once; each wrapper expresses it independently.

```
  SIGNAL LAYER  ──(daily Signal)──►  WRAPPER LAYER  ──►  BACKTEST HARNESS  ──►  GRADER
  bot/acd_rules.py                   bot/acd_wrappers.py  bot/backtest_acd.py    backtest-expert skill
  "the ACD brain"                    3 pluggable builds   races all 3 wrappers   robustness verdict
```

### Units and their boundaries

- **`bot/acd_rules.py`** — the ACD brain, pure Python (no data-source coupling).
  - Input: intraday SPX path for the day (for the opening range + A-trigger), yesterday's
    daily H/L/C (for the pivot), and the A-value parameter.
  - Output: a `Signal` object: `{date, direction ∈ {long, short, flat}, entry_time,
    entry_price, stop_B, pivot_band}`.
  - Also exposes the multi-day exit governor: a 3-day rolling pivot trailing stop function
    `held_position_should_exit(position, day_ohlc) -> bool`.
- **`bot/acd_wrappers.py`** — three builder functions, identical signature, the seam:
  `build_long_option(signal, chain)`, `build_debit_spread(signal, chain)`,
  `build_credit_spread(signal, chain)`. Each returns the position's legs.
- **`bot/backtest_acd.py`** — the loop. For each signal day → for each wrapper → enter at
  ~30–45 DTE → mark daily → apply exits → record P&L. Reuses `report_chains` / `config` /
  `sizing` where possible. Reports the metrics above per wrapper.

---

## The signal, precisely

- **Opening range:** high/low of 9:30–9:45 ET (first 15 minutes).
- **A value:** anchored at **0.18% of price** (Fisher's S&P Appendix number, ≈9–10 SPX pts
  today). 🚩 *Tunable — deliberate starting anchor, to be swept later, not gospel.*
- **A trigger:** price reaches OR-high + A (long) or OR-low − A (short) and **holds for
  ≥7.5 min** (half the 15-min range). Only **one A per day**; once set, direction is committed.
- **Pivot filter:** take the long only if price is above/through yesterday's pivot band;
  take the short only if below; inside the band → skip (no trade). This is the ACD edge over
  raw ORB — a trend-agreement gate plus the hold-time requirement.
- **Pivot range formula** (from yesterday's H/L/C):
  ```
  Pivot Price   = (High + Low + Close) / 3
  Second Number = (High + Low) / 2
  Differential  = | Pivot Price − Second Number |
  Pivot Range   = Pivot Price ± Differential      # a band
  ```
- **Entry cutoff:** the A must form by **~12:00 ET**, else skip the day. 🚩 *Tunable.*
- **Entry-day stop (B):** the opposite edge of the opening range.
- **Multi-day exit — the swing engine:** Fisher's **3-day rolling pivot trailing stop**.
  Each subsequent day, recompute the pivot band from the trailing 3-day H/L/C; exit when
  price closes back through the band against the position. Backstops: option **expiry** and
  the entry-day **B** stop.

---

## The three wrappers

All anchored at **~30–45 DTE** (🚩 *tunable — room for the swing, manageable theta*).
Strikes defined as **% of price** for cross-time consistency.

| Wrapper | Construction | Theta | Risk / Reward |
|---|---|---|---|
| **Long option** | 1 ATM-ish leg (call if long, put if short) | Against you | Risk = premium; reward uncapped |
| **Debit spread** | Long ATM + short ~1–2% OTM (same direction) | Near-neutral | Risk = net debit; reward capped at width |
| **Credit spread** | Short just-OTM + long further-OTM (ORB-style) | For you | Risk = width − credit (lopsided); reward = credit |

Excluded by design: **long straddle/strangle** — a non-directional volatility bet that
wastes ACD's directional edge.

---

## Data flow

- **Intraday (entry day):** reuse `bot/load_ivol_intraday.py` for the opening 15-min range
  and the A-trigger hold-time check — **already cached** (the ORB 3-year pull).
- **Dated chains + daily marks (NEW):** pull the ~30–45 DTE chain on the entry day (to build
  the position) and a daily price mark for each held day (to follow the position and apply
  the trailing stop), via the `stock-opts-by-param` EOD endpoint in `bot/load_ivolai.py`.
  Cached to `data_cache/`. **This is the new data we are keeping IVolatility live for** —
  the existing cache is 100% 0DTE and cannot support a multi-day hold.
- **Pivot range:** daily SPX H/L/C, already in our pipeline (used for condor settlement).

---

## Scoring & sizing

- **Primary metric:** total return ÷ max drawdown, both as % of capital-at-risk
  (account-independent, matching our existing reporting). 🚩 *Exact formula tunable.*
- **Cross-check:** Sharpe-like ratio (mean daily return / std of daily return).
- **Also reported:** win rate, trade count, **per-year regime breakdown** (the ORB lesson:
  2024 carried it, 2025 lost), and **slippage-per-leg sensitivity** (haircut applied before
  any filter, like ORB).
- **Sizing:** reuse `bot/config.py` `Profile` + `bot/sizing.py`; ~2–4% of the $10k account
  risked per trade; the bot auto-sizes and refuses to oversize.

---

## Testing approach

- TDD per unit (the condor/ORB discipline): write offline self-tests first, run on
  mock/fake data to prove the plumbing, *then* run on real cached + freshly-pulled data.
- Honest caveats baked into the report: regime breakdown, sample size, slippage.
- Final step per wrapper: run the metrics through the `backtest-expert` skill's
  stress-test checklist (parameter robustness, out-of-sample, sample size) for a verdict.

---

## Scope — what v1 is and is NOT (YAGNI)

**In v1:**
- One setup (A-held + pivot filter), three wrappers, fixed A-value anchor, 3-day pivot
  trailing exit, multi-day hold.

**Deliberately out (future iterations):**
- A-value sweep (tune the 0.18% anchor on real data).
- DTE sweep.
- Failed-A "rubber band" and C reversal trades.
- Formal ORB-vs-ACD head-to-head (the credit-spread wrapper already sets this up).

---

## Open risks / honest flags

- **Proprietary A-value gap:** Fisher hides the A-value formula; our 0.18% anchor is our own
  reconstruction. A chunk of the "edge" is ours to rediscover by sweep — no guarantee it
  reproduces his results. (See `strategies/ACD.md`.)
- **Overnight gap risk:** multi-day holds are exposed to weekend/overnight SPX gaps the
  intraday stops can't catch; the pivot trailing stop is the only defense there.
- **New data cost + time:** the dated-option pull is a fresh, slower job (1 req/sec cap) and
  keeps the $79/mo subscription running.
- **Wrapper-winner transferability:** the winner here is for the multi-day 0.18%/30–45-DTE
  regime; a different setup could favor a different wrapper.

---

## Meta

Engine reuse from prior bots: data loaders, intraday-path-from-options, backtest reporting,
`config.Profile`, `sizing.py`. New code is small and focused: `acd_rules.py`,
`acd_wrappers.py`, `backtest_acd.py`, plus a dated-chain helper in `load_ivolai.py`.
