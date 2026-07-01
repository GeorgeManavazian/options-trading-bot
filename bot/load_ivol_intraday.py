# load_ivol_intraday.py — pull IVolatility INTRADAY 1-minute option bars (real
# NBBO bid/ask + IV + underlying spot) and shape them for the ORB backtest. The
# intraday sibling of load_ivolai.py; caches every pull to data_cache/.
#
# Endpoint: /equities/intraday/single-equity-option-rawiv
# Auth:  export IVOL_API_KEY="your-key"
# Run:   .venv/bin/python bot/load_ivol_intraday.py   (real pull if key set, else
#                                                       an offline mock test)

import os
import time

import pandas as pd

API_KEY = os.environ.get("IVOL_API_KEY", "")
ENDPOINT = "/equities/intraday/single-equity-option-rawiv"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data_cache")

# IVolatility intraday column -> our name. VERIFIED on first live pull (2024-06-03):
# the feed's `timestamp` is a full "YYYY-MM-DD HH:MM:SS" datetime, which
# normalize_minutes() trims to "HH:MM".
INTRADAY_COLUMN_MAP = {
    "timestamp": "time",            # full datetime -> trimmed to HH:MM below
    "optionBidPrice": "bid",
    "optionAskPrice": "ask",
    "underlyingPrice": "spot",
    "optionIv": "iv",
}


def normalize_minutes(df):
    """Rename IVolatility intraday columns to ours and trim time to HH:MM.

    The feed's `timestamp` is a full "YYYY-MM-DD HH:MM:SS"; we keep just HH:MM so
    the rules engine can compare bar times as zero-padded strings. Duplicate
    minutes (the feed repeats the last quote after the close) are dropped.
    """
    df = df.rename(columns=INTRADAY_COLUMN_MAP)
    if "time" in df.columns:
        df["time"] = df["time"].astype(str).str.slice(11, 16)   # "...09:30:00" -> "09:30"
        df = df.drop_duplicates(subset="time", keep="first").reset_index(drop=True)
    return df


def fetch_option_minutes(symbol, trade_date, exp_date, strike, opt_type,
                         minute_type="MINUTE_1"):
    """One contract's 1-min bars for one day, cached to disk forever after.

    opt_type : "put"/"call" (mapped to PUT/CALL for the API).
    Returns a DataFrame with columns time/bid/ask/spot/iv.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    tag = f"{symbol}_{trade_date}_{exp_date}_{int(strike)}_{opt_type[0].upper()}_min.csv"
    cache_path = os.path.join(CACHE_DIR, tag)
    if os.path.exists(cache_path):
        return normalize_minutes(pd.read_csv(cache_path))

    if not API_KEY:
        raise RuntimeError("Set IVOL_API_KEY first:  export IVOL_API_KEY=...")
    import ivolatility as ivol
    ivol.setLoginParams(apiKey=API_KEY)
    get = ivol.setMethod(ENDPOINT)
    raw = get(symbol=symbol, date=trade_date, expDate=exp_date, strike=strike,
              optType=opt_type.upper(), minuteType=minute_type)
    time.sleep(1.1)                              # 1 req/sec cap
    raw.to_csv(cache_path, index=False)          # cache raw (pre-rename)
    return normalize_minutes(raw)


def load_cached_minutes(symbol, trade_date, exp_date, strike, opt_type):
    """Cache-only reader: normalized minute bars if already pulled, else None.
    Filename must match fetch_option_minutes exactly. No network -> the offline
    backtest marks fades through this."""
    tag = f"{symbol}_{trade_date}_{exp_date}_{int(strike)}_{opt_type[0].upper()}_min.csv"
    cache_path = os.path.join(CACHE_DIR, tag)
    if os.path.exists(cache_path):
        return normalize_minutes(pd.read_csv(cache_path))
    return None


def underlying_path(symbol, trade_date, exp_date, anchor_strike):
    """Read the underlying spot off a near-ATM option's bars -> [(t, spot)]."""
    df = fetch_option_minutes(symbol, trade_date, exp_date, anchor_strike, "put")
    return [(str(r["time"]), float(r["spot"])) for _, r in df.iterrows()]


def leg_close_series(symbol, trade_date, exp_date, short_strike, long_strike,
                     opt_type, entry_time):
    """Entry credit + cost-to-close series from entry_time onward.

    credit       = short.bid - long.ask at entry_time (what you collect selling).
    close_price  = short.ask - long.bid each later bar (what you'd pay to close).
    """
    short = fetch_option_minutes(symbol, trade_date, exp_date, short_strike, opt_type)
    long_ = fetch_option_minutes(symbol, trade_date, exp_date, long_strike, opt_type)
    short = short.set_index("time"); long_ = long_.set_index("time")
    common = sorted(t for t in short.index if t in long_.index and t >= entry_time)
    if not common:
        raise ValueError(f"no overlapping leg bars at/after {entry_time}")

    entry_t = common[0]                          # the first fillable bar at/after entry
    entry_credit = float(short.loc[entry_t, "bid"] - long_.loc[entry_t, "ask"])
    close_series = [(t, float(short.loc[t, "ask"] - long_.loc[t, "bid"]))
                    for t in common]
    return entry_credit, close_series


EOD_ENDPOINT = "/equities/eod/stock-opts-by-param"


def parse_0dte_chain(raw_df):
    """Raw 0DTE chain DataFrame -> (sorted strikes, anchor spot).

    Reuses the condor loader's COLUMN_MAP so the renames stay in one place.
    Pure function (no network) so it tests offline.
    """
    from load_ivolai import COLUMN_MAP
    df = raw_df.rename(columns=COLUMN_MAP)
    strikes = sorted({float(s) for s in df["strike"]})
    anchor_spot = float(df["spot"].iloc[0])
    return strikes, anchor_spot


def fetch_0dte_chain(symbol, trade_date, moneyness=6.0):
    """Pull the 0DTE EOD chain (both sides) -> (strikes, anchor_spot).

    Cached under a DISTINCT name (`..._0dte_...`) so it never collides with the
    condor's 1DTE chain cache. We only need the listed strikes (to snap to) and a
    rough spot to anchor the near-ATM option we read the morning path from.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(
        CACHE_DIR, f"{symbol}_{trade_date}_0dte_m{int(moneyness)}.csv")
    if os.path.exists(cache_path):
        return parse_0dte_chain(pd.read_csv(cache_path))

    if not API_KEY:
        raise RuntimeError("Set IVOL_API_KEY first:  export IVOL_API_KEY=...")
    import ivolatility as ivol
    ivol.setLoginParams(apiKey=API_KEY)
    get = ivol.setMethod(EOD_ENDPOINT)
    # One side suffices: SPX puts and calls share the same strike grid, and every
    # row carries the underlying price. Pulling just puts halves the API calls.
    df = get(symbol=symbol, tradeDate=trade_date, dteFrom=0, dteTo=0, cp="P",
             moneynessFrom=-moneyness, moneynessTo=moneyness)
    time.sleep(1.1)                              # 1 req/sec cap
    df.to_csv(cache_path, index=False)
    return parse_0dte_chain(df)


def _mock_minutes(strike, opt_type):
    """A pretend 1-min series for one contract (offline) — REAL IVol column shape."""
    base = 3.0
    rows = []
    for i, hhmm in enumerate(["10:45", "11:00", "11:30", "12:00", "16:00"]):
        rows.append({"timestamp": f"2024-06-03 {hhmm}:00",
                     "optionBidPrice": base - 0.1 + i * 0.05,
                     "optionAskPrice": base + 0.1 + i * 0.05,
                     "underlyingPrice": 5025 - i, "optionIv": 0.15})
    return pd.DataFrame(rows)


def _mock_0dte_df():
    """A pretend 0DTE EOD chain (IVolatility column shape) — offline."""
    rows = []
    for strike in [4980, 4990, 5000, 5010, 5020]:
        for cp in ("P", "C"):
            rows.append({"c_date": "2024-06-03", "expiration_date": "2024-06-03",
                         "price_strike": float(strike), "call_put": cp,
                         "Bid": 2.5, "Ask": 3.5, "iv": 0.15,
                         "underlying_price": 5003.0})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = normalize_minutes(_mock_minutes(5000, "put"))
    assert list(df.columns)[:4] == ["time", "bid", "ask", "spot"], df.columns
    path = [(r["time"], r["spot"]) for _, r in df.iterrows()]
    assert path[0] == ("10:45", 5025.0), path[0]
    print("Task 7 OK: intraday normalize + path extraction work offline")

    strikes, anchor = parse_0dte_chain(_mock_0dte_df())
    assert strikes == [4980.0, 4990.0, 5000.0, 5010.0, 5020.0], strikes
    assert anchor == 5003.0, anchor
    print("Task 7b OK: parse_0dte_chain returns strikes + anchor spot")

    assert load_cached_minutes("SPX", "1900-01-01", "1900-01-01", 5000, "put") is None
    print("Task 7c OK: load_cached_minutes returns None for an un-cached contract")
