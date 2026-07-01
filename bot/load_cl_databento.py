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
    # For daily data, preserve the date from the index (midnight UTC -> ET conversion shifts dates)
    out = {}
    for ts, hi, lo, cl in zip(df.index, df["high"], df["low"], df["close"]):
        out[ts.strftime("%Y-%m-%d")] = (float(hi), float(lo), float(cl))
    return out


def roll_days_from_df(df):
    """ET dates whose instrument_id differs from the prior ET day's (contract roll)."""
    # For daily data, use the date from the index directly
    days = {}
    for ts, iid in zip(df.index, df["instrument_id"]):
        days[ts.strftime("%Y-%m-%d")] = int(iid)
    ordered = sorted(days)
    return {ordered[k] for k in range(1, len(ordered)) if days[ordered[k]] != days[ordered[k-1]]}


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
