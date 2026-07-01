# backtest_orb.py — the ORB day-by-day backtest loop. Mirrors backtest_chains.py:
# per day -> opening range -> breakout -> pick spread -> settle BOTH ways ->
# win rate / equity / drawdown (reusing report_chains). Runs on fake data now;
# wire in real IVolatility intraday data via load_ivol_intraday (Task 8).
#
# Run with:  .venv/bin/python bot/backtest_orb.py

from orb_rules import build_orb
from orb_exits import exit_expire, exit_target_stop
from backtest_chains import report_chains


def _fake_days():
    """Two tradable days (a bull and a bear) + one chop day (no trade)."""
    strikes = [4950, 4960, 4970, 4980, 4990, 5000, 5010, 5020, 5030, 5040]
    bull = {"date": "2024-06-03",
            "path": [("09:30", 5005), ("10:00", 4998), ("10:30", 5010),
                     ("10:45", 5025)],
            "strikes": strikes, "entry_credit": 3.0,
            "close_series": [("10:45", 3.0), ("12:00", 1.0)], "settle": 5050.0}
    bear = {"date": "2024-06-04",
            "path": [("09:30", 5005), ("10:30", 5002), ("10:45", 4990)],
            "strikes": strikes, "entry_credit": 3.0,
            "close_series": [("10:45", 3.0), ("12:00", 8.0)], "settle": 4995.0}
    chop = {"date": "2024-06-05",   # box 5002-5005; later bars stay inside -> no trade
            "path": [("09:30", 5005), ("10:30", 5002), ("11:00", 5004),
                     ("12:00", 5003)],
            "strikes": strikes, "entry_credit": 3.0,
            "close_series": [], "settle": 5003.0}
    return [bull, bear, chop]


def _trade_from_day(day):
    """Run one prepared day through the brain + both exits. None if no breakout."""
    plan = build_orb(day["path"], day["strikes"], expiration=day["date"])
    if plan is None:
        return None
    credit = day["entry_credit"]
    max_loss = (plan["width"] - credit) * 100
    pnl = exit_expire(plan, credit, day["settle"])
    pnl_ts = exit_target_stop(plan, credit, day["close_series"], day["settle"])
    return {
        "date": day["date"], "direction": plan["direction"],
        "spot": plan["entry_spot"], "settle": day["settle"],
        "credit": credit * 100, "max_loss": max_loss,
        "pnl": pnl, "pnl_ts": pnl_ts,
        "ret_pct": pnl / max_loss if max_loss else 0.0,
    }


def run_orb_backtest_fake(days):
    """Walk prepared fake days -> trade dicts (skipping no-breakout days)."""
    trades = []
    for day in days:
        t = _trade_from_day(day)
        if t is not None:
            trades.append(t)
    return trades


def run_orb_backtest(from_date, to_date, profile=None, slippage_per_leg=0.0):
    """Backtest KIRK's ORB on REAL IVolatility intraday data over [from, to].

    slippage_per_leg : $ haircut per leg on a fill. Entry has 2 legs, so the credit
                       you actually collect is reduced by 2*slippage; closing (the
                       Arianne path) costs 2*slippage more per bar. Applied BEFORE
                       the return-on-risk filter, so thin-credit trades drop out —
                       the honest way to see if the edge survives real fills.

    Per 0DTE day: listed strikes + ATM anchor (cached 0DTE chain) -> morning
    underlying path -> build the spread (short strike OUTSIDE the range) -> apply
    Kirk's asymmetric filters (range width, return-on-risk, ADX on the put side,
    FOMC skip on puts / trade-through on calls) -> pull the two legs' minute bars
    -> settle Kirk-style (let expire = `pnl`) AND Arianne-style (50/130 = `pnl_ts`).
    """
    from config import ORB_KIRK
    import load_ivol_intraday as intra
    from backtest_chains import _spx_ohlc
    from filters import add_indicators, FOMC_DATES
    from orb_rules import orb_filters_ok

    profile = profile or ORB_KIRK
    sym = profile.symbol
    ohlc = _spx_ohlc(from_date, to_date)
    closes = {r["date"]: float(r["close"]) for _, r in ohlc.iterrows()}  # 0DTE settle
    ind = add_indicators(ohlc).set_index("date")                        # for ADX(14)
    fomc = set(FOMC_DATES)

    trades, no_breakout, filtered = [], 0, 0
    for D in sorted(closes):
        if not (from_date <= D <= to_date):
            continue
        try:
            strikes, anchor_spot = intra.fetch_0dte_chain(
                sym, D, moneyness=profile.moneyness)
            atm = min(strikes, key=lambda k: abs(k - anchor_spot))
            path = intra.underlying_path(sym, D, D, atm)
            plan = build_orb(path, strikes, expiration=D, width=profile.width,
                             range_start=profile.range_start,
                             range_end=profile.range_end, cutoff=profile.cutoff)
            if plan is None:
                no_breakout += 1
                continue
            credit, close_series = intra.leg_close_series(
                sym, D, D, plan["short_strike"], plan["long_strike"],
                plan["option_type"], plan["entry_time"])
            slip = 2 * slippage_per_leg                  # 2 legs per spread
            credit = credit - slip                       # you collect less at entry
            close_series = [(t, c + slip) for t, c in close_series]  # costs more to close
        except Exception as e:
            print(f"  skip {D}: {repr(e)[:70]}", flush=True)
            continue

        adx = float(ind.loc[D, "adx14"]) if D in ind.index else None
        ok, _reason = orb_filters_ok(
            plan, credit, adx, D in fomc,
            range_width_min=profile.range_width_min,
            put_rr_floor=profile.put_rr_floor, call_rr_floor=profile.call_rr_floor,
            put_adx_min=profile.put_adx_min)
        if not ok:
            filtered += 1
            continue

        settle = closes[D]
        max_loss = (plan["width"] - credit) * 100
        pnl = exit_expire(plan, credit, settle)              # KIRK: let it expire
        pnl_ts = exit_target_stop(plan, credit, close_series, settle)  # Arianne 50/130
        trades.append({
            "date": D, "direction": plan["direction"],
            "spot": plan["entry_spot"], "settle": settle,
            "credit": credit * 100, "max_loss": max_loss,
            "pnl": pnl, "pnl_ts": pnl_ts,
            "ret_pct": pnl / max_loss if max_loss else 0.0,
        })
    print(f"  (no-breakout days: {no_breakout} | filtered out: {filtered} | "
          f"traded: {len(trades)})", flush=True)
    return trades


def compare_exits(trades):
    """One-line Kirk (let-expire) vs Arianne (50/130) comparison, on capital-at-risk."""
    if not trades:
        return
    risk = sum(t["max_loss"] for t in trades) / len(trades)
    kirk = sum(t["pnl"] for t in trades)
    aria = sum(t["pnl_ts"] for t in trades)
    kw = sum(1 for t in trades if t["pnl"] > 0) / len(trades)
    aw = sum(1 for t in trades if t["pnl_ts"] > 0) / len(trades)
    print("\n=== KIRK (let-expire) vs ARIANNE (50%/130%) — same trades ===")
    print(f"  Kirk:    win {kw:.0%}   total ${kirk:,.0f}   ({kirk/(risk*len(trades)):+.0%} on risk)")
    print(f"  Arianne: win {aw:.0%}   total ${aria:,.0f}   ({aria/(risk*len(trades)):+.0%} on risk)")


if __name__ == "__main__":
    import os
    if os.environ.get("IVOL_API_KEY"):
        frm = os.environ.get("BT_FROM", "2024-06-03")
        to = os.environ.get("BT_TO", "2024-06-14")
        print(f"Running REAL SPX 0DTE ORB backtest: {frm} -> {to}\n", flush=True)
        trades = run_orb_backtest(frm, to)
        assert isinstance(trades, list)
        if trades:
            import pandas as pd
            os.makedirs("results/spx", exist_ok=True)
            out = f"results/spx/orb_{frm}_to_{to}.csv"
            pd.DataFrame(trades).to_csv(out, index=False)
            print(f"\nSaved {len(trades)} trades -> {out}")
        report_chains(trades)
        compare_exits(trades)
    else:
        trades = run_orb_backtest_fake(_fake_days())
        assert len(trades) == 2, f"expected 2 trades (chop sits out), got {len(trades)}"
        assert trades[0]["direction"] == "bull"
        assert trades[0]["pnl"] == 300.0, trades[0]["pnl"]
        print("Task 8 OK (offline): fake loop still green\n")
        report_chains(trades)
