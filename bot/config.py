# config.py — your "trading profile". This is the ONE place that describes you:
# your account, how much you're willing to risk, and what you trade. Everything
# else (sizing, the backtest) reads from here. Tweak these values freely — we
# WILL adjust them as we tune the strategy.

from dataclasses import dataclass


@dataclass
class Profile:
    # --- What you trade (defaults = Kirk's 1DTE SPX spec) ---
    symbol: str = "SPX"            # "SPX" or "XSP" (mini = 1/10 size)
    strike_method: str = "otm_dollar"  # "otm_dollar" (Kirk), "delta", or "otm_pct"
    otm_dollars: float = 5.0       # short strikes $5 from spot (Kirk's near-ATM box)
    wing_width: float = 5.0        # $5-wide spreads
    target_delta: float = 0.16     # only used if strike_method == "delta"
    moneyness: float = 6.0         # +/- % strike band to pull from the data feed

    # --- Your account & risk ---
    account: float = 10_000.0      # your capital, in $
    risk_pct: float = 0.03         # max fraction of the account to risk PER TRADE (3%)


@dataclass
class ORBProfile:
    """Kirk's FINAL live ORB spec (Option Alpha "Opening Range Breakout" series).

    Asymmetric by side: the put side (bullish breakouts) is filtered harder than
    the call side (bearish breakouts). Defaults below = Kirk's exact settings.
    """
    symbol: str = "SPX"            # 0DTE SPX, cash-settled
    width: float = 15.0            # $15-wide spreads, both sides (Kirk beat $10)
    range_start: str = "09:30"     # opening range = first 60 minutes...
    range_end: str = "10:30"       # ...9:30-10:30 ET high/low
    cutoff: str = "12:00"          # latest entry ~ noon
    range_width_min: float = 0.002  # skip mornings whose range < 0.2%
    put_rr_floor: float = 0.10     # put side: >=10% return on risk
    call_rr_floor: float = 0.04    # call side: >=4% return on risk
    put_adx_min: float = 15.0      # put side only: ADX(14) >= 15
    moneyness: float = 6.0         # +/- % strike band to pull from the data feed

    # --- Your account & risk (same sizing layer as the condor) ---
    account: float = 10_000.0
    risk_pct: float = 0.03


# The profile the bot uses by default = Kirk's spec. Edit this or pass your own.
DEFAULT = Profile()

# Kirk's ORB spec, ready to pass to backtest_orb.run_orb_backtest().
ORB_KIRK = ORBProfile()

# Handy presets (examples — tune as we go):
KIRK = Profile()  # SPX, $5-OTM shorts, $5 wings — the canonical 1DTE strategy
WIDE_DELTA = Profile(strike_method="delta", target_delta=0.16, wing_width=50.0)  # our old (naive) version


@dataclass
class ACDProfile:
    """Mark Fisher's ACD on SPX, multi-day swing via options. Defaults = the
    design-spec anchors; we WILL sweep these (see strategies/ACD.md)."""
    symbol: str = "SPX"
    # --- signal (Plan 1) ---
    a_pct: float = 0.0018          # A distance = 0.18% of price (Fisher's S&P anchor)
    hold_min: float = 7.5          # breakout must hold half the 15-min range
    range_start: str = "09:30"
    range_end: str = "09:45"       # 15-minute opening range
    cutoff: str = "12:00"          # latest A entry
    # --- wrappers + data (Plans 2-3; parked here now) ---
    dte_from: int = 30             # buy options ~30-45 DTE for the swing
    dte_to: int = 45
    debit_width: float = 25.0      # debit-spread wing distance ($)
    credit_short_otm: float = 10.0 # credit-spread short strike this far OTM ($)
    credit_width: float = 25.0     # credit-spread wing distance ($)
    moneyness: float = 6.0         # +/- % strike band to pull from the feed
    # --- account & risk (same sizing layer) ---
    account: float = 10_000.0
    risk_pct: float = 0.03


# ACD swing spec, ready for Plans 2-3.
ACD_DEFAULT = ACDProfile()
