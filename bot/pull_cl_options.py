# pull_cl_options.py — resumable pull of the bbo-1m legs for every phase-2 same-day signal.
# Skips already-cached legs; records completed signal keys so a re-run resumes.
# Run: cd bot && ../.venv/bin/python pull_cl_options.py   (redirect to results/cl_opt_pull.log)
import os

from load_cl_databento import CACHE_DIR
from load_cl_options_databento import resolve_legs, pull_leg
from backtest_cl_options import collect_same_day, START, END
from backtest_acd_cl import build_cl_history

PROGRESS = os.path.join(CACHE_DIR, "CL_options_pull.progress")


def _done():
    return set(open(PROGRESS).read().split()) if os.path.exists(PROGRESS) else set()


def main():
    mc = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
    dc = os.path.join(CACHE_DIR, f"CL_1d_{START}_{END}.csv")
    sigs = collect_same_day(build_cl_history(mc, dc))
    print(f"{len(sigs)} same-day signals to pull legs for", flush=True)
    done = _done()
    for i, s in enumerate(sigs):
        key = f"{s.date}:{s.name}:{s.direction}:{i}"
        if key in done:
            continue
        lg = resolve_legs(s.date, s.direction, s.entry_price)
        if lg is not None:
            try:
                pull_leg(lg["long_sym"], s.date)
                pull_leg(lg["short_sym"], s.date)
            except Exception as e:
                print(f"  WARN {s.date} {s.name}: {type(e).__name__} {str(e)[:80]}", flush=True)
        with open(PROGRESS, "a") as f:
            f.write(key + "\n")
        if i % 100 == 0:
            print(f"  {i}/{len(sigs)} done", flush=True)
    print("DONE.", flush=True)


if __name__ == "__main__":
    main()
