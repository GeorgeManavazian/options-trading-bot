# backtest_acd_cl.py — Phase-1 CL signal backtest: run the FULL ACD engine on crude and
# measure the directional edge per family + per year (no options). Offline on cache.
# Run: .venv/bin/python bot/backtest_acd_cl.py
import os
import statistics
from collections import Counter
from itertools import accumulate

from acd_micro import build_day
from acd_macro import DayEntry, BREAKOUT, FADES
from diag_full_signal import collect_signals, _edge
from acd_cl import CL
from load_cl_databento import (pull_cl_minutes, pull_cl_daily,
                               cl_day_path, cl_daily_hlc, cl_roll_days,
                               bars_by_et_day, _read_cache)
from backtest import max_drawdown

START, END = "2010-06-06", "2026-06-29"

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
                    "usd": (exit_px - entry) * sign * POINT_VALUE, "tick": tick})
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


def build_cl_history(min_csv, daily_csv):
    """Ordered DayEntry stream for the full engine. Roll days (instrument_id change) are kept
    in the sequence so the NEXT day still gets its correct same-contract prior for the pivot,
    but roll days emit NO signals (their own prior is cross-contract). This prevents a roll gap
    from fabricating a signal AND from contaminating the following day's pivot."""
    hlc = cl_daily_hlc(daily_csv)
    rolls = cl_roll_days(daily_csv)
    all_days = sorted(hlc)
    all_bars = bars_by_et_day(_read_cache(min_csv))     # read + transform the minute CSV ONCE
    hist = []
    for pos, D in enumerate(all_days):
        if D in rolls:
            continue                                    # skip signal emission; day still counts as a prior for D+1
        prior = hlc[all_days[pos - 1]] if pos > 0 else hlc[D]   # correct same-contract prior (the roll day itself)
        bars = all_bars.get(D, [])
        if not bars:
            continue
        try:
            dr = build_day(D, bars, prior, CL)
        except Exception:
            continue
        hist.append(DayEntry(D, hlc[D], dr))
    return hist


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
    for hold, tag in [(0, "same-day"), (1, "+1d"), (5, "+5d")]:
        print(f"\n########## HOLD {tag} ##########")
        report_pnl(pnl_trades(micro, dates, idx, closes, hold))
    return hist, micro, macro


if __name__ == "__main__":
    # self-test: build_cl_history is robust to empty/roll days on a mock cache (offline).
    import pandas as pd, tempfile
    from load_cl_databento import _write_cache
    dd = tempfile.mkdtemp()
    # 2024-01-12 is the roll (instrument_id 1->2); 2024-01-15 continues id=2 (NOT a roll)
    didx = pd.to_datetime(["2024-01-10","2024-01-11","2024-01-12","2024-01-15"], utc=True)
    dfd = pd.DataFrame({"open":[70,71,72,73],"high":[75.,76.,77.,78.],"low":[69.,70.,71.,72.],
                        "close":[74.,75.,76.,77.],"instrument_id":[1,1,2,2]}, index=didx); dfd.index.name="ts_event"
    # 14:00 UTC = 09:00 EST; add bars for 01-15 so it gets processed
    midx = pd.to_datetime(["2024-01-10 14:00","2024-01-10 14:20","2024-01-11 14:00","2024-01-11 14:20",
                           "2024-01-15 14:00","2024-01-15 14:20"], utc=True)
    dfm = pd.DataFrame({"open":[70]*6,"high":[70]*6,"low":[70]*6,"close":[74.,74.5,75.,75.5,76.,76.5],
                        "instrument_id":[1,1,1,1,2,2]}, index=midx); dfm.index.name="ts_event"
    dcsv=os.path.join(dd,"d.csv"); mcsv=os.path.join(dd,"m.csv"); _write_cache(dfd,dcsv); _write_cache(dfm,mcsv)
    h = build_cl_history(mcsv, dcsv)
    # (a) roll day must emit no signals
    assert all(e.date != "2024-01-12" for e in h), "roll day excluded"
    # (b) the day AFTER the roll must use the roll day (2024-01-12) as its prior, NOT 2024-01-11
    e15 = next((e for e in h if e.date == "2024-01-15"), None)
    assert e15 is not None, "2024-01-15 missing from history"
    hlc12 = (77., 71., 76.)  # 2024-01-12 HLC (high, low, close) from dfd above
    bars15 = bars_by_et_day(dfm)["2024-01-15"]
    dr_expected = build_day("2024-01-15", bars15, hlc12, CL)
    assert e15.day_result.or_high == dr_expected.or_high and e15.day_result.or_low == dr_expected.or_low, \
        f"01-15 OR mismatch: got [{e15.day_result.or_low},{e15.day_result.or_high}] want [{dr_expected.or_low},{dr_expected.or_high}]"
    print(f"Task 4 self-test OK: build_cl_history skipped roll day, {len(h)} entries, 01-15 prior=roll-day HLC")

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

    # if the full-history cache is present, run the real diagnostic too
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data_cache",
                                   f"CL_1d_{START}_{END}.csv")):
        dc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1d_{START}_{END}.csv")
        mc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1m_{START}_{END}.csv")
        run(mc, dc)
