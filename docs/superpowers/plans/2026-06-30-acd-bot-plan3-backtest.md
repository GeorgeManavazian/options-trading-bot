# ACD Bot — Plan 3: The Backtest Harness (`backtest_acd.py` + dated loader)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **PREREQUISITE:** the big pull (`bot/pull_acd_data.py`) must have finished — `data_cache/SPX_<date>_dte10-50_m10.csv` for the trading-day range. Tasks 1–5 build/test OFFLINE on mock data; only the final real run needs the pull complete.

**Goal:** Race the three wrappers on the identical ACD signal over 3 years and crown a winner by risk-adjusted return — marking each multi-day position day-by-day, exiting on the 3-day pivot trailing stop, and reporting per-wrapper risk-adjusted return / Sharpe / win-rate / per-year / slippage, then grading each via the `backtest-expert` skill.

**Architecture:** A new dated loader `bot/load_acd_dated.py` (reads the big-pull cache, picks the entry expiration, marks held legs with validation) and the harness `bot/backtest_acd.py` (signal → 3 wrappers → multi-day simulate → report). Reuses Plan 1 (`acd_rules`), Plan 2 (`acd_wrappers`), `run_acd_signal` (the 314-trade signal), `backtest_chains.report_chains`, and `config.ACDProfile`. Pure-logic units tested offline with mock chains/HLC.

**Tech Stack:** Python 3.12 + pandas, `.venv`, inline `__main__` self-tests (house convention).

## Global Constraints

- Files in `bot/`, bare sibling imports, run `.venv/bin/python bot/<file>.py`. Inline `assert` self-tests, no pytest.
- **Instrument SPX**; all P&L reported as **% return on capital-at-risk** (account-independent; XSP is the live-sizing concern, not here).
- **P&L formula (from Plan 2):** `entry_cost` = Σ(long ask) − Σ(short bid); at exit `net_exit` = Σ(long bid) − Σ(short ask); `pnl = (net_exit − entry_cost) * 100`.
- **Reviewer-mandated DATA-SEAM VALIDATION (entry conditions):** when reading any quote, **skip/raise on NaN or ≤0 bid/ask**; the entry-strike snap must be within ~½ the grid step of target and `short_strike ≠ long_strike`; clamp `max_loss = max(0, …)`. `try/except` `opening_range` (raises on no-bars days → skip the day).
- **v1 exit semantics (DECIDED — document, implement exactly):**
  - Mark and check exits **daily, on closes** (we have each day's dated chain + derived daily H/L/C).
  - Exit priority each held day, entry day onward: **(1) option expiry reached → exit at expiry; (2) 3-day rolling pivot trailing stop closes back through the band against the position → exit at that day's close; (3) entry-day B stop** — on the entry day, if the close is already beyond `stop_B` against the position → exit entry day. Else hold to the next day.
  - Mark the exit at that day's dated chain (`net_exit`). **If a held leg can't be marked on the exit day** (missing/NaN/zero quote) → carry the **most recent prior day's good mark**; if a position never gets a valid mark after entry → drop the trade and COUNT it (no silent loss).
  - Daily H/L/C derived from the cached intraday paths (same source as `run_acd_signal`) — approximate but offline and consistent.
- **Entry expiration:** the expiration in the day's dated chain whose DTE is nearest **35** (`ACDProfile`-tunable target within 30–45).
- Scope: the dated loader + simulator + harness + reporting. No new strategy logic; wrappers/signal are fixed.

---

### Task 1: `load_acd_dated.py` — dated-chain loader with validation

**Files:**
- Create: `bot/load_acd_dated.py`

**Interfaces:**
- Consumes: `load_ivolai.COLUMN_MAP`.
- Produces:
  - `dated_chain_df(symbol, date, dte_from=10, dte_to=50, moneyness=10) -> DataFrame` (renamed cols; raises `FileNotFoundError` if not pulled).
  - `pick_entry_chain(df, target_dte=35) -> (puts, calls, spot, expiration)` — cleaned (no NaN/≤0 quotes), expiration nearest `target_dte`.
  - `mark_legs(df, expiration, legs) -> float` — `net_exit` = Σ(long bid) − Σ(short ask), raising `ValueError` if any leg lacks a valid quote.

- [ ] **Step 1: Write the failing test**

Create `bot/load_acd_dated.py` with header + a mock-chain `__main__` test (no functions yet → fails):

```python
# load_acd_dated.py — read the big-pull dated chains (SPX_<date>_dte10-50_m10.csv),
# pick the entry expiration, and mark held legs — with the data-seam validation the
# reviews mandated (skip NaN/<=0 quotes; raise rather than emit a garbage position).
#
# Run with:  .venv/bin/python bot/load_acd_dated.py

import os

import pandas as pd

from load_ivolai import COLUMN_MAP

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")


def _mock_df():
    """Two expirations (dte 33 & 40), $5 grid, IVol column shape — offline."""
    rows = []
    for exp, dte in [("2024-09-03", 33), ("2024-09-10", 40)]:
        for k in [4990, 4995, 5000, 5005, 5010]:
            for cp in ("C", "P"):
                rows.append({"c_date": "2024-08-01", "expiration_date": exp, "dte": dte,
                             "price_strike": float(k), "call_put": cp,
                             "Bid": 20.0, "Ask": 21.0, "iv": 0.16,
                             "underlying_price": 5000.0})
    return pd.DataFrame(rows).rename(columns=COLUMN_MAP)


if __name__ == "__main__":
    df = _mock_df()
    puts, calls, spot, exp = pick_entry_chain(df, target_dte=35)
    assert exp == "2024-09-03", exp                 # dte 33 is nearest 35
    assert spot == 5000.0 and len(calls) == 5, (spot, len(calls))

    legs = [{"strike": 5000.0, "type": "call", "side": "long", "entry_price": 21.0},
            {"strike": 5005.0, "type": "call", "side": "short", "entry_price": 20.0}]
    net_exit = mark_legs(df, exp, legs)             # long bid 20 - short ask 21 = -1
    assert net_exit == -1.0, net_exit
    print("Task 1 OK: pick_entry_chain + mark_legs (with validation)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/load_acd_dated.py`
Expected: `NameError: name 'pick_entry_chain' is not defined`.

- [ ] **Step 3: Add the implementation** (above `_mock_df`)

```python
_PUT = ["P", "put", "Put"]
_CALL = ["C", "call", "Call"]


def dated_chain_df(symbol, date, dte_from=10, dte_to=50, moneyness=10):
    """Read one day's cached dated chain (the big pull), columns renamed."""
    path = os.path.join(
        CACHE_DIR, f"{symbol}_{date}_dte{dte_from}-{dte_to}_m{moneyness}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return pd.read_csv(path).rename(columns=COLUMN_MAP)


def _valid(side):
    """Rows with a real two-sided quote (no NaN, bid & ask > 0)."""
    side = side.dropna(subset=["strike", "bid", "ask"])
    return side[(side["bid"] > 0) & (side["ask"] > 0)]


def pick_entry_chain(df, target_dte=35):
    """(puts, calls, spot, expiration) for the expiration nearest target_dte."""
    dtes = df.groupby("expiration")["dte"].first()
    expiration = (dtes - target_dte).abs().idxmin()
    chain = df[df["expiration"] == expiration]
    puts = _valid(chain[chain["type"].isin(_PUT)]).copy()
    calls = _valid(chain[chain["type"].isin(_CALL)]).copy()
    spot = float(chain["spot"].iloc[0])
    return puts, calls, spot, expiration


def mark_legs(df, expiration, legs):
    """net_exit = sum(long bid) - sum(short ask) at `expiration`. Conservative close.

    Raises ValueError if any leg has no valid (non-NaN, >0) quote that day.
    """
    chain = df[df["expiration"] == expiration]
    net = 0.0
    for leg in legs:
        types = _CALL if leg["type"] == "call" else _PUT
        row = chain[(chain["type"].isin(types)) & (chain["strike"] == leg["strike"])]
        if row.empty:
            raise ValueError(f"no row for {leg['type']} {leg['strike']} @ {expiration}")
        bid, ask = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
        if not (bid > 0 and ask > 0):
            raise ValueError(f"no quote for {leg['type']} {leg['strike']} @ {expiration}")
        net += bid if leg["side"] == "long" else -ask
    return net
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/load_acd_dated.py`
Expected: `Task 1 OK: pick_entry_chain + mark_legs (with validation)`.

- [ ] **Step 5: Commit**

```bash
git add bot/load_acd_dated.py
git commit -m "feat(acd): dated-chain loader (entry pick + leg marking with validation)"
```

---

### Task 2: expose signals + daily H/L/C from `run_acd_signal.py`

The harness needs the trade Signals and the per-day H/L/C. Refactor the existing loop in `run_acd_signal.py` into reusable functions (no behavior change to its `__main__` summary).

**Files:**
- Modify: `bot/run_acd_signal.py`

**Interfaces:**
- Produces:
  - `daily_hlc() -> dict[str, (H, L, C)]` — approx daily H/L/C per cached day.
  - `trade_signals(a_pct=0.0018) -> list[dict]` — Signals (date + direction long/short + entry_spot + stop_B + pivot_band) for the days the brain trades (flats excluded).

- [ ] **Step 1: Write the failing test** (append to `run_acd_signal.py` `__main__`, before `run()` is called — or add a guarded self-check)

```python
    # --- Task 2 (Plan 3): reusable signal + HLC accessors ---
    hlc = daily_hlc()
    assert isinstance(hlc, dict) and len(hlc) > 700, len(hlc)
    sigs = trade_signals()
    assert all(s["direction"] in ("long", "short") for s in sigs), "trades only"
    assert 250 <= len(sigs) <= 380, len(sigs)        # ~314 expected
    print(f"Task 2 OK: {len(sigs)} trade signals, {len(hlc)} daily HLC")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/run_acd_signal.py`
Expected: `NameError: name 'daily_hlc' is not defined`.

- [ ] **Step 3: Refactor** — extract `daily_hlc()` and `trade_signals()` from the existing `run()` loop (reuse `cached_days`, `day_path`, `hlc_from_path`, `build_acd_signal`); keep `run()` printing its summary by calling them.

```python
def daily_hlc():
    """{date -> (H, L, C)} from each cached full-day path."""
    out = {}
    for D in cached_days():
        try:
            out[D] = hlc_from_path(day_path(D))
        except Exception:
            continue
    return out


def trade_signals(a_pct=0.0018):
    """Trade-day Signals (flats excluded), pivot from the prior day's H/L/C."""
    days = cached_days()
    out, prev_hlc = [], None
    for D in days:
        try:
            path = day_path(D)
        except Exception:
            prev_hlc = None
            continue
        if prev_hlc is not None:
            try:
                sig = build_acd_signal(path, prev_hlc, a_pct=a_pct)
                if sig["direction"] != "flat":
                    out.append({"date": D, **sig})
            except Exception:
                pass
        prev_hlc = hlc_from_path(path)
    return out
```

- [ ] **Step 4: Run to verify it passes** (Task 2 line prints; the existing offline run summary still prints when invoked normally)

Run: `.venv/bin/python bot/run_acd_signal.py`
Expected: `Task 2 OK: ~314 trade signals, ~748 daily HLC` and the normal summary unaffected.

- [ ] **Step 5: Commit**

```bash
git add bot/run_acd_signal.py
git commit -m "feat(acd): expose trade_signals + daily_hlc for the backtest harness"
```

---

### Task 3: `simulate_hold` — the multi-day exit simulator

The core: walk a position forward from entry, exit on expiry / 3-day pivot trailing stop / entry-day B, mark at exit (carrying the last good mark on a marking gap).

**Files:**
- Create: `bot/backtest_acd.py`

**Interfaces:**
- Consumes: `acd_rules.rolling_3day_pivot`, `acd_rules.pivot_trailing_exit`.
- Produces:
  - `simulate_hold(direction, position, expiration, entry_date, day_list, hlc, mark_fn) -> (pnl, exit_date, reason)`
    where `mark_fn(date, expiration, legs) -> net_exit | None` (None = no mark that day), `day_list` = sorted trading days, `hlc` = {date:(H,L,C)}.

- [ ] **Step 1: Write the failing test**

Create `bot/backtest_acd.py` with header + this `__main__` test (functions absent → fails):

```python
# backtest_acd.py — race the 3 wrappers on the identical ACD signal over 3 yrs.
# Per trade: entry-day dated chain -> build all 3 wrappers -> simulate the multi-day
# hold (3-day pivot trailing stop / expiry / entry-day B) -> P&L. Report per wrapper:
# risk-adjusted return (total / max drawdown), Sharpe, win rate, per-year, slippage.
#
# Run with:  .venv/bin/python bot/backtest_acd.py
#   (offline self-test by default; set IVOL_API_KEY + RUN_REAL=1 for the real 3yr run)

from acd_rules import rolling_3day_pivot, pivot_trailing_exit


if __name__ == "__main__":
    # A long position; pivot band sits below entry; a later day closes back through it.
    pos = {"legs": [{"strike": 5000.0, "type": "call", "side": "long", "entry_price": 20.0}],
           "entry_cost": 20.0, "max_loss": 2000.0}
    days = ["2024-08-01", "2024-08-02", "2024-08-05", "2024-08-06"]
    hlc = {"2024-08-01": (5005, 4995, 5000), "2024-08-02": (5010, 5000, 5008),
           "2024-08-05": (5012, 5002, 5009), "2024-08-06": (5006, 4980, 4985)}
    # mark_fn: option worth 25 (in the money) on the exit day.
    marks = {"2024-08-06": 25.0}
    mark_fn = lambda d, e, legs: marks.get(d)

    pnl, xd, reason = simulate_hold("long", pos, "2024-09-03", "2024-08-01",
                                    days, hlc, mark_fn)
    # exits 2024-08-06 when close 4985 drops through the rising pivot band; pnl=(25-20)*100
    assert reason == "pivot_stop" and xd == "2024-08-06", (reason, xd)
    assert pnl == 500.0, pnl
    print("Task 3 OK: simulate_hold exits on the 3-day pivot trailing stop")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/backtest_acd.py`
Expected: `NameError: name 'simulate_hold' is not defined`.

- [ ] **Step 3: Add the implementation**

```python
def simulate_hold(direction, position, expiration, entry_date, day_list, hlc, mark_fn):
    """Walk the position forward from entry_date. Exit on (1) expiry, (2) 3-day pivot
    trailing stop closing back through the band, or (3) entry-day B is folded in by the
    caller via the signal's stop_B check before calling. Returns (pnl, exit_date, reason).

    mark_fn(date, expiration, legs) -> net_exit or None. On a None (marking gap) we carry
    the most recent good mark; a trade that never marks returns (None, None, "no_mark").
    """
    entry_cost = position["entry_cost"]
    legs = position["legs"]
    held = [d for d in day_list if entry_date < d <= expiration]

    # trailing window of (H,L,C) up to and including the entry day
    recent = [hlc[d] for d in day_list if d <= entry_date and d in hlc][-3:]
    last_mark = mark_fn(entry_date, expiration, legs)     # entry-day mark (may be None)

    def _pnl(net_exit):
        return round((net_exit - entry_cost) * 100, 2)

    for d in held:
        m = mark_fn(d, expiration, legs)
        if m is not None:
            last_mark = m
        if d >= expiration:                              # (1) expiry
            return (_pnl(last_mark) if last_mark is not None else None,
                    d, "expiry" if last_mark is not None else "no_mark")
        if d in hlc:
            band = rolling_3day_pivot(recent) if recent else None
            if band and pivot_trailing_exit(direction, hlc[d][2], band):  # (2) pivot stop
                return (_pnl(last_mark) if last_mark is not None else None,
                        d, "pivot_stop" if last_mark is not None else "no_mark")
            recent = (recent + [hlc[d]])[-3:]

    # held to the last available day -> mark there
    return (_pnl(last_mark) if last_mark is not None else None,
            held[-1] if held else entry_date,
            "end" if last_mark is not None else "no_mark")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/backtest_acd.py`
Expected: `Task 3 OK: simulate_hold exits on the 3-day pivot trailing stop`.

- [ ] **Step 5: Commit**

```bash
git add bot/backtest_acd.py
git commit -m "feat(acd): simulate_hold multi-day exit simulator"
```

---

### Task 4: `run_acd_backtest` — the harness tying it together

**Files:**
- Modify: `bot/backtest_acd.py`

**Interfaces:**
- Consumes: `acd_wrappers.build_long_option/build_debit_spread/build_credit_spread`, `load_acd_dated.dated_chain_df/pick_entry_chain/mark_legs`, `run_acd_signal.trade_signals/daily_hlc`, `config.ACDProfile`, `acd_rules.pivot_bias`.
- Produces: `run_acd_backtest(profile=None) -> dict[wrapper_name -> list[trade dict]]`, each trade dict shaped for `report_chains` (`date, spot, settle, credit, max_loss, pnl, ret_pct`) plus `direction, wrapper, exit_date, reason`.

- [ ] **Step 1: Write a small offline test** using a stub: monkeypatch the three loaders to return a tiny mock chain + 2-day window, assert it produces one trade per wrapper with a numeric `ret_pct`. (Full code provided at implementation time, mirroring `backtest_orb._fake_days`'s offline style — it constructs 1 mock signal, 1 mock dated chain, builds the 3 wrappers, runs `simulate_hold` with a mock `mark_fn`, and asserts `len(result["credit_spread"]) == 1` and `-1 <= ret_pct`.)

- [ ] **Step 2–4: Implement + verify** the loop:
  - `signals = trade_signals(profile.a_pct)`, `hlc = daily_hlc()`, `days = sorted(hlc)`.
  - For each signal: `df = dated_chain_df("SPX", date)` (skip day on `FileNotFoundError`); `puts, calls, spot, exp = pick_entry_chain(df, target_dte=...)`; build the 3 wrappers (try/except per wrapper → skip on validation error); for each, `mark_fn = lambda d, e, legs: _safe_mark(d, e, legs)` where `_safe_mark` loads that day's `dated_chain_df` and calls `mark_legs`, returning `None` on any error; `pnl, xd, reason = simulate_hold(...)`; if `pnl is None` count a drop, else append a trade dict with `ret_pct = pnl / max_loss`.
  - Return `{wrapper: [trades]}`.

- [ ] **Step 5: Commit**

```bash
git add bot/backtest_acd.py
git commit -m "feat(acd): run_acd_backtest harness racing the 3 wrappers"
```

---

### Task 5: per-wrapper reporting + the real run

**Files:**
- Modify: `bot/backtest_acd.py`

**Interfaces:**
- Produces: `report_wrappers(results)` — for each wrapper, print `report_chains` (win rate / total / max drawdown) plus **risk-adjusted = total_return ÷ |max_drawdown|**, a Sharpe-like ratio (mean/std of per-trade `ret_pct`), per-year breakdown (reuse `backtest_chains.yearly_report`), and a slippage note. Then `__main__` runs offline by default; with `RUN_REAL=1` + key, runs the real 3-yr race, saves per-wrapper CSVs to `results/`, and prints the comparison.

- [ ] Implement `report_wrappers`, reusing `backtest_chains.report_chains` and `yearly_report` per wrapper; compute `risk_adj = total / abs(max_dd)` and `sharpe = mean(rets)/pstdev(rets)`. Commit.
- [ ] **Real run (needs the pull complete):** `RUN_REAL=1 .venv/bin/python bot/backtest_acd.py` → saves `results/acd_<wrapper>.csv` and prints the three-way risk-adjusted comparison.
- [ ] **Grade:** feed each wrapper's metrics (win rate, drawdown, trades, years, total) to the **`backtest-expert`** skill for the robustness/overfitting verdict; record which wrapper wins on risk-adjusted return AND survives the grading.

---

## Self-Review

- **Spec coverage:** dated loader + validation (T1), signal/HLC reuse (T2), multi-day exit simulator (T3), the 3-wrapper race harness (T4), risk-adjusted reporting + real run + grading (T5). All six reviewer entry-conditions are bound in Global Constraints and realized in T1 (validation), T3 (exit semantics + mark-carry), T4 (skip-on-FileNotFound, per-wrapper try/except).
- **Open at execution (validate against the real pull, not fabricated now):** Tasks 4–5 give full structure with offline tests; the exact mark-gap frequency and any expiration-coverage surprises get confirmed once `pull_acd_data.py` finishes — the `_safe_mark` carry-last-good + drop-and-count design already handles gaps without crashing.

## Done = the answer

When this runs, we get the thing this whole bot was built to answer: **which option wrapper, on the identical ACD signal, delivers the best risk-adjusted return over 3 years** — long option vs debit spread vs credit spread — with an honest robustness grade on top.
