# acd_wrappers.py — the OPTION WRAPPERS: turn one ACD Signal (long/short) into an
# actual option position. Three structurally-distinct expressions raced on the
# IDENTICAL signal (Plan 3): long option / debit spread / credit spread. Same seam
# as condor_rules.build_condor / orb_rules.build_orb. See
# docs/superpowers/specs/2026-06-30-acd-bot-design.md.
#
# Run with:  .venv/bin/python bot/acd_wrappers.py

import pandas as pd

from orb_rules import nearest


def _quote(df, target):
    """(strike, bid, ask) at the nearest available strike to `target`."""
    k = nearest(sorted(df["strike"].unique()), target)
    row = df[df["strike"] == k].iloc[0]
    return float(k), float(row["bid"]), float(row["ask"])


def build_long_option(signal, puts, calls, spot, expiration):
    """Buy one ATM option in the signal's direction (call if long, put if short).

    Risk = full premium (defined); reward uncapped. Pays the ask.
    """
    d = signal["direction"]
    side, typ = (calls, "call") if d == "long" else (puts, "put")
    k, _bid, ask = _quote(side, spot)
    return {"wrapper": "long_option", "direction": d, "expiration": expiration,
            "legs": [{"strike": k, "type": typ, "side": "long", "entry_price": ask}],
            "entry_cost": ask, "max_loss": ask * 100, "width": 0.0}


def _mock_chain():
    """A tiny parsed-style chain (spot 5000, $25 grid) for offline tests."""
    calls = pd.DataFrame({"strike": [5000, 5025, 5050, 5075],
                          "bid": [120, 105, 91, 78], "ask": [122, 107, 93, 80]})
    puts = pd.DataFrame({"strike": [4925, 4950, 4975, 5000],
                         "bid": [85, 95, 106, 118], "ask": [87, 97, 108, 120]})
    return puts, calls, 5000.0, "2024-09-03"


if __name__ == "__main__":
    puts, calls, spot, exp = _mock_chain()

    p = build_long_option({"direction": "long"}, puts, calls, spot, exp)
    assert p["legs"] == [{"strike": 5000.0, "type": "call", "side": "long",
                          "entry_price": 122.0}], p["legs"]
    assert p["max_loss"] == 12200.0 and p["entry_cost"] == 122.0, p
    assert p["width"] == 0.0 and p["wrapper"] == "long_option", p

    ps = build_long_option({"direction": "short"}, puts, calls, spot, exp)
    assert ps["legs"][0]["type"] == "put" and ps["legs"][0]["entry_price"] == 120.0, ps
    print("Task 1 OK: build_long_option buys the ATM call/put at the ask")
