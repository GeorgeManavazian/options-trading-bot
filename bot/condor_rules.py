# condor_rules.py — the iron condor RULES ENGINE (v1)
#
# Job: given a live option chain, pick the 4 legs of an iron condor and
# report the box (strikes, premium collected, max profit, max loss).
#
# An iron condor = sell a put + buy a cheaper put below it (the put spread),
# AND sell a call + buy a cheaper call above it (the call spread). You collect
# premium and win if price stays between the two SHORT strikes at expiration.
#
# Run with:  .venv/bin/python bot/condor_rules.py

import yfinance as yf
from greeks import bs_delta, years_to_expiry


# ---- The rules (knobs we can tune later) ---------------------------------
OTM_PCT = 0.01        # %-OTM rule: short strikes ~1% from current price
OTM_DOLLARS = 5.0     # $-OTM rule: short strikes this many POINTS from spot (Kirk: $5)
TARGET_DELTA = 0.16   # delta rule: sell the ~16-delta strikes (~1 std dev out)
WING_WIDTH = 5.0      # long "wings" sit this many points beyond each short strike


def pick_condor(symbol="SPY", method="delta", otm_pct=OTM_PCT,
                target_delta=TARGET_DELTA, wing_width=WING_WIDTH, exp_index=1):
    """Pick the 4 condor legs from LIVE data (the yfinance wrapper).

    This just FETCHES a live chain and hands it to build_condor (the brain).
    exp_index : 0 = nearest expiration (often 0DTE), 1 = next out (~1DTE).
    """
    tk = yf.Ticker(symbol)
    expiration = tk.options[exp_index]      # exp_index=1 -> ~1 day to expiration
    chain = tk.option_chain(expiration)
    spot = tk.fast_info["last_price"]        # where the underlying trades now

    return build_condor(chain.puts, chain.calls, spot, expiration,
                        symbol=symbol, method=method, otm_pct=otm_pct,
                        target_delta=target_delta, wing_width=wing_width)


def build_condor(puts, calls, spot, expiration, symbol="SPY", method="delta",
                 otm_pct=OTM_PCT, otm_dollars=OTM_DOLLARS, target_delta=TARGET_DELTA,
                 wing_width=WING_WIDTH, today=None):
    """Pick the 4 condor legs from a chain you HAND it (the brain).

    Works on ANY chain — live from yfinance, or historical/fake for a
    backtest — as long as `puts` and `calls` are tables with the columns
    strike / bid / ask / impliedVolatility.

    method : "delta"      -> sell the strikes nearest target_delta
             "otm_dollar" -> sell strikes a fixed $ amount from spot (Kirk's rule)
             "otm_pct"     -> sell strikes a flat % from spot
    today  : the entry date (for time-to-expiry). None = today's date. When
             backtesting, pass the historical trade date.
    """
    T = years_to_expiry(expiration, today)   # time to expiry, in years

    # --- Choose the two SHORT strikes by the selected rule ---
    if method == "delta":
        short_put = strike_by_delta(puts, "put", target_delta, spot, T)
        short_call = strike_by_delta(calls, "call", target_delta, spot, T)
    elif method == "otm_dollar":
        short_put = nearest_strike(puts, spot - otm_dollars)
        short_call = nearest_strike(calls, spot + otm_dollars)
    else:  # "otm_pct"
        short_put = nearest_strike(puts, spot * (1 - otm_pct))
        short_call = nearest_strike(calls, spot * (1 + otm_pct))

    # Wings: a fixed width beyond each short strike, snapped to real strikes.
    long_put = nearest_strike(puts, short_put - wing_width)
    long_call = nearest_strike(calls, short_call + wing_width)

    return {
        "symbol": symbol,
        "expiration": expiration,
        "spot": spot,
        "method": method,
        # We SELL these (collect their bid):
        "short_put": leg(puts, short_put, "put", spot, T),
        "short_call": leg(calls, short_call, "call", spot, T),
        # We BUY these (pay their ask):
        "long_put": leg(puts, long_put, "put", spot, T),
        "long_call": leg(calls, long_call, "call", spot, T),
        "wing_width": wing_width,
    }


def nearest_strike(table, target):
    """Return the strike in `table` numerically closest to `target`."""
    idx = (table["strike"] - target).abs().idxmin()
    return float(table.loc[idx, "strike"])


def strike_by_delta(table, option_type, target_delta, spot, T):
    """Return the strike whose |delta| is closest to `target_delta`.

    We compute each strike's delta from its own implied volatility, then
    pick the nearest match. (target_delta is given as a positive number,
    e.g. 0.16, and compared against the delta's magnitude.)
    """
    best_strike, best_diff = None, float("inf")
    for _, row in table.iterrows():
        iv = float(row["impliedVolatility"])
        d = bs_delta(option_type, spot, float(row["strike"]), iv, T)
        diff = abs(abs(d) - target_delta)
        if diff < best_diff:
            best_diff, best_strike = diff, float(row["strike"])
    return best_strike


def leg(table, strike, option_type, spot, T):
    """Pull the row for a given strike; include its price fields and delta."""
    row = table.loc[table["strike"] == strike].iloc[0]
    iv = float(row["impliedVolatility"])
    return {
        "strike": strike,
        "bid": float(row["bid"]),
        "ask": float(row["ask"]),
        "delta": bs_delta(option_type, spot, strike, iv, T),
    }


def summarize(c):
    """Compute and print the economics of the chosen condor."""
    # Premium collected (priced at mid; see net_credit).
    credit = net_credit(c)

    # Risk is capped by the wing width. Per 1 contract = 100 shares.
    max_profit = credit * 100
    max_loss = (c["wing_width"] - credit) * 100

    print(f"=== IRON CONDOR on {c['symbol']}  (exp {c['expiration']}, method={c['method']}) ===")
    print(f"Underlying now: ${c['spot']:,.2f}\n")
    print(f"  BUY  put  {c['long_put']['strike']:>7.1f}   (ask {c['long_put']['ask']:.2f})                 <- lower wing")
    print(f"  SELL put  {c['short_put']['strike']:>7.1f}   (bid {c['short_put']['bid']:.2f})  delta {c['short_put']['delta']:+.2f}  <- short put")
    print(f"        .... profit zone: price stays between "
          f"{c['short_put']['strike']:.0f} and {c['short_call']['strike']:.0f} ....")
    print(f"  SELL call {c['short_call']['strike']:>7.1f}   (bid {c['short_call']['bid']:.2f})  delta {c['short_call']['delta']:+.2f}  <- short call")
    print(f"  BUY  call {c['long_call']['strike']:>7.1f}   (ask {c['long_call']['ask']:.2f})                 <- upper wing\n")

    print(f"Net premium collected:  ${credit*100:,.2f}  (${credit:.2f} x 100)")
    print(f"Max profit (best case): ${max_profit:,.2f}")
    print(f"Max loss  (worst case): ${max_loss:,.2f}")
    if max_loss > 0:
        print(f"Reward-to-risk:         {max_profit/max_loss:.2f} : 1")


def _mid(leg):
    """Midpoint of a leg's bid/ask — the realistic fair-value fill."""
    return (leg["bid"] + leg["ask"]) / 2.0


def net_credit(c):
    """Premium collected up front (per share), priced at the MID of each leg.

    A 4-leg condor is sent as ONE combo order near mid — you do NOT cross the
    full bid/ask on all four legs (that worst-case assumption made losses look
    ~$70/contract bigger than reality). Explicit slippage is applied on top in
    the backtest (Kirk's "mid minus 5 cents/leg" convention).
    """
    return (_mid(c["short_put"]) + _mid(c["short_call"])
            - _mid(c["long_put"]) - _mid(c["long_call"]))


def payoff_at(c, settle):
    """Profit/loss (in $, for 1 contract) if the underlying SETTLES at `settle`.

    You keep the full credit, then pay out on whichever spread goes against you.
    A put spread only hurts below its short strike; a call spread only above its.
    Each spread's loss is capped at its width.
    """
    credit = net_credit(c)

    # How far each short strike is breached, capped at the wing width.
    put_loss = min(max(c["short_put"]["strike"] - settle, 0.0), c["wing_width"])
    call_loss = min(max(settle - c["short_call"]["strike"], 0.0), c["wing_width"])

    per_share = credit - put_loss - call_loss
    return per_share * 100


if __name__ == "__main__":
    condor = pick_condor("SPY")
    summarize(condor)

    # Show the P&L across a few "what if it closes here?" scenarios.
    sp = condor["short_put"]["strike"]
    sc = condor["short_call"]["strike"]
    print("\n=== P&L if SPY settles at... ===")
    scenarios = [
        ("crash below lower wing", condor["long_put"]["strike"] - 2),
        ("just below short put",    sp - 1),
        ("dead center (in zone)",  (sp + sc) / 2),
        ("just above short call",   sc + 1),
        ("spike above upper wing",  condor["long_call"]["strike"] + 2),
    ]
    for label, price in scenarios:
        print(f"  ${price:>7.1f}  {label:<24}  ->  P&L ${payoff_at(condor, price):>8.2f}")
