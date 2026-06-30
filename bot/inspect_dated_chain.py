# inspect_dated_chain.py — pull ONE real 30-45 DTE SPX chain and eyeball it, so
# Plan 2's wrapper code matches the real data shape (strike spacing, liquidity,
# which expirations exist). Caches under a DTE-AWARE name so it never collides
# with the condor's 1DTE `SPX_<date>_m6.csv` cache (same endpoint, different DTE).
#
# Run with:  .venv/bin/python bot/inspect_dated_chain.py [YYYY-MM-DD]

import os
import sys
import time

import pandas as pd

from load_ivolai import COLUMN_MAP

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")
ENDPOINT = "/equities/eod/stock-opts-by-param"


def _load_key():
    """Read IVOL_API_KEY from the env, else from the project .env file."""
    key = os.environ.get("IVOL_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(env_path) as f:
        for line in f:
            if line.strip().startswith("IVOL_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("IVOL_API_KEY not found in env or .env")


def fetch_dated_chain(symbol, trade_date, dte_from=30, dte_to=45, moneyness=6.0):
    """Pull both sides of one day's 30-45 DTE chain; cache DTE-aware. Returns raw df."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(
        CACHE_DIR, f"{symbol}_{trade_date}_dte{dte_from}-{dte_to}_m{int(moneyness)}.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)

    import ivolatility as ivol
    ivol.setLoginParams(apiKey=_load_key())
    get = ivol.setMethod(ENDPOINT)
    sides = []
    for cp in ("C", "P"):
        sides.append(get(symbol=symbol, tradeDate=trade_date,
                         dteFrom=dte_from, dteTo=dte_to, cp=cp,
                         moneynessFrom=-moneyness, moneynessTo=moneyness))
        time.sleep(1.1)                      # 1 req/sec cap
    df = pd.concat(sides, ignore_index=True)
    df.to_csv(cache, index=False)
    return df


def inspect(trade_date):
    raw = fetch_dated_chain("SPX", trade_date)
    df = raw.rename(columns=COLUMN_MAP)
    spot = float(df["spot"].iloc[0])
    print(f"Trade date {trade_date}  |  underlying spot ${spot:,.2f}  |  {len(df)} rows\n")

    print("Expirations available (and their DTE):")
    for exp in sorted(df["expiration"].unique()):
        sub = df[df["expiration"] == exp]
        print(f"  {exp}   dte={int(sub['dte'].iloc[0])}   "
              f"{len(sub)} rows   strikes {sub['strike'].min():,.0f}-{sub['strike'].max():,.0f}")

    exp = sorted(df["expiration"].unique())[0]
    chain = df[df["expiration"] == exp]
    strikes = sorted(chain["strike"].unique())
    spacing = min(b - a for a, b in zip(strikes, strikes[1:])) if len(strikes) > 1 else 0
    print(f"\nNearest expiry {exp}: {len(strikes)} strikes, min spacing ${spacing:,.0f}")

    print(f"\nNear-ATM rows around ${spot:,.0f} (calls then puts):")
    print(f"  {'type':<5}{'strike':>9}{'bid':>9}{'ask':>9}{'iv':>8}")
    for typ in ("C", "P"):
        side = chain[chain["type"] == typ].copy()
        side["dist"] = (side["strike"] - spot).abs()
        for _, r in side.sort_values("dist").head(4).iterrows():
            print(f"  {typ:<5}{r['strike']:>9,.0f}{r['bid']:>9.2f}{r['ask']:>9.2f}{r['impliedVolatility']:>8.3f}")


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2024-08-01"
    inspect(date)
