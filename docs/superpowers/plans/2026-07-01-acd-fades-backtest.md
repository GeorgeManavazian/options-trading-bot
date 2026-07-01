# ④b Intraday/Overnight Fade Backtest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtest the 164 ACD fade signals as options across a 2×2 grid — {0DTE, overnight ~1-DTE} × {debit spread, long option} — to see whether the checkpoint's fade edge survives as options-with-costs, and which horizon×structure monetizes it best.

**Architecture:** Reuse the existing signal seam (`build_history` → `apply_macro` → filter `FADES`). Add a pure debit-structure pricing module, a shared signal/leg module, a resumable intraday pull, and an offline driver that marks each grid cell from cached NBBO bars (entry) + the cached underlying close (settle-at-expiry). Grade via `backtest-expert`.

**Tech Stack:** Python 3.12 in `.venv`, pandas. House style: flat `bot/` modules, bare sibling imports, run `.venv/bin/python bot/<file>.py`, inline `__main__` assert self-tests (NO pytest), frequent commits.

## Global Constraints

- Python via `.venv`; run every file as `.venv/bin/python bot/<file>.py` (the `bot/` dir is `sys.path[0]`, so bare sibling imports like `from acd_wrappers import nearest` work).
- NO pytest — every module ends in an `if __name__ == "__main__":` block of `assert` self-tests that print `OK`/`passed`; "run the test" = run the file and read the output.
- Data cache lives in `data_cache/`; intraday minute-bar cache filename is EXACTLY `f"{symbol}_{trade_date}_{exp_date}_{int(strike)}_{opt_type[0].upper()}_min.csv"` (must match `load_ivol_intraday.fetch_option_minutes`).
- IVolatility rate cap = 1 req/sec (`fetch_option_minutes` already sleeps 1.1s). Real pulls need `IVOL_API_KEY` (in `.env`).
- Symbol = `"SPX"`. Strike grid = $5 (snap ATM via `round(price/5)*5`). Default debit-spread width = 25.0.
- Keep IVolatility subscribed. NEVER run git-history rewrites (the book PDF is in gitignored `research/`).
- P&L convention: per contract = `(exit_value − debit) * 100`; `max_loss = debit * 100` (both structures are debit-paid); `ret = pnl / max_loss = exit_value/debit − 1`.

---

### Task 1: `acd_fade_pricing.py` — pure debit-structure pricing/exit

**Files:**
- Create: `bot/acd_fade_pricing.py`

**Interfaces:**
- Consumes: nothing (pure; pandas only in the self-test).
- Produces:
  - `spread_entry(long_bars, short_bars, entry_time) -> (debit: float, entry_t: str)` — `long_bars`/`short_bars` are minute-bar DataFrames (columns `time,bid,ask`); `short_bars=None` for a long option.
  - `expire_value(structure, settle: float) -> float` — per-share intrinsic at expiry. `structure` is a dict `{"kind": "debit_spread"|"long_option", "opt_type": "call"|"put", "long_strike": float, "short_strike": float(optional), "width": float(optional)}`.
  - `close_value(structure, long_row, short_row) -> float` — per-share proceeds to close now (`long.bid − short.ask`; `short_row=None` for a long option).
  - `exit_target_stop(debit, value_series, settle_value, target=0.5, stop=0.5) -> float` — per-share exit value; `value_series` is a list of `(time, close_value)`.

- [ ] **Step 1: Write the module WITH its `__main__` self-tests (they define the expected behavior).**

```python
# acd_fade_pricing.py — pure pricing + exit for DEBIT fade structures (0DTE/overnight).
# Entry debit from real intraday NBBO bars; settle at expiry intrinsic from the
# underlying close; optional intraday target/stop for the 0DTE exit comparison.
# No network -> offline __main__ self-tests. Run: .venv/bin/python bot/acd_fade_pricing.py


def _by_time(bars):
    """{time(str): row} from a minute-bar DataFrame (columns time/bid/ask)."""
    return {str(r["time"]): r for _, r in bars.iterrows()}


def spread_entry(long_bars, short_bars, entry_time):
    """Net debit at the first bar with time >= entry_time. Long pays ask; short
    (None for a long option) receives bid. Returns (debit_per_share, entry_t)."""
    L = _by_time(long_bars)
    times = sorted(t for t in L if t >= entry_time)
    if short_bars is not None:
        S = _by_time(short_bars)
        times = [t for t in times if t in S]
    if not times:
        raise ValueError(f"no fillable bar at/after {entry_time}")
    t = times[0]
    debit = float(L[t]["ask"])
    if short_bars is not None:
        debit -= float(S[t]["bid"])
    return debit, t


def expire_value(structure, settle):
    """Per-share intrinsic value of the debit structure at expiry."""
    typ, lk = structure["opt_type"], structure["long_strike"]
    if structure["kind"] == "long_option":
        return max(settle - lk, 0.0) if typ == "call" else max(lk - settle, 0.0)
    w = structure["width"]                        # debit spread
    if typ == "call":                             # bull call: long lk, short lk+w
        return min(max(settle - lk, 0.0), w)
    return min(max(lk - settle, 0.0), w)          # bear put: long lk, short lk-w


def close_value(structure, long_row, short_row):
    """Per-share proceeds to close now (sell the structure): long.bid - short.ask."""
    v = float(long_row["bid"])
    if structure["kind"] == "debit_spread":
        v -= float(short_row["ask"])
    return v


def exit_target_stop(debit, value_series, settle_value, target=0.5, stop=0.5):
    """Walk (time, close_value) bars; first to reach +target*debit profit or
    -stop*debit loss ends the trade at that value; else settle_value."""
    for t, v in sorted(value_series):
        if v - debit >= target * debit:           # profit target
            return v
        if debit - v >= stop * debit:             # stop
            return v
    return settle_value


if __name__ == "__main__":
    import pandas as pd

    lb = pd.DataFrame({"time": ["10:00", "10:01"], "bid": [30, 31], "ask": [32, 33]})
    sb = pd.DataFrame({"time": ["10:00", "10:01"], "bid": [18, 19], "ask": [20, 21]})
    debit, t = spread_entry(lb, sb, "10:00")
    assert t == "10:00" and abs(debit - 14.0) < 1e-9, (debit, t)   # 32 - 18
    d2, _ = spread_entry(lb, None, "10:00")
    assert d2 == 32.0, d2                                          # long option = ask
    try:
        spread_entry(lb, sb, "23:59"); assert False
    except ValueError:
        pass
    print("OK spread_entry")

    cs = {"kind": "debit_spread", "opt_type": "call", "long_strike": 5000, "width": 25}
    assert expire_value(cs, 5030) == 25.0 and expire_value(cs, 5010) == 10.0
    assert expire_value(cs, 4990) == 0.0
    ps = {"kind": "debit_spread", "opt_type": "put", "long_strike": 5000, "width": 25}
    assert expire_value(ps, 4970) == 25.0 and expire_value(ps, 4990) == 10.0
    lo = {"kind": "long_option", "opt_type": "call", "long_strike": 5000}
    assert expire_value(lo, 5040) == 40.0 and expire_value(lo, 4960) == 0.0
    print("OK expire_value")

    assert close_value(cs, {"bid": 22}, {"ask": 8}) == 14.0
    assert close_value(lo, {"bid": 40}, None) == 40.0
    print("OK close_value")

    # debit 14; target 0.5 -> exit when value>=21; stop 0.5 -> exit when value<=7
    assert exit_target_stop(14, [("10:05", 16), ("10:10", 22)], 25) == 22   # target
    assert exit_target_stop(14, [("10:05", 10), ("10:10", 6)], 0) == 6      # stop
    assert exit_target_stop(14, [("10:05", 15), ("10:10", 16)], 25) == 25   # settle
    print("OK exit_target_stop")
    print("All acd_fade_pricing self-tests passed.")
```

- [ ] **Step 2: Run it to verify the self-tests pass.**

Run: `.venv/bin/python bot/acd_fade_pricing.py`
Expected: four `OK ...` lines then `All acd_fade_pricing self-tests passed.`

- [ ] **Step 3: Commit.**

```bash
git add bot/acd_fade_pricing.py
git commit -m "feat(fades): pure debit-structure pricing/exit (entry debit, expiry intrinsic, target/stop)"
```

---

### Task 2: add `load_cached_minutes` to `load_ivol_intraday.py`

**Files:**
- Modify: `bot/load_ivol_intraday.py` (add one function after `fetch_option_minutes`, ends ~line 67; add one self-test line to the existing `__main__`).

**Interfaces:**
- Consumes: module globals `CACHE_DIR`, `normalize_minutes`, `pd` (all already imported at top of the file).
- Produces: `load_cached_minutes(symbol, trade_date, exp_date, strike, opt_type) -> DataFrame | None` — cache-only reader (no network); returns normalized bars if the CSV exists, else `None`.

- [ ] **Step 1: Add the function** immediately after `fetch_option_minutes` (before `def underlying_path`).

```python
def load_cached_minutes(symbol, trade_date, exp_date, strike, opt_type):
    """Cache-only reader: normalized minute bars if already pulled, else None.
    Filename must match fetch_option_minutes exactly. No network -> the offline
    backtest marks fades through this."""
    tag = f"{symbol}_{trade_date}_{exp_date}_{int(strike)}_{opt_type[0].upper()}_min.csv"
    cache_path = os.path.join(CACHE_DIR, tag)
    if os.path.exists(cache_path):
        return normalize_minutes(pd.read_csv(cache_path))
    return None
```

- [ ] **Step 2: Add a self-test line** at the end of the existing `if __name__ == "__main__":` block (after the `Task 7b OK` print):

```python
    assert load_cached_minutes("SPX", "1900-01-01", "1900-01-01", 5000, "put") is None
    print("Task 7c OK: load_cached_minutes returns None for an un-cached contract")
```

- [ ] **Step 3: Run it to verify the module still passes.**

Run: `.venv/bin/python bot/load_ivol_intraday.py`
Expected: existing `Task 7 OK` / `Task 7b OK` lines plus `Task 7c OK: load_cached_minutes returns None for an un-cached contract`.

- [ ] **Step 4: Commit.**

```bash
git add bot/load_ivol_intraday.py
git commit -m "feat(intraday): load_cached_minutes cache-only reader for the offline fade backtest"
```

---

### Task 3: `acd_fade_signals.py` — collect fades + build the grid cells

**Files:**
- Create: `bot/acd_fade_signals.py`

**Interfaces:**
- Consumes: `build_history` (`diag_full_signal`), `macro_context`/`apply_macro` (`acd_macro`), `FADES` (`acd_options`), `Setup` fields `name/direction/entry_time/entry_price/conviction` (`acd_micro`).
- Produces:
  - `collect_fades() -> list[(date: str, setup: Setup)]` — the filtered fade signals (expect ~164).
  - `grid_cells(date, setup, calendar, width=25.0) -> list[dict]` — 2–4 cells, each:
    `{"horizon": "0DTE"|"overnight", "structure": {...}, "long_contract": (sym,date,exp,strike,typ), "short_contract": (...)|None, "settle_date": exp}`.
    Overnight cells are omitted when `date` is the last day in `calendar`.

- [ ] **Step 1: Write the module WITH `__main__` self-tests.**

```python
# acd_fade_signals.py — collect the ACD FADE signals and build the 2x2 backtest
# grid ({0DTE, overnight} x {debit_spread, long_option}) for each one. Shared by
# the pull script and the offline backtest so the two agree on contracts/strikes.
# Offline (build_history reads cached paths). Run: .venv/bin/python bot/acd_fade_signals.py
SYM = "SPX"


def collect_fades():
    """[(date, Setup)] for every filtered fade (failed_a / failed_a_pivot / failed_c)."""
    from diag_full_signal import build_history
    from acd_macro import macro_context, apply_macro
    from acd_options import FADES
    hist = build_history()
    out = []
    for i, day in enumerate(hist):
        ctx = macro_context(i, hist)
        for s in apply_macro(day.day_result.setups, ctx):
            if s.name in FADES:
                out.append((day.date, s))
    return out


def _strikes(setup, width):
    typ = "call" if setup.direction == "long" else "put"
    atm = round(setup.entry_price / 5.0) * 5.0
    short = atm + width if setup.direction == "long" else atm - width
    return typ, atm, short


def grid_cells(date, setup, calendar, width=25.0):
    """The 2x2 grid for one fade. `calendar` = sorted trading dates (overnight
    expiry = the next one). Contracts are (SYM, trade_date, exp, strike, typ)."""
    typ, atm, short = _strikes(setup, width)
    exps = [("0DTE", date)]
    i = calendar.index(date)
    if i + 1 < len(calendar):
        exps.append(("overnight", calendar[i + 1]))

    cells = []
    for horizon, exp in exps:
        lo = {"kind": "long_option", "opt_type": typ, "long_strike": atm}
        cells.append({"horizon": horizon, "structure": lo,
                      "long_contract": (SYM, date, exp, atm, typ),
                      "short_contract": None, "settle_date": exp})
        ds = {"kind": "debit_spread", "opt_type": typ, "long_strike": atm,
              "short_strike": short, "width": width}
        cells.append({"horizon": horizon, "structure": ds,
                      "long_contract": (SYM, date, exp, atm, typ),
                      "short_contract": (SYM, date, exp, short, typ),
                      "settle_date": exp})
    return cells


if __name__ == "__main__":
    from acd_micro import Setup
    cal = ["2024-06-03", "2024-06-04", "2024-06-05"]
    long_fade = Setup("failed_a", "long", "10:30", 5003.0, None, 1, "intraday", {})
    cells = grid_cells("2024-06-04", long_fade, cal, width=25.0)
    assert len(cells) == 4, len(cells)
    lo0 = [c for c in cells if c["horizon"] == "0DTE" and c["short_contract"] is None][0]
    assert lo0["long_contract"] == ("SPX", "2024-06-04", "2024-06-04", 5005.0, "call"), lo0
    ds_n = [c for c in cells if c["horizon"] == "overnight"
            and c["structure"]["kind"] == "debit_spread"][0]
    assert ds_n["long_contract"] == ("SPX", "2024-06-04", "2024-06-05", 5005.0, "call")
    assert ds_n["short_contract"] == ("SPX", "2024-06-04", "2024-06-05", 5030.0, "call")
    assert ds_n["settle_date"] == "2024-06-05", ds_n
    print("OK grid_cells (long fade -> call, ATM 5005, short 5030)")

    short_fade = Setup("failed_a", "short", "11:00", 5002.0, None, 1, "intraday", {})
    sc = grid_cells("2024-06-05", short_fade, cal)   # last day -> no overnight
    assert len(sc) == 2 and all(c["horizon"] == "0DTE" for c in sc), sc
    assert sc[0]["structure"]["opt_type"] == "put"
    dsp = [c for c in sc if c["structure"]["kind"] == "debit_spread"][0]
    assert dsp["short_contract"][3] == 4975.0, dsp   # 5000 - 25 (bear put)
    print("OK grid_cells (short fade -> put; last day drops overnight)")

    fades = collect_fades()
    print(f"collect_fades: {len(fades)} fade signals")
    assert len(fades) > 100 and all(len(t) == 2 for t in fades)
    print("All acd_fade_signals self-tests passed.")
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python bot/acd_fade_signals.py`
Expected: the two `OK grid_cells ...` lines, a `collect_fades: <N> fade signals` line (N ≈ 164), then `All acd_fade_signals self-tests passed.` (First run builds the signal history from cache — up to ~1 min.)

- [ ] **Step 3: Commit.**

```bash
git add bot/acd_fade_signals.py
git commit -m "feat(fades): collect fade signals + build the 2x2 horizon/structure grid"
```

---

### Task 4: `pull_fade_data.py` — resumable intraday leg pull

**Files:**
- Create: `bot/pull_fade_data.py`

**Interfaces:**
- Consumes: `collect_fades`/`grid_cells` (`acd_fade_signals`), `daily_hlc` (`run_acd_signal`), `fetch_option_minutes` (`load_ivol_intraday`).
- Produces: `unique_contracts(fades, calendar, width=25.0) -> sorted list[(sym,date,exp,strike,typ)]`; a `main()` that pulls each (cache-skipping) and logs to `results/fade_pull.log`.

- [ ] **Step 1: Write the module WITH an offline `__main__` self-test** (the pull loop itself needs the API; the self-test only exercises `unique_contracts`, which is offline).

```python
# pull_fade_data.py — pull the intraday 1-min bars for every fade's grid legs
# (0DTE + next-day expiry, ATM + width-OTM). Resumable (fetch_option_minutes
# cache-skips). Real pull needs IVOL_API_KEY. After this runs once, the backtest
# is fully offline. Run: .venv/bin/python bot/pull_fade_data.py
import os

from acd_fade_signals import collect_fades, grid_cells
from run_acd_signal import daily_hlc

LOG = os.path.join(os.path.dirname(__file__), "..", "results", "fade_pull.log")


def unique_contracts(fades, calendar, width=25.0):
    """Every distinct (sym, date, exp, strike, typ) leg across all fades' grids."""
    seen = {}
    for date, setup in fades:
        for cell in grid_cells(date, setup, calendar, width):
            for c in (cell["long_contract"], cell["short_contract"]):
                if c is not None:
                    seen[c] = True
    return sorted(seen)


def main():
    from load_ivol_intraday import fetch_option_minutes
    fades = collect_fades()
    calendar = sorted(daily_hlc())
    contracts = unique_contracts(fades, calendar)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    total = len(contracts)
    print(f"{len(fades)} fades -> {total} unique leg-contracts to pull", flush=True)
    ok = fail = 0
    with open(LOG, "a") as log:
        log.write(f"=== fade pull: {total} contracts ===\n")
        for n, (sym, date, exp, strike, typ) in enumerate(contracts, 1):
            try:
                fetch_option_minutes(sym, date, exp, strike, typ)  # caches; sleeps 1.1s
                ok += 1
            except Exception as e:                                 # missing contract etc.
                fail += 1
                log.write(f"FAIL {sym} {date} {exp} {int(strike)} {typ}: {e}\n")
            if n % 25 == 0 or n == total:
                msg = f"[{n}/{total}] ok={ok} fail={fail}"
                print(msg, flush=True); log.write(msg + "\n"); log.flush()
    print(f"done: ok={ok} fail={fail} (log: results/fade_pull.log)")


if __name__ == "__main__":
    if os.environ.get("IVOL_API_KEY"):
        main()
    else:                                          # offline: just verify the plan
        fades = collect_fades()
        calendar = sorted(daily_hlc())
        contracts = unique_contracts(fades, calendar)
        assert contracts and all(len(c) == 5 for c in contracts)
        print(f"OK (offline): {len(fades)} fades -> {len(contracts)} unique contracts "
              f"(~{len(contracts)} pulls @1.1s ≈ {len(contracts)*1.1/60:.0f} min). "
              f"Set IVOL_API_KEY to pull.")
```

- [ ] **Step 2: Run the offline plan check.**

Run: `.venv/bin/python bot/pull_fade_data.py`
Expected (no key set): `OK (offline): <N> fades -> <M> unique contracts (~M pulls ... ≈ ~12 min). Set IVOL_API_KEY to pull.`

- [ ] **Step 3: Commit.**

```bash
git add bot/pull_fade_data.py
git commit -m "feat(fades): resumable intraday leg pull (offline plan check without a key)"
```

---

### Task 5: `backtest_acd_fades.py` — the ④b driver + report

**Files:**
- Create: `bot/backtest_acd_fades.py`

**Interfaces:**
- Consumes: `collect_fades`/`grid_cells` (`acd_fade_signals`); `spread_entry`/`expire_value`/`close_value`/`exit_target_stop` (`acd_fade_pricing`); `load_cached_minutes` (`load_ivol_intraday`); `daily_hlc` (`run_acd_signal`); `_with_slip`/`_stats` (`backtest_acd_full`).
- Produces: `price_cell(cell, setup, closes) -> dict | None` (one trade or a drop); `run_fades() -> (trades, dropped)`; `report(trades)`.

- [ ] **Step 1: Write the module WITH a `__main__` that first runs a pure `price_cell` self-test on monkeypatched cached bars, then (if the real cache is present) runs the full backtest.**

```python
# backtest_acd_fades.py — (4b) backtest the ACD FADES as options across the 2x2
# grid ({0DTE, overnight} x {debit_spread, long_option}). Enter at the fade's
# intraday time (real NBBO bars); settle at each option's expiry via the cached
# underlying close. Reports per cell + a slippage sweep + a 0DTE hold-vs-stop
# comparison. Offline on cache. Run: .venv/bin/python bot/backtest_acd_fades.py
import statistics
from collections import Counter
from itertools import accumulate

from acd_fade_signals import collect_fades, grid_cells
from acd_fade_pricing import spread_entry, expire_value, close_value, exit_target_stop
from load_ivol_intraday import load_cached_minutes
from run_acd_signal import daily_hlc
from backtest_acd_full import _with_slip, _stats


def _value_series(structure, long_bars, short_bars, entry_t):
    """[(time, close_value)] from entry_t onward (0DTE active-exit walk)."""
    Lb = {str(r["time"]): r for _, r in long_bars.iterrows()}
    Sb = {str(r["time"]): r for _, r in short_bars.iterrows()} if short_bars is not None else None
    out = []
    for t in sorted(Lb):
        if t < entry_t:
            continue
        if Sb is not None and t not in Sb:
            continue
        out.append((t, close_value(structure, Lb[t], None if Sb is None else Sb[t])))
    return out


def price_cell(cell, setup, closes, target=0.5, stop=0.5):
    """One grid cell -> a trade dict, or None if un-markable/degenerate."""
    long_bars = load_cached_minutes(*cell["long_contract"])
    if long_bars is None or long_bars.empty:
        return None
    short_c = cell["short_contract"]
    short_bars = load_cached_minutes(*short_c) if short_c else None
    if short_c and (short_bars is None or short_bars.empty):
        return None
    try:
        debit, entry_t = spread_entry(long_bars, short_bars, setup.entry_time)
    except ValueError:
        return None
    if debit <= 0:                                 # inverted/degenerate -> skip
        return None
    settle_px = closes.get(cell["settle_date"])
    if settle_px is None or settle_px <= 0:
        return None
    struct = cell["structure"]
    hold_val = expire_value(struct, settle_px)     # hold-to-expiry
    nlegs = 1 if short_c is None else 2
    trade = {"date": cell["long_contract"][1], "horizon": cell["horizon"],
             "kind": struct["kind"], "nlegs": nlegs, "debit": debit,
             "max_loss": debit * 100,
             "pnl0": round((hold_val - debit) * 100, 2)}
    if cell["horizon"] == "0DTE":                  # active target/stop comparison
        vs = _value_series(struct, long_bars, short_bars, entry_t)
        ts_val = exit_target_stop(debit, vs, hold_val, target, stop)
        trade["pnl0_ts"] = round((ts_val - debit) * 100, 2)
    return trade


def run_fades():
    closes = {d: v[2] for d, v in daily_hlc().items()}
    calendar = sorted(closes)
    fades = collect_fades()
    trades, dropped = [], 0
    for date, setup in fades:
        for cell in grid_cells(date, setup, calendar):
            t = price_cell(cell, setup, closes)
            if t is None:
                dropped += 1
            else:
                trades.append(t)
    return trades, dropped


def _cell_line(rows, label):
    n, wr, total, mdd, ra = _stats([r["ret_pct"] for r in rows])
    print(f"  {label:<26} n={n:>3}  win {wr:.0%}  total {total:+.0%} on risk  "
          f"maxDD {mdd:.0%}  risk-adj {ra:+.2f}")


def report(trades):
    print(f"\n=== FADE backtest — {len(trades)} trades ===")
    print("by cell:", dict(Counter((t['horizon'], t['kind']) for t in trades)))
    base = _with_slip(trades, 0.0)                 # adds ret_pct = pnl/max_loss
    print("\n@0 slippage, hold-to-expiry, by grid cell:")
    for horizon in ("0DTE", "overnight"):
        for kind in ("debit_spread", "long_option"):
            rows = [t for t in base if t["horizon"] == horizon and t["kind"] == kind]
            if rows:
                _cell_line(rows, f"{horizon}/{kind}")

    print("\nslippage sweep (per cell, does the edge survive costs?):")
    for horizon in ("0DTE", "overnight"):
        for kind in ("debit_spread", "long_option"):
            sub = [t for t in trades if t["horizon"] == horizon and t["kind"] == kind]
            if not sub:
                continue
            line = f"  {horizon}/{kind:<13}"
            for slip in (0.0, 0.05, 0.10, 0.20):
                rets = [r["ret_pct"] for r in _with_slip(sub, slip)]
                _, wr2, tot2, _, _ = _stats(rets)
                line += f"  {int(slip*100)}c:{tot2:+.0%}/{wr2:.0%}"
            print(line)

    ov = [t for t in base if t["horizon"] == "0DTE" and "pnl0_ts" in t]
    if ov:
        print("\n0DTE exit comparison (the recurring hold-vs-tight-stop lesson):")
        hold = [t["ret_pct"] for t in ov]
        ts = [t["pnl0_ts"] / t["max_loss"] for t in ov]
        _, wr_h, tot_h, mdd_h, _ = _stats(hold)
        _, wr_t, tot_t, mdd_t, _ = _stats(ts)
        print(f"  hold-to-close : win {wr_h:.0%}  total {tot_h:+.0%}  maxDD {mdd_h:.0%}")
        print(f"  target/stop   : win {wr_t:.0%}  total {tot_t:+.0%}  maxDD {mdd_t:.0%}")


if __name__ == "__main__":
    # --- pure price_cell self-test on monkeypatched cached bars (offline) ---
    import pandas as pd
    import load_ivol_intraday as lv
    from acd_micro import Setup

    def fake_cache(sym, date, exp, strike, typ):
        # long 5000 call ~ deep; short 5025 call ~ cheaper -> debit ~12; settle 5040
        px = {5000.0: (30, 32), 5025.0: (18, 20)}.get(float(strike))
        if px is None:
            return None
        bid, ask = px
        return pd.DataFrame({"time": ["10:00", "16:00"], "bid": [bid, bid],
                             "ask": [ask, ask]})
    lv.load_cached_minutes = fake_cache            # monkeypatch (backtest imported the name)
    globals()["load_cached_minutes"] = fake_cache

    setup = Setup("failed_a", "long", "10:00", 5003.0, None, 1, "intraday", {})
    ds_cell = {"horizon": "0DTE",
               "structure": {"kind": "debit_spread", "opt_type": "call",
                             "long_strike": 5000.0, "short_strike": 5025.0, "width": 25.0},
               "long_contract": ("SPX", "2024-06-03", "2024-06-03", 5000.0, "call"),
               "short_contract": ("SPX", "2024-06-03", "2024-06-03", 5025.0, "call"),
               "settle_date": "2024-06-03"}
    tr = price_cell(ds_cell, setup, {"2024-06-03": (0, 0, 5040.0)})
    # debit = 32 - 18 = 14; expire_value(bull call, 5040) = min(40,25) = 25; pnl=(25-14)*100
    assert tr is not None and abs(tr["debit"] - 14.0) < 1e-9 and tr["pnl0"] == 1100.0, tr
    assert tr["nlegs"] == 2 and "pnl0_ts" in tr, tr
    print(f"OK price_cell (debit 14, pnl {tr['pnl0']})")

    lo_cell = {"horizon": "0DTE",
               "structure": {"kind": "long_option", "opt_type": "call", "long_strike": 5000.0},
               "long_contract": ("SPX", "2024-06-03", "2024-06-03", 5000.0, "call"),
               "short_contract": None, "settle_date": "2024-06-03"}
    tr2 = price_cell(lo_cell, setup, {"2024-06-03": (0, 0, 5040.0)})
    # debit = ask 32; expire_value = 40; pnl = (40-32)*100 = 800
    assert tr2["debit"] == 32.0 and tr2["pnl0"] == 800.0 and tr2["nlegs"] == 1, tr2
    print(f"OK price_cell long option (debit 32, pnl {tr2['pnl0']})")

    print("Restore + attempt full run (needs the real cache)...")
    import importlib
    importlib.reload(lv)
    from load_ivol_intraday import load_cached_minutes as _real
    globals()["load_cached_minutes"] = _real
    trades, dropped = run_fades()
    print(f"full run: {len(trades)} trades, {dropped} dropped")
    if trades:
        report(trades)
    else:
        print("(no cached fade bars yet — run bot/pull_fade_data.py first)")
```

- [ ] **Step 2: Run the self-tests (they pass offline even before the real pull; the full run prints the no-cache note).**

Run: `.venv/bin/python bot/backtest_acd_fades.py`
Expected: `OK price_cell (debit 14, pnl 1100.0)`, `OK price_cell long option (debit 32, pnl 800.0)`, then either a full report or `(no cached fade bars yet — run bot/pull_fade_data.py first)`.

- [ ] **Step 3: Commit.**

```bash
git add bot/backtest_acd_fades.py
git commit -m "feat(fades): 4b backtest driver — 2x2 grid, per-cell report, slippage sweep, exit comparison"
```

---

### Task 6: Real pull → run → grade → record

**Files:**
- Create: `results/fade_pull.log` (written by the pull), `results/backtest_fades_eval_YYYY-MM-DD.md` (the grade).
- Modify: `STATUS.md` (Session log + current-phase brief).

- [ ] **Step 1: Run the real intraday pull in the background** (needs `IVOL_API_KEY` from `.env`; ~12 min, resumable).

Run: `set -a; source .env; set +a; nohup .venv/bin/python bot/pull_fade_data.py > results/fade_pull.log 2>&1 &`
Check: `tail -f results/fade_pull.log` until `done: ok=... fail=...`. Re-run the same command to top up any gaps (cache-skips).

- [ ] **Step 2: Run the backtest on the now-populated cache.**

Run: `.venv/bin/python bot/backtest_acd_fades.py`
Expected: the two `OK price_cell` lines, `full run: <N> trades, <D> dropped`, then the per-cell report + slippage sweep + 0DTE exit comparison.

- [ ] **Step 3: Grade the results with the `backtest-expert` skill.** Invoke the skill, feed it every cell's win rate / total-on-risk / maxDD / risk-adj / Sharpe / slippage sweep and the honesty caveats from the spec (§5). Write its verdict to `results/backtest_fades_eval_2026-07-01.md` (score, the flags, per-cell read, and the honest overall verdict — does the fade edge survive as options-with-costs, and which cell is the best expression, or is it a rigorously-tested negative).

- [ ] **Step 4: Update `STATUS.md`** — add a Session-10 log entry (what ④b tested, the headline per-cell result, the grade, the honest verdict) and refresh the "current phase / next step" brief.

- [ ] **Step 5: Commit.**

```bash
git add results/backtest_fades_eval_2026-07-01.md STATUS.md
git commit -m "feat(fades): 4b results + backtest-expert grade + STATUS update"
```

---

## Self-Review

**Spec coverage:**
- 2×2 grid (0DTE/overnight × debit/long option) → Task 3 `grid_cells`, Task 5 `price_cell`/`report`. ✓
- Enter at intraday fade time, real NBBO → Task 1 `spread_entry`, Task 4 pull, Task 5 `price_cell`. ✓
- Settle at expiry via cached underlying close → Task 1 `expire_value`, Task 5 `closes`. ✓
- Overnight = next trading day → Task 3 `grid_cells` (calendar index+1). ✓
- Resumable ~650-pull data step → Task 4. ✓
- Per-cell metrics + slippage sweep, offline on cache → Task 5 `report` (reuses `_with_slip`/`_stats`). ✓
- 0DTE hold-vs-target/stop lesson re-test → Task 1 `exit_target_stop`, Task 5 `report`. ✓
- `backtest-expert` grade + honest caveats + STATUS → Task 6. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete. ✓

**Type consistency:** `structure` dict keys (`kind/opt_type/long_strike/short_strike/width`) are identical across Tasks 1/3/5. Contract tuple shape `(sym,date,exp,strike,typ)` identical in Tasks 3/4/5. `trade` dict carries `pnl0`/`nlegs`/`max_loss` — exactly what the imported `_with_slip` (backtest_acd_full) consumes to add `ret_pct`. ✓

**One deliberate note for the executor:** Task 5's `report` relies on `_with_slip` producing `ret_pct = pnl/max_loss` — confirm that field name in `backtest_acd_full._with_slip` before running (it does today: `"ret_pct": pnl / t["max_loss"]`). If it ever changes, mirror it locally.
