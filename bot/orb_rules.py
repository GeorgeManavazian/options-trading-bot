# orb_rules.py — the ORB RULES ENGINE (the "brain"), data-source-agnostic.
#
# Job: from a day's intraday underlying path, compute the 9:30-10:30 opening
# range, detect a breakout, and pick the credit spread to sell. Pure Python
# (lists/dicts) so it tests offline — the same "seam" as condor_rules.build_condor.
#
# Run with:  .venv/bin/python bot/orb_rules.py


def opening_range(path, start="09:30", end="10:30"):
    """High and low of the underlying during the opening window [start, end].

    path : list of (t, spot) where t is "HH:MM" (zero-padded) and spot is float.
    Returns (high, low). The "box" the breakout must escape.
    """
    window = [spot for t, spot in path if start <= t <= end]
    if not window:
        raise ValueError(f"no price bars in opening window {start}-{end}")
    return float(max(window)), float(min(window))


def detect_breakout(path, high, low, range_end="10:30", cutoff="12:00"):
    """First breakout strictly after range_end and at/before cutoff.

    Above `high` -> bullish; below `low` -> bearish. Whichever happens first in
    time wins (a whipsaw is classified by its FIRST breach). None if the price
    never escapes the box by the cutoff.
    """
    for t, spot in sorted(path):              # chronological by "HH:MM"
        if t <= range_end or t > cutoff:
            continue
        if spot > high:
            return {"direction": "bull", "time": t, "spot": float(spot)}
        if spot < low:
            return {"direction": "bear", "time": t, "spot": float(spot)}
    return None


def nearest(strikes, target):
    """Listed strike numerically closest to target."""
    return float(min(strikes, key=lambda k: abs(k - target)))


def build_orb(path, strikes, expiration, width=15.0, buffer=0.0,
              range_start="09:30", range_end="10:30", cutoff="12:00"):
    """Pick the ORB credit spread from a day's intraday path + listed strikes.

    Returns a trade plan dict, or None if there's no breakout by the cutoff.
    The brain only chooses strikes/direction — the CREDIT comes later from the
    option data at the entry minute (see backtest_orb / orb_exits).
    """
    high, low = opening_range(path, range_start, range_end)
    bo = detect_breakout(path, high, low, range_end, cutoff)
    if bo is None:
        return None

    # Kirk's template: the SHORT strike is the first listed strike strictly
    # OUTSIDE the opening range on the safe side (further OTM than the box edge).
    if bo["direction"] == "bull":             # sell a PUT spread BELOW the range
        option_type = "put"
        below = [k for k in strikes if k < low - buffer]
        short_strike = max(below) if below else nearest(strikes, low)
        long_strike = nearest(strikes, short_strike - width)
    else:                                     # bear -> sell a CALL spread ABOVE
        option_type = "call"
        above = [k for k in strikes if k > high + buffer]
        short_strike = min(above) if above else nearest(strikes, high)
        long_strike = nearest(strikes, short_strike + width)

    mid = (high + low) / 2
    return {
        "direction": bo["direction"],
        "option_type": option_type,
        "short_strike": short_strike,
        "long_strike": long_strike,
        "width": abs(short_strike - long_strike),
        "entry_time": bo["time"],
        "entry_spot": bo["spot"],
        "range_high": high,
        "range_low": low,
        "range_width_pct": (high - low) / mid if mid else 0.0,
        "expiration": expiration,
    }


def orb_filters_ok(plan, credit, adx, is_fomc, range_width_min=0.002,
                   put_rr_floor=0.10, call_rr_floor=0.04, put_adx_min=15.0):
    """Kirk's FINAL filter stack — asymmetric by side. Returns (ok, reason).

    Both sides : opening range width must be >= range_width_min (0.2%).
    PUT side (bullish breakout): return-on-risk >= 10%, ADX >= 15, SKIP FOMC days.
    CALL side (bearish breakout): return-on-risk >= 4%, no ADX gate, TRADE THROUGH
                                  FOMC (Kirk found Fed days were "juiced up").
    return-on-risk = credit / max_loss, where max_loss = width - credit (per share).
    """
    if plan["range_width_pct"] < range_width_min:
        return False, f"range {plan['range_width_pct']:.2%} < {range_width_min:.1%}"

    max_loss = plan["width"] - credit
    rr = credit / max_loss if max_loss > 0 else 0.0

    if plan["option_type"] == "put":          # bullish breakout
        if rr < put_rr_floor:
            return False, f"RR {rr:.0%} < {put_rr_floor:.0%} (put)"
        if adx is None or adx < put_adx_min:
            return False, f"ADX {adx} < {put_adx_min} (put)"
        if is_fomc:
            return False, "FOMC (put side skips)"
    else:                                     # bearish breakout (call) — trade through FOMC
        if rr < call_rr_floor:
            return False, f"RR {rr:.0%} < {call_rr_floor:.0%} (call)"
    return True, ""


if __name__ == "__main__":
    # A morning that ranges between 5000 and 5010 in the first hour.
    path = [("09:30", 5005), ("09:45", 5010), ("10:00", 4998),
            ("10:15", 5000), ("10:30", 5002), ("10:45", 5025)]
    hi, lo = opening_range(path)
    assert hi == 5010, hi
    assert lo == 4998, lo
    print("Task 1 OK: opening_range high/low correct")

    # Bullish: first bar after 10:30 to break is above the high (5010).
    bull = detect_breakout(path, 5010, 4998)
    assert bull == {"direction": "bull", "time": "10:45", "spot": 5025}, bull

    # Bearish: a path that breaks DOWN through the low first.
    bear_path = [("09:30", 5005), ("10:30", 5002), ("10:45", 4990)]
    bear = detect_breakout(bear_path, 5010, 4998)
    assert bear == {"direction": "bear", "time": "10:45", "spot": 4990}, bear

    # No breakout: stays inside the box through the cutoff -> None.
    chop = [("09:30", 5005), ("10:30", 5002), ("11:00", 5004), ("12:00", 5001)]
    assert detect_breakout(chop, 5010, 4998) is None

    # Whipsaw: breaks UP first (10:45) even though it later dives -> bull, 10:45.
    whip = [("10:30", 5002), ("10:45", 5025), ("11:00", 4900)]
    assert detect_breakout(whip, 5010, 4998)["direction"] == "bull"
    print("Task 2 OK: detect_breakout handles bull/bear/chop/whipsaw")

    strikes = [4950, 4960, 4970, 4980, 4990, 5000, 5010, 5020, 5030, 5040]
    # Reuse `path` (bull breakout at 10:45, range 4998-5010).
    plan = build_orb(path, strikes, expiration="2024-06-03", width=20.0)
    assert plan["direction"] == "bull"
    assert plan["option_type"] == "put"
    assert plan["short_strike"] == 4990, plan["short_strike"]   # first strike BELOW low 4998
    assert plan["long_strike"] == 4970, plan["long_strike"]     # 20 below the short
    assert plan["entry_time"] == "10:45"
    assert abs(plan["range_width_pct"] - 12 / 5004) < 1e-9, plan["range_width_pct"]

    # Bear breakout -> call spread ABOVE the range high. Opening window reaches
    # 5012 (high); short call = first strike ABOVE 5012 -> 5020; breaks DOWN at 10:45.
    bear_path = [("09:30", 5008), ("10:00", 5012), ("10:30", 5002), ("10:45", 4990)]
    bplan = build_orb(bear_path, strikes, expiration="2024-06-03", width=20.0)
    assert bplan["option_type"] == "call"
    assert bplan["short_strike"] == 5020, bplan["short_strike"]  # first strike above 5012
    assert bplan["long_strike"] == 5040, bplan["long_strike"]

    # No breakout -> None. Box is 5002-5005; later bars stay inside it.
    chop = [("09:30", 5005), ("10:30", 5002), ("11:00", 5004), ("12:00", 5003)]
    assert build_orb(chop, strikes, expiration="2024-06-03") is None
    print("Task 3 OK: build_orb picks the right side, strikes, and sits out chop")

    # --- Kirk's filter stack (orb_filters_ok) ---
    putp = {"option_type": "put", "width": 20.0, "range_width_pct": 0.0024}
    assert orb_filters_ok(putp, 3.0, adx=20, is_fomc=False)[0] is True    # RR 18%, ADX ok
    assert orb_filters_ok(putp, 3.0, adx=10, is_fomc=False)[0] is False   # ADX<15
    assert orb_filters_ok(putp, 3.0, adx=20, is_fomc=True)[0] is False    # put skips FOMC
    assert orb_filters_ok(putp, 1.0, adx=20, is_fomc=False)[0] is False   # RR 5.3%<10%

    callp = {"option_type": "call", "width": 20.0, "range_width_pct": 0.0024}
    # Call side: 4% RR floor, NO ADX gate, TRADES THROUGH FOMC.
    assert orb_filters_ok(callp, 1.0, adx=None, is_fomc=True)[0] is True   # RR 5.3%>=4%, FOMC ok
    assert orb_filters_ok(callp, 0.5, adx=None, is_fomc=False)[0] is False # RR 2.6%<4%

    tight = {"option_type": "call", "width": 20.0, "range_width_pct": 0.001}
    assert orb_filters_ok(tight, 5.0, adx=None, is_fomc=False)[0] is False # range<0.2%
    print("Task 3b OK: orb_filters_ok enforces Kirk's asymmetric put/call filters")
