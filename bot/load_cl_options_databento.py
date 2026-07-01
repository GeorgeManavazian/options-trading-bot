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
    rows.sort()
    return pd.DataFrame(rows, columns=["time","bid","ask"])


def definition_snapshot(year, month):
    """Cache+return the LO.OPT option universe for the first available day of year-month."""
    path = os.path.join(CACHE_DIR, f"CL_optdef_{year}-{month:02d}.csv")
    if os.path.exists(path):
        return pd.read_csv(path, dtype={"raw_symbol": str})
    start = f"{year}-{month:02d}-01"
    end_month = month % 12 + 1
    end_year = year + (1 if month == 12 else 0)
    end = f"{end_year}-{end_month:02d}-01"
    data = _client().timeseries.get_range(
        dataset="GLBX.MDP3", symbols=["LO.OPT"], stype_in="parent",
        schema="definition", start=start, end=end)
    df = data.to_df()
    df = df[df["instrument_class"].isin(["C","P"])].copy()
    df["exp"] = df["expiration"].astype(str).str[:10]
    # first available snapshot day only (definitions repeat daily; one snapshot is enough)
    first_day = df.index.min()
    df = df[df.index == first_day]
    out = df[["raw_symbol","instrument_class","strike_price","exp"]].reset_index(drop=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def _nearest(values, target):
    return min(values, key=lambda v: abs(v - target))


def resolve_legs(date, direction, entry_price, width=2.0, snapshot=None):
    if entry_price is None or entry_price <= 0:
        return None
    if snapshot is None:
        y, m = int(date[:4]), int(date[5:7])
        snapshot = definition_snapshot(y, m)
    ic = "C" if direction == "long" else "P"
    opt_type = "call" if direction == "long" else "put"
    df = snapshot[snapshot["instrument_class"] == ic]
    exps = sorted(e for e in df["exp"].unique() if e >= date)
    if not exps:
        return None
    exp = exps[0]
    strikes = sorted(df[df["exp"] == exp]["strike_price"].astype(float).unique())
    if not strikes:
        return None
    long_strike = _nearest(strikes, float(entry_price))
    short_target = long_strike + width if opt_type == "call" else long_strike - width
    short_strike = _nearest(strikes, short_target)
    if short_strike == long_strike:
        return None
    sub = df[df["exp"] == exp]
    def sym(strike):
        r = sub[abs(sub["strike_price"].astype(float) - strike) < 1e-6]
        return None if r.empty else str(r.iloc[0]["raw_symbol"])
    ls, ss = sym(long_strike), sym(short_strike)
    if ls is None or ss is None:
        return None
    return {"long_sym": ls, "short_sym": ss, "long_strike": long_strike,
            "short_strike": short_strike, "opt_type": opt_type, "kind": "debit_spread",
            "width": abs(short_strike - long_strike), "expiry": exp, "date": date}


if __name__ == "__main__":
    import pandas as pd

    # EST day: 14:00 UTC -> 09:00 EST, 14:05 -> 09:05, 21:30 -> 16:30 (dropped, outside window)
    est = pd.DataFrame({"bid_px_00":[2.01, 2.03, 9.9], "ask_px_00":[2.05, 2.06, 9.9]},
                       index=pd.to_datetime(["2024-01-10 14:00","2024-01-10 14:05","2024-01-10 21:30"], utc=True))
    est.index.name = "ts_event"
    out = option_bbo_by_et(est, "09:00", "16:00")
    assert list(out.columns) == ["time","bid","ask"], out.columns
    assert out["time"].tolist() == ["09:00","09:05"], out["time"].tolist()   # 16:30 dropped, sorted
    assert abs(out.iloc[0]["ask"] - 2.05) < 1e-9

    # EDT day (DST): 13:00 UTC -> 09:00 EDT (would be 08:00 EST -> dropped, so this proves DST offset)
    edt = pd.DataFrame({"bid_px_00":[1.50], "ask_px_00":[1.55]},
                       index=pd.to_datetime(["2024-03-11 13:00"], utc=True))
    edt.index.name = "ts_event"
    out_edt = option_bbo_by_et(edt, "09:00", "16:00")
    assert out_edt["time"].tolist() == ["09:00"], out_edt["time"].tolist()

    # a NaN/zero bid row is dropped
    bad = est.copy(); bad.loc[bad.index[0], "bid_px_00"] = 0.0
    out2 = option_bbo_by_et(bad, "09:00", "16:00")
    assert out2["time"].tolist() == ["09:05"], out2["time"].tolist()
    print("Task 1 OK: option_bbo_by_et (ET window, DST, sorted, drop bad quotes)")

    # --- Task 2: resolve_legs on a mock definition snapshot (offline) ---
    snap = pd.DataFrame({
        "raw_symbol": ["LON4 C7500","LON4 C7600","LON4 C7700","LON4 C7800",
                       "LON4 P7500","LON4 P7400","LON4 P7300",
                       "LOQ4 C7600"],
        "instrument_class": ["C","C","C","C","P","P","P","C"],
        "strike_price": [75.0,76.0,77.0,78.0,75.0,74.0,73.0,76.0],
        "exp": ["2024-06-14"]*7 + ["2024-07-17"],
    })
    lg = resolve_legs("2024-06-03","long",76.2,width=2.0,snapshot=snap)
    assert lg["opt_type"]=="call" and lg["expiry"]=="2024-06-14", lg
    assert lg["long_strike"]==76.0 and lg["short_strike"]==78.0, lg   # ATM 76, +2 -> 78
    assert lg["long_sym"]=="LON4 C7600" and lg["short_sym"]=="LON4 C7800", lg
    sg = resolve_legs("2024-06-03","short",75.1,width=2.0,snapshot=snap)
    assert sg["opt_type"]=="put" and sg["long_strike"]==75.0 and sg["short_strike"]==73.0, sg  # 75, -2 ->73
    assert resolve_legs("2024-12-31","long",76.0,snapshot=snap) is None, "no future expiry -> None"
    print("Task 2 OK: resolve_legs (nearest expiry, ATM long, width short, dir-aware)")
    print("ALL load_cl_options_databento self-tests passed")
