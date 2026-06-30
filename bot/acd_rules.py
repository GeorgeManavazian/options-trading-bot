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


if __name__ == "__main__":
    # --- Task 2: a_value + 15-min opening range ---
    a = a_value(5000.0)                       # 0.18% of 5000
    assert abs(a - 9.0) < 1e-9, a
    path = [("09:30", 5005), ("09:38", 5010), ("09:44", 4998), ("09:45", 5002)]
    hi, lo = opening_range(path, "09:30", "09:45")
    assert hi == 5010 and lo == 4998, (hi, lo)
    print("Task 2 OK: a_value and 15-min opening range")
