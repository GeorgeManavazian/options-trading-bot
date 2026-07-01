# acd_fade_signals.py — collect the ACD FADE signals and build the 2x2 backtest
# grid ({0DTE, overnight} x {debit_spread, long_option}) for each one. Shared by
# the pull script and the offline backtest so the two agree on contracts/strikes.
# Offline (build_history reads cached paths). Run: .venv/bin/python bot/acd_fade_signals.py
SYM = "SPX"


def collect_fades():
    """[(date, Setup)] for every filtered fade (failed_a / failed_a_pivot / failed_c)."""
    from diag_full_signal import build_history
    from acd_macro import macro_context, apply_macro
    from acd_options import FADES
    hist = build_history()
    out = []
    for i, day in enumerate(hist):
        ctx = macro_context(i, hist)
        for s in apply_macro(day.day_result.setups, ctx):
            if s.name in FADES:
                out.append((day.date, s))
    return out


def _strikes(setup, width):
    typ = "call" if setup.direction == "long" else "put"
    atm = round(setup.entry_price / 5.0) * 5.0
    short = atm + width if setup.direction == "long" else atm - width
    return typ, atm, short


def grid_cells(date, setup, calendar, width=25.0):
    """The 2x2 grid for one fade. `calendar` = sorted trading dates (overnight
    expiry = the next one). Contracts are (SYM, trade_date, exp, strike, typ)."""
    typ, atm, short = _strikes(setup, width)
    exps = [("0DTE", date)]
    i = calendar.index(date)
    if i + 1 < len(calendar):
        exps.append(("overnight", calendar[i + 1]))

    cells = []
    for horizon, exp in exps:
        lo = {"kind": "long_option", "opt_type": typ, "long_strike": atm}
        cells.append({"horizon": horizon, "structure": lo,
                      "long_contract": (SYM, date, exp, atm, typ),
                      "short_contract": None, "settle_date": exp})
        ds = {"kind": "debit_spread", "opt_type": typ, "long_strike": atm,
              "short_strike": short, "width": width}
        cells.append({"horizon": horizon, "structure": ds,
                      "long_contract": (SYM, date, exp, atm, typ),
                      "short_contract": (SYM, date, exp, short, typ),
                      "settle_date": exp})
    return cells


if __name__ == "__main__":
    from acd_micro import Setup
    cal = ["2024-06-03", "2024-06-04", "2024-06-05"]
    long_fade = Setup("failed_a", "long", "10:30", 5003.0, None, 1, "intraday", {})
    cells = grid_cells("2024-06-04", long_fade, cal, width=25.0)
    assert len(cells) == 4, len(cells)
    lo0 = [c for c in cells if c["horizon"] == "0DTE" and c["short_contract"] is None][0]
    assert lo0["long_contract"] == ("SPX", "2024-06-04", "2024-06-04", 5005.0, "call"), lo0
    ds_n = [c for c in cells if c["horizon"] == "overnight"
            and c["structure"]["kind"] == "debit_spread"][0]
    assert ds_n["long_contract"] == ("SPX", "2024-06-04", "2024-06-05", 5005.0, "call")
    assert ds_n["short_contract"] == ("SPX", "2024-06-04", "2024-06-05", 5030.0, "call")
    assert ds_n["settle_date"] == "2024-06-05", ds_n
    print("OK grid_cells (long fade -> call, ATM 5005, short 5030)")

    short_fade = Setup("failed_a", "short", "11:00", 5002.0, None, 1, "intraday", {})
    sc = grid_cells("2024-06-05", short_fade, cal)   # last day -> no overnight
    assert len(sc) == 2 and all(c["horizon"] == "0DTE" for c in sc), sc
    assert sc[0]["structure"]["opt_type"] == "put"
    dsp = [c for c in sc if c["structure"]["kind"] == "debit_spread"][0]
    assert dsp["short_contract"][3] == 4975.0, dsp   # 5000 - 25 (bear put)
    print("OK grid_cells (short fade -> put; last day drops overnight)")

    fades = collect_fades()
    print(f"collect_fades: {len(fades)} fade signals")
    assert len(fades) > 100 and all(len(t) == 2 for t in fades)
    print("All acd_fade_signals self-tests passed.")
