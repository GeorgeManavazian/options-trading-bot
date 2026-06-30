# load_ivol.py — turn an IVolatility CSV export into chains our engine can eat.
#
# This is the ONLY file that knows IVolatility's exact column names. Everything
# downstream (build_condor, payoff_at) works on our OWN tidy names. So if the
# real download's headers differ slightly from this mock, we fix ONE thing:
# COLUMN_MAP below. The engine never changes.
#
# Run with:  .venv/bin/python bot/load_ivol.py

import os
from datetime import date

import pandas as pd

from condor_rules import build_condor, summarize

# --- The translation layer: IVolatility's column name -> our engine's name ----
# (left = whatever the CSV header says; right = what condor_rules expects.)
COLUMN_MAP = {
    "call/put": "type",                 # "P" / "C"
    "strike": "strike",
    "bid": "bid",
    "ask": "ask",
    "iv": "impliedVolatility",          # IVol hands us IV directly — no solver needed
    "expiration": "expiration",
    "date": "date",                     # the trade/entry date
    "stock price for iv": "spot",       # the underlying (SPX) level that day
}

SAMPLE = os.path.join(os.path.dirname(__file__), "sample_data", "ivol_sample.csv")


def load_chain(path, entry_date=None):
    """Read an IVolatility CSV and return ONE day's ~1DTE chain.

    Returns (puts, calls, spot, expiration, entry_date) where puts/calls are
    tables with strike / bid / ask / impliedVolatility — exactly what
    build_condor wants. We rename columns first, then slice to a single entry
    date and its NEAREST future expiration (that's the ~1DTE chain).
    """
    raw = pd.read_csv(path)
    df = raw.rename(columns=COLUMN_MAP)

    # Default to the first date in the file if none asked for.
    if entry_date is None:
        entry_date = sorted(df["date"].unique())[0]
    day = df[df["date"] == entry_date]

    # The 1DTE expiration = the nearest expiration AFTER the entry date.
    future_exps = sorted(e for e in day["expiration"].unique() if e > entry_date)
    expiration = future_exps[0]
    chain = day[day["expiration"] == expiration]

    puts = chain[chain["type"].isin(["P", "put", "Put"])].copy()
    calls = chain[chain["type"].isin(["C", "call", "Call"])].copy()
    spot = float(chain["spot"].iloc[0])
    return puts, calls, spot, expiration, entry_date


if __name__ == "__main__":
    puts, calls, spot, expiration, entry_date = load_chain(SAMPLE)

    print(f"Loaded IVolatility chain: entry {entry_date}, expiry {expiration}, "
          f"spot ${spot:,.2f}, {len(puts)} puts + {len(calls)} calls.\n")

    # SPX strikes sit 25 apart, so the wings need to be WIDE (a 5-pt wing would
    # snap onto the short strike itself). This is a real per-underlying knob.
    condor = build_condor(puts, calls, spot, expiration, symbol="SPX",
                          wing_width=50, today=date.fromisoformat(entry_date))
    summarize(condor)
