# pull_fade_data.py — pull the intraday 1-min bars for every fade's grid legs
# (0DTE + next-day expiry, ATM + width-OTM). Resumable (fetch_option_minutes
# cache-skips). Real pull needs IVOL_API_KEY. After this runs once, the backtest
# is fully offline. Run: .venv/bin/python bot/pull_fade_data.py
import os

from acd_fade_signals import collect_fades, grid_cells
from run_acd_signal import daily_hlc

LOG = os.path.join(os.path.dirname(__file__), "..", "results", "spx", "fade_pull.log")


def unique_contracts(fades, calendar, width=25.0):
    """Every distinct (sym, date, exp, strike, typ) leg across all fades' grids."""
    seen = {}
    for date, setup in fades:
        for cell in grid_cells(date, setup, calendar, width):
            for c in (cell["long_contract"], cell["short_contract"]):
                if c is not None:
                    seen[c] = True
    return sorted(seen)


def main():
    from load_ivol_intraday import fetch_option_minutes
    fades = collect_fades()
    calendar = sorted(daily_hlc())
    contracts = unique_contracts(fades, calendar)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    total = len(contracts)
    print(f"{len(fades)} fades -> {total} unique leg-contracts to pull", flush=True)
    ok = fail = 0
    with open(LOG, "a") as log:
        log.write(f"=== fade pull: {total} contracts ===\n")
        for n, (sym, date, exp, strike, typ) in enumerate(contracts, 1):
            try:
                fetch_option_minutes(sym, date, exp, strike, typ)  # caches; sleeps 1.1s
                ok += 1
            except Exception as e:                                 # missing contract etc.
                fail += 1
                log.write(f"FAIL {sym} {date} {exp} {int(strike)} {typ}: {e}\n")
            if n % 25 == 0 or n == total:
                msg = f"[{n}/{total}] ok={ok} fail={fail}"
                print(msg, flush=True); log.write(msg + "\n"); log.flush()
    print(f"done: ok={ok} fail={fail} (log: results/fade_pull.log)")


if __name__ == "__main__":
    if os.environ.get("IVOL_API_KEY"):
        main()
    else:                                          # offline: just verify the plan
        fades = collect_fades()
        calendar = sorted(daily_hlc())
        contracts = unique_contracts(fades, calendar)
        assert contracts and all(len(c) == 5 for c in contracts)
        print(f"OK (offline): {len(fades)} fades -> {len(contracts)} unique contracts "
              f"(~{len(contracts)} pulls @1.1s ≈ {len(contracts)*1.1/60:.0f} min). "
              f"Set IVOL_API_KEY to pull.")
