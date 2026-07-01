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

    # if the full-history cache is present, run the real diagnostic too
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data_cache",
                                   f"CL_1d_{START}_{END}.csv")):
        dc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1d_{START}_{END}.csv")
        mc = os.path.join(os.path.dirname(__file__), "..", "data_cache", f"CL_1m_{START}_{END}.csv")
        run(mc, dc)
