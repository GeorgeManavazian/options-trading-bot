# ACD Crude Options Overlay (Phase 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Express phase-1's same-day crude signals as directional debit spreads priced on real Databento NBBO, and measure whether the edge survives options + costs — under both hold-to-close and active ±50% exits.

**Architecture:** Reuse phase-1 signals (`backtest_acd_cl.build_cl_history`) and the ④b debit-pricing engine (`acd_fade_pricing`). Add three new files: a crude-options loader (resolve legs from Databento `LO` definitions + pull `bbo-1m` NBBO), a resumable leg-pull driver, and the phase-2 backtest driver. Phase-1 and V5 files are untouched.

**Tech Stack:** Python 3.12 in `.venv`; `databento` (0.80.0); `pandas`; std-lib. Data = Databento CME `GLBX.MDP3`, parent `LO` (WTI crude options), schemas `definition` (leg resolution) + `bbo-1m` (NBBO fills).

## Global Constraints

- **Isolation (hard):** never edit `acd_micro.py`, `acd_macro.py`, `acd_fade_pricing.py`, `backtest_acd_cl.py`, `load_cl_databento.py`, `diag_full_signal.py`, or any V5/SPX file. Reuse by import only. New files only.
- **House test style:** inline `if __name__ == "__main__":` asserts (NO pytest); run via `.venv/bin/python bot/<file>.py`. Commit only when self-tests print OK.
- **Offline-after-pull:** only pull functions hit the API; the backtest reads cached CSVs.
- **Secrets:** read `DATABENTO_API_KEY` from `.env` (present, gitignored); never hardcode/print. Reuse `load_cl_databento._client`.
- **Data facts (confirmed live):** `LO.OPT` `definition` rows carry `raw_symbol`, `instrument_class` ("C"/"P"), `strike_price` (float), `expiration` (tz ts), `underlying` (CL future). Pull one option by `symbols=[raw_symbol], stype_in="raw_symbol", schema="bbo-1m"`. `bbo-1m` cols include `bid_px_00`,`ask_px_00`; UTC `ts_event` index. Cost `bbo-1m` ≈ $0.0018/option-day → full job ≈ $9 (inside credit). Cost-check with `metadata.get_cost` before the full pull.
- **Structure:** directional **debit spread** — bull call (long ATM call, short ATM+width call) for longs; bear put (long ATM put, short ATM−width put) for shorts. Width default **$2.0**. Structure dict shape for `acd_fade_pricing`: `{"kind":"debit_spread","opt_type":"call"|"put","long_strike":float,"width":float}`.
- **Point value:** CL option = **$1000** per 1.00 of premium.
- **P&L:** per share debit `d` (long.ask−short.bid at entry), exit value `x` (long.bid−short.ask). return-on-risk `= x/d − 1`. Slippage `c` $/share/leg-side: `ret_c = (x − 2c)/(d + 2c) − 1`.
- **ET session window** for option bars: 09:00–16:00 (match the futures RTH the signals use).
- **Reused constants/functions:** `acd_macro.BREAKOUT`/`FADES`; `acd_fade_pricing.spread_entry`/`close_value`/`exit_target_stop`; `backtest_acd_cl.build_cl_history`/`_ret_stats`; `acd_macro.macro_context`/`apply_macro`; `load_cl_databento._client`/`_read_cache`/`_write_cache`/`CACHE_DIR`/`ET`.

---

### Task 1: Option NBBO → ET bars transform (pure, offline, TDD)

**Files:**
- Create: `bot/load_cl_options_databento.py`

**Interfaces:**
- Consumes: nothing (pure pandas).
- Produces: `option_bbo_by_et(df, session_open="09:00", session_close="16:00") -> pd.DataFrame` — from a raw `bbo-1m` df (tz-aware UTC `ts_event` index, cols `bid_px_00`/`ask_px_00`) → a DataFrame with columns `time` (ET "HH:MM"), `bid`, `ask`; ET-windowed to [open,close], sorted by time, rows with NaN or ≤0 bid/ask dropped. (Columns `time`/`bid`/`ask` are exactly what `acd_fade_pricing.spread_entry`/`close_value` consume.)

- [ ] **Step 1: Write the failing self-test**

Append to `bot/load_cl_options_databento.py`:

```python
if __name__ == "__main__":
    import pandas as pd

    idx = pd.to_datetime([
        "2024-01-10 14:00:00",  # 09:00 EST
        "2024-01-10 14:05:00",  # 09:05 EST
        "2024-01-10 21:30:00",  # 16:30 EST -> outside window
        "2024-03-11 13:00:00",  # 09:00 EDT (DST)
    ], utc=True)
    raw = pd.DataFrame({"bid_px_00":[2.01, 2.03, 9.9, 1.50],
                        "ask_px_00":[2.05, 2.06, 9.9, 1.55]}, index=idx)
    raw.index.name = "ts_event"
    out = option_bbo_by_et(raw, "09:00", "16:00")
    assert list(out.columns) == ["time","bid","ask"], out.columns
    assert out["time"].tolist() == ["09:00","09:05","09:00"], out["time"].tolist()  # 16:30 dropped
    assert abs(out.iloc[0]["ask"] - 2.05) < 1e-9
    # a NaN/zero bid row is dropped
    raw2 = raw.copy(); raw2.loc[raw2.index[0], "bid_px_00"] = 0.0
    out2 = option_bbo_by_et(raw2, "09:00", "16:00")
    assert out2["time"].tolist() == ["09:05","09:00"], out2["time"].tolist()
    print("Task 1 OK: option_bbo_by_et (ET window, DST, drop bad quotes)")
    print("ALL load_cl_options_databento self-tests passed")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: FAIL — `NameError: name 'option_bbo_by_et' is not defined`.

- [ ] **Step 3: Implement (top of file, above the self-tests)**

```python
# load_cl_options_databento.py — resolve crude (LO) option legs from Databento definitions
# and pull/cache their bbo-1m NBBO bars, reshaped for acd_fade_pricing. Pure transforms are
# network-free + self-tested; pull functions hit the API and cache to data_cache/.
# Run: .venv/bin/python bot/load_cl_options_databento.py
import os

import pandas as pd

from load_cl_databento import _client, _read_cache, _write_cache, CACHE_DIR, ET


def option_bbo_by_et(df, session_open="09:00", session_close="16:00"):
    """Raw bbo-1m df (tz-aware UTC index, bid_px_00/ask_px_00) -> DataFrame[time,bid,ask] in ET,
    RTH-windowed, sorted, dropping NaN/<=0 quotes."""
    if df.empty:
        return pd.DataFrame(columns=["time","bid","ask"])
    et = df.tz_convert(ET) if df.index.tz is not None else df.tz_localize("UTC").tz_convert(ET)
    rows = []
    for ts, bid, ask in zip(et.index, et["bid_px_00"], et["ask_px_00"]):
        hhmm = ts.strftime("%H:%M")
        if session_open <= hhmm <= session_close and pd.notna(bid) and pd.notna(ask) \
                and bid > 0 and ask > 0:
            rows.append((hhmm, float(bid), float(ask)))
    rows.sort()
    return pd.DataFrame(rows, columns=["time","bid","ask"])
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: PASS — prints `ALL load_cl_options_databento self-tests passed`.

- [ ] **Step 5: Commit**

```bash
git add bot/load_cl_options_databento.py
git commit -m "feat(cl-opt): bbo-1m -> ET time/bid/ask transform for crude options"
```

---

### Task 2: Leg resolution from Databento definitions

**Files:**
- Modify: `bot/load_cl_options_databento.py`

**Interfaces:**
- Consumes: `_client`, `_read_cache`, `_write_cache`, `CACHE_DIR` (from `load_cl_databento`).
- Produces:
  - `definition_snapshot(year, month) -> pd.DataFrame` — pull/cache the `LO.OPT` `definition` for the first available day of that year-month; columns kept: `raw_symbol`, `instrument_class`, `strike_price`, `exp` ("YYYY-MM-DD" string from `expiration`). Cache `data_cache/CL_optdef_<year>-<month>.csv`; skip API if cached.
  - `resolve_legs(date, direction, entry_price, width=2.0, snapshot=None) -> dict | None` — using the month snapshot (or `snapshot` if passed, for tests): `opt_type` = "call" if `direction=="long"` else "put"; pick nearest `exp >= date`; among that expiry+type's listed strikes pick `long_strike` = nearest to `entry_price`; `short_strike` = nearest listed strike to `long_strike + width` (call) or `long_strike - width` (put). Return `{"long_sym","short_sym","long_strike","short_strike","opt_type","kind":"debit_spread","width","expiry","date"}`, or `None` if unresolvable (no future expiry, or short==long).

- [ ] **Step 1: Write the failing self-test (append inside `__main__`, before the final print)**

```python
    # --- Task 2: resolve_legs on a mock definition snapshot (offline) ---
    snap = pd.DataFrame({
        "raw_symbol": ["LON4 C7500","LON4 C7600","LON4 C7700","LON4 C7800",
                       "LON4 P7500","LON4 P7400","LON4 P7300",
                       "LOQ4 C7600"],
        "instrument_class": ["C","C","C","C","P","P","P","C"],
        "strike_price": [75.0,76.0,77.0,78.0,75.0,74.0,73.0,76.0],
        "exp": ["2024-06-14"]*7 + ["2024-07-17"],
    })
    lg = resolve_legs("2024-06-03","long",76.2,width=2.0,snapshot=snap)
    assert lg["opt_type"]=="call" and lg["expiry"]=="2024-06-14", lg
    assert lg["long_strike"]==76.0 and lg["short_strike"]==78.0, lg   # ATM 76, +2 -> 78
    assert lg["long_sym"]=="LON4 C7600" and lg["short_sym"]=="LON4 C7800", lg
    sg = resolve_legs("2024-06-03","short",75.1,width=2.0,snapshot=snap)
    assert sg["opt_type"]=="put" and sg["long_strike"]==75.0 and sg["short_strike"]==73.0, sg  # 75, -2 ->73
    assert resolve_legs("2024-12-31","long",76.0,snapshot=snap) is None, "no future expiry -> None"
    print("Task 2 OK: resolve_legs (nearest expiry, ATM long, width short, dir-aware)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: FAIL — `NameError: name 'resolve_legs' is not defined`.

- [ ] **Step 3: Implement (add below `option_bbo_by_et`)**

```python
def definition_snapshot(year, month):
    """Cache+return the LO.OPT option universe for the first available day of year-month."""
    path = os.path.join(CACHE_DIR, f"CL_optdef_{year}-{month:02d}.csv")
    if os.path.exists(path):
        return pd.read_csv(path, dtype={"raw_symbol": str})
    start = f"{year}-{month:02d}-01"
    end_month = month % 12 + 1
    end_year = year + (1 if month == 12 else 0)
    end = f"{end_year}-{end_month:02d}-01"
    data = _client().timeseries.get_range(
        dataset="GLBX.MDP3", symbols=["LO.OPT"], stype_in="parent",
        schema="definition", start=start, end=end)
    df = data.to_df()
    df = df[df["instrument_class"].isin(["C","P"])].copy()
    df["exp"] = df["expiration"].astype(str).str[:10]
    # first available snapshot day only (definitions repeat daily; one snapshot is enough)
    first_day = df.index.min()
    df = df[df.index == first_day]
    out = df[["raw_symbol","instrument_class","strike_price","exp"]].reset_index(drop=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def _nearest(values, target):
    return min(values, key=lambda v: abs(v - target))


def resolve_legs(date, direction, entry_price, width=2.0, snapshot=None):
    if entry_price is None or entry_price <= 0:
        return None
    if snapshot is None:
        y, m = int(date[:4]), int(date[5:7])
        snapshot = definition_snapshot(y, m)
    ic = "C" if direction == "long" else "P"
    opt_type = "call" if direction == "long" else "put"
    df = snapshot[snapshot["instrument_class"] == ic]
    exps = sorted(e for e in df["exp"].unique() if e >= date)
    if not exps:
        return None
    exp = exps[0]
    strikes = sorted(df[df["exp"] == exp]["strike_price"].astype(float).unique())
    if not strikes:
        return None
    long_strike = _nearest(strikes, float(entry_price))
    short_target = long_strike + width if opt_type == "call" else long_strike - width
    short_strike = _nearest(strikes, short_target)
    if short_strike == long_strike:
        return None
    sub = df[df["exp"] == exp]
    def sym(strike):
        r = sub[abs(sub["strike_price"].astype(float) - strike) < 1e-6]
        return None if r.empty else str(r.iloc[0]["raw_symbol"])
    ls, ss = sym(long_strike), sym(short_strike)
    if ls is None or ss is None:
        return None
    return {"long_sym": ls, "short_sym": ss, "long_strike": long_strike,
            "short_strike": short_strike, "opt_type": opt_type, "kind": "debit_spread",
            "width": abs(short_strike - long_strike), "expiry": exp, "date": date}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: PASS — prints `Task 2 OK: resolve_legs ...`.

- [ ] **Step 5: Commit**

```bash
git add bot/load_cl_options_databento.py
git commit -m "feat(cl-opt): resolve_legs + cached LO definition snapshots"
```

---

### Task 3: Leg pull + cache + reader (real smoke pull)

**Files:**
- Modify: `bot/load_cl_options_databento.py`

**Interfaces:**
- Consumes: `option_bbo_by_et` (Task 1), `_client`/`_read_cache`/`_write_cache`/`CACHE_DIR` (import).
- Produces:
  - `pull_leg(symbol, date) -> str` — pull `bbo-1m` for one option `raw_symbol` over `[date, date+1)`, cache `data_cache/CLopt_<safe_symbol>_<date>.csv` (replace spaces in symbol with `_`), return path; skip API if cached.
  - `leg_bars(symbol, date) -> pd.DataFrame` — read the cached leg CSV → `option_bbo_by_et` → DataFrame[time,bid,ask] (empty DataFrame if the cache file is missing).

- [ ] **Step 1: Write the failing self-test (append inside `__main__`, before final print)**

```python
    # --- Task 3: leg cache round-trip on a mock bbo df (offline) ---
    import tempfile as _tf
    _d = _tf.mkdtemp()
    _p = os.path.join(_d, "CLopt_TEST_2024-06-03.csv")
    _write_cache(raw, _p)                       # 'raw' from Task 1 (bbo-1m shaped)
    _bars = option_bbo_by_et(_read_cache(_p))
    assert list(_bars.columns) == ["time","bid","ask"] and len(_bars) >= 2, _bars
    print("Task 3 OK: leg cache round-trip")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: FAIL (the assert references the round-trip; if `_write_cache`/`_read_cache` handle it this asserts logic, but the step is a guard — if it passes immediately, still proceed; the real new code is `pull_leg`/`leg_bars` below). If it passes, continue to Step 3 to add `pull_leg`/`leg_bars`.

- [ ] **Step 3: Implement (add below `resolve_legs`)**

```python
def _leg_path(symbol, date):
    safe = symbol.replace(" ", "_")
    return os.path.join(CACHE_DIR, f"CLopt_{safe}_{date}.csv")


def pull_leg(symbol, date):
    path = _leg_path(symbol, date)
    if os.path.exists(path):
        return path
    # date+1 for the [start,end) window
    d = pd.Timestamp(date) + pd.Timedelta(days=1)
    end = d.strftime("%Y-%m-%d")
    data = _client().timeseries.get_range(
        dataset="GLBX.MDP3", symbols=[symbol], stype_in="raw_symbol",
        schema="bbo-1m", start=date, end=end)
    _write_cache(data.to_df(), path)
    return path


def leg_bars(symbol, date):
    path = _leg_path(symbol, date)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["time","bid","ask"])
    return option_bbo_by_et(_read_cache(path))
```

- [ ] **Step 4: Run self-tests (offline)**

Run: `.venv/bin/python bot/load_cl_options_databento.py`
Expected: PASS — Task 1/2/3 OK lines.

- [ ] **Step 5: Real smoke — resolve + pull one signal's legs**

Run (from `bot/`):
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && "/Users/georgiemanavazian/Documents/Options trading/.venv/bin/python" -c "
from load_cl_options_databento import resolve_legs, pull_leg, leg_bars
lg = resolve_legs('2024-06-03','long',76.0)     # pulls the June-2024 definition snapshot
print('legs:', lg['long_sym'], '/', lg['short_sym'], 'exp', lg['expiry'])
pull_leg(lg['long_sym'],'2024-06-03'); pull_leg(lg['short_sym'],'2024-06-03')
lb = leg_bars(lg['long_sym'],'2024-06-03'); sb = leg_bars(lg['short_sym'],'2024-06-03')
print('long bars:', len(lb), 'short bars:', len(sb))
print(lb.head(2).to_string()); 
from acd_fade_pricing import spread_entry
d,t = spread_entry(lb, sb, '09:00'); print('debit at first fill:', round(d,3), 'at', t)
"
```
Expected: prints resolved leg symbols (a call and its +$2 call), non-empty bar counts for both legs, and a positive debit at ~09:00. Confirms the real definition→leg→NBBO→pricing chain works end to end.

- [ ] **Step 6: Commit**

```bash
git add bot/load_cl_options_databento.py
git commit -m "feat(cl-opt): pull_leg + leg_bars (bbo-1m), smoke-verified end-to-end pricing"
```

---

### Task 4: Phase-2 backtest driver (offline on mock, TDD)

**Files:**
- Create: `bot/backtest_cl_options.py`

**Interfaces:**
- Consumes: `build_cl_history` (`backtest_acd_cl`), `macro_context`/`apply_macro`/`BREAKOUT`/`FADES` (`acd_macro`), `spread_entry`/`close_value`/`exit_target_stop` (`acd_fade_pricing`), `resolve_legs`/`leg_bars` (`load_cl_options_databento`), `_ret_stats` (`backtest_acd_cl`), `CACHE_DIR` (`load_cl_databento`).
- Produces:
  - `collect_same_day(hist) -> list[Setup]` — iterate `hist`, run `macro_context`+`apply_macro`, return the full filtered micro `Setup` objects (they carry `date, direction, entry_time, entry_price, name, conviction`). Matches phase-1's same-day set; keeps `entry_time` (unlike `collect_signals`).
  - `price_signal(setup, width=2.0) -> dict | None` — resolve legs, read cached leg bars, `spread_entry` at `setup.entry_time`, build the intraday cost-to-close series, compute `close_val` (hold-to-close) and `active_val` (`exit_target_stop ±0.5`). Return `{"date","name","direction","debit","close_val","active_val"}` or `None` (unresolvable/degenerate).
  - `slip_ret(debit, exit_val, c) -> float` = `(exit_val - 2*c)/(debit + 2*c) - 1`.
  - `report(trades, exit_key)` — per-family/per-year/slippage report for one exit style, reusing `_ret_stats`.

- [ ] **Step 1: Write the module with an offline self-test**

```python
# backtest_cl_options.py — Phase-2: express phase-1 same-day crude signals as directional
# debit spreads on Databento NBBO; report hold-to-close vs active exit. Offline on cache.
# Run: .venv/bin/python bot/backtest_cl_options.py
import os
import statistics

from acd_macro import macro_context, apply_macro, BREAKOUT, FADES
from acd_fade_pricing import spread_entry, close_value, exit_target_stop
from load_cl_options_databento import resolve_legs, leg_bars
from load_cl_databento import CACHE_DIR
from backtest_acd_cl import build_cl_history, _ret_stats

START, END = "2010-06-06", "2026-06-29"


def collect_same_day(hist):
    out = []
    for i in range(len(hist)):
        ctx = macro_context(i, hist)
        out.extend(apply_macro(hist[i].day_result.setups, ctx))
    return out


def price_signal(setup, width=2.0):
    lg = resolve_legs(setup.date, setup.direction, setup.entry_price, width=width)
    if lg is None:
        return None
    lb = leg_bars(lg["long_sym"], setup.date)
    sb = leg_bars(lg["short_sym"], setup.date)
    if lb.empty or sb.empty:
        return None
    try:
        debit, entry_t = spread_entry(lb, sb, setup.entry_time)
    except ValueError:
        return None
    if debit <= 0:
        return None
    structure = {"kind": "debit_spread", "opt_type": lg["opt_type"],
                 "long_strike": lg["long_strike"], "width": lg["width"]}
    Ls = {str(r["time"]): r for _, r in lb.iterrows()}
    Ss = {str(r["time"]): r for _, r in sb.iterrows()}
    common = sorted(t for t in Ls if t in Ss and t >= entry_t)
    if not common:
        return None
    series = [(t, close_value(structure, Ls[t], Ss[t])) for t in common]
    close_val = series[-1][1]
    active_val = exit_target_stop(debit, series, close_val, 0.5, 0.5)
    return {"date": setup.date, "name": setup.name, "direction": setup.direction,
            "debit": debit, "close_val": close_val, "active_val": active_val}


def slip_ret(debit, exit_val, c):
    return (exit_val - 2 * c) / (debit + 2 * c) - 1.0


def report(trades, exit_key):
    if not trades:
        print(f"  ({exit_key}: no trades)"); return
    rets = [t[exit_key] / t["debit"] - 1.0 for t in trades]
    n, wr, tot, mdd, ra = _ret_stats(rets)
    sd = statistics.pstdev(rets); sharpe = statistics.mean(rets) / sd if sd > 0 else 0
    print(f"\n=== CL OPTIONS [{exit_key}] — {n} trades ===")
    print(f"@0 slip: win {wr:.0%}  total {tot:+.0%} on risk  maxDD {mdd:.0%}  "
          f"RISK-ADJ {ra:+.2f}  Sharpe {sharpe:+.2f}")
    for label, keys in [("BREAKOUTS", BREAKOUT), ("fades", FADES)]:
        sub = [t[exit_key]/t["debit"]-1.0 for t in trades if t["name"] in keys]
        if sub:
            w = sum(1 for r in sub if r > 0)
            print(f"    {label:<10} n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("  by year:")
    for yr in sorted({t["date"][:4] for t in trades}):
        sub = [t[exit_key]/t["debit"]-1.0 for t in trades if t["date"][:4] == yr]
        w = sum(1 for r in sub if r > 0)
        print(f"    {yr}  n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("  slippage sweep ($/leg/side):")
    for c in (0.0, 0.01, 0.02, 0.05):
        rr = [slip_ret(t["debit"], t[exit_key], c) for t in trades]
        n2, wr2, tot2, _, ra2 = _ret_stats(rr)
        print(f"    {c:.2f}:  win {wr2:.0%}  total {tot2:+.0%}  risk-adj {ra2:+.2f}")


if __name__ == "__main__":
    # offline self-test: slip_ret math + report on hand-built trades
    assert abs(slip_ret(1.0, 1.5, 0.0) - 0.5) < 1e-9
    assert slip_ret(1.0, 1.5, 0.05) < 0.5, "slippage lowers return"
    fake = [
        {"date":"2020-01-02","name":"a_held","direction":"long","debit":1.0,"close_val":1.4,"active_val":1.5},
        {"date":"2021-05-05","name":"failed_a","direction":"short","debit":1.0,"close_val":1.6,"active_val":1.5},
        {"date":"2021-06-06","name":"a_held","direction":"long","debit":1.0,"close_val":0.5,"active_val":0.5},
    ]
    report(fake, "close_val")
    report(fake, "active_val")
    print("Task 4 self-test OK: slip_ret + report")
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python bot/backtest_cl_options.py`
Expected: PASS — prints two report blocks and `Task 4 self-test OK: slip_ret + report`. (No real backtest yet — legs aren't pulled; that's Task 5/6.)

- [ ] **Step 3: Add the `run()` driver (insert before `if __name__`)**

```python
def run(width=2.0):
    mc = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
    dc = os.path.join(CACHE_DIR, f"CL_1d_{START}_{END}.csv")
    hist = build_cl_history(mc, dc)
    sigs = collect_same_day(hist)
    trades, dropped = [], 0
    for s in sigs:
        t = price_signal(s, width=width)
        if t is None:
            dropped += 1
            continue
        trades.append(t)
    print(f"CL options overlay: {len(trades)} trades ({dropped} dropped) from {len(sigs)} signals")
    report(trades, "close_val")
    report(trades, "active_val")
    return trades
```

And extend the `if __name__` block's END so it runs the real backtest when the futures cache exists AND at least one option leg is cached:

```python
    import glob
    if os.path.exists(os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")) and \
            glob.glob(os.path.join(CACHE_DIR, "CLopt_*.csv")):
        run()
```

- [ ] **Step 4: Run (self-test passes; real run skipped until legs pulled)**

Run: `.venv/bin/python bot/backtest_cl_options.py`
Expected: PASS — self-test prints; real run skipped (no `CLopt_*.csv` cached yet). No error.

- [ ] **Step 5: Commit**

```bash
git add bot/backtest_cl_options.py
git commit -m "feat(cl-opt): phase-2 driver — same-day debit spreads, hold-vs-active report"
```

---

### Task 5: Resumable leg-pull driver

**Files:**
- Create: `bot/pull_cl_options.py`

**Interfaces:**
- Consumes: `build_cl_history`/`START`/`END`-style paths, `collect_same_day` (`backtest_cl_options`), `resolve_legs`/`pull_leg` (`load_cl_options_databento`), `CACHE_DIR` (`load_cl_databento`).
- Produces: `main()` — for each same-day signal, resolve legs and pull both (skip cached), logging progress; a `.progress` sidecar of completed signal keys for resumability.

- [ ] **Step 1: Write the module**

```python
# pull_cl_options.py — resumable pull of the bbo-1m legs for every phase-2 same-day signal.
# Skips already-cached legs; records completed signal keys so a re-run resumes.
# Run: cd bot && ../.venv/bin/python pull_cl_options.py   (redirect to results/cl_opt_pull.log)
import os

from load_cl_databento import CACHE_DIR
from load_cl_options_databento import resolve_legs, pull_leg
from backtest_cl_options import collect_same_day, START, END
from backtest_acd_cl import build_cl_history

PROGRESS = os.path.join(CACHE_DIR, "CL_options_pull.progress")


def _done():
    return set(open(PROGRESS).read().split()) if os.path.exists(PROGRESS) else set()


def main():
    mc = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
    dc = os.path.join(CACHE_DIR, f"CL_1d_{START}_{END}.csv")
    sigs = collect_same_day(build_cl_history(mc, dc))
    print(f"{len(sigs)} same-day signals to pull legs for", flush=True)
    done = _done()
    for i, s in enumerate(sigs):
        key = f"{s.date}:{s.name}:{s.direction}:{i}"
        if key in done:
            continue
        lg = resolve_legs(s.date, s.direction, s.entry_price)
        if lg is not None:
            try:
                pull_leg(lg["long_sym"], s.date)
                pull_leg(lg["short_sym"], s.date)
            except Exception as e:
                print(f"  WARN {s.date} {s.name}: {type(e).__name__} {str(e)[:80]}", flush=True)
        with open(PROGRESS, "a") as f:
            f.write(key + "\n")
        if i % 100 == 0:
            print(f"  {i}/{len(sigs)} done", flush=True)
    print("DONE.", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Cost-check before any bulk pull**

Run (from `bot/`):
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && "/Users/georgiemanavazian/Documents/Options trading/.venv/bin/python" -c "
from backtest_cl_options import collect_same_day, START, END
from backtest_acd_cl import build_cl_history
from load_cl_databento import CACHE_DIR
import os
mc=os.path.join(CACHE_DIR,f'CL_1m_{START}_{END}.csv'); dc=os.path.join(CACHE_DIR,f'CL_1d_{START}_{END}.csv')
sigs=collect_same_day(build_cl_history(mc,dc))
print('signals:', len(sigs), '-> ~', len(sigs)*2, 'leg-days; est cost ~ \$', round(len(sigs)*2*0.0018,2))
"
```
Expected: prints the signal count (~2,500) and an estimated cost (~$9). Confirm it is comfortably within the remaining Databento credit before Step 3. (This step does NOT pull.)

- [ ] **Step 3: Commit the puller (do NOT run the full pull yet — that's Task 6)**

```bash
git add bot/pull_cl_options.py
git commit -m "feat(cl-opt): resumable leg-pull driver over same-day signals"
```

---

### Task 6: Full leg pull, real backtest, and grade

**Files:**
- Create: `results/backtest_cl_options_eval_2026-07-01.md`

- [ ] **Step 1: Run the full leg pull (background, ~$9 of credit)**

Run (from `bot/`), backgrounded, logging to `results/cl_opt_pull.log`:
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && "/Users/georgiemanavazian/Documents/Options trading/.venv/bin/python" pull_cl_options.py > ../results/cl_opt_pull.log 2>&1 &
```
Wait for `DONE.` in the log (a few minutes; it caches ~5,000 leg files, resumable if interrupted). Note any `WARN` lines (illiquid/missing legs) — they become drops, which is expected.

- [ ] **Step 2: Run the real backtest and capture output**

Run:
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && "/Users/georgiemanavazian/Documents/Options trading/.venv/bin/python" backtest_cl_options.py | tee ../results/backtest_cl_options_raw_2026-07-01.txt
```
Expected: the trade/drop counts and both `close_val` and `active_val` report blocks (per-family, per-year, slippage) over the full same-day signal set.

- [ ] **Step 3: Grade with `backtest-expert`**

Invoke the `backtest-expert` skill; feed it the metrics for BOTH exits (n, win, total-on-risk, maxDD, risk-adj, Sharpe, per-year, slippage sweep, and the BREAKOUTS vs fades split). Compute avg-win/avg-loss the same way phase-1 did (a small stats pass over the trades) so the grader inputs are real, not estimated. Ask for the same REFINE/DEPLOY lens used on prior slices.

- [ ] **Step 4: Write the eval**

Create `results/backtest_cl_options_eval_2026-07-01.md`: headline verdict (does the same-day edge survive as options-with-costs? which exit wins?), the per-family + per-year tables for the better exit, the slippage verdict, the drop rate (and what it implies about tradeability), the `backtest-expert` grade, and the caveats from spec §6 (NBBO fills, sparse option minutes/drops, same-day-close≠settlement, DTE varies, a-priori params). State the go/no-go for paper trading.

- [ ] **Step 5: Commit**

```bash
git add -f results/backtest_cl_options_eval_2026-07-01.md results/backtest_cl_options_raw_2026-07-01.txt
git commit -m "docs(cl-opt): phase-2 options backtest results + backtest-expert grade + eval"
```

- [ ] **Step 6: Whole-branch opus review before any merge**

Dispatch an opus reviewer over the full `acd-crude-options` branch diff. Focus: temporal integrity (entry uses only bars ≥ entry_time; exit uses same-day bars only), leg-resolution correctness (nearest expiry ≥ date, correct strikes/direction, symbol mapping), pricing math (debit = long.ask−short.bid; close = long.bid−short.ask; slippage model), drop handling, and eval honesty. Fix findings, re-run self-tests, then present merge options.

---

## Self-Review

**Spec coverage:**
- §2 same-day signals + debit spreads + nearest-expiry + two exits → Tasks 2 (resolve), 4 (collect_same_day, price_signal both exits). ✓
- §3 Databento data (definitions, bbo-1m, cheap, pull-by-symbol, cost-check) → Tasks 1–3, 5 (cost-check), 6 (pull). ✓
- §4 architecture / reuse / new files only → all tasks import; no shared edits. ✓ Collector keeps `entry_time` (the spec-noted fix) → Task 4 `collect_same_day`. ✓
- §5 data flow → Task 4 `price_signal` matches step-for-step. ✓
- §6 caveats, §7 success, §8 testing → Task 6 Step 4 + inline self-tests each task + Task 6 Step 6 review. ✓

**Placeholder scan:** no TBD/TODO; every code step has complete code; tests are concrete. Task 3 Step 2 notes the guard-test may pass immediately (honest, not a placeholder). ✓

**Type consistency:** `resolve_legs` returns the dict consumed by `price_signal`; `leg_bars`/`option_bbo_by_et` return DataFrame[time,bid,ask] consumed by `spread_entry`/`close_value` (verified against `acd_fade_pricing` signatures); structure dict keys (`kind`,`opt_type`,`long_strike`,`width`) match `close_value`/`expire_value`; `slip_ret(debit, exit_val, c)` consistent Tasks 4/report; `collect_same_day` used identically in Tasks 4/5. ✓

**Note:** `START`/`END` are defined in `backtest_cl_options.py` (Task 4) and imported by `pull_cl_options.py` (Task 5) — single source, no drift. `_ret_stats` reused from phase-1 (generic on a returns list).
