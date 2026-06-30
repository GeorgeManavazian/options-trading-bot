# filters.py — Kirk's ENTRY FILTERS. The strategy only trades when conditions are
# favorable; these filters are where his edge comes from (not the condor itself).
#
# All computed from SPX daily OHLC: skip FOMC days (and the day before), skip big
# gaps/ranges, require RSI in-band, price above its 10-day SMA, and CCI > 50.
#
# Run with:  .venv/bin/python bot/filters.py     (self-test on synthetic data)

from datetime import date, timedelta

import pandas as pd

# FOMC announcement dates (2nd day of each meeting), 2023-2026. We skip these AND
# the calendar day before. NOTE: hand-entered from the Fed schedule — verify if
# precision matters (a wrong date just mis-skips one day).
FOMC_DATES = [
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
    "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
]


def _fomc_blocked():
    """The set of dates to skip: each FOMC date + the calendar day before."""
    blocked = set()
    for d in FOMC_DATES:
        dt = date.fromisoformat(d)
        blocked.add(d)
        blocked.add((dt - timedelta(days=1)).isoformat())
    return blocked


FOMC_BLOCKED = _fomc_blocked()


def add_indicators(ohlc):
    """Add Kirk's indicator columns to a daily OHLC frame (date/open/high/low/close).

    Returns a new frame sorted by date with: sma10, rsi14, cci20, gap, intraday.
    """
    df = ohlc.sort_values("date").reset_index(drop=True).copy()
    c = df["close"]

    df["sma10"] = c.rolling(10).mean()

    # RSI(14), simple-average version.
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["rsi14"] = 100 - 100 / (1 + rs)

    # CCI(20) on the typical price.
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: (abs(x - x.mean())).mean(), raw=True)
    df["cci20"] = (tp - sma_tp) / (0.015 * mad.replace(0, 1e-9))

    # Overnight gap and the day's move (open->close ~ the move by ~3:30 entry).
    df["gap"] = (df["open"] - c.shift(1)) / c.shift(1)
    df["intraday"] = (df["close"] - df["open"]) / df["open"]

    # ADX(14), Wilder's trend-strength gauge (used by ORB's put side, threshold 15).
    n = 14
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = ((up > down) & (up > 0)) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)) * down.clip(lower=0)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - c.shift()).abs(),
                    (df["low"] - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()          # Wilder smoothing
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    df["adx14"] = dx.ewm(alpha=1 / n, adjust=False).mean()
    return df


def trade_ok(row, date_str, gap_max=0.015, range_max=0.015,
             rsi_lo=20, rsi_hi=80, cci_min=50):
    """Do all of Kirk's filters pass for this day? Returns (ok, [reasons_failed])."""
    reasons = []
    if date_str in FOMC_BLOCKED:
        reasons.append("FOMC")
    if pd.isna(row["sma10"]) or row["close"] <= row["sma10"]:
        reasons.append("below 10-day SMA")
    if pd.isna(row["rsi14"]) or not (rsi_lo <= row["rsi14"] <= rsi_hi):
        reasons.append("RSI extreme")
    if pd.isna(row["cci20"]) or row["cci20"] <= cci_min:
        reasons.append("CCI<=50")
    if pd.isna(row["gap"]) or abs(row["gap"]) > gap_max:
        reasons.append("big gap")
    if pd.isna(row["intraday"]) or abs(row["intraday"]) > range_max:
        reasons.append("big intraday move")
    return (len(reasons) == 0, reasons)


if __name__ == "__main__":
    # Self-test: a calm uptrend should PASS; a gap-down day should FAIL.
    import pandas as pd
    rows = []
    price = 4000.0
    for i in range(40):
        price *= 1.002                       # steady mild uptrend
        rows.append({"date": f"2024-02-{i+1:02d}", "open": price, "high": price * 1.003,
                     "low": price * 0.997, "close": price * 1.001})
    df = add_indicators(pd.DataFrame(rows))
    last = df.iloc[-1]
    print("Calm uptrend day:", trade_ok(last, last["date"]))
    assert last["adx14"] > 15, last["adx14"]   # a steady trend -> strong ADX
    print(f"ADX(14) on steady uptrend: {last['adx14']:.1f}  (expected >15)")

    gap = df.iloc[-1].copy()                  # force a big overnight gap
    gap["gap"] = -0.03
    print("Big gap-down day:", trade_ok(gap, gap["date"]))
    print("FOMC day:", trade_ok(last, "2024-01-31"))
