# ACD on Crude Oil (CL) — Phase 1 Signal Backtest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the full, already-built ACD signal engine on crude-oil futures (CL) and measure — honestly, per-family and per-year — whether it has a directional edge on a *trending* instrument, especially the breakout half that stayed flat on SPX.

**Architecture:** Reuse the instrument-agnostic engine (`acd_micro.build_day`, `acd_macro.macro_context`/`apply_macro`) **unchanged**. All crude code is new files: a Databento loader (`load_cl_databento.py`), a CL `InstrumentSpec` (`acd_cl.py`), and a phase-1 backtest driver (`backtest_acd_cl.py`) that mirrors the SPX checkpoint (`diag_full_signal.py`) plus an underlying P&L + slippage report. V5/SPX files are never touched.

**Tech Stack:** Python 3.12 in `.venv`; `databento` (0.80.0, installed); `pandas`; std-lib only otherwise. Data = Databento CME `GLBX.MDP3`, symbol `CL.c.0`, `stype_in="continuous"`, schemas `ohlcv-1m` + `ohlcv-1d`.

## Global Constraints

- **Isolation (hard):** never edit `acd_micro.py`, `acd_macro.py`, or any V5/SPX file. Reuse by import only. A crude-specific rule change means a forked CL-only copy, not a shared edit.
- **House testing style:** inline `if __name__ == "__main__":` assert self-tests in each module (NO pytest). Run with `.venv/bin/python bot/<file>.py`. Commit only when self-tests print OK.
- **Conventions:** flat `bot/` modules, bare sibling imports (e.g. `from acd_micro import build_day`), cache CSVs under `data_cache/`, results under `results/`.
- **Offline-after-pull:** the backtest must run with zero network once data is cached (like `load_ivolai`/`diag_full_signal`). Only the pull functions touch the API.
- **Secrets:** read `DATABENTO_API_KEY` from `.env` (already stored, gitignored). Never hardcode or print the key.
- **Data facts (confirmed live):** `CL.c.0` 1-min available 2010-06-06→present; index is tz-aware UTC `ts_event`; columns `open,high,low,close,volume,instrument_id,symbol`; full-history pull ≈ $20, inside the $125 free credit.
- **Point value:** CL = $1000 per 1.00 point; tick = $0.01 ($10/contract).
- **Reused constants:** `acd_macro.BREAKOUT`, `acd_macro.FADES` (import; do not redefine).

---

### Task 1: CL data transforms (pure, offline, TDD)

The network-free core of the loader: convert a raw Databento-shaped DataFrame into the exact structures the engine consumes. Tested on mock DataFrames including a DST boundary — no API.

**Files:**
- Create: `bot/load_cl_databento.py`

**Interfaces:**
- Consumes: nothing (pure pandas).
- Produces:
  - `bars_by_et_day(df, session_open="09:00", session_close="16:00") -> dict[str, list[tuple[str, float]]]` — `{ "YYYY-MM-DD": [("HH:MM", close_price), ...] }`, times in America/New_York, only bars with `session_open <= HH:MM <= session_close`, sorted. Price used = the bar `close`.
  - `daily_hlc_from_df(df) -> dict[str, tuple[float, float, float]]` — `{ "YYYY-MM-DD": (High, Low, Close) }` from a daily DataFrame (one row per ET day).
  - `roll_days_from_df(df) -> set[str]` — ET dates where `instrument_id` differs from the prior ET day's (contract roll → pivot from a different contract; the driver skips these).

- [ ] **Step 1: Write the failing self-test block**

Append to `bot/load_cl_databento.py`:

```python
if __name__ == "__main__":
    import pandas as pd

    # mock 1-min bars across a DST boundary: 2024-03-10 is US spring-forward.
    # 14:00 UTC = 10:00 EDT (after DST) ; 14:00 UTC on 2024-01-10 = 09:00 EST.
    idx = pd.to_datetime([
        "2024-01-10 14:00:00", "2024-01-10 14:01:00", "2024-01-10 20:59:00",  # EST: 09:00,09:01,15:59
        "2024-03-11 13:00:00", "2024-03-11 13:01:00",                          # EDT: 09:00,09:01
    ], utc=True)
    m = pd.DataFrame({"open":[1,2,3,4,5], "high":[1,2,3,4,5], "low":[1,2,3,4,5],
                      "close":[10.0,11.0,12.0,13.0,14.0], "instrument_id":[1,1,1,2,2]}, index=idx)
    m.index.name = "ts_event"

    bd = bars_by_et_day(m, "09:00", "16:00")
    assert set(bd) == {"2024-01-10", "2024-03-11"}, bd
    assert bd["2024-01-10"] == [("09:00",10.0),("09:01",11.0),("15:59",12.0)], bd["2024-01-10"]
    assert bd["2024-03-11"] == [("09:00",13.0),("09:01",14.0)], bd["2024-03-11"]
    print("Task 1a OK: bars_by_et_day (DST-aware, RTH-windowed)")

    # daily HLC + roll detection
    didx = pd.to_datetime(["2024-01-10","2024-01-11","2024-01-12"], utc=True)
    d = pd.DataFrame({"open":[70,71,72], "high":[75.0,76.0,77.0], "low":[69.0,70.0,71.0],
                      "close":[74.0,75.0,76.0], "instrument_id":[1,1,2]}, index=didx)
    d.index.name = "ts_event"
    hlc = daily_hlc_from_df(d)
    assert hlc["2024-01-11"] == (76.0,70.0,75.0), hlc
    assert roll_days_from_df(d) == {"2024-01-12"}, roll_days_from_df(d)
    print("Task 1b OK: daily_hlc_from_df + roll_days_from_df")
    print("ALL Task 1 self-tests passed")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_cl_databento.py`
Expected: FAIL — `NameError: name 'bars_by_et_day' is not defined`.

- [ ] **Step 3: Write the transforms (top of file, above the self-tests)**

```python
# load_cl_databento.py — pull + cache CL crude-oil futures from Databento (CME GLBX.MDP3)
# and reshape into what the ACD engine consumes. Pure transforms are network-free and
# self-tested; pull functions (Task 2) touch the API and cache to data_cache/.
#
# Auth: DATABENTO_API_KEY in .env.  Run: .venv/bin/python bot/load_cl_databento.py
import os
import glob

import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")
ET = "America/New_York"


def bars_by_et_day(df, session_open="09:00", session_close="16:00"):
    """Raw Databento 1-min df (tz-aware UTC index) -> {date: [(HH:MM, close), ...]} in ET,
    filtered to the RTH window and sorted by time."""
    if df.empty:
        return {}
    et = df.tz_convert(ET) if df.index.tz is not None else df.tz_localize("UTC").tz_convert(ET)
    out = {}
    for ts, close in zip(et.index, et["close"]):
        hhmm = ts.strftime("%H:%M")
        if session_open <= hhmm <= session_close:
            out.setdefault(ts.strftime("%Y-%m-%d"), []).append((hhmm, float(close)))
    for d in out:
        out[d].sort()
    return out


def daily_hlc_from_df(df):
    """Daily Databento df -> {date: (High, Low, Close)} (ET calendar date)."""
    et = df.tz_convert(ET) if df.index.tz is not None else df.tz_localize("UTC").tz_convert(ET)
    out = {}
    for ts, hi, lo, cl in zip(et.index, et["high"], et["low"], et["close"]):
        out[ts.strftime("%Y-%m-%d")] = (float(hi), float(lo), float(cl))
    return out


def roll_days_from_df(df):
    """ET dates whose instrument_id differs from the prior ET day's (contract roll)."""
    et = df.tz_convert(ET) if df.index.tz is not None else df.tz_localize("UTC").tz_convert(ET)
    days = {}
    for ts, iid in zip(et.index, et["instrument_id"]):
        days[ts.strftime("%Y-%m-%d")] = int(iid)
    ordered = sorted(days)
    return {ordered[k] for k in range(1, len(ordered)) if days[ordered[k]] != days[ordered[k-1]]}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/load_cl_databento.py`
Expected: PASS — prints `ALL Task 1 self-tests passed`.

- [ ] **Step 5: Commit**

```bash
git add bot/load_cl_databento.py
git commit -m "feat(cl): Databento->ACD data transforms (DST-aware bars, daily HLC, roll days)"
```

---

### Task 2: CL pull + cache + offline readers (real smoke pull)

Add the API-facing pull + cache, and the offline readers the backtest calls. Verified with a tiny real 5-day pull (well within credit).

**Files:**
- Modify: `bot/load_cl_databento.py`

**Interfaces:**
- Consumes: `bars_by_et_day`, `daily_hlc_from_df`, `roll_days_from_df` (Task 1).
- Produces:
  - `pull_cl_minutes(start, end) -> str` — pull `ohlcv-1m` for `CL.c.0` over `[start, end)` (dates `YYYY-MM-DD`), cache to `data_cache/CL_1m_<start>_<end>.csv`, return the path. Skip the API if the file exists.
  - `pull_cl_daily(start, end) -> str` — same for `ohlcv-1d` → `data_cache/CL_1d_<start>_<end>.csv`.
  - `_read_cache(path) -> pd.DataFrame` — read a cached CSV back into a tz-aware-UTC-indexed df.
  - `cl_day_path(date, min_csv) -> list[tuple[str,float]]` — the ET RTH path for one day from a cached 1-min CSV.
  - `cl_daily_hlc(daily_csv) -> dict` and `cl_roll_days(daily_csv) -> set` — from a cached daily CSV.

- [ ] **Step 1: Write the failing self-test (append to the `__main__` block)**

Append after the Task 1 asserts:

```python
    # --- Task 2: round-trip a mock df through the CSV cache helpers ---
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "CL_1d_x.csv")
    _write_cache(d, p)
    back = _read_cache(p)
    assert daily_hlc_from_df(back)["2024-01-11"] == (76.0,70.0,75.0), "cache round-trip HLC"
    assert cl_roll_days(p) == {"2024-01-12"}, "cache round-trip rolls"
    print("Task 2 OK: cache write/read round-trip")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_cl_databento.py`
Expected: FAIL — `NameError: name '_write_cache' is not defined`.

- [ ] **Step 3: Implement pull + cache + readers**

Add below the transforms:

```python
def _client():
    key = ""
    env = os.path.join(os.path.dirname(__file__), "..", ".env")
    for line in open(env):
        if line.startswith("DATABENTO_API_KEY"):
            key = line.strip().split("=", 1)[1].strip()
    import databento as db
    return db.Historical(key)


def _write_cache(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path)                       # ts_event index (UTC ISO) + columns


def _read_cache(path):
    df = pd.read_csv(path, index_col="ts_event", parse_dates=["ts_event"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def _pull(schema, start, end, tag):
    path = os.path.join(CACHE_DIR, f"CL_{tag}_{start}_{end}.csv")
    if os.path.exists(path):
        return path
    data = _client().timeseries.get_range(
        dataset="GLBX.MDP3", symbols=["CL.c.0"], stype_in="continuous",
        schema=schema, start=start, end=end)
    _write_cache(data.to_df(), path)
    return path


def pull_cl_minutes(start, end):
    return _pull("ohlcv-1m", start, end, "1m")


def pull_cl_daily(start, end):
    return _pull("ohlcv-1d", start, end, "1d")


def cl_day_path(date, min_csv):
    return bars_by_et_day(_read_cache(min_csv)).get(date, [])


def cl_daily_hlc(daily_csv):
    return daily_hlc_from_df(_read_cache(daily_csv))


def cl_roll_days(daily_csv):
    return roll_days_from_df(_read_cache(daily_csv))
```

- [ ] **Step 4: Run self-tests (offline)**

Run: `.venv/bin/python bot/load_cl_databento.py`
Expected: PASS — prints `Task 2 OK: cache write/read round-trip`.

- [ ] **Step 5: Real smoke pull (5 days) + verify shape**

Run:
```bash
.venv/bin/python -c "
from bot.load_cl_databento import pull_cl_daily, pull_cl_minutes, cl_day_path, cl_daily_hlc
import sys; sys.path.insert(0,'bot')
" 2>/dev/null || cd bot && .venv/bin/python -c "
from load_cl_databento import pull_cl_daily, pull_cl_minutes, cl_day_path, cl_daily_hlc, cl_roll_days
dp = pull_cl_daily('2024-06-03','2024-06-08'); mp = pull_cl_minutes('2024-06-03','2024-06-08')
print('daily cache:', dp); print('min cache:', mp)
hlc = cl_daily_hlc(dp); print('daily HLC keys:', sorted(hlc)[:3], '...', 'sample:', hlc.get('2024-06-03'))
path = cl_day_path('2024-06-03', mp); print('06-03 path len:', len(path), 'first/last:', path[0], path[-1])
print('rolls:', cl_roll_days(dp))
"
```
Expected: prints two cache paths (files now in `data_cache/`), a daily HLC sample tuple, a non-empty 06-03 path whose first bar time is `09:00` (ET) and last ≤ `16:00`, and a (likely empty) roll set. Confirms real columns/timezone match Task 1's assumptions.

- [ ] **Step 6: Commit**

```bash
git add bot/load_cl_databento.py
git commit -m "feat(cl): Databento pull+cache and offline readers (smoke-verified on 5 real days)"
```

---

### Task 3: CL InstrumentSpec + loader→engine seam smoke

Define crude's `InstrumentSpec` and prove one real cached crude day flows through the *unmodified* engine to a `DayResult`.

**Files:**
- Create: `bot/acd_cl.py`

**Interfaces:**
- Consumes: `InstrumentSpec` (`acd_micro`), `build_day` (`acd_micro`), `cl_day_path`/`cl_daily_hlc`/`pull_cl_*` (`load_cl_databento`).
- Produces: `CL` (an `InstrumentSpec` instance).

- [ ] **Step 1: Write the file with inline self-test**

```python
# acd_cl.py — crude-oil InstrumentSpec + a smoke test that the UNMODIFIED ACD engine
# (acd_micro.build_day) runs on a real cached crude day. Isolated from SPX/V5.
# Run: .venv/bin/python bot/acd_cl.py
from acd_micro import InstrumentSpec, build_day

# Crude RTH open 09:00 ET (confirmed). A/C anchored as % of the OR midpoint; crude is more
# volatile than SPX (SPX=0.18%/0.21%) so start wider — TUNE via the Task 6 sweep, don't trust
# a single value. tick=$0.01. cutoff/late_day in ET.
CL = InstrumentSpec(
    symbol="CL",
    session_open="09:00",
    or_minutes=15,
    a_pct=0.0025,
    c_pct=0.0030,
    hold_fraction=0.5,
    cutoff="12:00",
    tick=0.01,
    late_day="14:30",
)

if __name__ == "__main__":
    assert CL.symbol == "CL" and CL.session_open == "09:00" and CL.tick == 0.01
    assert 0 < CL.a_pct < CL.c_pct < 0.02, "sane crude A/C anchors"
    print("acd_cl spec OK:", CL)

    # loader -> unmodified engine seam on one real cached day (needs Task 2's smoke pull cached)
    from load_cl_databento import pull_cl_daily, pull_cl_minutes, cl_day_path, cl_daily_hlc
    dp = pull_cl_daily("2024-06-03", "2024-06-08")
    mp = pull_cl_minutes("2024-06-03", "2024-06-08")
    hlc = cl_daily_hlc(dp)
    days = sorted(hlc)
    D = days[1]                                  # a day with a prior day for the pivot
    dr = build_day(D, cl_day_path(D, mp), hlc[days[0]], CL)
    assert dr.date == D and dr.or_high >= dr.or_low, dr
    print(f"seam OK: build_day({D}) -> OR[{dr.or_low},{dr.or_high}] "
          f"events={len(dr.events)} setups={[s.name for s in dr.setups]}")
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python bot/acd_cl.py`
Expected: PASS — prints `acd_cl spec OK` and a `seam OK` line with a real OR and setup list. (If it fails on missing cache, re-run Task 2 Step 5 first.)

- [ ] **Step 3: Commit**

```bash
git add bot/acd_cl.py
git commit -m "feat(cl): crude InstrumentSpec + loader->engine seam smoke test"
```

---

### Task 4: Phase-1 forward-return edge diagnostic

The crude analogue of the SPX checkpoint: run the full engine over cached crude history and print the per-family forward-return edge tables. Reuse the checkpoint's generic helpers.

**Files:**
- Create: `bot/backtest_acd_cl.py`

**Interfaces:**
- Consumes: `build_day`/`CL`, `DayEntry`/`macro_context`/`apply_macro`, `BREAKOUT`/`FADES` (`acd_macro`), `collect_signals`/`_edge` (`diag_full_signal`), `cl_day_path`/`cl_daily_hlc`/`cl_roll_days`/`pull_cl_*` (`load_cl_databento`).
- Produces: `build_cl_history(min_csv, daily_csv) -> list[DayEntry]` (skips roll days for the pivot); `run()`.

- [ ] **Step 1: Write the module with an inline self-test on mock history**

```python
# backtest_acd_cl.py — Phase-1 CL signal backtest: run the FULL ACD engine on crude and
# measure the directional edge per family + per year (no options). Offline on cache.
# Run: .venv/bin/python bot/backtest_acd_cl.py
import os
import statistics
from collections import Counter

from acd_micro import build_day
from acd_macro import DayEntry, macro_context, apply_macro, BREAKOUT, FADES
from diag_full_signal import collect_signals, _edge
from acd_cl import CL
from load_cl_databento import (pull_cl_minutes, pull_cl_daily,
                               cl_day_path, cl_daily_hlc, cl_roll_days)

START, END = "2010-06-06", "2026-06-29"


def build_cl_history(min_csv, daily_csv):
    """Ordered DayEntry stream for the full engine. Skips contract-roll days (their pivot
    would come from a different contract) so a roll gap can't fabricate a signal."""
    hlc = cl_daily_hlc(daily_csv)
    rolls = cl_roll_days(daily_csv)
    days = [d for d in sorted(hlc) if d not in rolls]
    hist = []
    for idx, D in enumerate(days):
        prior = hlc[days[idx - 1]] if idx > 0 else hlc[D]
        path = cl_day_path(D, min_csv)
        if not path:
            continue
        try:
            dr = build_day(D, path, prior, CL)
        except Exception:
            continue
        hist.append(DayEntry(D, hlc[D], dr))
    return hist


if __name__ == "__main__":
    # self-test: build_cl_history is robust to empty/roll days on a mock cache (offline).
    import pandas as pd, tempfile
    from load_cl_databento import _write_cache
    dd = tempfile.mkdtemp()
    didx = pd.to_datetime(["2024-01-10","2024-01-11","2024-01-12"], utc=True)
    dfd = pd.DataFrame({"open":[70,71,72],"high":[75.,76.,77.],"low":[69.,70.,71.],
                        "close":[74.,75.,76.],"instrument_id":[1,1,2]}, index=didx); dfd.index.name="ts_event"
    midx = pd.to_datetime(["2024-01-10 14:00","2024-01-10 14:20","2024-01-11 14:00","2024-01-11 14:20"], utc=True)
    dfm = pd.DataFrame({"open":[70]*4,"high":[70]*4,"low":[70]*4,"close":[74.,74.5,75.,75.5],
                        "instrument_id":[1,1,1,1]}, index=midx); dfm.index.name="ts_event"
    dcsv=os.path.join(dd,"d.csv"); mcsv=os.path.join(dd,"m.csv"); _write_cache(dfd,dcsv); _write_cache(dfm,mcsv)
    h = build_cl_history(mcsv, dcsv)
    assert all(e.date != "2024-01-12" for e in h), "roll day excluded"
    print(f"Task 4 self-test OK: build_cl_history skipped roll day, {len(h)} entries")
```

- [ ] **Step 2: Run to verify the self-test passes**

Run: `.venv/bin/python bot/backtest_acd_cl.py`
Expected: PASS — prints `Task 4 self-test OK ...`.

- [ ] **Step 3: Add the `run()` diagnostic (forward-return edge, per family)**

Insert before the `if __name__` block:

```python
def run(min_csv, daily_csv):
    hist = build_cl_history(min_csv, daily_csv)
    dates = [e.date for e in hist]
    idx = {d: i for i, d in enumerate(dates)}
    closes = {e.date: e.ohlc[2] for e in hist}
    print(f"Full ACD engine over {len(hist)} CL days ({dates[0]} -> {dates[-1]})")

    micro, macro = collect_signals(hist)
    print(f"\nMICRO signals: {len(micro)}  by name: {dict(Counter(s[3] for s in micro))}")
    print(f"MACRO signals: {len(macro)}  by name: {dict(Counter(s[3] for s in macro))}")

    _edge(micro, dates, idx, closes, "FILTERED MICRO (all)")
    _edge([s for s in micro if s[3] in FADES], dates, idx, closes, "MICRO fades")
    _edge([s for s in micro if s[3] in BREAKOUT], dates, idx, closes, "MICRO BREAKOUTS (the CL test)")
    _edge([s for s in micro if s[4] >= 3], dates, idx, closes, "MICRO high-conviction (>=3)")
    _edge(macro, dates, idx, closes, "MACRO (reversal/trt/sushi)")
    return hist, micro, macro
```

And replace the `if __name__` body's *end* so that, when the real cache exists, it also runs the diagnostic:

```python
    # if the full-history cache is present, run the real diagnostic too
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data_cache",
                                   f"CL_1d_{START}_{END}.csv")):
        dc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1d_{START}_{END}.csv")
        mc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1m_{START}_{END}.csv")
        run(mc, dc)
```

- [ ] **Step 4: Run (self-test still passes; real diagnostic skipped until Task 6 pull)**

Run: `.venv/bin/python bot/backtest_acd_cl.py`
Expected: PASS — Task 4 self-test line prints; the real diagnostic block is skipped (no full cache yet). No error.

- [ ] **Step 5: Commit**

```bash
git add bot/backtest_acd_cl.py
git commit -m "feat(cl): phase-1 forward-return edge diagnostic (full engine on crude)"
```

---

### Task 5: Underlying P&L + stats + slippage + per-year (TDD on mock trades)

Add the tradeable-P&L layer: turn signals into per-trade directional returns, and report win rate / total / maxDD / risk-adj / Sharpe / per-year, with a tick-based slippage sweep — matching the metric shape of `backtest_acd_full` so crude is comparable to the SPX slices.

**Files:**
- Modify: `bot/backtest_acd_cl.py`
- Reuse: `max_drawdown` (`backtest`)

**Interfaces:**
- Consumes: `max_drawdown` (`backtest`), `POINT_VALUE`.
- Produces:
  - `POINT_VALUE = 1000.0`
  - `pnl_trades(sigs, dates, idx, closes, hold, tick=0.01) -> list[dict]` — one dict per trade with keys `date, name, direction, entry, exit, ret` (directional % return `(exit/entry-1)*sign`) and `usd` (`(exit-entry)*sign*POINT_VALUE`). Skips trades without a valid `+hold` close.
  - `_ret_stats(rets) -> (n, winrate, total, mdd, risk_adj)`
  - `slip_ret(t, ticks) -> float` — `t["ret"]` haircut by `2*ticks*tick/entry` (round-trip).
  - `report_pnl(trades, tick=0.01)` — overall + per-family + per-year + slippage sweep (0/1/2/5 ticks).

- [ ] **Step 1: Write failing self-tests (append inside `__main__`, after Task 4's)**

```python
    # --- Task 5: P&L + stats on hand-built trades ---
    fake = [
        {"date":"2020-01-02","name":"a_held","direction":"long","entry":100.0,"exit":102.0,
         "ret":0.02,"usd":2000.0},
        {"date":"2021-05-05","name":"failed_a","direction":"short","entry":50.0,"exit":49.0,
         "ret":0.02,"usd":1000.0},
        {"date":"2021-06-06","name":"a_held","direction":"long","entry":80.0,"exit":76.0,
         "ret":-0.05,"usd":-4000.0},
    ]
    n, wr, tot, mdd, ra = _ret_stats([t["ret"] for t in fake])
    assert n == 3 and abs(tot - (-0.01)) < 1e-9, (n, tot)
    assert abs(wr - 2/3) < 1e-9, wr
    # slippage haircut reduces a positive return
    assert slip_ret(fake[0], 1) < fake[0]["ret"], "slippage lowers return"
    print("Task 5 OK: _ret_stats + slip_ret")
    report_pnl(fake)                      # smoke: prints per-family + per-year + sweep without error
    print("ALL backtest_acd_cl self-tests passed")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/backtest_acd_cl.py`
Expected: FAIL — `NameError: name '_ret_stats' is not defined`.

- [ ] **Step 3: Implement the P&L layer**

Add imports at the top: `from itertools import accumulate` and `from backtest import max_drawdown`. Then add:

```python
POINT_VALUE = 1000.0        # CL: $1000 per 1.00 point


def pnl_trades(sigs, dates, idx, closes, hold, tick=0.01):
    out = []
    for date, direction, entry, name, conv in sigs:
        i = idx.get(date)
        if i is None or i + hold >= len(dates) or entry <= 0:
            continue
        exit_px = closes[dates[i + hold]]
        if exit_px <= 0:
            continue
        sign = 1.0 if direction == "long" else -1.0
        out.append({"date": date, "name": name, "direction": direction,
                    "entry": entry, "exit": exit_px,
                    "ret": (exit_px / entry - 1.0) * sign,
                    "usd": (exit_px - entry) * sign * POINT_VALUE})
    return out


def slip_ret(t, ticks):
    return t["ret"] - 2 * ticks * t.get("tick", 0.01) / t["entry"]


def _ret_stats(rets):
    n = len(rets)
    if not n:
        return 0, 0.0, 0.0, 0.0, 0.0
    wins = sum(1 for r in rets if r > 0)
    total = sum(rets)
    mdd = max_drawdown(list(accumulate(rets)))
    ra = total / abs(mdd) if mdd else (float("inf") if total > 0 else 0.0)
    return n, wins / n, total, mdd, ra


def report_pnl(trades, tick=0.01):
    if not trades:
        print("  (no trades)"); return
    rets = [t["ret"] for t in trades]
    n, wr, tot, mdd, ra = _ret_stats(rets)
    sd = statistics.pstdev(rets)
    sharpe = statistics.mean(rets) / sd if sd > 0 else 0
    usd = sum(t["usd"] for t in trades)
    print(f"\n=== CL P&L — {n} trades ===")
    print(f"@0 slip: win {wr:.0%}  total {tot:+.0%} on entry  ${usd:+,.0f}/1-contract  "
          f"maxDD {mdd:.0%}  RISK-ADJ {ra:+.2f}  Sharpe {sharpe:+.2f}")
    print("by family:")
    for label, keys in [("BREAKOUTS", BREAKOUT), ("fades", FADES)]:
        sub = [t["ret"] for t in trades if t["name"] in keys]
        if sub:
            w = sum(1 for r in sub if r > 0)
            print(f"    {label:<10} n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("by year:")
    for yr in sorted({t["date"][:4] for t in trades}):
        sub = [t["ret"] for t in trades if t["date"][:4] == yr]
        w = sum(1 for r in sub if r > 0)
        print(f"    {yr}  n={len(sub):>4}  win {w/len(sub):.0%}  total {sum(sub):+.0%}")
    print("slippage sweep (ticks/side):")
    for ticks in (0, 1, 2, 5):
        rr = [slip_ret(t, ticks) for t in trades]
        n2, wr2, tot2, _, ra2 = _ret_stats(rr)
        print(f"  {ticks}t:  win {wr2:.0%}  total {tot2:+.0%}  risk-adj {ra2:+.2f}")
```

- [ ] **Step 4: Wire P&L into `run()`** — add at the end of `run()` before `return`:

```python
    for hold, tag in [(0, "same-day"), (1, "+1d"), (5, "+5d")]:
        print(f"\n########## HOLD {tag} ##########")
        report_pnl(pnl_trades(micro, dates, idx, closes, hold))
```

- [ ] **Step 5: Run to verify all self-tests pass**

Run: `.venv/bin/python bot/backtest_acd_cl.py`
Expected: PASS — prints `Task 5 OK ...`, a smoke `report_pnl` block, and `ALL backtest_acd_cl self-tests passed`.

- [ ] **Step 6: Commit**

```bash
git add bot/backtest_acd_cl.py
git commit -m "feat(cl): underlying P&L + per-family/per-year stats + slippage sweep"
```

---

### Task 6: Full-history pull, real backtest, and `backtest-expert` grade

Pull the full 16 years, run the real diagnostic + P&L, then grade it honestly and write the eval.

**Files:**
- Create: `results/backtest_cl_eval_2026-07-01.md`

**Interfaces:** consumes everything above.

- [ ] **Step 1: Pull the full history (background, ~$20 of free credit)**

Run:
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && .venv/bin/python -c "
from load_cl_databento import pull_cl_daily, pull_cl_minutes
print('daily:', pull_cl_daily('2010-06-06','2026-06-29'))
print('minutes:', pull_cl_minutes('2010-06-06','2026-06-29'))
print('DONE')
"
```
Expected: prints two cache paths under `data_cache/` and `DONE`. (1-min over 16 yrs is large; if it errors on size, split into yearly ranges and concatenate — note any split in the eval.)

- [ ] **Step 2: Run the real backtest and capture output**

Run:
```bash
cd "/Users/georgiemanavazian/Documents/Options trading/bot" && .venv/bin/python backtest_acd_cl.py | tee ../results/backtest_cl_raw_2026-07-01.txt
```
Expected: the signal counts, per-family forward-return edge tables, and the P&L/slippage/per-year blocks for holds same-day/+1d/+5d — over the full CL history.

- [ ] **Step 3: Grade with the `backtest-expert` skill**

Invoke the `backtest-expert` skill; feed it the metrics from Step 2 (n, win rate, total-on-entry, maxDD, risk-adj, Sharpe, per-year, slippage sweep, and — decisively — the **breakout-family** numbers vs SPX's flat breakouts). Ask for the same REFINE/DEPLOY lens used on prior slices.

- [ ] **Step 4: Write the eval**

Create `results/backtest_cl_eval_2026-07-01.md` with: the headline verdict (does the full ACD method — and specifically breakouts — have a directional edge on trending crude?), the per-family + per-year table, the slippage verdict, the `backtest-expert` grade, and the honesty caveats from spec §6 (signal≠options P&L; raw continuous roll artifacts; A/C tuning params owed a walk-forward; 2020 negative-price event). State the phase-2 go/no-go recommendation.

- [ ] **Step 5: Commit**

```bash
git add results/backtest_cl_eval_2026-07-01.md results/backtest_cl_raw_2026-07-01.txt
git commit -m "docs(cl): phase-1 crude backtest results + backtest-expert grade + eval"
```

- [ ] **Step 6: Whole-branch opus review before any merge**

Dispatch an opus reviewer over the full `acd-crude-oil-bot` branch diff (has caught a real bug every prior sub-project). Fix findings, re-run all module self-tests, then present merge options.

---

## Self-Review

**Spec coverage:**
- §2 isolation → Global Constraints + reuse-by-import in every task; no shared edits. ✓
- §3 data (Databento, TZ, continuous, cache, offline) → Tasks 1–2 (transforms, pull, cache, DST, roll days). ✓ (Adjusted spec's "ratio-adjusted" to reality: Databento `CL.c.0` is raw continuous → roll-day skipping instead. Noted in Task 4 + eval caveats.)
- §4 CL InstrumentSpec → Task 3. ✓
- §5 phase-1 backtest (full engine, family split, holds, P&L, slippage, per-year, grade) → Tasks 4–6. ✓
- §6 caveats → Task 6 Step 4. §7 success criteria → Task 6. §8 testing → inline self-tests each task + Task 6 Step 6 review. ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code; test code is concrete. ✓

**Type consistency:** `bars_by_et_day`/`daily_hlc_from_df`/`roll_days_from_df` used identically in Tasks 2/4; `cl_day_path(date, min_csv)` signature consistent Tasks 2/3/4; `pnl_trades`/`_ret_stats`/`slip_ret`/`report_pnl` names consistent Tasks 5. `_edge`/`collect_signals` imported with the same signatures they have in `diag_full_signal.py`. ✓

**Note:** the spec said ratio-adjusted continuous; Databento's `CL.c.0` is raw continuous (confirmed), so the plan skips roll-boundary days instead — a faithful, honest substitute that avoids fabricated adjustment. Flagged for the eval.
