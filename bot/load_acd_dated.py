# load_acd_dated.py — read the big-pull dated chains (SPX_<date>_dte10-50_m10.csv),
# pick the entry expiration, and mark held legs — with the data-seam validation the
# reviews mandated (skip NaN/<=0 quotes; raise rather than emit a garbage position).
#
# Run with:  .venv/bin/python bot/load_acd_dated.py

import os

import pandas as pd

from load_ivolai import COLUMN_MAP

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")


_PUT = ["P", "put", "Put"]
_CALL = ["C", "call", "Call"]


def dated_chain_df(symbol, date, dte_from=10, dte_to=50, moneyness=10):
    """Read one day's cached dated chain (the big pull), columns renamed."""
    path = os.path.join(
        CACHE_DIR, f"{symbol}_{date}_dte{dte_from}-{dte_to}_m{moneyness}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return pd.read_csv(path).rename(columns=COLUMN_MAP)


def _valid(side):
    """Rows with a real two-sided quote (no NaN, bid & ask > 0)."""
    side = side.dropna(subset=["strike", "bid", "ask"])
    return side[(side["bid"] > 0) & (side["ask"] > 0)]


def pick_entry_chain(df, target_dte=35):
    """(puts, calls, spot, expiration) for the expiration nearest target_dte."""
    dtes = df.groupby("expiration")["dte"].first()
    expiration = (dtes - target_dte).abs().idxmin()
    chain = df[df["expiration"] == expiration]
    puts = _valid(chain[chain["type"].isin(_PUT)]).copy()
    calls = _valid(chain[chain["type"].isin(_CALL)]).copy()
    spot = float(chain["spot"].iloc[0])
    return puts, calls, spot, expiration


def mark_legs(df, expiration, legs):
    """net_exit = sum(long bid) - sum(short ask) at `expiration`. Conservative close.

    Raises ValueError if any leg has no valid (non-NaN, >0) quote that day.
    """
    chain = df[df["expiration"] == expiration]
    net = 0.0
    for leg in legs:
        types = _CALL if leg["type"] == "call" else _PUT
        row = chain[(chain["type"].isin(types)) & (chain["strike"] == leg["strike"])]
        if row.empty:
            raise ValueError(f"no row for {leg['type']} {leg['strike']} @ {expiration}")
        bid, ask = float(row["bid"].iloc[0]), float(row["ask"].iloc[0])
        if not (bid > 0 and ask > 0):
            raise ValueError(f"no quote for {leg['type']} {leg['strike']} @ {expiration}")
        net += bid if leg["side"] == "long" else -ask
    return net


def _mock_df():
    """Two expirations (dte 33 & 40), $5 grid, IVol column shape — offline."""
    rows = []
    for exp, dte in [("2024-09-03", 33), ("2024-09-10", 40)]:
        for k in [4990, 4995, 5000, 5005, 5010]:
            for cp in ("C", "P"):
                rows.append({"c_date": "2024-08-01", "expiration_date": exp, "dte": dte,
                             "price_strike": float(k), "call_put": cp,
                             "Bid": 20.0, "Ask": 21.0, "iv": 0.16,
                             "underlying_price": 5000.0})
    return pd.DataFrame(rows).rename(columns=COLUMN_MAP)


if __name__ == "__main__":
    df = _mock_df()
    puts, calls, spot, exp = pick_entry_chain(df, target_dte=35)
    assert exp == "2024-09-03", exp                 # dte 33 is nearest 35
    assert spot == 5000.0 and len(calls) == 5, (spot, len(calls))

    legs = [{"strike": 5000.0, "type": "call", "side": "long", "entry_price": 21.0},
            {"strike": 5005.0, "type": "call", "side": "short", "entry_price": 20.0}]
    net_exit = mark_legs(df, exp, legs)             # long bid 20 - short ask 21 = -1
    assert net_exit == -1.0, net_exit
    print("Task 1 OK: pick_entry_chain + mark_legs (with validation)")
