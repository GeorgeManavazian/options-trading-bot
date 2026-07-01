# V5 Paper Trading — Part 1 (Offline Real-Time Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline core of the V5 paper trader — a real-time signal engine + a paper executor/ledger that never submits orders — proven equivalent to the backtest by replaying cached days, and an audit that quantifies the one known live-vs-backtest divergence.

**Architecture:** `RealtimeEngine` re-runs the no-lookahead `build_day` on bars-so-far each minute and emits newly fired V5 fades (macro layer not needed: it never drops fades and V5's flat sizing ignores conviction). `PaperExecutor` simulates the V5 debit-spread trade off a pluggable `quote_source` (cache-backed in replay, Schwab later) and writes a ledger. A full-history replay audit proves the engine never misses a backtest fade and prices the extras the backtest retroactively suppressed (the `held-A-later` drop rule — unknowable live).

**Tech Stack:** Python 3.12 in `.venv`, pandas (cache reads only), stdlib. House style: flat `bot/` modules, bare sibling imports, run `.venv/bin/python bot/<file>.py`, inline `__main__` assert self-tests (NO pytest), frequent commits.

## Global Constraints

- Run every file as `.venv/bin/python bot/<file>.py`. NO pytest — self-tests in `if __name__ == "__main__":` printing `OK`/`passed`.
- **V5 config (fixed):** fade names `("failed_a", "failed_a_pivot")` (excludes `failed_c`); 0DTE debit spread (long ATM, short ±25 in the fade direction, $5 grid); active exit `target=0.5, stop=0.5` of debit; settle at the close if neither fires.
- **Fill conventions (match the backtest):** entry debit = `long.ask − short.bid` at the first bar `time ≥ entry_time`; close value = `long.bid − short.ask`; expiry intrinsic via `acd_fade_pricing.expire_value`.
- **Paper sizing:** 3% of CURRENT equity per trade, compounding, starting equity $10,000. **Fractional contracts allowed in paper mode** (3% of $10k = $300 < one SPX spread's ~$700 risk; the paper trader measures strategy fidelity, not lot rounding — the XSP-vs-SPX lot decision belongs to Part 2 and is noted in the ledger header).
- **Safety (hard rule):** `PaperExecutor` must contain NO broker/order code — no `schwab`, `requests`, `httpx`, `urllib` imports, no order-submission method. A self-test greps its own source to enforce this.
- Outputs go to `results/spx/` (`paper_ledger.csv`, `paper_account.json`, `replay_audit_2026-07-01.md`).
- Everything OFFLINE on the existing cache; no network, no API key. Never run git-history rewrites (book PDF in gitignored `research/`).
- Known ground truth for self-tests (from `results/spx/v5_trade_ledger.md` row 1): on 2023-07-12, V5's first trade = `failed_a` **long**, signal 11:42, bull call spread 4465/4490, debit $7.00, hit +50% target at 12:50, P&L per contract **+$395.00** (== `price_cell(...)["pnl0_ts"]`).

---

### Task 1: `realtime_v5.py` — the real-time V5 signal engine

**Files:**
- Create: `bot/realtime_v5.py`

**Interfaces:**
- Consumes: `build_day`, `SPX` (acd_micro); in the self-test: `daily_hlc`, `day_path` (run_acd_signal).
- Produces: `V5_NAMES = ("failed_a", "failed_a_pivot")`; class `RealtimeEngine(date, prior_hlc, spec=SPX, names=V5_NAMES)` with `on_bar((time, price)) -> list[Setup]` (newly fired fades, each returned exactly once, keyed by `(name, direction, entry_time)`).

- [ ] **Step 1: Write the module WITH its `__main__` self-test.**

```python
# realtime_v5.py — the REAL-TIME V5 signal engine. Feeds bars-so-far to the no-lookahead
# build_day each minute and emits newly fired V5 fades (failed_a / failed_a_pivot).
# The macro layer is NOT needed at runtime: apply_macro never drops fades and only bumps
# conviction, which V5's flat sizing ignores. Live-equivalent to the backtest by
# construction; the replay audit (replay_audit.py) proves it over the full cache.
# Offline. Run: .venv/bin/python bot/realtime_v5.py
from acd_micro import build_day, SPX

V5_NAMES = ("failed_a", "failed_a_pivot")


class RealtimeEngine:
    """Accumulates one day's (time, price) bars; on_bar returns fades newly fired at
    that bar. A setup fires once (dedup key = (name, direction, entry_time))."""

    def __init__(self, date, prior_hlc, spec=SPX, names=V5_NAMES):
        self.date, self.prior_hlc, self.spec = date, prior_hlc, spec
        self.names = tuple(names)
        self.bars = []
        self._fired = set()

    def on_bar(self, bar):
        self.bars.append((str(bar[0]), float(bar[1])))
        try:
            dr = build_day(self.date, self.bars, self.prior_hlc, self.spec)
        except ValueError:              # opening range not formable yet (first bars)
            return []
        new = []
        for s in dr.setups:
            if s.name not in self.names:
                continue
            key = (s.name, s.direction, s.entry_time)
            if key not in self._fired:
                self._fired.add(key)
                new.append(s)
        return new


if __name__ == "__main__":
    from run_acd_signal import daily_hlc, day_path

    hlc = daily_hlc()
    days = sorted(hlc)
    D = "2023-07-12"                               # V5 trade #1 lives on this day
    prior = hlc[days[days.index(D) - 1]]
    bars = sorted(day_path(D))

    eng = RealtimeEngine(D, prior)
    fired, fire_bar = [], {}
    for b in bars:
        for s in eng.on_bar(b):
            fired.append(s)
            fire_bar[(s.name, s.direction, s.entry_time)] = str(b[0])

    keys = {(s.name, s.direction, s.entry_time) for s in fired}
    assert ("failed_a", "long", "11:42") in keys, keys       # the known ledger row-1 signal
    assert fire_bar[("failed_a", "long", "11:42")] == "11:42", fire_bar  # fires AT its bar
    assert len(fired) == len(keys), "a setup fired twice"    # dedup
    # full-day equivalence on this day: every backtest fade must have fired intraday
    full = {(s.name, s.direction, s.entry_time)
            for s in build_day(D, bars, prior, SPX).setups if s.name in V5_NAMES}
    assert full <= keys, ("realtime MISSED backtest fades", full - keys)
    print(f"OK RealtimeEngine: {len(keys)} fade(s) fired on {D}, "
          f"failed_a/long/11:42 fired at its own bar, full-day set ⊆ fired set")
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python bot/realtime_v5.py`
Expected: `OK RealtimeEngine: ... failed_a/long/11:42 fired at its own bar, full-day set ⊆ fired set` (first run builds from cache; the replay itself takes seconds). If the `fires AT its bar` assert fails, STOP and report BLOCKED with the actual fire bar — that would mean fade detection lags its entry_time, which changes live fill assumptions and must be surfaced, not patched.

- [ ] **Step 3: Commit.**

```bash
git add bot/realtime_v5.py
git commit -m "feat(paper): RealtimeEngine — bar-by-bar V5 fade engine, replay-verified on the known first trade"
```

---

### Task 2: `paper_executor.py` — the paper trader + ledger

**Files:**
- Create: `bot/paper_executor.py`

**Interfaces:**
- Consumes: `_strikes` (acd_fade_signals), `expire_value` (acd_fade_pricing); in tests: `load_cached_minutes` (load_ivol_intraday), `grid_cells` (acd_fade_signals), `price_cell` (backtest_acd_fades), `daily_hlc` (run_acd_signal), `Setup` (acd_micro).
- Produces:
  - `cached_quote_source(sym, date) -> fn(strike, opt_type, time) -> (bid, ask) | None` — quote at the first cached bar `≥ time` (replay adapter; Part 2 swaps in Schwab).
  - `PaperExecutor(quote_source, equity=10_000.0, risk_pct=0.03, width=25.0, target=0.5, stop=0.5, ledger_path=..., state_path=...)` with `on_signal(date, setup)`, `on_bar(time)`, `on_close(date, settle_px)`.

- [ ] **Step 1: Write the module WITH its `__main__` self-tests.**

```python
# paper_executor.py — the PAPER trader: simulates V5 fills/exits off a pluggable
# quote_source and writes results/spx/paper_ledger.csv + paper_account.json.
# SAFETY: this class has NO broker connection and NO order-submission path — it only
# reads quotes and writes files. Sizing: 3% of CURRENT equity, compounding; fractional
# contracts in paper mode (lot rounding / XSP-vs-SPX is a Part-2 decision).
# Offline. Run: .venv/bin/python bot/paper_executor.py
import csv
import json
import os

from acd_fade_signals import _strikes
from acd_fade_pricing import expire_value

LEDGER = "results/spx/paper_ledger.csv"
STATE = "results/spx/paper_account.json"
COLS = ["date", "signal_time", "setup", "direction", "structure", "long_strike",
        "short_strike", "contracts", "debit_paid", "max_loss_$", "exit_reason",
        "exit_time", "exit_value", "pnl_$", "equity_after", "mode"]


def cached_quote_source(sym, date):
    """Replay adapter: quotes from the cached minute bars (first bar >= time)."""
    from load_ivol_intraday import load_cached_minutes
    cache = {}

    def quote(strike, opt_type, time):
        key = (float(strike), opt_type)
        if key not in cache:
            df = load_cached_minutes(sym, date, date, strike, opt_type)
            cache[key] = (None if df is None or df.empty else
                          sorted((str(r["time"]), float(r["bid"]), float(r["ask"]))
                                 for _, r in df.iterrows()))
        rows = cache[key]
        if not rows:
            return None
        later = [r for r in rows if r[0] >= str(time)]
        return (later[0][1], later[0][2]) if later else None

    return quote


class PaperExecutor:
    def __init__(self, quote_source, equity=10_000.0, risk_pct=0.03, width=25.0,
                 target=0.5, stop=0.5, ledger_path=LEDGER, state_path=STATE):
        self.q, self.equity, self.risk_pct = quote_source, float(equity), risk_pct
        self.width, self.target, self.stop = width, target, stop
        self.ledger_path, self.state_path = ledger_path, state_path
        self.open = []                                   # open position dicts

    def on_signal(self, date, setup):
        """Simulate entering the V5 debit spread at current quotes. Returns the
        position dict, or None if quotes are missing / degenerate."""
        typ, atm, short = _strikes(setup, self.width)
        ql = self.q(atm, typ, setup.entry_time)
        qs = self.q(short, typ, setup.entry_time)
        if ql is None or qs is None:
            return None
        debit = ql[1] - qs[0]                            # long.ask - short.bid
        if debit <= 0:
            return None
        contracts = (self.risk_pct * self.equity) / (debit * 100)   # fractional (paper)
        pos = {"date": date, "signal_time": setup.entry_time, "setup": setup.name,
               "direction": setup.direction, "opt_type": typ, "long_strike": atm,
               "short_strike": short, "debit": debit, "contracts": contracts}
        self.open.append(pos)
        return pos

    def _value(self, pos, time):
        ql = self.q(pos["long_strike"], pos["opt_type"], time)
        qs = self.q(pos["short_strike"], pos["opt_type"], time)
        if ql is None or qs is None:
            return None
        return ql[0] - qs[1]                             # long.bid - short.ask

    def on_bar(self, time):
        """Check open positions for the +/-50% exit at this bar."""
        still = []
        for pos in self.open:
            v = self._value(pos, time)
            d = pos["debit"]
            if v is not None and v - d >= self.target * d:
                self._close(pos, "hit +50% target", time, v)
            elif v is not None and d - v >= self.stop * d:
                self._close(pos, "hit -50% stop", time, v)
            else:
                still.append(pos)
        self.open = still

    def on_close(self, date, settle_px):
        """Settle whatever is still open at the day's close (expiry intrinsic)."""
        for pos in list(self.open):
            struct = {"kind": "debit_spread", "opt_type": pos["opt_type"],
                      "long_strike": pos["long_strike"], "width": self.width}
            self._close(pos, "held to close", "16:00", expire_value(struct, settle_px))
        self.open = []

    def _close(self, pos, reason, time, exit_value):
        pnl = (exit_value - pos["debit"]) * 100 * pos["contracts"]
        self.equity += pnl
        kind = "bull call spread" if pos["opt_type"] == "call" else "bear put spread"
        row = {"date": pos["date"], "signal_time": pos["signal_time"],
               "setup": pos["setup"], "direction": pos["direction"],
               "structure": f"{kind} {int(pos['long_strike'])}/{int(pos['short_strike'])}",
               "long_strike": pos["long_strike"], "short_strike": pos["short_strike"],
               "contracts": round(pos["contracts"], 4),
               "debit_paid": round(pos["debit"], 2),
               "max_loss_$": round(pos["debit"] * 100 * pos["contracts"], 2),
               "exit_reason": reason, "exit_time": time,
               "exit_value": round(exit_value, 2), "pnl_$": round(pnl, 2),
               "equity_after": round(self.equity, 2), "mode": "paper"}
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        write_header = not os.path.exists(self.ledger_path)
        with open(self.ledger_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if write_header:
                w.writeheader()
            w.writerow(row)
        with open(self.state_path, "w") as f:
            json.dump({"equity": round(self.equity, 2)}, f)


if __name__ == "__main__":
    import tempfile
    from acd_micro import Setup

    # --- safety: no broker/order code in this module ---
    src = open(__file__).read()
    for banned in ("import schwab", "import requests", "import httpx", "import urllib"):
        assert banned not in src, f"SAFETY: {banned} found in paper_executor"
    print("OK safety: no broker/network imports")

    # --- mock quote source: long 5000 call 30/32, short 5025 call 18/20 -> debit 14 ---
    tmp = tempfile.mkdtemp()
    led, st = os.path.join(tmp, "l.csv"), os.path.join(tmp, "s.json")
    quotes = {(5000.0, "call"): (30.0, 32.0), (5025.0, "call"): (18.0, 20.0)}

    def mkq(book):
        return lambda k, t, tm: book.get((float(k), t))

    ex = PaperExecutor(mkq(quotes), equity=10_000.0, ledger_path=led, state_path=st)
    sig = Setup("failed_a", "long", "10:00", 5001.0, None, 1, "intraday", {})
    pos = ex.on_signal("2024-01-02", sig)
    assert pos is not None and abs(pos["debit"] - 14.0) < 1e-9, pos
    assert abs(pos["contracts"] - 300.0 / 1400.0) < 1e-9, pos["contracts"]   # 3% of 10k
    # target: value moves to 21 (long.bid 29 - short.ask 8) -> +50% of debit
    quotes[(5000.0, "call")] = (29.0, 31.0)
    quotes[(5025.0, "call")] = (6.0, 8.0)
    ex.on_bar("11:00")
    assert not ex.open, "target should have closed the position"
    # pnl = (21-14)*100*0.2143 = +$150 = +50% of the $300 risked; equity compounds
    assert abs(ex.equity - 10_150.0) < 0.01, ex.equity
    print(f"OK target exit + compounding: equity {ex.equity:,.2f}")

    # stop path on a fresh position: value drops to 7 -> -50%
    quotes[(5000.0, "call")] = (30.0, 32.0)
    quotes[(5025.0, "call")] = (18.0, 20.0)
    ex.on_signal("2024-01-02", sig)
    quotes[(5000.0, "call")] = (15.0, 17.0)
    quotes[(5025.0, "call")] = (8.0, 10.0)                     # value = 15-10 = 5 <= 7
    ex.on_bar("12:00")
    assert not ex.open and ex.equity < 10_150.0, ex.equity
    print(f"OK stop exit: equity {ex.equity:,.2f}")

    # settle path: no exit fires -> expiry intrinsic at the close
    quotes[(5000.0, "call")] = (30.0, 32.0)
    quotes[(5025.0, "call")] = (18.0, 20.0)
    ex.on_signal("2024-01-02", sig)
    ex.on_close("2024-01-02", 5040.0)                          # intrinsic = min(40,25) = 25
    assert not ex.open
    with open(led) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and rows[-1]["exit_reason"] == "held to close", rows[-1]
    assert rows[-1]["mode"] == "paper"
    print("OK settle path + ledger rows")

    # --- paper-fill equivalence on the known real day (cache-backed quotes) ---
    from run_acd_signal import daily_hlc
    from acd_fade_signals import grid_cells
    from backtest_acd_fades import price_cell

    hlc = daily_hlc()
    D = "2023-07-12"
    real_sig = Setup("failed_a", "long", "11:42", 4465.68, None, 1, "intraday", {})
    led2, st2 = os.path.join(tmp, "l2.csv"), os.path.join(tmp, "s2.json")
    ex2 = PaperExecutor(cached_quote_source("SPX", D), ledger_path=led2, state_path=st2)
    pos2 = ex2.on_signal(D, real_sig)
    assert pos2 is not None, "cached quotes missing for the known trade"
    # walk the day's minutes like the live loop would
    for hh in range(11, 17):
        for mm in range(0, 60):
            t = f"{hh:02d}:{mm:02d}"
            if t <= "11:42" or not ex2.open:
                continue
            ex2.on_bar(t)
    if ex2.open:
        ex2.on_close(D, hlc[D][2])
    with open(led2) as f:
        row = list(csv.DictReader(f))[-1]
    per_contract = float(row["pnl_$"]) / float(row["contracts"])
    # ground truth: the backtest's active-exit P&L for this exact trade (+$395.00)
    cal = sorted(hlc)
    cell = next(c for c in grid_cells(D, real_sig, cal)
                if c["horizon"] == "0DTE" and c["structure"]["kind"] == "debit_spread")
    truth = price_cell(cell, real_sig, {d: v[2] for d, v in hlc.items()})["pnl0_ts"]
    assert abs(per_contract - truth) < 0.01, (per_contract, truth)
    assert row["exit_reason"] == "hit +50% target", row["exit_reason"]
    print(f"OK paper-fill equivalence: per-contract {per_contract:+.2f} == backtest {truth:+.2f}")
    print("All paper_executor self-tests passed.")
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python bot/paper_executor.py`
Expected: `OK safety`, `OK target exit + compounding: equity 10,150.00`, `OK stop exit`, `OK settle path + ledger rows`, then `OK paper-fill equivalence: per-contract +395.00 == backtest +395.00`, `All paper_executor self-tests passed.` If the equivalence assert fails, STOP and report BLOCKED with both numbers (the executor's exit walk has diverged from the backtest's — a real bug, not a tolerance issue).

- [ ] **Step 3: Commit.**

```bash
git add bot/paper_executor.py
git commit -m "feat(paper): PaperExecutor + ledger — no-order simulator, fill-equivalent to the backtest"
```

---

### Task 3: `replay_audit.py` — full-history equivalence + honesty audit

**Files:**
- Create: `bot/replay_audit.py`

**Interfaces:**
- Consumes: `RealtimeEngine`, `V5_NAMES` (realtime_v5); `build_day`, `SPX` (acd_micro); `daily_hlc`, `day_path` (run_acd_signal); `grid_cells` (acd_fade_signals); `price_cell` (backtest_acd_fades).
- Produces: `audit() -> (n_days, n_backtest_signals, extras)` where `extras = [(date, Setup)]`; `price_extras(extras, closes, cal) -> (rets, unpriceable)`; `__main__` runs both and writes `results/spx/replay_audit_2026-07-01.md`.

- [ ] **Step 1: Write the module.**

```python
# replay_audit.py — the REPLAY AUDIT: replay every cached day bar-by-bar through the
# RealtimeEngine and compare against the full-day backtest.
#   (1) EQUIVALENCE GATE: realtime must NEVER miss a backtest fade (hard assert).
#   (2) HONESTY QUANTIFIER: the backtest retroactively DROPS a failed_a when a same-side
#       A holds LATER in the day (acd_micro.setups_from_failed) — unknowable live. Those
#       fades WILL fire live. This audit counts them and prices them (V5 active exit) to
#       measure how much the backtest flattered V5 vs what is actually tradeable.
# Offline; full replay takes ~10-30 min (build_day re-runs per bar). Progress printed.
# Run: .venv/bin/python bot/replay_audit.py
import statistics

from acd_micro import build_day, SPX
from realtime_v5 import RealtimeEngine, V5_NAMES
from run_acd_signal import daily_hlc, day_path
from acd_fade_signals import grid_cells
from backtest_acd_fades import price_cell


def audit():
    hlc = daily_hlc()
    days = sorted(hlc)
    n_days = n_back = 0
    extras = []
    for i in range(1, len(days)):
        D = days[i]
        prior = hlc[days[i - 1]]
        try:
            bars = sorted(day_path(D))
        except Exception:
            continue                                    # un-replayable day (no cached path)
        if not bars:
            continue
        eng = RealtimeEngine(D, prior)
        fired = {}
        for b in bars:
            for s in eng.on_bar(b):
                fired[(s.name, s.direction, s.entry_time)] = s
        try:
            full = {(s.name, s.direction, s.entry_time)
                    for s in build_day(D, bars, prior, SPX).setups if s.name in V5_NAMES}
        except ValueError:
            continue
        n_days += 1
        n_back += len(full)
        missing = full - set(fired)
        assert not missing, ("REALTIME MISSED BACKTEST FADES", D, missing)   # the gate
        for k in set(fired) - full:
            extras.append((D, fired[k]))
        if n_days % 100 == 0:
            print(f"[{n_days} days] backtest fades so far {n_back}, extras {len(extras)}",
                  flush=True)
    return n_days, n_back, extras


def price_extras(extras, closes, cal):
    """Price each extra as V5 would trade it (0DTE debit spread, active exit)."""
    rets, unpriceable = [], 0
    for D, s in extras:
        cell = next((c for c in grid_cells(D, s, cal)
                     if c["horizon"] == "0DTE" and c["structure"]["kind"] == "debit_spread"),
                    None)
        t = price_cell(cell, s, closes) if cell else None
        if t is None or "pnl0_ts" not in t:
            unpriceable += 1                            # legs not in cache (never pulled)
        else:
            rets.append(t["pnl0_ts"] / t["max_loss"])
    return rets, unpriceable


if __name__ == "__main__":
    print("Replaying every cached day through the RealtimeEngine (~10-30 min)...",
          flush=True)
    n_days, n_back, extras = audit()
    print(f"\nEQUIVALENCE GATE PASSED: over {n_days} days / {n_back} backtest fade "
          f"signals, the realtime engine missed ZERO.")
    hlc = daily_hlc()
    closes = {d: v[2] for d, v in hlc.items()}
    rets, unpriceable = price_extras(extras, closes, sorted(hlc))
    lines = [
        "# Replay Audit — realtime V5 vs the backtest (2026-07-01)", "",
        f"- Days replayed bar-by-bar: **{n_days}**",
        f"- Backtest V5 fade signals: **{n_back}** — realtime missed **0** (hard gate).",
        f"- **Extras** (fades that fire live but the backtest retroactively dropped "
        f"because a same-side A held later): **{len(extras)}**",
    ]
    if rets:
        w = sum(1 for r in rets if r > 0)
        lines += [
            f"- Priced extras (V5 active exit): n={len(rets)}, win {w / len(rets):.0%}, "
            f"total {sum(rets):+.0%} on risk, mean {statistics.mean(rets):+.1%}",
            f"- Unpriceable extras (legs never pulled): {unpriceable}",
            "",
            f"**Honest read:** live V5 will take these {len(extras)} extra trades. "
            f"Their priced P&L above is the correction to apply to the backtest headline "
            f"(+4171% on risk / 119 trades). If the total is materially negative, the "
            f"backtest flattered V5 and the paper forward-test should be judged against "
            f"the CORRECTED expectation.",
        ]
    else:
        lines += [f"- No extras were priceable (unpriceable: {unpriceable}).",
                  "", "**Honest read:** extras exist but their option legs were never "
                  "pulled; a small IVolatility pull would complete the correction."]
    out = "results/spx/replay_audit_2026-07-01.md"
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}")
```

- [ ] **Step 2: Run it (long — background is fine).**

Run: `.venv/bin/python bot/replay_audit.py` (expect ~10–30 min; progress every 100 days)
Expected: `EQUIVALENCE GATE PASSED ... missed ZERO`, an extras count with priced stats, and `wrote results/spx/replay_audit_2026-07-01.md`. If the gate assert fires, STOP and report BLOCKED with the day and the missed setups — the realtime engine has a real bug.

- [ ] **Step 3: Commit.**

```bash
git add bot/replay_audit.py
git commit -m "feat(paper): full-history replay audit — equivalence gate + pricing of the live-vs-backtest extras"
```

---

### Task 4: Interpret the audit → record → publish

**Files:**
- Create (force-add): `results/spx/replay_audit_2026-07-01.md`
- Modify: `STATUS.md`

- [ ] **Step 1:** Read the audit output. Note the extras count, their priced total, and the corrected V5 expectation.
- [ ] **Step 2:** Update `STATUS.md` — Session-11 log entry: paper-trading Part 1 core built (RealtimeEngine + PaperExecutor + audit), the equivalence-gate result, the extras finding (count + P&L correction + the honest read), and next = Part 2 (Schwab client, gated on the developer approval).
- [ ] **Step 3:** Commit + push.

```bash
git add -f results/spx/replay_audit_2026-07-01.md
git add STATUS.md
git commit -m "feat(paper): replay-audit results + STATUS — live-vs-backtest gap quantified"
git push origin main
```

---

## Self-Review

**Spec coverage:** real-time engine reusing `build_day` (T1) ✓; paper executor + ledger, no-order guarantee + safety self-test (T2) ✓; replay equivalence (T1 single-day, T3 full-history hard gate) ✓; paper-fill equivalence vs `price_cell` (T2) ✓; pluggable `bar/quote` seams (`on_bar` takes plain tuples; `cached_quote_source` is the replay adapter Part 2 swaps) ✓; 3% compounding / $10k default (T2) ✓; spec's flagged macro-context risk — resolved by design (engine skips the macro layer; justification in T1 header) plus the NEW retroactive-drop divergence found in planning, which T3 quantifies ✓; outputs in `results/spx/` ✓.

**Placeholder scan:** none — every step carries complete code.

**Type consistency:** `RealtimeEngine.on_bar((time, price)) -> [Setup]` consumed identically in T2's equivalence test and T3's audit. `quote(strike, opt_type, time) -> (bid, ask)|None` identical between the mock and `cached_quote_source`. `Setup` field order `(name, direction, entry_time, entry_price, stop, conviction, horizon, refs)` matches `acd_micro`. `price_cell(...)["pnl0_ts"]` / `["max_loss"]` match ④b. `_strikes(setup, width) -> (typ, atm, short)` matches `acd_fade_signals`.

**Notes for the executor:** (1) T2's cache-backed equivalence test constructs the known signal with `entry_price=4465.68` — `_strikes` snaps it to ATM 4465, matching the ledger row (`bull call spread 4465/4490`). (2) T3's audit is CPU-bound (~10–30 min); run it in the background and check progress lines. (3) The T1 "fires at its own bar" assert and the T3 gate are BLOCK-on-failure asserts — report, don't weaken.
