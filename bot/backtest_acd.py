# backtest_acd.py — race the 3 wrappers on the identical ACD signal over 3 yrs.
# Per trade: entry-day dated chain -> build all 3 wrappers -> simulate the multi-day
# hold (3-day pivot trailing stop / expiry / entry-day B) -> P&L. Report per wrapper:
# risk-adjusted return (total / max drawdown), Sharpe, win rate, per-year, slippage.
#
# Run with:  .venv/bin/python bot/backtest_acd.py
#   (offline self-test by default; set IVOL_API_KEY + RUN_REAL=1 for the real 3yr run)

from acd_rules import rolling_3day_pivot, pivot_trailing_exit


def simulate_hold(direction, position, expiration, entry_date, day_list, hlc, mark_fn):
    """Walk the position forward from entry_date. Exit on (1) expiry, (2) 3-day pivot
    trailing stop closing back through the band, or (3) entry-day B is folded in by the
    caller via the signal's stop_B check before calling. Returns (pnl, exit_date, reason).

    mark_fn(date, expiration, legs) -> net_exit or None. On a None (marking gap) we carry
    the most recent good mark; a trade that never marks returns (None, exit_date, "no_mark").
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


def _safe_mark(chain_fn, sym, date, expiration, legs):
    """net_exit for `legs` from `date`'s dated chain, or None on any data problem."""
    from load_acd_dated import mark_legs
    try:
        return mark_legs(chain_fn(sym, date), expiration, legs)
    except Exception:
        return None


def _degenerate(position):
    """True if a spread collapsed onto one strike (off-the-end / too-coarse snap)."""
    legs = position["legs"]
    return len(legs) > 1 and len({leg["strike"] for leg in legs}) < len(legs)


def run_acd_backtest(profile=None, sym="SPX", slippage_per_leg=0.0,
                     signals_fn=None, hlc_fn=None, chain_fn=None):
    """Race the 3 wrappers on the identical ACD signal. Returns (results, dropped).

    results = {wrapper -> [trade dicts]}; dropped = {wrapper -> count}. Data access is
    injectable (signals_fn/hlc_fn/chain_fn) so it tests offline. Data-seam validation
    (reviewer entry-conditions): entry chain missing -> skip the day; wrapper build error,
    non-positive max_loss, degenerate/collapsed spread, or a position that never marks ->
    drop and COUNT it (never a silent loss).
    """
    from config import ACD_DEFAULT
    from run_acd_signal import trade_signals, daily_hlc
    from load_acd_dated import dated_chain_df, pick_entry_chain
    from acd_wrappers import (build_long_option, build_debit_spread,
                              build_credit_spread)

    profile = profile or ACD_DEFAULT
    signals_fn = signals_fn or (lambda: trade_signals(profile.a_pct))
    hlc_fn = hlc_fn or daily_hlc
    chain_fn = chain_fn or dated_chain_df
    target_dte = int((profile.dte_from + profile.dte_to) / 2)

    builders = {
        "long_option": lambda s, p, c, sp, e: build_long_option(s, p, c, sp, e),
        "debit_spread": lambda s, p, c, sp, e: build_debit_spread(
            s, p, c, sp, e, width=profile.debit_width),
        "credit_spread": lambda s, p, c, sp, e: build_credit_spread(
            s, p, c, sp, e, short_otm=profile.credit_short_otm, width=profile.credit_width),
    }
    results = {k: [] for k in builders}
    dropped = {k: 0 for k in builders}

    hlc = hlc_fn()
    days = sorted(hlc)
    for sig in signals_fn():
        D = sig["date"]
        try:
            puts, calls, spot, exp = pick_entry_chain(chain_fn(sym, D), target_dte)
        except Exception:
            continue                                     # entry chain missing -> skip day
        for name, build in builders.items():
            try:
                pos = build(sig, puts, calls, spot, exp)
            except Exception:
                dropped[name] += 1
                continue
            max_loss = max(0.0, pos["max_loss"])          # clamp (reviewer entry-cond)
            if max_loss <= 0 or _degenerate(pos):
                dropped[name] += 1
                continue
            mark_fn = (lambda d, e, legs, _cf=chain_fn: _safe_mark(_cf, sym, d, e, legs))
            pnl, xd, reason = simulate_hold(
                sig["direction"], pos, exp, D, days, hlc, mark_fn)
            if pnl is None:                               # never marked -> drop + count
                dropped[name] += 1
                continue
            nlegs = len(pos["legs"])
            pnl -= slippage_per_leg * nlegs * 2 * 100     # nlegs * (entry+exit) * 100
            results[name].append({
                "date": D, "wrapper": name, "direction": sig["direction"],
                "spot": spot, "settle": (hlc[xd][2] if xd in hlc else spot),
                "credit": abs(pos["entry_cost"]) * 100, "max_loss": max_loss,
                "pnl": round(pnl, 2), "ret_pct": pnl / max_loss,
                "exit_date": xd, "reason": reason,
            })
    return results, dropped


def report_wrappers(results, dropped=None):
    """Per-wrapper risk-adjusted return (total / max drawdown) + Sharpe + win + per-year,
    then the winner. All in % return on capital-at-risk (account-independent)."""
    import statistics
    from itertools import accumulate
    from backtest import max_drawdown
    from backtest_chains import yearly_report

    dropped = dropped or {}
    print("\n=== ACD WRAPPER RACE — % return on capital-at-risk ===")
    summary = []
    for name, trades in results.items():
        if not trades:
            print(f"\n{name}: no trades ({dropped.get(name, 0)} dropped)")
            continue
        rets = [t["ret_pct"] for t in trades]
        n = len(rets)
        wins = sum(1 for r in rets if r > 0)
        total = sum(rets)
        equity = list(accumulate(rets))
        mdd = max_drawdown(equity)
        risk_adj = total / abs(mdd) if mdd else float("inf")
        sd = statistics.pstdev(rets)
        sharpe = statistics.mean(rets) / sd if sd > 0 else 0.0
        print(f"\n{name}  ({n} trades, {dropped.get(name, 0)} dropped)")
        print(f"  win rate:       {wins / n:.0%}")
        print(f"  total return:   {total:+.0%} on risk")
        print(f"  max drawdown:   {mdd:.0%} of risk capital")
        print(f"  RISK-ADJUSTED:  {risk_adj:+.2f}   (total / maxDD)  <- the yardstick")
        print(f"  Sharpe-like:    {sharpe:+.2f}")
        yearly_report(trades, label=name)
        summary.append((name, risk_adj, total, mdd, wins / n))
    if summary:
        print("\n=== WINNER by risk-adjusted return ===")
        for name, ra, tot, mdd, wr in sorted(summary, key=lambda x: -x[1]):
            print(f"  {name:<14} risk-adj {ra:+.2f}   "
                  f"(total {tot:+.0%}, maxDD {mdd:.0%}, win {wr:.0%})")


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

    # --- Task 4/5: harness races 3 wrappers on injected stubs (offline) ---
    import pandas as pd
    from load_ivolai import COLUMN_MAP

    def _wide_chain(_sym, d):
        """A realistic mock dated chain: monotonic prices (calls fall / puts rise with
        strike) so spreads stay bounded, $5 grid wide enough for 25-pt wings."""
        rows = []
        for k in range(4900, 5101, 5):
            call = max(1.0, (5100 - k) * 0.4 + 2)
            put = max(1.0, (k - 4900) * 0.4 + 2)
            for cp, mid in (("C", call), ("P", put)):
                rows.append({"c_date": d, "expiration_date": "2024-09-05", "dte": 35,
                             "price_strike": float(k), "call_put": cp,
                             "Bid": round(mid - 0.5, 2), "Ask": round(mid + 0.5, 2),
                             "iv": 0.16, "underlying_price": 5000.0})
        return pd.DataFrame(rows).rename(columns=COLUMN_MAP)

    _sig = {"date": "2024-08-01", "direction": "long", "entry_spot": 5000.0,
            "stop_B": 4995.0, "pivot_band": (4980.0, 4990.0)}
    _hlc = {"2024-08-01": (5005, 4995, 5000), "2024-08-02": (5010, 5000, 5008),
            "2024-08-05": (5012, 5002, 5009), "2024-08-06": (5006, 4980, 4970)}
    res, drp = run_acd_backtest(
        signals_fn=lambda: [_sig], hlc_fn=lambda: _hlc, chain_fn=_wide_chain)
    assert set(res) == {"long_option", "debit_spread", "credit_spread"}, set(res)
    assert all(len(res[k]) == 1 for k in res), {k: len(v) for k, v in res.items()}
    assert all(res[k][0]["ret_pct"] >= -1.01 for k in res), "ret_pct below -100% of risk"
    assert all(res[k][0]["reason"] == "pivot_stop" for k in res), \
        {k: res[k][0]["reason"] for k in res}
    print("Task 4/5 OK: harness races 3 wrappers + reports (offline stub)")
    report_wrappers(res, drp)

    # --- REAL 3-yr run (needs the big pull complete + IVOL_API_KEY) ---
    import os
    if os.environ.get("RUN_REAL"):
        os.makedirs("results", exist_ok=True)
        slip = float(os.environ.get("SLIP", "0"))
        real, real_drp = run_acd_backtest(slippage_per_leg=slip)
        for name, trades in real.items():
            if trades:
                pd.DataFrame(trades).to_csv(f"results/acd_{name}.csv", index=False)
                print(f"saved results/acd_{name}.csv ({len(trades)} trades)")
        report_wrappers(real, real_drp)
