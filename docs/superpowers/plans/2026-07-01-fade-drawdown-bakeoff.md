# Fade Drawdown Bake-Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one offline harness that races ~8 drawdown-reduction variants of the debit-spread fade strategy and ranks them by risk-adjusted return + year-by-year robustness (not raw total).

**Architecture:** One new file, `bot/backtest_fade_variants.py`, reusing the ④b engine. Build a tagged debit-spread trade list once, then express each variant as a config over four composable switches (filter/exit/sizing/diversify), compute a mean-normalized weighted return series, and score each on risk-adjusted return with per-year and 10¢-slippage columns.

**Tech Stack:** Python 3.12 in `.venv`, stdlib only (dataclasses, statistics). House style: flat `bot/` modules, bare sibling imports, run `.venv/bin/python bot/<file>.py`, inline `__main__` assert self-tests (NO pytest), frequent commits.

## Global Constraints

- Run every file as `.venv/bin/python bot/<file>.py` (the `bot/` dir is `sys.path[0]`, so bare sibling imports work). NO pytest — self-tests live in `if __name__ == "__main__":` as `assert`s that print `OK`/`passed`.
- **Judging rule:** rank variants by **risk-adjusted return = total ÷ maxDD** (steady-kid metric); raw total is shown but does NOT decide. Cross-check by per-year totals and 10¢-slippage survival.
- **P&L / metric convention (from ④b):** per-trade return `= pnl/max_loss`; `max_loss = debit*100`. `max_drawdown(curve)` returns a POSITIVE magnitude; `risk_adj = total/mdd`.
- **Slippage haircut:** `pnl_after = pnl − slip·nlegs·2·100` (dollars), then `ret = pnl_after/max_loss`, then `× weight`.
- **Sizing normalization:** every sizing rule's per-trade weights are rescaled so the variant's **mean weight = 1.0** (compare path shape at equal average exposure).
- **Base = debit spreads only** (long options are excluded — the lottery tickets). Both horizons available.
- Filters: `all` (failed_a+failed_a_pivot+failed_c) / `no_failed_c` (drop failed_c) / `failed_a_only` (name == "failed_a" strictly).
- Data is already cached (④b pull). Everything runs OFFLINE, no network, no API key.
- Keep IVolatility subscribed. NEVER run git-history rewrites (book PDF in gitignored `research/`).

---

### Task 1: `collect_fade_trades()` — the tagged trade list

**Files:**
- Create: `bot/backtest_fade_variants.py`

**Interfaces:**
- Consumes: `collect_fades`/`grid_cells` (`acd_fade_signals`), `price_cell` (`backtest_acd_fades`), `daily_hlc` (`run_acd_signal`).
- Produces: `collect_fade_trades() -> list[dict]`, memoized. Each trade dict:
  `{"date","name","conviction","horizon","nlegs","max_loss","pnl_hold","pnl_active"}`
  (`pnl_active` == `pnl_hold` for overnight trades, which have no intraday next-day exit).

- [ ] **Step 1: Write the module header + `collect_fade_trades` + a `__main__` self-test.**

```python
# backtest_fade_variants.py — drawdown BAKE-OFF: race ~8 variants of the debit-spread
# fade strategy (filter/exit/sizing/diversify switches) and rank them by RISK-ADJUSTED
# return + year-by-year robustness (NOT raw total). Offline on the ④b cache.
# Spec: docs/superpowers/specs/2026-07-01-fade-drawdown-bakeoff.md
# Run:  .venv/bin/python bot/backtest_fade_variants.py
import statistics
from dataclasses import dataclass

from acd_fade_signals import collect_fades, grid_cells
from backtest_acd_fades import price_cell
from run_acd_signal import daily_hlc
from backtest_acd_full import _stats

_TRADES = None


def collect_fade_trades():
    """Tagged debit-spread fade trades (both horizons), built once from cache."""
    global _TRADES
    if _TRADES is not None:
        return _TRADES
    closes = {d: v[2] for d, v in daily_hlc().items()}
    cal = sorted(closes)
    out = []
    for date, s in collect_fades():
        for cell in grid_cells(date, s, cal):
            if cell["structure"]["kind"] != "debit_spread":
                continue
            t = price_cell(cell, s, closes)
            if t is None:
                continue
            out.append({"date": date, "name": s.name, "conviction": s.conviction,
                        "horizon": cell["horizon"], "nlegs": t["nlegs"],
                        "max_loss": t["max_loss"], "pnl_hold": t["pnl0"],
                        "pnl_active": t.get("pnl0_ts", t["pnl0"])})
    _TRADES = out
    return out


if __name__ == "__main__":
    trades = collect_fade_trades()
    assert len(trades) > 250, len(trades)
    assert {t["horizon"] for t in trades} == {"0DTE", "overnight"}, "both horizons expected"
    assert any(t["name"] == "failed_c" for t in trades), "failed_c expected"
    need = {"date", "name", "conviction", "horizon", "nlegs", "max_loss", "pnl_hold", "pnl_active"}
    assert all(need <= t.keys() for t in trades)
    assert all(t["pnl_active"] == t["pnl_hold"] for t in trades if t["horizon"] == "overnight")
    print(f"OK collect_fade_trades: {len(trades)} trades "
          f"(0DTE {sum(1 for t in trades if t['horizon']=='0DTE')}, "
          f"overnight {sum(1 for t in trades if t['horizon']=='overnight')})")
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python bot/backtest_fade_variants.py`
Expected: `OK collect_fade_trades: <N> trades (0DTE ~162, overnight ~164)` (first run builds the signal history from cache — up to ~1 min).

- [ ] **Step 3: Commit.**

```bash
git add bot/backtest_fade_variants.py
git commit -m "feat(bakeoff): collect_fade_trades — tagged debit-spread trade list (both horizons)"
```

---

### Task 2: `Variant` + `apply_variant` — the switch logic

**Files:**
- Modify: `bot/backtest_fade_variants.py` (add `Variant`, `_FILTERS`, `_weights_from`, `apply_variant` above `__main__`; append asserts to the end of the `__main__` block).

**Interfaces:**
- Consumes: `dataclass` (already imported).
- Produces:
  - `Variant(name, filt="all", exit_rule="hold", sizing="flat", horizons="0DTE")` dataclass.
  - `apply_variant(trades, v) -> list[dict]` — filtered, horizon-selected, date-sorted rows
    `{"date","weight","pnl","nlegs","max_loss"}`; `weight` is mean-normalized to 1.0; `pnl` is
    `pnl_active` if `v.exit_rule=="active"` else `pnl_hold`.

- [ ] **Step 1: Add the dataclass + helpers + `apply_variant` (above `__main__`).**

```python
@dataclass
class Variant:
    name: str
    filt: str = "all"          # all | no_failed_c | failed_a_only
    exit_rule: str = "hold"    # hold | active
    sizing: str = "flat"       # flat | conviction | throttle
    horizons: str = "0DTE"     # 0DTE | overnight | blend


_FILTERS = {
    "all": lambda t: True,
    "no_failed_c": lambda t: t["name"] != "failed_c",
    "failed_a_only": lambda t: t["name"] == "failed_a",
}


def _weights_from(pnls, convs, sizing):
    """Per-trade weights (date-ordered), then mean-normalized to 1.0."""
    if sizing == "flat":
        w = [1.0] * len(pnls)
    elif sizing == "conviction":
        w = [float(c) for c in convs]
    elif sizing == "throttle":                    # anti-martingale: halve after 2 losses
        w, streak = [], 0
        for p in pnls:
            w.append(0.5 if streak >= 2 else 1.0)  # decided by losses BEFORE this trade
            streak = streak + 1 if p <= 0 else 0
    else:
        raise ValueError(f"unknown sizing {sizing!r}")
    m = sum(w) / len(w) if w else 1.0
    return [x / m for x in w] if m else w


def apply_variant(trades, v):
    picked = [t for t in trades if _FILTERS[v.filt](t)]
    if v.horizons != "blend":
        picked = [t for t in picked if t["horizon"] == v.horizons]
    picked = sorted(picked, key=lambda t: t["date"])
    pnls = [t["pnl_active"] if v.exit_rule == "active" else t["pnl_hold"] for t in picked]
    ws = _weights_from(pnls, [t["conviction"] for t in picked], v.sizing)
    return [{"date": t["date"], "weight": w, "pnl": p,
             "nlegs": t["nlegs"], "max_loss": t["max_loss"]}
            for t, p, w in zip(picked, pnls, ws)]
```

- [ ] **Step 2: Append synthetic self-tests to the END of the existing `__main__` block** (after the Task 1 `print`).

```python
    def _mk(date, name, hz, ph, pa=None, conv=1, nlegs=2, ml=100.0):
        return {"date": date, "name": name, "conviction": conv, "horizon": hz,
                "nlegs": nlegs, "max_loss": ml, "pnl_hold": ph,
                "pnl_active": ph if pa is None else pa}

    syn = [_mk("2024-01-01", "failed_a", "0DTE", 50, 20),
           _mk("2024-01-02", "failed_c", "0DTE", -100, -30),
           _mk("2024-01-03", "failed_a", "overnight", 40)]
    r = apply_variant(syn, Variant("t", filt="no_failed_c", horizons="blend"))
    assert [x["date"] for x in r] == ["2024-01-01", "2024-01-03"], r      # failed_c dropped
    r = apply_variant(syn, Variant("t", exit_rule="active", horizons="0DTE"))
    assert [x["pnl"] for x in r] == [20, -30], r                          # active uses pnl_active
    r = apply_variant(syn, Variant("t", horizons="blend"))
    assert len(r) == 3 and abs(sum(x["weight"] for x in r) / len(r) - 1.0) < 1e-9  # mean weight 1
    print("OK apply_variant: filter / active / blend / normalize")

    losers = [_mk(f"2024-02-0{i}", "failed_a", "0DTE", -10) for i in range(1, 5)] \
        + [_mk("2024-02-05", "failed_a", "0DTE", 100)]
    r = apply_variant(losers, Variant("t", sizing="throttle", horizons="0DTE"))
    raw = [1.0, 1.0, 0.5, 0.5, 0.5]                                       # halve after 2 losses
    m = sum(raw) / len(raw)
    assert all(abs(r[i]["weight"] - raw[i] / m) < 1e-9 for i in range(5)), [x["weight"] for x in r]
    print("OK apply_variant: throttle sizing")
```

- [ ] **Step 3: Run it.**

Run: `.venv/bin/python bot/backtest_fade_variants.py`
Expected: the Task 1 line plus `OK apply_variant: filter / active / blend / normalize` and `OK apply_variant: throttle sizing`.

- [ ] **Step 4: Commit.**

```bash
git add bot/backtest_fade_variants.py
git commit -m "feat(bakeoff): Variant + apply_variant (filter/exit/sizing/diversify switches)"
```

---

### Task 3: `weighted_returns` + `score` + `per_year` — the metrics

**Files:**
- Modify: `bot/backtest_fade_variants.py` (add the three functions above `__main__`; append asserts to `__main__`).

**Interfaces:**
- Consumes: `apply_variant` output rows; `_stats` (`backtest_acd_full`); `statistics`.
- Produces:
  - `weighted_returns(rows, slip=0.0) -> list[(date, ret)]` — per row `(pnl − slip·nlegs·2·100)/max_loss · weight`.
  - `score(pairs) -> dict` with `n, win, total, mdd (positive), risk_adj (=total/mdd), sharpe`.
  - `per_year(pairs) -> dict[year -> total]`.

- [ ] **Step 1: Add the functions (above `__main__`).**

```python
def weighted_returns(rows, slip=0.0):
    """[(date, weighted return)] with an optional per-leg slippage haircut."""
    out = []
    for r in rows:
        pnl = r["pnl"] - slip * r["nlegs"] * 2 * 100
        out.append((r["date"], pnl / r["max_loss"] * r["weight"]))
    return out


def score(pairs):
    rets = [w for _, w in pairs]
    n, wr, total, mdd, ra = _stats(rets)          # mdd positive; ra = total/mdd
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    sharpe = statistics.mean(rets) / sd if sd > 0 else 0.0
    return {"n": n, "win": wr, "total": total, "mdd": mdd, "risk_adj": ra, "sharpe": sharpe}


def per_year(pairs):
    yr = {}
    for date, w in pairs:
        yr[date[:4]] = yr.get(date[:4], 0.0) + w
    return yr
```

- [ ] **Step 2: Append self-tests to the END of `__main__`.**

```python
    known = [("2024-01-01", 1.0), ("2024-06-01", -1.0), ("2025-01-01", 1.0)]
    s = score(known)                              # cum 1,0,1 -> mdd 1.0 ; total 1.0 ; ra 1.0
    assert s["n"] == 3 and abs(s["total"] - 1.0) < 1e-9
    assert abs(s["mdd"] - 1.0) < 1e-9 and abs(s["risk_adj"] - 1.0) < 1e-9, s
    yr = per_year(known)
    assert abs(yr["2024"] - 0.0) < 1e-9 and abs(yr["2025"] - 1.0) < 1e-9, yr
    wr_rows = [{"date": "2024-01-01", "weight": 1.0, "pnl": 100, "nlegs": 2, "max_loss": 100.0}]
    assert abs(weighted_returns(wr_rows, 0.0)[0][1] - 1.0) < 1e-9
    assert weighted_returns(wr_rows, 0.10)[0][1] < 1.0     # slippage haircut lowers the return
    print("OK score / per_year / weighted_returns")
```

- [ ] **Step 3: Run it.**

Run: `.venv/bin/python bot/backtest_fade_variants.py`
Expected: prior lines plus `OK score / per_year / weighted_returns`.

- [ ] **Step 4: Commit.**

```bash
git add bot/backtest_fade_variants.py
git commit -m "feat(bakeoff): weighted_returns + score + per_year metrics"
```

---

### Task 4: `LINEUP` + `report` + the real bake-off run

**Files:**
- Modify: `bot/backtest_fade_variants.py` (add `LINEUP` + `report` above `__main__`; append the real run + cross-check to the END of `__main__`).

**Interfaces:**
- Consumes: everything above.
- Produces: `LINEUP` (the 9 variants), `report(trades, lineup=LINEUP) -> rows` (prints the scoreboard ranked by `risk_adj`; returns the sorted `[(variant, score, ra10, per_year)]`).

- [ ] **Step 1: Add `LINEUP` + `report` (above `__main__`).**

```python
LINEUP = [
    Variant("V0 ref 0DTE",       "all",         "hold",   "flat",     "0DTE"),
    Variant("V0b ref overnight", "all",         "hold",   "flat",     "overnight"),
    Variant("V1 no_failed_c",    "no_failed_c", "hold",   "flat",     "0DTE"),
    Variant("V2 active exit",    "all",         "active", "flat",     "0DTE"),
    Variant("V3 throttle",       "all",         "hold",   "throttle", "0DTE"),
    Variant("V4 blend",          "all",         "hold",   "flat",     "blend"),
    Variant("V5 no_c+active",    "no_failed_c", "active", "flat",     "0DTE"),
    Variant("V6 no_c+blend",     "no_failed_c", "hold",   "flat",     "blend"),
    Variant("V7 everything",     "no_failed_c", "active", "throttle", "blend"),
]


def report(trades, lineup=LINEUP):
    rows = []
    for v in lineup:
        r = apply_variant(trades, v)
        p0 = weighted_returns(r, 0.0)
        rows.append((v, score(p0), score(weighted_returns(r, 0.10))["risk_adj"], per_year(p0)))
    rows.sort(key=lambda x: x[1]["risk_adj"], reverse=True)
    years = sorted({y for _, _, _, yr in rows for y in yr})
    print("\n=== FADE DRAWDOWN BAKE-OFF — ranked by RISK-ADJUSTED return ===")
    print("(steady-kid metric; raw total shown but does NOT decide the winner)\n")
    print(f"{'variant':<20}{'n':>4}{'win':>5}{'total':>9}{'maxDD':>8}{'risk-adj':>9}{'ra@10c':>8}  "
          + "".join(f"{y:>8}" for y in years))
    for v, s, ra10, yr in rows:
        print(f"{v.name:<20}{s['n']:>4}{s['win']:>5.0%}{s['total']:>+9.0%}{s['mdd']:>8.0%}"
              f"{s['risk_adj']:>+9.2f}{ra10:>+8.2f}  " + "".join(f"{yr.get(y, 0):>+8.0%}" for y in years))
    print("\nNOTE: best-of-9 selection = mild overfitting; the winner needs a walk-forward before trust.")
    return rows
```

- [ ] **Step 2: Append the real run + ④b cross-check to the END of `__main__`.**

```python
    print("\nBuilding the bake-off (cached)...")
    all_trades = collect_fade_trades()
    ranked = report(all_trades)
    # cross-check: V0 (all/hold/flat/0DTE, weights all 1.0) must reproduce ④b's
    # 0DTE/debit_spread reference: total +5180% (=51.8) and maxDD 796% (=7.96).
    v0 = next(s for v, s, _, _ in ranked if v.name == "V0 ref 0DTE")
    assert 51 < v0["total"] < 53, f"V0 total {v0['total']} != ~51.8 (④b regression)"
    assert 7.5 < v0["mdd"] < 8.2, f"V0 maxDD {v0['mdd']} != ~7.96 (④b regression)"
    print("OK cross-check: V0 reproduces the ④b 0DTE/debit_spread reference")
```

- [ ] **Step 3: Run it.**

Run: `.venv/bin/python bot/backtest_fade_variants.py`
Expected: all prior `OK` lines, then the ranked bake-off scoreboard (9 rows, per-year columns), then `OK cross-check: V0 reproduces the ④b 0DTE/debit_spread reference`.

- [ ] **Step 4: Commit.**

```bash
git add bot/backtest_fade_variants.py
git commit -m "feat(bakeoff): variant lineup + ranked scoreboard + ④b V0 cross-check"
```

---

### Task 5: Interpret → grade the winner → record

**Files:**
- Create: `results/backtest_fade_bakeoff_eval_2026-07-01.md`
- Modify: `STATUS.md`

- [ ] **Step 1: Capture the scoreboard.**

Run: `.venv/bin/python bot/backtest_fade_variants.py 2>&1 | tee results/fade_bakeoff_run.txt`
Read the ranked table.

- [ ] **Step 2: Identify the winner** = the top row by `risk-adj` that ALSO (a) is positive in the majority of years and (b) keeps a positive `ra@10c`. If the top risk-adj row fails the year/slippage cross-check, step down to the next row that passes and note why in the eval.

- [ ] **Step 3: Grade the winner via the `backtest-expert` skill.** Invoke the skill; feed it the winner's n / win% / avg-win% / avg-loss% / maxDD / per-year / slippage. Write the verdict to `results/backtest_fade_bakeoff_eval_2026-07-01.md`: the full ranked table, which switch(es) actually moved risk-adjusted return, the winner + its grade, the honest read on whether any variant beats the V0/V0b base on the steady-kid metric (or an honest null result), and the explicit walk-forward caveat.

- [ ] **Step 4: Update `STATUS.md`** — add to the Session 10 log: the bake-off result (which fix helped, the winning variant + grade), and refresh the current-phase brief's "next" pointer.

- [ ] **Step 5: Commit + push.**

```bash
git add -f results/backtest_fade_bakeoff_eval_2026-07-01.md
git add STATUS.md bot/backtest_fade_variants.py
git commit -m "feat(bakeoff): drawdown bake-off results + backtest-expert grade + STATUS"
git push origin main
```

---

## Self-Review

**Spec coverage:**
- Base = debit spreads, both horizons → Task 1 `collect_fade_trades`. ✓
- Four composable switches (filter/exit/sizing/diversify) → Task 2 `Variant`/`apply_variant`. ✓
- Mean-normalized weights → Task 2 `_weights_from`. ✓
- Judge on risk-adjusted return + per-year + 10¢ slippage, raw total shown not deciding → Task 3 `score`/`per_year`, Task 4 `report` (ranked by `risk_adj`). ✓
- ~8 curated variants + combos → Task 4 `LINEUP` (9 incl. two references). ✓
- Weighted slippage (not reusing `_with_slip`) → Task 3 `weighted_returns`. ✓
- Grade winner + honesty/walk-forward caveat → Task 5. ✓
- Offline, no network → all tasks read cache only. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete. ✓

**Type consistency:** trade-dict keys (`date/name/conviction/horizon/nlegs/max_loss/pnl_hold/pnl_active`) identical across Tasks 1–2. `apply_variant` row keys (`date/weight/pnl/nlegs/max_loss`) match `weighted_returns` consumption in Task 3. `score` dict keys (`n/win/total/mdd/risk_adj/sharpe`) match `report` usage in Task 4. `Variant` field names (`filt/exit_rule/sizing/horizons`) identical in Tasks 2 and 4. ✓

**Note for the executor:** Tasks 2–4 each APPEND their self-tests to the END of the single `__main__` block (Task 4's real run + cross-check goes last). Add all functions ABOVE `__main__`. The V0 cross-check anchors the harness to ④b's published numbers — if it fails, the harness diverged from ④b and must be reconciled before trusting the scoreboard.
