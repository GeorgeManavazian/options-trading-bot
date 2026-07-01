# pull_cl_options.py — resumable, concurrent, batched pull of the bbo-1m legs for every
# phase-2 same-day signal. Both legs of a signal are fetched in one request; many signals
# run concurrently. Month definition snapshots are pre-warmed single-pass (concurrently,
# distinct files) so the worker threads never race on definition cache writes.
# Run: cd bot && ../.venv/bin/python pull_cl_options.py   (redirect to results/cl_opt_pull.log)
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from load_cl_databento import CACHE_DIR
from load_cl_options_databento import resolve_legs, pull_legs_batch, definition_snapshot
from backtest_cl_options import collect_same_day, START, END
from backtest_acd_cl import build_cl_history

PROGRESS = os.path.join(CACHE_DIR, "CL_options_pull.progress")
WORKERS = 4   # lowered from 8 to avoid Databento 504s on concurrent definition pulls
_lock = threading.Lock()


def _done():
    return set(open(PROGRESS).read().split()) if os.path.exists(PROGRESS) else set()


def _record(key):
    with _lock:
        with open(PROGRESS, "a") as f:
            f.write(key + "\n")


def _pull_one(i, s):
    key = f"{s.date}:{s.name}:{s.direction}:{i}"
    try:
        lg = resolve_legs(s.date, s.direction, s.entry_price)   # may re-pull a missing month def
        if lg is None:
            _record(key)
            return "none"
        pull_legs_batch([lg["long_sym"], lg["short_sym"]], s.date)
    except Exception as e:
        print(f"  WARN {s.date} {s.name}: {type(e).__name__} {str(e)[:80]} (will retry)", flush=True)
        return "err"
    _record(key)
    return "ok"


def main():
    mc = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
    dc = os.path.join(CACHE_DIR, f"CL_1d_{START}_{END}.csv")
    sigs = collect_same_day(build_cl_history(mc, dc))
    done = _done()
    todo = [(i, s) for i, s in enumerate(sigs)
            if f"{s.date}:{s.name}:{s.direction}:{i}" not in done]
    print(f"{len(sigs)} signals; {len(todo)} to pull ({len(sigs)-len(todo)} already done)", flush=True)

    months = sorted({(s.date[:4], s.date[5:7]) for _, s in todo})
    print(f"pre-warming {len(months)} month definition snapshots...", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(definition_snapshot, int(y), int(m)) for y, m in months]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                print(f"  def WARN: {type(e).__name__} {str(e)[:60]}", flush=True)
    print("definitions warmed; pulling legs concurrently...", flush=True)

    ok = err = none = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(_pull_one, i, s) for i, s in todo]
        for k, f in enumerate(as_completed(futs)):
            r = f.result()
            ok += (r == "ok"); err += (r == "err"); none += (r == "none")
            if k % 200 == 0:
                print(f"  {k}/{len(todo)} processed (ok={ok} none={none} err={err})", flush=True)
    print(f"DONE. ok={ok} none(no-legs)={none} err(retry)={err}", flush=True)


if __name__ == "__main__":
    main()
