# backtest_acd_0dte.py — EXPERIMENT: express the ACD signal (15-min opening range,
# A-held breakout, pivot trend filter) the way ORB does — a 0DTE credit spread sold in
# the signal's direction and held to expiry. Tests whether ACD's pickier entry beats
# Kirk's ORB entry at the premium-harvest game (the mechanism that actually worked).
#
# Reuses the tested ORB stack: build_acd_signal (the brain), the 0DTE intraday loader,
# orb_exits.exit_expire, and report_chains. Strike minute-bars for ACD's (tighter-range)
# strikes are pulled on demand and cached; needs IVOL_API_KEY for the first run.
#
# Run:  IVOL_API_KEY=... .venv/bin/python bot/backtest_acd_0dte.py
#       (optional slice:  BT_FROM=2023-07-03 BT_TO=2023-08-01 ...)

import os

from acd_rules import build_acd_signal
from run_acd_signal import daily_hlc
from orb_rules import nearest
from orb_exits import exit_expire
from backtest_chains import report_chains, yearly_report
from config import ACD_DEFAULT
import load_ivol_intraday as intra

SYM = "SPX"


def build_acd_0dte_plan(path, strikes, prev_hlc, expiration, profile, width, buffer=0.0):
    """ACD signal -> a 0DTE credit spread OUTSIDE the 15-min range. None if flat.

    Bullish (long) -> sell a PUT spread below the range; bearish (short) -> sell a
    CALL spread above it. Same strike placement as build_orb, but the ACD signal
    (hold-time + pivot filter) decides direction, and the range is the 15-min one.
    """
    sig = build_acd_signal(path, prev_hlc, a_pct=profile.a_pct, hold_min=profile.hold_min,
                           range_start=profile.range_start, range_end=profile.range_end,
                           cutoff=profile.cutoff)
    if sig["direction"] == "flat":
        return None
    high, low = sig["range_high"], sig["range_low"]
    if sig["direction"] == "long":            # bullish -> sell a PUT spread BELOW
        option_type = "put"
        below = [k for k in strikes if k < low - buffer]
        short_strike = max(below) if below else nearest(strikes, low)
        long_strike = nearest(strikes, short_strike - width)
    else:                                     # bearish -> sell a CALL spread ABOVE
        option_type = "call"
        above = [k for k in strikes if k > high + buffer]
        short_strike = min(above) if above else nearest(strikes, high)
        long_strike = nearest(strikes, short_strike + width)
    return {"direction": sig["direction"], "option_type": option_type,
            "short_strike": short_strike, "long_strike": long_strike,
            "width": abs(short_strike - long_strike), "entry_time": sig["entry_time"],
            "entry_spot": sig["entry_spot"], "expiration": expiration}


def run_acd_0dte(profile=ACD_DEFAULT, width=15.0, slippage_per_leg=0.0,
                 from_date=None, to_date=None):
    hlc = daily_hlc()
    days = sorted(hlc)
    trades, no_trade, prev = [], 0, None
    for D in days:
        in_window = (from_date is None or D >= from_date) and (to_date is None or D <= to_date)
        try:
            strikes, anchor = intra.fetch_0dte_chain(SYM, D)
            atm = min(strikes, key=lambda k: abs(k - anchor))
            path = intra.underlying_path(SYM, D, D, atm)
        except Exception:
            prev = None
            continue
        if prev is not None and in_window:
            plan = build_acd_0dte_plan(path, strikes, prev, D, profile, width)
            if plan is None:
                no_trade += 1
            else:
                try:
                    credit, _cs = intra.leg_close_series(
                        SYM, D, D, plan["short_strike"], plan["long_strike"],
                        plan["option_type"], plan["entry_time"])
                    credit -= 2 * slippage_per_leg
                    max_loss = (plan["width"] - credit) * 100
                    settle = hlc[D][2]
                    if max_loss > 0:
                        pnl = exit_expire(plan, credit, settle)
                        trades.append({
                            "date": D, "direction": plan["direction"],
                            "spot": plan["entry_spot"], "settle": settle,
                            "credit": credit * 100, "max_loss": max_loss,
                            "pnl": pnl, "ret_pct": pnl / max_loss})
                except Exception as e:
                    print(f"  skip {D}: {repr(e)[:60]}", flush=True)
        prev = hlc[D]

    print(f"\n(signal flat/no-trade days: {no_trade} | traded: {len(trades)})")
    report_chains(trades)
    if trades:
        yearly_report(trades, label="ACD 0DTE (let-expire)")
        for label, typ in (("PUT side (bullish)", "long"), ("CALL side (bearish)", "short")):
            sub = [t for t in trades if t["direction"] == typ]
            if sub:
                wins = sum(1 for t in sub if t["pnl"] > 0) / len(sub)
                tot = sum(t["ret_pct"] for t in sub)
                be = sum(1 for t in sub if t["pnl"] > 0)   # (context)
                print(f"  {label:<22} n={len(sub):>3}  win {wins:.0%}  "
                      f"total {tot:+.0%} on risk")
    return trades


if __name__ == "__main__":
    run_acd_0dte(from_date=os.environ.get("BT_FROM"), to_date=os.environ.get("BT_TO"))
