# pull_acd_data.py — THE BIG PULL. Fetch the dated 10-50 DTE SPX chain (moneyness
# +/-10%) for every trading day in our cached 3-yr window, so Plan 3's backtest can
# (a) build entry positions on the 314 ACD trade days AND (b) mark held positions
# day-by-day as the trailing stop runs. One wide daily chain serves both: the entry
# strikes (30-45 DTE, near ATM) and the held strikes (fixed at entry, drifting in
# moneyness as the index moves) all fall inside dte 10-50 / +/-10%.
#
# Cached DTE-aware (SPX_<date>_dte10-50_m10.csv) — no collision with the condor's
# SPX_<date>_m6.csv. RESUMABLE: skips days already cached, so it can stop/restart
# across sessions and only pulls what's missing.
#
# Run (background):  .venv/bin/python bot/pull_acd_data.py

import os
import glob

from inspect_dated_chain import fetch_dated_chain

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")
SYM = "SPX"
DTE_FROM, DTE_TO, MONEY = 10, 50, 10


def trading_days():
    """Every trading day we have cached (one 0dte file per day = one trading day)."""
    days = set()
    for p in glob.glob(os.path.join(CACHE_DIR, f"{SYM}_*_0dte_m*.csv")):
        days.add(os.path.basename(p).split("_")[1])
    return sorted(days)


def already_cached(D):
    return os.path.exists(
        os.path.join(CACHE_DIR, f"{SYM}_{D}_dte{DTE_FROM}-{DTE_TO}_m{MONEY}.csv"))


if __name__ == "__main__":
    days = trading_days()
    todo = [D for D in days if not already_cached(D)]
    print(f"Big pull: {len(days)} trading days total, {len(todo)} still to pull "
          f"(dte {DTE_FROM}-{DTE_TO}, moneyness +/-{MONEY}%)", flush=True)

    done = err = 0
    for i, D in enumerate(todo, 1):
        try:
            df = fetch_dated_chain(SYM, D, DTE_FROM, DTE_TO, MONEY)   # ~2.2s (C+P, throttled)
            done += 1
            if i % 20 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] {D}: {len(df)} rows  "
                      f"(pulled {done}, errors {err})", flush=True)
        except Exception as e:
            err += 1
            print(f"  [{i}/{len(todo)}] FAIL {D}: {repr(e)[:90]}", flush=True)

    print(f"DONE: pulled {done}, errors {err}, "
          f"already-cached {len(days) - len(todo)} (of {len(days)} days)", flush=True)
