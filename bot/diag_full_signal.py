# diag_full_signal.py — THE CHECKPOINT. Wire the FULL ACD signal engine (① micro + ② macro)
# over the cached SPX data and measure whether the FILTERED, SIZED signals actually predict the
# underlying's direction (vs a buy-and-hold baseline). This is the gate before building options.
#
# Offline (uses cached intraday paths + daily H/L/C; no API). Run:  .venv/bin/python bot/diag_full_signal.py
import statistics

from acd_micro import build_day, SPX
from acd_macro import DayEntry, macro_context, apply_macro
from run_acd_signal import daily_hlc, day_path

HORIZONS = [0, 1, 3, 5]        # 0 = entry -> SAME-day close; else +k daily closes


def build_history():
    hlc = daily_hlc()
    days = sorted(hlc)
    hist = []
    for idx, D in enumerate(days):
        prior = hlc[days[idx - 1]] if idx > 0 else hlc[D]   # prior day's H/L/C for the pivot
        try:
            dr = build_day(D, day_path(D), prior, SPX)
        except Exception:
            continue
        hist.append(DayEntry(D, hlc[D], dr))
    return hist


def collect_signals(hist):
    """Return (micro, macro) lists of (date, direction, entry_price, name, conviction)."""
    micro, macro = [], []
    for i in range(len(hist)):
        ctx = macro_context(i, hist)
        for s in apply_macro(hist[i].day_result.setups, ctx):
            micro.append((hist[i].date, s.direction, s.entry_price, s.name, s.conviction))
        for s in ctx.macro_setups:
            macro.append((hist[i].date, s.direction, s.entry_price, s.name, s.conviction))
    return micro, macro


def _edge(sigs, dates, idx, closes, label):
    print(f"\n--- {label}  (n={len(sigs)}) ---")
    if not sigs:
        print("  (no signals)")
        return
    print(f"  {'horizon':<9}{'n':>5}{'mean dir-ret':>14}{'% positive':>12}{'median':>10}")
    for h in HORIZONS:
        rets = []
        for date, direction, entry, name, conv in sigs:
            i = idx.get(date)
            if i is None or i + h >= len(dates):
                continue
            fut = closes[dates[i + h]]
            if entry <= 0 or fut <= 0:
                continue
            sign = 1.0 if direction == "long" else -1.0
            rets.append((fut / entry - 1.0) * sign)
        if not rets:
            continue
        tag = "same-day" if h == 0 else f"+{h}d"
        print(f"  {tag:<9}{len(rets):>5}{statistics.mean(rets):>+13.3%}"
              f"{sum(1 for r in rets if r > 0) / len(rets):>11.0%}{statistics.median(rets):>+10.3%}")


def run():
    hist = build_history()
    dates = [e.date for e in hist]
    idx = {d: i for i, d in enumerate(dates)}
    closes = {e.date: e.ohlc[2] for e in hist}
    print(f"Full ACD engine over {len(hist)} days ({dates[0]} -> {dates[-1]})")

    micro, macro = collect_signals(hist)
    from collections import Counter
    print(f"\nFiltered MICRO signals: {len(micro)}  by name: {dict(Counter(s[3] for s in micro))}")
    print(f"MACRO signals:          {len(macro)}  by name: {dict(Counter(s[3] for s in macro))}")
    print(f"long/short (micro): {sum(1 for s in micro if s[1]=='long')}/"
          f"{sum(1 for s in micro if s[1]=='short')}")

    _edge(micro, dates, idx, closes, "FILTERED MICRO setups (all)")
    _edge([s for s in micro if s[3] in ("failed_a", "failed_a_pivot", "failed_c")],
          dates, idx, closes, "MICRO fades only")
    _edge([s for s in micro if s[3] not in ("failed_a", "failed_a_pivot", "failed_c")],
          dates, idx, closes, "MICRO breakouts/reversals only")
    _edge([s for s in micro if s[4] >= 3], dates, idx, closes, "MICRO high-conviction (>=3)")
    _edge(macro, dates, idx, closes, "MACRO setups (reversal/trt/sushi)")

    # baseline: unconditional forward drift (any day, in the LONG direction)
    print("\n--- BASELINE: unconditional SPX drift (long, any day) ---")
    print(f"  {'horizon':<9}{'mean':>13}{'% positive':>12}")
    for h in HORIZONS:
        if h == 0:
            continue
        rets = [closes[dates[i + h]] / closes[dates[i]] - 1.0
                for i in range(len(dates)) if i + h < len(dates) and closes[dates[i]] > 0]
        print(f"  +{h}d{'':<6}{statistics.mean(rets):>+12.3%}"
              f"{sum(1 for r in rets if r > 0) / len(rets):>11.0%}")


if __name__ == "__main__":
    run()
