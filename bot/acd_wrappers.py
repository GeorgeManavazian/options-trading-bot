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


def build_debit_spread(signal, puts, calls, spot, expiration, width=25.0):
    """Directional debit spread: long ATM, short `width` further OUT in the
    signal direction. Bull call spread (long) / bear put spread (short).

    Risk = net debit (defined); reward capped at the width. Long pays ask,
    short receives bid.
    """
    d = signal["direction"]
    if d == "long":                              # bull call spread
        side, typ = calls, "call"
        lk, _lb, lask = _quote(side, spot)
        sk, sbid, _sa = _quote(side, lk + width)
    else:                                        # bear put spread
        side, typ = puts, "put"
        lk, _lb, lask = _quote(side, spot)
        sk, sbid, _sa = _quote(side, lk - width)
    net_debit = lask - sbid
    return {"wrapper": "debit_spread", "direction": d, "expiration": expiration,
            "legs": [{"strike": lk, "type": typ, "side": "long", "entry_price": lask},
                     {"strike": sk, "type": typ, "side": "short", "entry_price": sbid}],
            "entry_cost": net_debit, "max_loss": net_debit * 100,
            "width": abs(sk - lk)}


def build_credit_spread(signal, puts, calls, spot, expiration,
                        short_otm=10.0, width=25.0):
    """Directional credit spread in the signal direction (ORB-style): sell a put
    spread BELOW (long) / a call spread ABOVE (short).

    short = `short_otm` out-of-the-money; long = `width` further out (the wing).
    Risk = width - credit (defined, lopsided); reward = credit. Short receives
    bid, long pays ask.
    """
    d = signal["direction"]
    if d == "long":                              # sell put spread below spot
        side, typ = puts, "put"
        sk, sbid, _sa = _quote(side, spot - short_otm)
        lk, _lb, lask = _quote(side, sk - width)
    else:                                        # sell call spread above spot
        side, typ = calls, "call"
        sk, sbid, _sa = _quote(side, spot + short_otm)
        lk, _lb, lask = _quote(side, sk + width)
    credit = sbid - lask
    real_width = abs(sk - lk)
    return {"wrapper": "credit_spread", "direction": d, "expiration": expiration,
            "legs": [{"strike": sk, "type": typ, "side": "short", "entry_price": sbid},
                     {"strike": lk, "type": typ, "side": "long", "entry_price": lask}],
            "entry_cost": -credit, "max_loss": (real_width - credit) * 100,
            "width": real_width}


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

    # --- Task 2: debit spread ---
    d = build_debit_spread({"direction": "long"}, puts, calls, spot, exp, width=25.0)
    assert d["legs"][0] == {"strike": 5000.0, "type": "call", "side": "long",
                            "entry_price": 122.0}, d
    assert d["legs"][1] == {"strike": 5025.0, "type": "call", "side": "short",
                            "entry_price": 105.0}, d
    assert abs(d["entry_cost"] - 17.0) < 1e-9 and d["max_loss"] == 1700.0, d
    assert d["width"] == 25.0 and d["wrapper"] == "debit_spread", d

    ds = build_debit_spread({"direction": "short"}, puts, calls, spot, exp, width=25.0)
    # bear put: long 5000 put (ask 120), short 4975 put (bid 106) -> net 14
    assert ds["legs"][1]["strike"] == 4975.0 and ds["max_loss"] == 1400.0, ds
    print("Task 2 OK: build_debit_spread nets the debit + max_loss (bull call / bear put)")

    # --- Task 3: credit spread (test grid: short_otm=25, width=25) ---
    c = build_credit_spread({"direction": "long"}, puts, calls, spot, exp,
                            short_otm=25.0, width=25.0)
    # long signal -> sell put spread BELOW: short 4975 put (bid 106), long 4950 put (ask 97)
    assert c["legs"][0] == {"strike": 4975.0, "type": "put", "side": "short",
                            "entry_price": 106.0}, c
    assert c["legs"][1] == {"strike": 4950.0, "type": "put", "side": "long",
                            "entry_price": 97.0}, c
    assert abs(c["entry_cost"] + 9.0) < 1e-9, c          # credit 9 -> entry_cost -9
    assert c["max_loss"] == 1600.0 and c["wrapper"] == "credit_spread", c  # (25-9)*100

    cs = build_credit_spread({"direction": "short"}, puts, calls, spot, exp,
                             short_otm=25.0, width=25.0)
    # short signal -> sell call spread ABOVE: short 5025 call (bid 105), long 5050 call (ask 93)
    assert cs["legs"][0]["strike"] == 5025.0 and cs["max_loss"] == 1300.0, cs  # (25-12)*100
    print("Task 3 OK: build_credit_spread nets the credit + max_loss (put below / call above)")
