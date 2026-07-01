# acd_options.py — ③ the OPTIONS OVERLAY. Maps an ACD Setup (from ①/②: direction, conviction,
# horizon, setup-name) to an option POSITION via a pluggable Policy, reusing acd_wrappers. This is
# where the strategy becomes options (the "options improve risk/return over stock" thesis). It does
# NOT pull chains, pick the expiration, mark, or compute P&L — that's ④ (the backtest).
#
# Spec: docs/superpowers/specs/2026-07-01-acd-options-overlay.md
# Run:  .venv/bin/python bot/acd_options.py
from dataclasses import dataclass

from acd_wrappers import build_long_option, build_debit_spread, build_credit_spread
from sizing import position_size

FADES = {"failed_a", "failed_a_pivot", "failed_c"}          # mean-reversion (strongest edge)
MACRO = {"reversal_trade", "trt", "sushi"}                  # multi-day edge
# everything else = the breakout family (weak on SPX -> express as premium)


@dataclass
class Policy:
    dte_intraday: int = 0
    dte_overnight: int = 2
    dte_multiday: int = 30
    fade_structure: str = "debit_spread"
    breakout_structure: str = "credit_spread"
    macro_high_structure: str = "long_option"
    macro_low_structure: str = "debit_spread"
    high_conv: int = 3
    debit_width: float = 25.0
    credit_short_otm: float = 10.0
    credit_width: float = 25.0


DEFAULT_POLICY = Policy()


def horizon_of(setup):
    return "multiday" if setup.name in MACRO else setup.horizon


def dte_target(setup, policy=DEFAULT_POLICY):
    h = horizon_of(setup)
    table = {"intraday": policy.dte_intraday, "overnight": policy.dte_overnight,
             "multiday": policy.dte_multiday}
    if h not in table:
        raise ValueError(f"unknown horizon {h!r} for setup {setup.name!r}")
    return table[h]


def choose_structure(setup, policy=DEFAULT_POLICY):
    if setup.name in FADES:
        return policy.fade_structure
    if setup.name in MACRO:
        return (policy.macro_high_structure if setup.conviction >= policy.high_conv
                else policy.macro_low_structure)
    return policy.breakout_structure


_BUILDERS = {
    "long_option": lambda sig, p, c, sp, e, pol: build_long_option(sig, p, c, sp, e),
    "debit_spread": lambda sig, p, c, sp, e, pol: build_debit_spread(sig, p, c, sp, e, width=pol.debit_width),
    "credit_spread": lambda sig, p, c, sp, e, pol: build_credit_spread(
        sig, p, c, sp, e, short_otm=pol.credit_short_otm, width=pol.credit_width),
}


def express(setup, puts, calls, spot, expiration, policy=DEFAULT_POLICY):
    """Map a Setup to an option Position (uniform acd_wrappers dict + overlay metadata)."""
    structure = choose_structure(setup, policy)
    if structure not in _BUILDERS:
        raise ValueError(f"unknown structure {structure!r} (policy misconfigured)")
    sig = {"direction": setup.direction}
    pos = _BUILDERS[structure](sig, puts, calls, spot, expiration, policy)
    pos.update(setup=setup.name, conviction=setup.conviction,
               horizon=horizon_of(setup), dte_target=dte_target(setup, policy))
    return pos


def size_position(max_loss, account, risk_pct, conviction, max_conviction=5):
    """Contracts to trade; the risk budget scales with conviction (Fisher: size up on confluence).
    Returns (contracts, pct_of_account_at_risk, note) from sizing.position_size."""
    frac = risk_pct * (0.4 + 0.6 * conviction / max_conviction)   # 40%..100% of the risk cap
    return position_size(max_loss, account, frac)


# ---------------------------------------------------------------- self-tests
if __name__ == "__main__":
    import pandas as pd
    from acd_micro import Setup

    def _chain():
        rp, rc = [], []
        for k in range(4900, 5101, 5):
            call = max(1.0, (5100 - k) * 0.4 + 2)
            put = max(1.0, (k - 4900) * 0.4 + 2)
            rc.append({"strike": float(k), "bid": call - 0.5, "ask": call + 0.5})
            rp.append({"strike": float(k), "bid": put - 0.5, "ask": put + 0.5})
        return pd.DataFrame(rp), pd.DataFrame(rc), 5000.0, "2024-09-05"

    puts, calls, spot, exp = _chain()
    mk = lambda name, direction, conv, horizon="intraday": Setup(
        name, direction, "10:00", 5000.0, 4990.0, conv, horizon, {})

    # fade -> debit spread, intraday, 0DTE
    p = express(mk("failed_a", "long", 1), puts, calls, spot, exp)
    assert p["wrapper"] == "debit_spread" and p["horizon"] == "intraday" and p["dte_target"] == 0, p
    print("OK: fade -> debit spread (0DTE)")

    # fade overnight -> dte 2
    p = express(mk("failed_c", "short", 1, "overnight"), puts, calls, spot, exp)
    assert p["dte_target"] == 2, p
    print("OK: overnight fade -> 2 DTE")

    # high-conviction macro reversal -> long option, multiday, 30 DTE
    p = express(mk("reversal_trade", "short", 3), puts, calls, spot, exp)
    assert p["wrapper"] == "long_option" and p["horizon"] == "multiday" and p["dte_target"] == 30, p
    print("OK: high-conv macro reversal -> long option (30 DTE)")

    # low-conviction macro sushi -> debit spread, multiday
    p = express(mk("sushi", "long", 2), puts, calls, spot, exp)
    assert p["wrapper"] == "debit_spread" and p["horizon"] == "multiday", p
    print("OK: low-conv macro -> debit spread")

    # breakout -> credit spread
    p = express(mk("a_held", "long", 2), puts, calls, spot, exp)
    assert p["wrapper"] == "credit_spread", p
    print("OK: breakout -> credit spread (premium)")

    # conviction sizing scales up
    n1, _, _ = size_position(1000, 100_000, 0.03, 1)
    n5, _, _ = size_position(1000, 100_000, 0.03, 5)
    assert n5 > n1 and n1 >= 1, (n1, n5)
    print(f"OK: conviction sizing ({n1} -> {n5} contracts)")

    print("\nAll ACD options-overlay self-tests passed.")
