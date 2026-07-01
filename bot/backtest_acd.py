# backtest_acd.py — race the 3 wrappers on the identical ACD signal over 3 yrs.
# Per trade: entry-day dated chain -> build all 3 wrappers -> simulate the multi-day
# hold (3-day pivot trailing stop / expiry / entry-day B) -> P&L. Report per wrapper:
# risk-adjusted return (total / max drawdown), Sharpe, win rate, per-year, slippage.
#
# Run with:  .venv/bin/python bot/backtest_acd.py
#   (offline self-test by default; set IVOL_API_KEY + RUN_REAL=1 for the real 3yr run)

from acd_rules import rolling_3day_pivot, pivot_trailing_exit


def simulate_hold(direction, position, expiration, entry_date, day_list, hlc, mark_fn):
    """Walk the position forward from entry_date. Exit on (1) expiry, (2) 3-day pivot
    trailing stop closing back through the band, or (3) entry-day B is folded in by the
    caller via the signal's stop_B check before calling. Returns (pnl, exit_date, reason).

    mark_fn(date, expiration, legs) -> net_exit or None. On a None (marking gap) we carry
    the most recent good mark; a trade that never marks returns (None, None, "no_mark").
    """
    entry_cost = position["entry_cost"]
    legs = position["legs"]
    held = [d for d in day_list if entry_date < d <= expiration]

    # trailing window of (H,L,C) up to and including the entry day
    recent = [hlc[d] for d in day_list if d <= entry_date and d in hlc][-3:]
    last_mark = mark_fn(entry_date, expiration, legs)     # entry-day mark (may be None)

    def _pnl(net_exit):
        return round((net_exit - entry_cost) * 100, 2)

    for d in held:
        m = mark_fn(d, expiration, legs)
        if m is not None:
            last_mark = m
        if d >= expiration:                              # (1) expiry
            return (_pnl(last_mark) if last_mark is not None else None,
                    d, "expiry" if last_mark is not None else "no_mark")
        if d in hlc:
            band = rolling_3day_pivot(recent) if recent else None
            if band and pivot_trailing_exit(direction, hlc[d][2], band):  # (2) pivot stop
                return (_pnl(last_mark) if last_mark is not None else None,
                        d, "pivot_stop" if last_mark is not None else "no_mark")
            recent = (recent + [hlc[d]])[-3:]

    # held to the last available day -> mark there
    return (_pnl(last_mark) if last_mark is not None else None,
            held[-1] if held else entry_date,
            "end" if last_mark is not None else "no_mark")


if __name__ == "__main__":
    # A long position; pivot band sits below entry; a later day closes back through it.
    pos = {"legs": [{"strike": 5000.0, "type": "call", "side": "long", "entry_price": 20.0}],
           "entry_cost": 20.0, "max_loss": 2000.0}
    days = ["2024-08-01", "2024-08-02", "2024-08-05", "2024-08-06"]
    hlc = {"2024-08-01": (5005, 4995, 5000), "2024-08-02": (5010, 5000, 5008),
           "2024-08-05": (5012, 5002, 5009), "2024-08-06": (5006, 4980, 4985)}
    # mark_fn: option worth 25 (in the money) on the exit day.
    marks = {"2024-08-06": 25.0}
    mark_fn = lambda d, e, legs: marks.get(d)

    pnl, xd, reason = simulate_hold("long", pos, "2024-09-03", "2024-08-01",
                                    days, hlc, mark_fn)
    # exits 2024-08-06 when close 4985 drops through the rising pivot band; pnl=(25-20)*100
    assert reason == "pivot_stop" and xd == "2024-08-06", (reason, xd)
    assert pnl == 500.0, pnl
    print("Task 3 OK: simulate_hold exits on the 3-day pivot trailing stop")
