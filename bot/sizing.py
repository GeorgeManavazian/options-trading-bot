# sizing.py — the position-sizing brain. Turns "risk X% of my account" into an
# actual number of condors to trade. The bot calls this so it can never oversize.

import math


def position_size(max_loss_per_condor, account, risk_pct):
    """How many condors to trade so total risk stays within risk_pct of account.

    max_loss_per_condor : the collateral one condor ties up (its max loss, $).
    account             : your capital ($).
    risk_pct            : max fraction of the account to risk per trade (0.03 = 3%).

    Returns (contracts, pct_used, note):
      contracts  - whole number of condors to trade (0 if one is already too big)
      pct_used   - the % of the account actually at risk at that size
      note       - empty if fine; otherwise WHY you can't trade (too big)
    """
    if max_loss_per_condor <= 0 or account <= 0:
        return 0, 0.0, "bad inputs"

    budget = risk_pct * account                       # $ you're willing to risk per trade
    contracts = math.floor(budget / max_loss_per_condor)

    if contracts < 1:
        one_pct = max_loss_per_condor / account
        return 0, 0.0, (f"one condor risks {one_pct:.0%} of the account — over your "
                        f"{risk_pct:.0%} limit. Use a smaller instrument (XSP) or "
                        f"narrower wings.")

    pct_used = contracts * max_loss_per_condor / account
    return contracts, pct_used, ""


if __name__ == "__main__":
    # Quick self-test across the cases we discussed for a $10k account.
    cases = [
        ("3-wide XSP", 270, 10_000, 0.03),
        ("5-wide XSP", 450, 10_000, 0.03),
        ("SPX 50-wide", 4_485, 10_000, 0.03),
        ("SPX on $250k", 4_485, 250_000, 0.03),
    ]
    for label, ml, acct, rp in cases:
        n, pct, note = position_size(ml, acct, rp)
        print(f"{label:<14} risk ${ml:>6,} / ${acct:>7,} @ {rp:.0%}  ->  "
              f"{n} contract(s), {pct:.1%} at risk   {note}")
