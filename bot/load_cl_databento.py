# load_cl_databento.py — pull + cache CL crude-oil futures from Databento (CME GLBX.MDP3)
# and reshape into what the ACD engine consumes. Pure transforms are network-free and
# self-tested; pull functions (Task 2) touch the API and cache to data_cache/.
#
# Auth: DATABENTO_API_KEY in .env.  Run: .venv/bin/python bot/load_cl_databento.py
import os

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
    """Daily Databento df -> {date: (High, Low, Close)} (ET calendar date).

    Assumes the daily df is midnight-UTC indexed (Databento timestamps daily bars at
    00:00:00 UTC of the trading date).  We do NOT tz_convert to ET here because
    converting midnight UTC -> ET would shift every date back by one day, producing
    2024-06-02 instead of 2024-06-03, etc.
    """
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


# ---------------------------------------------------------------------------
# Task 2: Databento API pull + CSV cache + offline reader functions
# ---------------------------------------------------------------------------

def _client():
    key = ""
    env = os.path.join(os.path.dirname(__file__), "..", ".env")
    for line in open(env):
        if line.startswith("DATABENTO_API_KEY"):
            key = line.strip().split("=", 1)[1].strip()
    import databento as db
    return db.Historical(key)


def _write_cache(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path)                        # ts_event index (UTC ISO) + columns


def _read_cache(path):
    df = pd.read_csv(path, index_col="ts_event", parse_dates=["ts_event"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def _pull(schema, start, end, tag):
    path = os.path.join(CACHE_DIR, f"CL_{tag}_{start}_{end}.csv")
    if os.path.exists(path):
        return path
    data = _client().timeseries.get_range(
        dataset="GLBX.MDP3", symbols=["CL.c.0"], stype_in="continuous",
        schema=schema, start=start, end=end)
    _write_cache(data.to_df(), path)
    return path


def pull_cl_minutes(start, end):
    return _pull("ohlcv-1m", start, end, "1m")


def pull_cl_daily(start, end):
    return _pull("ohlcv-1d", start, end, "1d")


def cl_day_path(date, min_csv):
    return bars_by_et_day(_read_cache(min_csv)).get(date, [])


def cl_daily_hlc(daily_csv):
    return daily_hlc_from_df(_read_cache(daily_csv))


def cl_roll_days(daily_csv):
    return roll_days_from_df(_read_cache(daily_csv))


if __name__ == "__main__":
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

    # --- Task 2: round-trip a mock df through the CSV cache helpers ---
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "CL_1d_x.csv")
    _write_cache(d, p)
    back = _read_cache(p)
    assert daily_hlc_from_df(back)["2024-01-11"] == (76.0, 70.0, 75.0), "cache round-trip HLC"
    assert cl_roll_days(p) == {"2024-01-12"}, "cache round-trip rolls"
    print("Task 2 OK: cache write/read round-trip")
