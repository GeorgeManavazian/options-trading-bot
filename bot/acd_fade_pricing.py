# acd_fade_pricing.py — pure pricing + exit for DEBIT fade structures (0DTE/overnight).
# Entry debit from real intraday NBBO bars; settle at expiry intrinsic from the
# underlying close; optional intraday target/stop for the 0DTE exit comparison.
# No network -> offline __main__ self-tests. Run: .venv/bin/python bot/acd_fade_pricing.py


def _by_time(bars):
    """{time(str): row} from a minute-bar DataFrame (columns time/bid/ask)."""
    return {str(r["time"]): r for _, r in bars.iterrows()}


def spread_entry(long_bars, short_bars, entry_time):
    """Net debit at the first bar with time >= entry_time. Long pays ask; short
    (None for a long option) receives bid. Returns (debit_per_share, entry_t)."""
    L = _by_time(long_bars)
    times = sorted(t for t in L if t >= entry_time)
    if short_bars is not None:
        S = _by_time(short_bars)
        times = [t for t in times if t in S]
    if not times:
        raise ValueError(f"no fillable bar at/after {entry_time}")
    t = times[0]
    debit = float(L[t]["ask"])
    if short_bars is not None:
        debit -= float(S[t]["bid"])
    return debit, t


def expire_value(structure, settle):
    """Per-share intrinsic value of the debit structure at expiry."""
    typ, lk = structure["opt_type"], structure["long_strike"]
    if structure["kind"] == "long_option":
        return max(settle - lk, 0.0) if typ == "call" else max(lk - settle, 0.0)
    w = structure["width"]                        # debit spread
    if typ == "call":                             # bull call: long lk, short lk+w
        return min(max(settle - lk, 0.0), w)
    return min(max(lk - settle, 0.0), w)          # bear put: long lk, short lk-w


def close_value(structure, long_row, short_row):
    """Per-share proceeds to close now (sell the structure): long.bid - short.ask."""
    v = float(long_row["bid"])
    if structure["kind"] == "debit_spread":
        v -= float(short_row["ask"])
    return v


def exit_target_stop(debit, value_series, settle_value, target=0.5, stop=0.5):
    """Walk (time, close_value) bars; first to reach +target*debit profit or
    -stop*debit loss ends the trade at that value; else settle_value."""
    for t, v in sorted(value_series):
        if v - debit >= target * debit:           # profit target
            return v
        if debit - v >= stop * debit:             # stop
            return v
    return settle_value


if __name__ == "__main__":
    import pandas as pd

    lb = pd.DataFrame({"time": ["10:00", "10:01"], "bid": [30, 31], "ask": [32, 33]})
    sb = pd.DataFrame({"time": ["10:00", "10:01"], "bid": [18, 19], "ask": [20, 21]})
    debit, t = spread_entry(lb, sb, "10:00")
    assert t == "10:00" and abs(debit - 14.0) < 1e-9, (debit, t)   # 32 - 18
    d2, _ = spread_entry(lb, None, "10:00")
    assert d2 == 32.0, d2                                          # long option = ask
    try:
        spread_entry(lb, sb, "23:59"); assert False
    except ValueError:
        pass
    print("OK spread_entry")

    cs = {"kind": "debit_spread", "opt_type": "call", "long_strike": 5000, "width": 25}
    assert expire_value(cs, 5030) == 25.0 and expire_value(cs, 5010) == 10.0
    assert expire_value(cs, 4990) == 0.0
    ps = {"kind": "debit_spread", "opt_type": "put", "long_strike": 5000, "width": 25}
    assert expire_value(ps, 4970) == 25.0 and expire_value(ps, 4990) == 10.0
    lo = {"kind": "long_option", "opt_type": "call", "long_strike": 5000}
    assert expire_value(lo, 5040) == 40.0 and expire_value(lo, 4960) == 0.0
    print("OK expire_value")

    assert close_value(cs, {"bid": 22}, {"ask": 8}) == 14.0
    assert close_value(lo, {"bid": 40}, None) == 40.0
    print("OK close_value")

    # debit 14; target 0.5 -> exit when value>=21; stop 0.5 -> exit when value<=7
    assert exit_target_stop(14, [("10:05", 16), ("10:10", 22)], 25) == 22   # target
    assert exit_target_stop(14, [("10:05", 10), ("10:10", 6)], 0) == 6      # stop
    assert exit_target_stop(14, [("10:05", 15), ("10:10", 16)], 25) == 25   # settle
    print("OK exit_target_stop")
    print("All acd_fade_pricing self-tests passed.")
