# ACD Bot — Plan 2: The Option Wrappers (`acd_wrappers.py`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three pluggable option "wrappers" that turn one ACD `Signal` (long/short) into an actual option position — `build_long_option`, `build_debit_spread`, `build_credit_spread` — so Plan 3 can race them on the identical signal.

**Architecture:** One new flat module `bot/acd_wrappers.py`. Each builder has the SAME signature `(signal, puts, calls, spot, expiration, **params)` and returns a uniform `position` dict (legs + entry economics + max_loss). It is the seam, mirroring `condor_rules.build_condor` / `orb_rules.build_orb`: the brain (Plan 1) and the data (Plan 3) are decoupled from how the trade is expressed. `puts`/`calls` are pandas DataFrames as produced by `load_ivolai.parse_chain` (columns include `strike`, `bid`, `ask`). Tested offline on a small mock chain via an inline `__main__` block (house convention — no pytest).

**Tech Stack:** Python 3.12 + pandas (chains are DataFrames), run inside `.venv`. Reuses `orb_rules.nearest`. Inline `assert` self-tests.

## Global Constraints

- Module lives in `bot/`, run as `.venv/bin/python bot/acd_wrappers.py` from the project root (bare `from orb_rules import nearest` resolves).
- Instrument = **SPX**; results reported as % return on capital-at-risk (account-independent — XSP for live trading is a separate sizing concern, not this layer's).
- `puts` / `calls` are DataFrames with at least columns `strike`, `bid`, `ask` (from `load_ivolai.parse_chain`, whose `COLUMN_MAP` already renames the raw feed). Real SPX strike spacing is $5; the mock test uses a $25 grid for compactness — code must be spacing-agnostic via `nearest`.
- Conservative fills: a **long** leg pays the **ask**, a **short** leg receives the **bid**.
- **Uniform position dict** every builder returns:
  ```
  {
    "wrapper":   "long_option" | "debit_spread" | "credit_spread",
    "direction": "long" | "short",
    "expiration": <str>,
    "legs": [ {"strike": float, "type": "call"|"put", "side": "long"|"short", "entry_price": float}, ... ],
    "entry_cost": float,   # net per-share: sum(long legs' ask) - sum(short legs' bid). debit>0, credit<0.
    "max_loss":  float,    # dollars per contract (×100)
    "width":     float,    # spread width in $ (0.0 for the single long option)
  }
  ```
- **Sizing fields parked in `config.ACDProfile`** (Plan 1): `debit_width=25.0`, `credit_short_otm=10.0`, `credit_width=25.0`. The harness passes these; the builders take them as params with those defaults.
- **P&L convention for Plan 3 (document, don't implement here):** `entry_cost` IS the net entry. At exit, `net_exit = sum(long legs' bid) - sum(short legs' ask)`, and `pnl = (net_exit - entry_cost) * 100`. This single formula is correct for all three wrappers (verified: a credit spread expiring worthless → net_exit≈0 → pnl ≈ -entry_cost×100 = +credit, as intended).
- Std-lib + pandas only. Scope = the three builders + one `_quote` helper. No P&L, no data fetching, no harness — those are Plan 3.

---

### Task 1: `_quote` helper + `build_long_option`

**Files:**
- Create: `bot/acd_wrappers.py`

**Interfaces:**
- Consumes: `orb_rules.nearest(strikes, target) -> float`.
- Produces:
  - `_quote(df, target) -> (strike, bid, ask)` — quote at the nearest available strike.
  - `build_long_option(signal, puts, calls, spot, expiration) -> position dict` (buy 1 ATM call if long, ATM put if short).

- [ ] **Step 1: Write the failing test**

Create `bot/acd_wrappers.py` with the header + `__main__` test only (no functions yet → fails):

```python
# acd_wrappers.py — the OPTION WRAPPERS: turn one ACD Signal (long/short) into an
# actual option position. Three structurally-distinct expressions raced on the
# IDENTICAL signal (Plan 3): long option / debit spread / credit spread. Same seam
# as condor_rules.build_condor / orb_rules.build_orb. See
# docs/superpowers/specs/2026-06-30-acd-bot-design.md.
#
# Run with:  .venv/bin/python bot/acd_wrappers.py

import pandas as pd

from orb_rules import nearest


def _mock_chain():
    """A tiny parsed-style chain (spot 5000, $25 grid) for offline tests."""
    calls = pd.DataFrame({"strike": [5000, 5025, 5050, 5075],
                          "bid": [120, 105, 91, 78], "ask": [122, 107, 93, 80]})
    puts = pd.DataFrame({"strike": [4925, 4950, 4975, 5000],
                         "bid": [85, 95, 106, 118], "ask": [87, 97, 108, 120]})
    return puts, calls, 5000.0, "2024-09-03"


if __name__ == "__main__":
    puts, calls, spot, exp = _mock_chain()

    p = build_long_option({"direction": "long"}, puts, calls, spot, exp)
    assert p["legs"] == [{"strike": 5000.0, "type": "call", "side": "long",
                          "entry_price": 122.0}], p["legs"]
    assert p["max_loss"] == 12200.0 and p["entry_cost"] == 122.0, p
    assert p["width"] == 0.0 and p["wrapper"] == "long_option", p

    ps = build_long_option({"direction": "short"}, puts, calls, spot, exp)
    assert ps["legs"][0]["type"] == "put" and ps["legs"][0]["entry_price"] == 120.0, ps
    print("Task 1 OK: build_long_option buys the ATM call/put at the ask")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `NameError: name 'build_long_option' is not defined`.

- [ ] **Step 3: Add the implementation** (above `_mock_chain`)

```python
def _quote(df, target):
    """(strike, bid, ask) at the nearest available strike to `target`."""
    k = nearest(sorted(df["strike"].unique()), target)
    row = df[df["strike"] == k].iloc[0]
    return float(k), float(row["bid"]), float(row["ask"])


def build_long_option(signal, puts, calls, spot, expiration):
    """Buy one ATM option in the signal's direction (call if long, put if short).

    Risk = full premium (defined); reward uncapped. Pays the ask.
    """
    d = signal["direction"]
    side, typ = (calls, "call") if d == "long" else (puts, "put")
    k, _bid, ask = _quote(side, spot)
    return {"wrapper": "long_option", "direction": d, "expiration": expiration,
            "legs": [{"strike": k, "type": typ, "side": "long", "entry_price": ask}],
            "entry_cost": ask, "max_loss": ask * 100, "width": 0.0}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `Task 1 OK: build_long_option buys the ATM call/put at the ask`.

- [ ] **Step 5: Commit**

```bash
git add bot/acd_wrappers.py
git commit -m "feat(acd): _quote helper + build_long_option wrapper"
```

---

### Task 2: `build_debit_spread`

Bull call spread (long) / bear put spread (short): long the ATM option, short one `width` further out in the signal direction. Cheaper than the naked long, capped reward, calmer theta.

**Files:**
- Modify: `bot/acd_wrappers.py`

**Interfaces:**
- Produces: `build_debit_spread(signal, puts, calls, spot, expiration, width=25.0) -> position dict`.

- [ ] **Step 1: Write the failing test** (append to `__main__`)

```python
    # --- Task 2: debit spread ---
    d = build_debit_spread({"direction": "long"}, puts, calls, spot, exp, width=25.0)
    assert d["legs"][0] == {"strike": 5000.0, "type": "call", "side": "long",
                            "entry_price": 122.0}, d
    assert d["legs"][1] == {"strike": 5025.0, "type": "call", "side": "short",
                            "entry_price": 105.0}, d
    assert abs(d["entry_cost"] - 17.0) < 1e-9 and d["max_loss"] == 1700.0, d
    assert d["width"] == 25.0 and d["wrapper"] == "debit_spread", d

    ds = build_debit_spread({"direction": "short"}, puts, calls, spot, exp, width=25.0)
    # bear put: long 5000 put (ask 120), short 4975 put (bid 106) -> net 14
    assert ds["legs"][1]["strike"] == 4975.0 and ds["max_loss"] == 1400.0, ds
    print("Task 2 OK: build_debit_spread nets the debit + max_loss (bull call / bear put)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `NameError: name 'build_debit_spread' is not defined`.

- [ ] **Step 3: Add the implementation**

```python
def build_debit_spread(signal, puts, calls, spot, expiration, width=25.0):
    """Directional debit spread: long ATM, short `width` further OUT in the
    signal direction. Bull call spread (long) / bear put spread (short).

    Risk = net debit (defined); reward capped at the width. Long pays ask,
    short receives bid.
    """
    d = signal["direction"]
    if d == "long":                              # bull call spread
        side, typ, short_target = calls, "call", None
        lk, _lb, lask = _quote(side, spot)
        sk, sbid, _sa = _quote(side, lk + width)
    else:                                        # bear put spread
        side, typ = puts, "put"
        lk, _lb, lask = _quote(side, spot)
        sk, sbid, _sa = _quote(side, lk - width)
    net_debit = lask - sbid
    return {"wrapper": "debit_spread", "direction": d, "expiration": expiration,
            "legs": [{"strike": lk, "type": typ, "side": "long", "entry_price": lask},
                     {"strike": sk, "type": typ, "side": "short", "entry_price": sbid}],
            "entry_cost": net_debit, "max_loss": net_debit * 100,
            "width": abs(sk - lk)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `Task 2 OK: build_debit_spread nets the debit + max_loss (bull call / bear put)`.

- [ ] **Step 5: Commit**

```bash
git add bot/acd_wrappers.py
git commit -m "feat(acd): build_debit_spread wrapper"
```

---

### Task 3: `build_credit_spread`

Sell a spread in the signal direction (put spread below if long, call spread above if short) — ORB-style. Theta tailwind, high win rate, lopsided risk.

**Files:**
- Modify: `bot/acd_wrappers.py`

**Interfaces:**
- Produces: `build_credit_spread(signal, puts, calls, spot, expiration, short_otm=10.0, width=25.0) -> position dict`.

- [ ] **Step 1: Write the failing test** (append to `__main__`)

```python
    # --- Task 3: credit spread (test grid: short_otm=25, width=25) ---
    c = build_credit_spread({"direction": "long"}, puts, calls, spot, exp,
                            short_otm=25.0, width=25.0)
    # long signal -> sell put spread BELOW: short 4975 put (bid 106), long 4950 put (ask 97)
    assert c["legs"][0] == {"strike": 4975.0, "type": "put", "side": "short",
                            "entry_price": 106.0}, c
    assert c["legs"][1] == {"strike": 4950.0, "type": "put", "side": "long",
                            "entry_price": 97.0}, c
    assert abs(c["entry_cost"] + 9.0) < 1e-9, c          # credit 9 -> entry_cost -9
    assert c["max_loss"] == 1600.0 and c["wrapper"] == "credit_spread", c  # (25-9)*100

    cs = build_credit_spread({"direction": "short"}, puts, calls, spot, exp,
                             short_otm=25.0, width=25.0)
    # short signal -> sell call spread ABOVE: short 5025 call (bid 105), long 5050 call (ask 93)
    assert cs["legs"][0]["strike"] == 5025.0 and cs["max_loss"] == 1300.0, cs  # (25-12)*100
    print("Task 3 OK: build_credit_spread nets the credit + max_loss (put below / call above)")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `NameError: name 'build_credit_spread' is not defined`.

- [ ] **Step 3: Add the implementation**

```python
def build_credit_spread(signal, puts, calls, spot, expiration,
                        short_otm=10.0, width=25.0):
    """Directional credit spread in the signal direction (ORB-style): sell a put
    spread BELOW (long) / a call spread ABOVE (short).

    short = `short_otm` out-of-the-money; long = `width` further out (the wing).
    Risk = width - credit (defined, lopsided); reward = credit. Short receives
    bid, long pays ask.
    """
    d = signal["direction"]
    if d == "long":                              # sell put spread below spot
        side, typ = puts, "put"
        sk, sbid, _sa = _quote(side, spot - short_otm)
        lk, _lb, lask = _quote(side, sk - width)
    else:                                        # sell call spread above spot
        side, typ = calls, "call"
        sk, sbid, _sa = _quote(side, spot + short_otm)
        lk, _lb, lask = _quote(side, sk + width)
    credit = sbid - lask
    real_width = abs(sk - lk)
    return {"wrapper": "credit_spread", "direction": d, "expiration": expiration,
            "legs": [{"strike": sk, "type": typ, "side": "short", "entry_price": sbid},
                     {"strike": lk, "type": typ, "side": "long", "entry_price": lask}],
            "entry_cost": -credit, "max_loss": (real_width - credit) * 100,
            "width": real_width}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python bot/acd_wrappers.py`
Expected: `Task 3 OK: build_credit_spread nets the credit + max_loss (put below / call above)`.

- [ ] **Step 5: Commit**

```bash
git add bot/acd_wrappers.py
git commit -m "feat(acd): build_credit_spread wrapper"
```

---

## Self-Review (wrappers)

- **Spec coverage:** all three design-spec wrappers (long option / debit spread / credit spread) — Tasks 1/2/3. Uniform position dict + `entry_cost`/`max_loss`/`width` per the Global Constraints. The deferred straddle is correctly absent.
- **Placeholder scan:** none — every step has full code + exact run command + expected output.
- **Type consistency:** `_quote` returns `(float, float, float)`; every builder returns the same dict shape with `entry_cost` = sum(long ask) − sum(short bid) (debit positive, credit negative), consumed identically by Plan 3's `pnl = (net_exit - entry_cost)*100`. `direction` flows from the Plan-1 `Signal` (`entry_spot`, not `entry_price`).

## Follow-on

- **Plan 3 — `backtest_acd.py` + dated-mark loader:** add a DTE-aware dated-chain fetch (the `inspect_dated_chain.fetch_dated_chain` pattern, cache name `SPX_<date>_dte30-45_m6.csv`), drive it from the 314 signal days, mark each held position daily, apply the entry-day B stop + 3-day pivot trailing exit + expiry, then report per-wrapper risk-adjusted return (total ÷ max drawdown), Sharpe, win rate, per-year breakdown, slippage sensitivity — graded via the `backtest-expert` skill. MUST `try/except` `opening_range` (raises on no-bars days → skip).
