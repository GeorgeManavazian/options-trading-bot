# V5 Trade Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an auditable trade-by-trade ledger of all 119 V5 fade trades (CSV + readable Markdown), with each row's P&L reconstructed from the real cached option prices and asserted equal to the backtest.

**Architecture:** One new file `bot/trade_ledger.py` that re-walks the V5 trade set through the ④b engine, capturing every field (incl. the plain-English entry reason and the exit reason/time), writes `results/v5_trade_ledger.csv` and `results/v5_trade_ledger.md`, and prints a sample. Offline on the ④b cache.

**Tech Stack:** Python 3.12 in `.venv`, stdlib only (`csv`, `collections`). House style: flat `bot/` modules, bare sibling imports, run `.venv/bin/python bot/<file>.py`, inline `__main__` assert self-tests (NO pytest), frequent commits.

## Global Constraints

- Run every file as `.venv/bin/python bot/<file>.py` (bare sibling imports work). NO pytest — self-tests in `if __name__ == "__main__":` printing `OK`/`passed`.
- **Trust guarantee:** every reconstructed row's `pnl_$` MUST equal the backtest's `price_cell(...)["pnl0_ts"]` (active-exit P&L) within 0.01 — asserted per row inside `build_ledger`; a mismatch is a hard failure.
- **V5 config:** 0DTE `debit_spread` cells only, filter out `failed_c`, active exit with target=0.5 / stop=0.5 (the `price_cell` defaults).
- **Columns (exact order):** `#, date, signal_time, direction, setup, conviction, why_entered, underlying_at_entry, structure, option_type, long_strike, short_strike, debit_paid, max_loss, exit_reason, exit_time, settle_close, pnl_$, return_on_risk_%, result`.
- **Expected totals (reconcile with the V5 scoreboard):** 119 trades; sum of `return_on_risk_%` ≈ 4171 (i.e. +4171% on risk); win rate ≈ 82%.
- **Honest framing** (in the .md): backtest on real prices, every trade shown, auditable, NOT live/paper — walk-forward is the owed next step.
- Data is already cached; everything OFFLINE, no network. Keep IVolatility subscribed; never run git-history rewrites (book PDF in gitignored `research/`).

---

### Task 1: `build_ledger()` — reconstruct the 119 trades

**Files:**
- Create: `bot/trade_ledger.py`

**Interfaces:**
- Consumes: `collect_fades`/`grid_cells` (acd_fade_signals), `price_cell`/`_value_series` (backtest_acd_fades), `spread_entry`/`expire_value` (acd_fade_pricing), `load_cached_minutes` (load_ivol_intraday), `daily_hlc` (run_acd_signal).
- Produces: `COLUMNS` (list), `_why(setup) -> str`, `_exit(struct, long_bars, short_bars, fill_bar, debit, hold_val) -> (reason, exit_time, exit_value)`, `build_ledger() -> list[dict]` (119 rows, each with all `COLUMNS` keys; per-row `pnl_$ == backtest pnl0_ts` asserted internally).

- [ ] **Step 1: Write the module + `build_ledger` + a `__main__` self-test.**

```python
# trade_ledger.py — auditable trade-by-trade record of the winning V5 fade config
# (0DTE debit spread, drop failed_c, active +50%/-50% exit). Reconstructs every trade
# from the SAME real cached option prices the ④b backtest used, asserting each row's
# P&L == the backtest. Writes results/v5_trade_ledger.{csv,md}. Offline on cache.
# Spec: docs/superpowers/specs/2026-07-01-v5-trade-ledger.md
# Run:  .venv/bin/python bot/trade_ledger.py
import csv
import os
from collections import defaultdict

from acd_fade_signals import collect_fades, grid_cells
from backtest_acd_fades import price_cell, _value_series
from acd_fade_pricing import spread_entry, expire_value
from load_ivol_intraday import load_cached_minutes
from run_acd_signal import daily_hlc

TARGET, STOP = 0.5, 0.5          # V5 active-exit thresholds (price_cell defaults)

COLUMNS = ["#", "date", "signal_time", "direction", "setup", "conviction", "why_entered",
           "underlying_at_entry", "structure", "option_type", "long_strike", "short_strike",
           "debit_paid", "max_loss", "exit_reason", "exit_time", "settle_close", "pnl_$",
           "return_on_risk_%", "result"]


def _why(setup):
    if setup.direction == "long":
        s = ("SPX broke BELOW the A-trigger (a bearish breakout signal) then failed to hold it "
             "-> faded LONG, betting the failed breakdown snaps back up.")
    else:
        s = ("SPX broke ABOVE the A-trigger (a bullish breakout signal) then failed to hold it "
             "-> faded SHORT, betting the failed breakout reverses down.")
    if setup.name == "failed_a_pivot":
        s += " The failed level sat on the prior-day pivot range (two signals agreeing -> higher conviction)."
    return s


def _exit(struct, long_bars, short_bars, fill_bar, debit, hold_val):
    """Replay the active exit (same logic as price_cell); return (reason, time, value)."""
    for t, v in sorted(_value_series(struct, long_bars, short_bars, fill_bar)):
        if v - debit >= TARGET * debit:
            return "hit +50% target", t, v
        if debit - v >= STOP * debit:
            return "hit -50% stop", t, v
    return "held to close", "16:00", hold_val


def build_ledger():
    """All 119 V5 trades, fully reconstructed; each row's pnl_$ asserted == backtest."""
    closes = {d: v[2] for d, v in daily_hlc().items()}
    cal = sorted(closes)
    rows = []
    for date, s in collect_fades():
        if s.name == "failed_c":                      # V5 filter
            continue
        cell = next((c for c in grid_cells(date, s, cal)
                     if c["horizon"] == "0DTE" and c["structure"]["kind"] == "debit_spread"), None)
        if cell is None:
            continue
        t = price_cell(cell, s, closes)               # the backtest's own number
        if t is None:
            continue
        long_bars = load_cached_minutes(*cell["long_contract"])
        short_bars = load_cached_minutes(*cell["short_contract"])
        debit, fill_bar = spread_entry(long_bars, short_bars, s.entry_time)
        struct = cell["structure"]
        settle = closes[date]
        hold_val = expire_value(struct, settle)
        reason, xtime, xval = _exit(struct, long_bars, short_bars, fill_bar, debit, hold_val)
        pnl = round((xval - debit) * 100, 2)
        assert abs(pnl - t["pnl0_ts"]) < 0.01, (date, pnl, t["pnl0_ts"])   # TRUST GUARANTEE
        typ = struct["opt_type"]
        kind = "bull call spread" if typ == "call" else "bear put spread"
        lk, sk = struct["long_strike"], struct["short_strike"]
        rows.append({
            "#": len(rows) + 1, "date": date, "signal_time": s.entry_time,
            "direction": s.direction, "setup": s.name, "conviction": s.conviction,
            "why_entered": _why(s), "underlying_at_entry": round(s.entry_price, 2),
            "structure": f"{kind} {int(lk)}/{int(sk)}", "option_type": typ,
            "long_strike": lk, "short_strike": sk, "debit_paid": round(debit, 2),
            "max_loss": round(debit * 100, 2), "exit_reason": reason, "exit_time": xtime,
            "settle_close": round(settle, 2), "pnl_$": pnl,
            "return_on_risk_%": round(pnl / (debit * 100) * 100, 1),
            "result": "WIN" if pnl > 0 else "LOSS",
        })
    return rows


if __name__ == "__main__":
    rows = build_ledger()
    assert len(rows) == 119, f"expected 119 V5 trades, got {len(rows)}"
    assert set(COLUMNS) <= set(rows[0]), set(COLUMNS) - set(rows[0])
    tot = sum(r["return_on_risk_%"] for r in rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    assert 4100 < tot < 4250, f"total {tot} != ~4171 (scoreboard reconcile)"
    assert 0.78 <= wins / len(rows) <= 0.86, wins / len(rows)
    print(f"OK build_ledger: {len(rows)} trades, +{tot:.0f}% on risk, win {wins/len(rows)*100:.0f}% "
          f"(per-row P&L == backtest, asserted)")
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python bot/trade_ledger.py`
Expected: `OK build_ledger: 119 trades, +4171% on risk, win 82% (per-row P&L == backtest, asserted)` (first run builds the signal history from cache — up to ~1 min).

- [ ] **Step 3: Commit.**

```bash
git add bot/trade_ledger.py
git commit -m "feat(ledger): build_ledger — reconstruct all 119 V5 trades, per-row P&L asserted == backtest"
```

---

### Task 2: `write_csv` + `write_md` + generate the artifacts

**Files:**
- Modify: `bot/trade_ledger.py` (add `_narrative`, `write_csv`, `write_md` above `__main__`; append the file-generation + sample to the END of the existing `__main__`).

**Interfaces:**
- Consumes: `build_ledger()` output rows, `COLUMNS`, `csv`, `os`, `defaultdict`.
- Produces: `_narrative(row) -> str`, `write_csv(rows, path)`, `write_md(rows, path)`.

- [ ] **Step 1: Add the three functions (above `__main__`).**

```python
def _narrative(r):
    tag = "WIN" if r["result"] == "WIN" else "LOSS"
    return (f'{r["date"]} {r["signal_time"]} — faded {r["direction"].upper()} ({r["setup"]}): '
            f'{r["structure"]} for ${r["debit_paid"]:.2f} -> {r["exit_reason"]} at {r["exit_time"]} '
            f'-> {r["pnl_$"]:+.0f} ({r["return_on_risk_%"]:+.0f}%) [{tag}]')


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in COLUMNS})


def write_md(rows, path):
    tot = sum(r["return_on_risk_%"] for r in rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    out = ["# V5 Fade Strategy — Full Trade Ledger\n"]
    out.append("**What this is:** every trade the winning V5 fade config took over ~3 years, "
               "reconstructed from real historical option prices (IVolatility). Nothing is "
               "cherry-picked — winners and losers, all " + str(len(rows)) + ". Each row's profit/loss "
               "is recomputed from the source prices and **asserted equal to the backtest**, so this "
               "ledger *is* the backtest, not a flattering retelling.\n")
    out.append("**Honest caveat:** these are **backtest** results, not live or paper-traded. The "
               "config was chosen as the best of 9 variants, so a walk-forward / forward-test is the "
               "real next step before trusting it with money.\n")
    out.append("## Summary\n")
    out.append(f"- **Config:** 0DTE debit spread · drop the treacherous `failed_c` fade · "
               f"active +50%/-50% exit")
    out.append(f"- **Span:** {rows[0]['date']} → {rows[-1]['date']} · **{len(rows)} trades**")
    out.append(f"- **Result:** +{tot:.0f}% on capital-at-risk · **{wins/len(rows)*100:.0f}% win rate**")
    out.append(f"- **In account terms:** a $10,000 account risking 1% per trade → **+42%** "
               f"(${'14,171'}), worst dip **-1.1%**\n")
    out.append("## Every trade\n")
    out.append("| # | date | dir | setup | structure | debit | exit | P&L | on risk | result |")
    out.append("|--:|------|-----|-------|-----------|------:|------|----:|--------:|--------|")
    for r in rows:
        out.append(f"| {r['#']} | {r['date']} | {r['direction']} | {r['setup']} | {r['structure']} "
                   f"| ${r['debit_paid']:.2f} | {r['exit_reason']} @ {r['exit_time']} "
                   f"| {r['pnl_$']:+.0f} | {r['return_on_risk_%']:+.0f}% | {r['result']} |")
    out.append("\n## Trade-by-trade (one line each)\n")
    by_year = defaultdict(list)
    for r in rows:
        by_year[r["date"][:4]].append(r)
    for y in sorted(by_year):
        out.append(f"\n### {y}\n")
        for r in by_year[y]:
            out.append(f"{r['#']}. {_narrative(r)}")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
```

- [ ] **Step 2: Append the artifact generation + sample to the END of `__main__`** (after the Task 1 `print`, reusing the `rows` already built).

```python
    os.makedirs("results", exist_ok=True)
    write_csv(rows, "results/v5_trade_ledger.csv")
    write_md(rows, "results/v5_trade_ledger.md")
    with open("results/v5_trade_ledger.csv") as f:
        n_csv = sum(1 for _ in f) - 1                  # minus header
    assert n_csv == len(rows), (n_csv, len(rows))
    print(f"wrote results/v5_trade_ledger.csv ({n_csv} rows) and results/v5_trade_ledger.md")
    print("\nSAMPLE (first 8 trades):")
    for r in rows[:8]:
        print("  " + _narrative(r))
```

- [ ] **Step 3: Run it.**

Run: `.venv/bin/python bot/trade_ledger.py`
Expected: the `OK build_ledger` line, then `wrote results/v5_trade_ledger.csv (119 rows) and results/v5_trade_ledger.md`, then 8 sample narrative lines (first should be the 2023-07-12 failed_a long → +$395 WIN).

- [ ] **Step 4: Eyeball the outputs.**

Run: `head -3 results/v5_trade_ledger.csv && echo "---" && head -20 results/v5_trade_ledger.md`
Confirm the CSV header matches `COLUMNS` and the MD has the honest summary + table start.

- [ ] **Step 5: Commit.**

```bash
git add bot/trade_ledger.py
git commit -m "feat(ledger): write_csv + write_md + generate the V5 ledger artifacts"
```

---

### Task 3: Publish the artifacts + record

**Files:**
- Create (force-add, `results/` is gitignored): `results/v5_trade_ledger.csv`, `results/v5_trade_ledger.md`.
- Also commit the (currently untracked) V5 equity chart artifacts: `bot/plot_v5_results.py`, `results/v5_equity_curve.png`.
- Modify: `STATUS.md`.

- [ ] **Step 1: Regenerate the artifacts** (ensure they're current).

Run: `.venv/bin/python bot/trade_ledger.py`
Confirm the `wrote ...` line and 119 rows.

- [ ] **Step 2: Update `STATUS.md`** — add to the Session-10 log: the V5 trade ledger built (CSV + MD, per-row P&L asserted == backtest, 119 trades published to the repo) as the transparency/evidence artifact; note the equity chart too.

- [ ] **Step 3: Commit + push.**

```bash
git add -f results/v5_trade_ledger.csv results/v5_trade_ledger.md results/v5_equity_curve.png
git add bot/trade_ledger.py bot/plot_v5_results.py STATUS.md
git commit -m "feat(ledger): publish V5 trade ledger (CSV + MD) + equity chart as auditable evidence"
git push origin main
```

---

## Self-Review

**Spec coverage:**
- CSV of all 119 trades × exact columns → Task 1 (`build_ledger`, `COLUMNS`), Task 2 (`write_csv`). ✓
- Readable MD (honest summary + caveats + table + per-year one-line narratives) → Task 2 (`write_md`, `_narrative`). ✓
- `why_entered` deterministic narrative → Task 1 (`_why`). ✓
- Exit reason/time reconstruction → Task 1 (`_exit`, reusing `_value_series`). ✓
- Per-row P&L == backtest assertion (trust guarantee) → Task 1 (`assert` in `build_ledger`). ✓
- Reconcile n=119 / +4171% / 82% → Task 1 self-test asserts. ✓
- Honest framing in the .md → Task 2 (`write_md` header). ✓
- Publish to repo → Task 3 (force-add + push). ✓
- Offline, reuse ④b engine → all tasks read cache only. ✓

**Placeholder scan:** No TBD/TODO; every code step complete. ✓

**Type consistency:** `COLUMNS` defined in Task 1, consumed by `write_csv`/`write_md` in Task 2 (same names). Row-dict keys built in Task 1 == `COLUMNS` == the keys `_narrative`/`write_md` read. `_exit` returns `(reason, time, value)` consumed positionally in `build_ledger`. ✓

**Note for the executor:** Task 2 reuses the `rows` variable already bound by Task 1's self-test in the same `__main__` block (do not rebuild). The `$14,171` / `+42%` / `-1.1%` account figures in the MD summary are the published equity-chart numbers (from `plot_v5_results.py`, $10k @ 1%/trade) — kept as fixed copy, consistent with `results/v5_equity_curve.png`.
