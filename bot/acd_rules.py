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
