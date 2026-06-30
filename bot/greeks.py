# greeks.py — compute option delta from inputs we already have.
#
# We only use Python's built-in `math` module — no extra libraries.
# Later, if we switch to Schwab/ThetaData (which serve delta directly),
# we just stop calling bs_delta() and read their number instead.

from math import log, sqrt, erf, exp
from datetime import date


def norm_cdf(x):
    """Standard normal CDF — 'area under the bell curve to the left of x'.

    This is what turns a distance-in-std-devs into a probability.
    Built from math.erf so we need no scipy/numpy.
    """
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def years_to_expiry(expiration_str, today=None):
    """Convert an 'YYYY-MM-DD' expiration into time-to-expiry in YEARS.

    Black-Scholes measures time in years (T). 1 day ~= 1/365.
    We floor at half a day so a 0DTE doesn't divide-by-zero.
    """
    today = today or date.today()
    exp = date.fromisoformat(expiration_str)
    days = max((exp - today).days, 0.5)
    return days / 365.0


def bs_delta(option_type, spot, strike, sigma, T, r=0.04):
    """Black-Scholes delta.

    option_type : "call" or "put"
    spot   (S)  : current underlying price
    strike (K)  : the option's strike
    sigma  (σ)  : implied volatility (annualized, decimal — e.g. 0.12)
    T           : time to expiry in years
    r           : risk-free rate (tiny effect for 1DTE; 4% is fine)

    Returns delta: calls 0..+1, puts -1..0.
    """
    # Guard against bad inputs (zero IV/time show up for dead/illiquid strikes).
    if sigma <= 0 or T <= 0:
        return 0.0

    # d1 = how many (vol-scaled) std devs the strike is from the forward price.
    d1 = (log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))

    call_delta = norm_cdf(d1)
    if option_type == "call":
        return call_delta
    return call_delta - 1.0          # put delta (negative)


def bs_price(option_type, spot, strike, sigma, T, r=0.04):
    """Black-Scholes fair value of an option (per share).

    Same inputs as bs_delta. Returns the theoretical price. We need this so we
    can run it BACKWARDS (see implied_vol) to recover IV from a market price.
    """
    if T <= 0 or sigma <= 0:                       # no time/vol left -> just intrinsic value
        intrinsic = spot - strike if option_type == "call" else strike - spot
        return max(intrinsic, 0.0)

    d1 = (log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    if option_type == "call":
        return spot * norm_cdf(d1) - strike * exp(-r * T) * norm_cdf(d2)
    return strike * exp(-r * T) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def implied_vol(option_type, spot, strike, price, T, r=0.04):
    """Back out implied volatility from an option's market price.

    Black-Scholes price only goes UP as sigma rises, so we can binary-search
    (bisection): guess a sigma, see if the model price is too high or too low,
    halve the range, repeat. ~60 steps nails it to machine precision.

    Use this when the data feed gives us PRICES but not IV (e.g. if the chain
    endpoint omits it) — we recover IV, then feed it to bs_delta for strike
    selection. Returns 0.0 if the price is below intrinsic (a dead/bad quote).
    """
    if T <= 0 or price <= 0:
        return 0.0
    intrinsic = max((spot - strike) if option_type == "call" else (strike - spot), 0.0)
    if price <= intrinsic:                         # no time value -> IV undefined/zero
        return 0.0

    lo, hi = 1e-6, 5.0                             # search sigma in 0%..500%
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs_price(option_type, spot, strike, mid, T, r) > price:
            hi = mid                               # model too expensive -> lower vol
        else:
            lo = mid                               # model too cheap -> raise vol
    return 0.5 * (lo + hi)


if __name__ == "__main__":
    # Self-test: make a price with a KNOWN vol, then check implied_vol recovers it.
    S, K, T, true_sigma = 5000.0, 4950.0, 1 / 365, 0.15
    px = bs_price("put", S, K, true_sigma, T)
    recovered = implied_vol("put", S, K, px, T)
    print(f"true IV = {true_sigma:.4f}  ->  price ${px:.4f}  ->  recovered IV = {recovered:.4f}")
    print(f"delta of that put: {bs_delta('put', S, K, recovered, T):+.3f}")
