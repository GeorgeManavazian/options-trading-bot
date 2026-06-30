# run_acd_signal.py — run the ACD BRAIN over ALL cached days, fully OFFLINE (no
# API key), to see how often it actually trades (and long vs short) BEFORE we pull
# any dated-option data. This answers "how much options data do we need to pull?":
# the brain decides which days are worth pulling.
#
# It needs only (1) the morning price path — cached for the full 3-yr ORB window —
# and (2) yesterday's High/Low/Close for the pivot, which we derive from the prior
# day's cached full-day path (an approximation of the index's daily H/L/C).
#
# Run with:  .venv/bin/python bot/run_acd_signal.py

import os
import glob

from acd_rules import build_acd_signal
from load_ivol_intraday import fetch_0dte_chain, underlying_path

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")
SYM = "SPX"


def cached_days():
    """Sorted trading days that have a 0dte chain cached (-> minute data too)."""
    days = set()
    for p in glob.glob(os.path.join(CACHE_DIR, f"{SYM}_*_0dte_m*.csv")):
        days.add(os.path.basename(p).split("_")[1])   # SPX_2024-06-03_0dte_m6.csv
    return sorted(days)


def day_path(D):
    """Full-day underlying path [(t, spot)] for day D, read from cache."""
    strikes, anchor = fetch_0dte_chain(SYM, D)
    atm = min(strikes, key=lambda k: abs(k - anchor))
    return underlying_path(SYM, D, D, atm)


def hlc_from_path(path):
    """Approx daily High/Low/Close from a full-day underlying path."""
    spots = [s for _, s in path]
    return (max(spots), min(spots), spots[-1])


def daily_hlc():
    """{date -> (H, L, C)} from each cached full-day path."""
    out = {}
    for D in cached_days():
        try:
            out[D] = hlc_from_path(day_path(D))
        except Exception:
            continue
    return out


def trade_signals(a_pct=0.0018):
    """Trade-day Signals (flats excluded), pivot from the prior day's H/L/C."""
    days = cached_days()
    out, prev_hlc = [], None
    for D in days:
        try:
            path = day_path(D)
        except Exception:
            prev_hlc = None
            continue
        if prev_hlc is not None:
            try:
                sig = build_acd_signal(path, prev_hlc, a_pct=a_pct)
                if sig["direction"] != "flat":
                    out.append({"date": D, **sig})
            except Exception:
                pass
        prev_hlc = hlc_from_path(path)
    return out


def run():
    days = cached_days()
    print(f"Cached days: {len(days)}  ({days[0]} -> {days[-1]})\n")

    prev_hlc = None
    counts = {"long": 0, "short": 0, "flat": 0}
    trades = []
    skipped = 0
    for D in days:
        try:
            path = day_path(D)
        except Exception:
            skipped += 1
            prev_hlc = None              # data gap -> next pivot is untrustworthy too
            continue
        if prev_hlc is None:             # need yesterday's H/L/C for the pivot
            prev_hlc = hlc_from_path(path)
            continue
        try:
            sig = build_acd_signal(path, prev_hlc)
            counts[sig["direction"]] += 1
            if sig["direction"] != "flat":
                trades.append((D, sig["direction"], sig["entry_time"],
                               round(sig["entry_spot"], 1)))
        except Exception:
            skipped += 1
        prev_hlc = hlc_from_path(path)

    total = sum(counts.values())
    n_trade = counts["long"] + counts["short"]
    print(f"Evaluated {total} days (skipped {skipped} for missing/short data)\n")
    print(f"  TRADE days:     {n_trade}  ({n_trade / max(total, 1):.0%} of days)")
    print(f"     long:        {counts['long']}")
    print(f"     short:       {counts['short']}")
    print(f"  sit-out (flat): {counts['flat']}\n")
    print("First 10 trade signals:")
    for D, d, t, s in trades[:10]:
        print(f"  {D}  {d:<5} entry {t} @ {s:,.1f}")
    print(f"\n=> Option data to pull is driven by {n_trade} trade days, not all {total}.")


if __name__ == "__main__":
    # --- Task 2 (Plan 3): reusable signal + HLC accessors ---
    hlc = daily_hlc()
    assert isinstance(hlc, dict) and len(hlc) > 700, len(hlc)
    sigs = trade_signals()
    assert all(s["direction"] in ("long", "short") for s in sigs), "trades only"
    assert 250 <= len(sigs) <= 380, len(sigs)        # ~314 expected
    print(f"Task 2 OK: {len(sigs)} trade signals, {len(hlc)} daily HLC")

    run()
