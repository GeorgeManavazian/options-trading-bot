# diag_signal_edge.py — DIAGNOSTIC (read-only, offline): does the ACD signal have raw
# directional edge on the UNDERLYING, before any options/exits? For each trade signal,
# measure the underlying's forward move at +1..+10 trading days, in the signal's direction.
# Positive mean + >50% hit-rate = the entry predicts direction (fix the exit). ~0 or
# negative = the signal itself has no edge (rethink the entry).
#
# Run with:  .venv/bin/python bot/diag_signal_edge.py

import statistics

from run_acd_signal import trade_signals, daily_hlc

HORIZONS = [1, 2, 3, 5, 10]


def forward_edge():
    sigs = trade_signals()
    hlc = daily_hlc()
    days = sorted(hlc)
    idx = {d: i for i, d in enumerate(days)}
    closes = {d: hlc[d][2] for d in days}

    print(f"ACD signals: {len(sigs)}  "
          f"(long {sum(1 for s in sigs if s['direction']=='long')}, "
          f"short {sum(1 for s in sigs if s['direction']=='short')})\n")

    def stats(rows, label):
        print(f"--- {label} ---")
        print(f"  {'horizon':<9}{'n':>5}{'mean dir-ret':>14}{'% positive':>12}{'median':>10}")
        for h in HORIZONS:
            rets = []
            for s in rows:
                i = idx.get(s["date"])
                if i is None or i + h >= len(days):
                    continue
                entry = float(s["entry_spot"])
                fut = closes[days[i + h]]
                if entry <= 0 or fut <= 0:                    # skip bad-data days
                    continue
                sign = 1.0 if s["direction"] == "long" else -1.0
                rets.append((fut / entry - 1.0) * sign)      # return IN the signal direction
            if not rets:
                continue
            n = len(rets)
            mean = statistics.mean(rets)
            pos = sum(1 for r in rets if r > 0) / n
            med = statistics.median(rets)
            print(f"  +{h}d{'':<5}{n:>5}{mean:>+13.3%}{pos:>11.0%}{med:>+10.3%}")
        print()

    stats(sigs, "ALL signals")
    stats([s for s in sigs if s["direction"] == "long"], "LONG only")
    stats([s for s in sigs if s["direction"] == "short"], "SHORT only")

    # Baseline: SPX's own average forward drift over the same window (unconditional),
    # so we can tell whether the signal beats just being in the market.
    all_days_rets = {h: [] for h in HORIZONS}
    for i, d in enumerate(days):
        if closes[d] <= 0:
            continue
        for h in HORIZONS:
            if i + h < len(days) and closes[days[i + h]] > 0:
                all_days_rets[h].append(closes[days[i + h]] / closes[d] - 1.0)
    print("--- BASELINE: unconditional SPX drift (any day, not signal-conditioned) ---")
    for h in HORIZONS:
        r = all_days_rets[h]
        print(f"  +{h}d  mean {statistics.mean(r):+.3%}  %positive {sum(1 for x in r if x>0)/len(r):.0%}")


if __name__ == "__main__":
    forward_edge()
