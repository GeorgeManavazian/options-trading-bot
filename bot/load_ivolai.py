# load_ivolai.py — fetch historical SPX option chains from IVolatility's API and
# hand them to our engine (the API sibling of load_ivol.py).
#
# Uses the official `ivolatility` library. The endpoint that returns a FULL chain
# WITH bid/ask + IV in one call is:
#     /equities/eod/stock-opts-by-param
# It requires cp ('C'/'P'), a dte range, and a moneyness range — so we call it
# once per side and stitch the two together. Every row also carries the
# underlying price, so we get the entry spot for free.
#
# Auth:  export IVOL_API_KEY="your-key"
# Run:   .venv/bin/python bot/load_ivolai.py     (real single-day test if key set,
#                                                 else an offline mock test)

import os
from datetime import date

import pandas as pd

from condor_rules import build_condor, summarize

API_KEY = os.environ.get("IVOL_API_KEY", "")
ENDPOINT = "/equities/eod/stock-opts-by-param"

# IVolatility column  ->  our engine's column name.
COLUMN_MAP = {
    "call_put": "type",                 # "C" / "P"
    "price_strike": "strike",
    "Bid": "bid",
    "Ask": "ask",
    "iv": "impliedVolatility",          # IVol gives IV directly — no solver needed
    "expiration_date": "expiration",
    "c_date": "date",                   # the trade/entry date
    "underlying_price": "spot",         # SPX level that day (entry spot)
}


CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")

# Entry-time variants of the chain endpoint. "eod" = end of day (~4pm);
# "1545" = the 3:45pm snapshot (closest feed to Kirk's 3:30pm entry).
ENDPOINTS = {
    "eod": ("/equities/eod/stock-opts-by-param", ""),
    "1545": ("/equities/eod/stock-opts-by-param-1545", "_1545"),
}


def fetch_chain_df(symbol, trade_date, dte_from=1, dte_to=4, moneyness=6.0, entry="eod"):
    """Pull one trading day's option chain (both sides) as one DataFrame.

    entry : "eod" (~4pm close) or "1545" (3:45pm — near Kirk's 3:30 entry).
    CACHED to disk per (symbol, date, moneyness, entry): once pulled, read from
    data_cache/ forever after — so experiments re-run with ZERO API calls.

    dte 1..4 (not just 1) so Fridays still find the next trading day's expiry
    over the weekend; parse_chain then keeps the NEAREST expiration.
    """
    endpoint, tag = ENDPOINTS[entry]
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_{trade_date}_m{int(moneyness)}{tag}.csv")
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path)

    if not API_KEY:
        raise RuntimeError("Set IVOL_API_KEY first:  export IVOL_API_KEY=...")
    import time
    import ivolatility as ivol
    ivol.setLoginParams(apiKey=API_KEY)
    get = ivol.setMethod(endpoint)
    sides = []
    for cp in ("C", "P"):
        sides.append(get(symbol=symbol, tradeDate=trade_date,
                         dteFrom=dte_from, dteTo=dte_to, cp=cp,
                         moneynessFrom=-moneyness, moneynessTo=moneyness))
        time.sleep(1.1)                 # respect Builder's 1-request/second limit
    df = pd.concat(sides, ignore_index=True)
    df.to_csv(cache_path, index=False)  # cache for instant re-runs
    return df


def parse_chain(df, entry_date=None):
    """Normalize a chain DataFrame and slice to ONE day's ~1DTE chain.

    Returns (puts, calls, spot, expiration, entry_date) — exactly what
    build_condor wants. Spot comes from the chain's underlying_price column.
    """
    df = df.rename(columns=COLUMN_MAP)

    if entry_date is None:
        entry_date = sorted(df["date"].unique())[0]
    day = df[df["date"] == entry_date]

    future_exps = sorted(e for e in day["expiration"].unique() if e > entry_date)
    expiration = future_exps[0]
    chain = day[day["expiration"] == expiration]

    puts = chain[chain["type"].isin(["P", "put", "Put"])].copy()
    calls = chain[chain["type"].isin(["C", "call", "Call"])].copy()
    spot = float(chain["spot"].iloc[0])
    return puts, calls, spot, expiration, entry_date


def load_chain(symbol, trade_date, **kw):
    """Fetch + parse one trading day's ~1DTE chain (the real path)."""
    return parse_chain(fetch_chain_df(symbol, trade_date, **kw))


def _mock_chain_df():
    """A pretend chain (one SPX 1DTE day) in IVolatility's column shape — offline."""
    mids = {4900: 9, 4925: 13, 4950: 18, 4975: 24, 5000: 30,
            5025: 24, 5050: 18, 5075: 13, 5100: 9}
    rows = []
    for strike, mid in mids.items():
        for cp in ("P", "C"):
            rows.append({"c_date": "2024-06-03", "expiration_date": "2024-06-04",
                         "price_strike": float(strike), "call_put": cp,
                         "Bid": mid - 0.5, "Ask": mid + 0.5, "iv": 0.15,
                         "underlying_price": 5000.0})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    if API_KEY:
        # Real single-day test against IVolatility.
        puts, calls, spot, expiration, entry_date = load_chain("SPX", "2024-06-03")
        print(f"REAL chain: entry {entry_date}, expiry {expiration}, spot ${spot:,.2f}, "
              f"{len(puts)} puts + {len(calls)} calls.\n")
    else:
        puts, calls, spot, expiration, entry_date = parse_chain(_mock_chain_df())
        print(f"(no key) MOCK chain: entry {entry_date}, expiry {expiration}, "
              f"spot ${spot:,.2f}, {len(puts)} puts + {len(calls)} calls.\n")

    condor = build_condor(puts, calls, spot, expiration, symbol="SPX",
                          wing_width=50, today=date.fromisoformat(entry_date))
    summarize(condor)
