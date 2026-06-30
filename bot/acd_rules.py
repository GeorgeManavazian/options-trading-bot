# acd_rules.py — the ACD RULES ENGINE (the "brain"), data-source-agnostic.
#
# Mark Fisher's ACD on SPX: from a day's intraday path + yesterday's H/L/C,
# emit a daily signal (long/short/flat + entry + stop). Pure Python (lists/dicts,
# std-lib only) so it tests offline — the same seam as orb_rules.build_orb.
# See strategies/ACD.md and docs/superpowers/specs/2026-06-30-acd-bot-design.md.
#
# Run with:  .venv/bin/python bot/acd_rules.py

from orb_rules import opening_range, nearest


def a_value(price, pct=0.0018):
    """The ACD breakout distance: a fraction of price (Fisher's S&P anchor 0.18%).

    Deliberate tunable anchor — we sweep `pct` later. price is the opening-range
    midpoint (a proxy for 'today's level').
    """
    return float(price) * pct


def _to_min(hhmm):
    """'HH:MM' -> minutes since midnight (for hold-time arithmetic)."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def detect_a(path, high, low, a_val, range_end="09:45", hold_min=7.5,
             cutoff="12:00"):
    """First breakout beyond high+a_val (long) / low-a_val (short) that HOLDS.

    A bar after range_end (and at/before cutoff) that pierces the level is only a
    confirmed A if price stays beyond the level for >= hold_min minutes. Entry is
    the first bar at/after trigger + hold_min. Only the first confirmed A is
    returned (one A per day). Returns None if nothing holds by the cutoff.
    """
    up_level = float(high) + a_val
    dn_level = float(low) - a_val
    bars = sorted(path)                        # chronological by 'HH:MM'
    end_m, cut_m = _to_min(range_end), _to_min(cutoff)

    for t, spot in bars:
        tm = _to_min(t)
        if tm <= end_m or tm > cut_m:
            continue
        if spot >= up_level:
            side, level, beyond = "long", up_level, (lambda s: s >= up_level)
        elif spot <= dn_level:
            side, level, beyond = "short", dn_level, (lambda s: s <= dn_level)
        else:
            continue

        # Confirm: every bar within the hold window stays beyond; the first bar
        # at/after tm + hold_min is the entry.
        confirm = None
        held = True
        for t2, spot2 in bars:
            tm2 = _to_min(t2)
            if tm2 < tm:
                continue
            if tm2 - tm >= hold_min:
                confirm = (t2, float(spot2))
                break
            if not beyond(spot2):              # snapped back inside the window
                held = False
                break
        if held and confirm is not None:
            return {"direction": side, "trigger_time": t,
                    "entry_time": confirm[0], "entry_spot": confirm[1]}
    return None


def pivot_range(high, low, close):
    """Fisher's pivot band from a prior period's H/L/C. Returns (low, high) band.

        pivot  = (H + L + C) / 3
        second = (H + L) / 2
        diff   = | pivot - second |
        band   = pivot ± diff
    """
    pivot = (float(high) + float(low) + float(close)) / 3.0
    second = (float(high) + float(low)) / 2.0
    diff = abs(pivot - second)
    return (pivot - diff, pivot + diff)


def pivot_bias(spot, band):
    """Where today's price sits vs the pivot band -> trend gate."""
    low_band, high_band = band
    if spot > high_band:
        return "bull"
    if spot < low_band:
        return "bear"
    return "neutral"


def _flat(band, high, low):
    return {"direction": "flat", "entry_time": None, "entry_spot": None,
            "stop_B": None, "pivot_band": band, "range_high": high,
            "range_low": low}


def build_acd_signal(path, prev_hlc, a_pct=0.0018, hold_min=7.5,
                     range_start="09:30", range_end="09:45", cutoff="12:00"):
    """One day's ACD signal: a held A that AGREES with yesterday's pivot bias.

    prev_hlc = (high, low, close) of the prior day. Returns a Signal dict; the
    direction is 'flat' when there's no held A or the A fights the pivot.
    """
    high, low = opening_range(path, range_start, range_end)
    band = pivot_range(*prev_hlc)
    mid = (high + low) / 2.0
    a = detect_a(path, high, low, a_value(mid, a_pct),
                 range_end=range_end, hold_min=hold_min, cutoff=cutoff)
    if a is None:
        return _flat(band, high, low)

    bias = pivot_bias(a["entry_spot"], band)
    agree = (a["direction"] == "long" and bias == "bull") or \
            (a["direction"] == "short" and bias == "bear")
    if not agree:
        return _flat(band, high, low)

    stop_B = low if a["direction"] == "long" else high   # opposite range edge
    return {"direction": a["direction"], "entry_time": a["entry_time"],
            "entry_spot": a["entry_spot"], "stop_B": stop_B,
            "pivot_band": band, "range_high": high, "range_low": low}


def rolling_3day_pivot(hlc_list):
    """Pivot band from the trailing (up to) 3 days: highest high, lowest low,
    last close. Fisher's multi-day trailing-stop band."""
    window = hlc_list[-3:]
    high = max(h for h, l, c in window)
    low = min(l for h, l, c in window)
    close = window[-1][2]
    return pivot_range(high, low, close)


def pivot_trailing_exit(direction, day_close, band):
    """Exit a multi-day hold when the day's close falls back through the band
    against the position. Long exits below the band low; short above the high."""
    low_band, high_band = band
    if direction == "long":
        return day_close < low_band
    if direction == "short":
        return day_close > high_band
    return True                                # 'flat' should never be held


if __name__ == "__main__":
    # --- Task 2: a_value + 15-min opening range ---
    a = a_value(5000.0)                       # 0.18% of 5000
    assert abs(a - 9.0) < 1e-9, a
    path = [("09:30", 5005), ("09:38", 5010), ("09:44", 4998), ("09:45", 5002)]
    hi, lo = opening_range(path, "09:30", "09:45")
    assert hi == 5010 and lo == 4998, (hi, lo)
    print("Task 2 OK: a_value and 15-min opening range")

    # --- Task 3: detect_a (breakout + hold-time) ---
    hi, lo, av = 5010.0, 4998.0, 9.0          # up_level 5019, dn_level 4989
    # Holds: crosses up at 09:50 and stays above 5019 through >=7.5 min.
    hold = [("09:46", 5012), ("09:50", 5020), ("09:52", 5021),
            ("09:55", 5022), ("09:58", 5023)]
    a = detect_a(hold, hi, lo, av)
    assert a["direction"] == "long", a
    assert a["trigger_time"] == "09:50", a
    assert a["entry_time"] == "09:58", a       # first bar >= 09:50 + 7.5 min
    assert a["entry_spot"] == 5023.0, a

    # Whipsaw: crosses up at 09:50 then snaps back inside at 09:52 (<7.5 min) -> None.
    whip = [("09:46", 5012), ("09:50", 5020), ("09:52", 5000)]
    assert detect_a(whip, hi, lo, av) is None, "whipsaw must be rejected"

    # Down side: crosses below 4989 and holds.
    down = [("09:46", 4995), ("09:50", 4988), ("09:52", 4987),
            ("09:58", 4986)]
    ad = detect_a(down, hi, lo, av)
    assert ad["direction"] == "short" and ad["entry_time"] == "09:58", ad

    # No trigger: stays inside the box -> None.
    inside = [("09:46", 5005), ("09:50", 5008), ("10:00", 5002)]
    assert detect_a(inside, hi, lo, av) is None
    print("Task 3 OK: detect_a confirms holds, rejects whipsaws, handles both sides")

    # --- Task 4: pivot range + bias (Fisher's formula) ---
    band = pivot_range(5050.0, 4990.0, 5030.0)
    # pivot=(5050+4990+5030)/3=5023.333; second=(5050+4990)/2=5020; diff=3.333
    assert abs(band[0] - 5020.0) < 1e-3, band
    assert abs(band[1] - 5026.667) < 1e-3, band
    assert pivot_bias(5030.0, band) == "bull"      # above the band
    assert pivot_bias(5000.0, band) == "bear"      # below the band
    assert pivot_bias(5024.0, band) == "neutral"   # inside the band
    print("Task 4 OK: pivot_range matches Fisher's formula; bias gates correctly")

    # --- Task 5: build_acd_signal (A held + pivot agreement) ---
    # 15-min range 4998-5010; A up holds to 5023 by 09:58; pivot band below -> bull.
    up_path = [("09:30", 5005), ("09:40", 5010), ("09:44", 4998),
               ("09:50", 5020), ("09:52", 5021), ("09:58", 5023)]
    prev = (4990.0, 4950.0, 4980.0)            # band well below 5023 -> bull agree
    sig = build_acd_signal(up_path, prev)
    assert sig["direction"] == "long", sig
    assert sig["entry_time"] == "09:58", sig
    assert sig["stop_B"] == 4998.0, sig        # opposite range edge

    # Same A up, but pivot band ABOVE the entry spot -> bias not bull -> flat.
    prev_high = (5100.0, 5030.0, 5090.0)       # band above 5023 -> bear/neutral
    sig2 = build_acd_signal(up_path, prev_high)
    assert sig2["direction"] == "flat", sig2

    # No A at all (stays inside) -> flat.
    chop = [("09:30", 5005), ("09:50", 5008), ("10:00", 5002)]
    assert build_acd_signal(chop, prev)["direction"] == "flat"
    print("Task 5 OK: build_acd_signal requires a held A that agrees with the pivot")

    # --- Task 6: 3-day rolling pivot trailing stop ---
    days = [(5050.0, 4990.0, 5030.0), (5070.0, 5010.0, 5060.0),
            (5080.0, 5020.0, 5075.0)]
    rband = rolling_3day_pivot(days)
    # highest high 5080, lowest low 4990, last close 5075
    assert abs(rband[0] - pivot_range(5080.0, 4990.0, 5075.0)[0]) < 1e-9, rband
    # Long position: exit when the close drops below the band low.
    assert pivot_trailing_exit("long", rband[0] - 1, rband) is True
    assert pivot_trailing_exit("long", rband[1] + 1, rband) is False
    # Short position: exit when the close rises above the band high.
    assert pivot_trailing_exit("short", rband[1] + 1, rband) is True
    assert pivot_trailing_exit("short", rband[0] - 1, rband) is False
    print("Task 6 OK: rolling pivot trailing stop triggers on a close back through the band")
