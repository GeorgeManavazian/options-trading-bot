# load_cl_options_databento.py — resolve crude (LO) option legs from Databento definitions
# and pull/cache their bbo-1m NBBO bars, reshaped for acd_fade_pricing. Pure transforms are
# network-free + self-tested; pull functions hit the API and cache to data_cache/.
# Run: .venv/bin/python bot/load_cl_options_databento.py
import os

import pandas as pd

from load_cl_databento import _client, _read_cache, _write_cache, CACHE_DIR, ET


def option_bbo_by_et(df, session_open="09:00", session_close="16:00"):
    """Raw bbo-1m df (tz-aware UTC index, bid_px_00/ask_px_00) -> DataFrame[time,bid,ask] in ET,
    RTH-windowed, sorted, dropping NaN/<=0 quotes."""
    if df.empty:
        return pd.DataFrame(columns=["time","bid","ask"])
    et = df.tz_convert(ET) if df.index.tz is not None else df.tz_localize("UTC").tz_convert(ET)
    rows = []
    for ts, bid, ask in zip(et.index, et["bid_px_00"], et["ask_px_00"]):
        hhmm = ts.strftime("%H:%M")
        if session_open <= hhmm <= session_close and pd.notna(bid) and pd.notna(ask) \
                and bid > 0 and ask > 0:
            rows.append((hhmm, float(bid), float(ask)))
    return pd.DataFrame(rows, columns=["time","bid","ask"])


if __name__ == "__main__":
    import pandas as pd

    idx = pd.to_datetime([
        "2024-01-10 14:00:00",  # 09:00 EST
        "2024-01-10 14:05:00",  # 09:05 EST
        "2024-01-10 21:30:00",  # 16:30 EST -> outside window
        "2024-03-11 13:00:00",  # 09:00 EDT (DST)
    ], utc=True)
    raw = pd.DataFrame({"bid_px_00":[2.01, 2.03, 9.9, 1.50],
                        "ask_px_00":[2.05, 2.06, 9.9, 1.55]}, index=idx)
    raw.index.name = "ts_event"
    out = option_bbo_by_et(raw, "09:00", "16:00")
    assert list(out.columns) == ["time","bid","ask"], out.columns
    assert out["time"].tolist() == ["09:00","09:05","09:00"], out["time"].tolist()  # 16:30 dropped
    assert abs(out.iloc[0]["ask"] - 2.05) < 1e-9
    # a NaN/zero bid row is dropped
    raw2 = raw.copy(); raw2.loc[raw2.index[0], "bid_px_00"] = 0.0
    out2 = option_bbo_by_et(raw2, "09:00", "16:00")
    assert out2["time"].tolist() == ["09:05","09:00"], out2["time"].tolist()
    print("Task 1 OK: option_bbo_by_et (ET window, DST, drop bad quotes)")
    print("ALL load_cl_options_databento self-tests passed")
