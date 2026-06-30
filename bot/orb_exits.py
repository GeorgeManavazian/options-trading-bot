# orb_exits.py — settle an ORB credit spread two ways: Kirk's let-it-expire, and
# the 50%-profit / 130%-stop active version. Pure Python (no data fetching) so it
# tests offline. P&L returned in $ for ONE contract (x100), like condor payoff_at.
#
# Run with:  .venv/bin/python bot/orb_exits.py


def exit_expire(plan, credit, settle):
    """P&L ($, 1 contract) holding the spread to the 0DTE close at `settle`.

    Keep the full credit, then pay out only if the short strike is breached, with
    the loss capped at the spread width. A put spread hurts BELOW its short; a
    call spread ABOVE its short.
    """
    width = plan["width"]
    if plan["option_type"] == "put":
        loss = min(max(plan["short_strike"] - settle, 0.0), width)
    else:                                     # call spread
        loss = min(max(settle - plan["short_strike"], 0.0), width)
    return (credit - loss) * 100


def exit_target_stop(plan, credit, close_series, settle, target=0.5, stop=1.3):
    """P&L ($, 1 contract) actively managing to a profit target / stop loss.

    Walk the spread's cost-to-close minute by minute. First bar to reach the
    profit target (profit >= target*credit) or the stop (loss >= stop*credit)
    ends the trade there. If neither fires by the close, settle at expiry.
    Loss is capped at the spread width.
    """
    for t, close_price in sorted(close_series):
        profit = credit - close_price            # per share, if we buy it back now
        if profit >= target * credit:
            return profit * 100
        loss = close_price - credit
        if loss >= stop * credit:
            return -min(loss, plan["width"]) * 100
    return exit_expire(plan, credit, settle)     # never triggered -> hold to expiry


if __name__ == "__main__":
    # Bull put spread: short 5000 / long 4980 (20 wide), $3.00 credit.
    plan = {"option_type": "put", "short_strike": 5000, "long_strike": 4980,
            "width": 20.0}
    # Settles ABOVE the short put -> keep full credit. 3.00 * 100 = 300.
    assert exit_expire(plan, 3.0, 5050) == 300.0, exit_expire(plan, 3.0, 5050)
    # Settles 5 below the short (4995): lose 5/share, net 3-5=-2 -> -200.
    assert exit_expire(plan, 3.0, 4995) == -200.0, exit_expire(plan, 3.0, 4995)
    # Crashes below the long wing (4960): max loss = width-credit = 17 -> -1700.
    assert exit_expire(plan, 3.0, 4960) == -1700.0, exit_expire(plan, 3.0, 4960)

    # Bear call spread: short 5010 / long 5030, $3.00 credit.
    cplan = {"option_type": "call", "short_strike": 5010, "long_strike": 5030,
             "width": 20.0}
    assert exit_expire(cplan, 3.0, 4950) == 300.0      # below short call -> full credit
    assert exit_expire(cplan, 3.0, 5015) == -200.0     # 5 above short -> -2/share
    print("Task 4 OK: exit_expire payoff correct for put & call spreads")

    # Put spread, $4 credit, 20 wide. Target=50% -> exit when profit>=2 (close<=2).
    pplan = {"option_type": "put", "short_strike": 5000, "long_strike": 4980,
             "width": 20.0}
    hit_target = [("11:00", 3.5), ("11:30", 2.0), ("12:00", 1.0)]   # 2.0 -> profit 2
    assert exit_target_stop(pplan, 4.0, hit_target, settle=4999) == 200.0

    # Stop=130% -> exit when loss>=5.2 (close>=9.2). 10.0 hits it: loss 6 -> -600.
    hit_stop = [("11:00", 6.0), ("11:30", 10.0)]
    assert exit_target_stop(pplan, 4.0, hit_stop, settle=4990) == -600.0

    # Neither triggers -> fall back to expiry. Settle 5050 -> full credit 400.
    no_trigger = [("11:00", 4.5), ("12:00", 4.2)]
    assert exit_target_stop(pplan, 4.0, no_trigger, settle=5050) == 400.0
    print("Task 5 OK: exit_target_stop honors target, stop, and expiry fallback")
