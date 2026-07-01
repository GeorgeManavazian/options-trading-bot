# pull_cl_full.py — memory-safe, resumable full-history pull of CL 1-minute bars from
# Databento into the single cache file the backtest expects
# (data_cache/CL_1m_2010-06-06_2026-06-29.csv). Pulls YEAR BY YEAR and appends, so we
# never hold 16 years of rows in memory at once. Resumable: completed year-chunks are
# recorded in a .progress sidecar and skipped on re-run.
#
# Run: cd bot && ../.venv/bin/python pull_cl_full.py   (logs to results/cl_pull.log if redirected)
import os

from load_cl_databento import _client, CACHE_DIR

START, END = "2010-06-06", "2026-06-29"
FINAL = os.path.join(CACHE_DIR, f"CL_1m_{START}_{END}.csv")
PROGRESS = FINAL + ".progress"

# [start, end) year chunks covering the full range.
CHUNKS = [("2010-06-06", "2011-01-01")]
CHUNKS += [(f"{y}-01-01", f"{y+1}-01-01") for y in range(2011, 2026)]
CHUNKS += [("2026-01-01", END)]


def _done():
    if not os.path.exists(PROGRESS):
        return set()
    return set(open(PROGRESS).read().split())


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    done = _done()
    client = _client()
    for start, end in CHUNKS:
        key = f"{start}_{end}"
        if key in done:
            print(f"skip {key} (already done)", flush=True)
            continue
        print(f"pull {key} ...", flush=True)
        data = client.timeseries.get_range(
            dataset="GLBX.MDP3", symbols=["CL.c.0"], stype_in="continuous",
            schema="ohlcv-1m", start=start, end=end)
        df = data.to_df()
        header = not os.path.exists(FINAL)
        df.to_csv(FINAL, mode="a", header=header)
        with open(PROGRESS, "a") as f:
            f.write(key + "\n")
        print(f"  wrote {len(df)} rows (header={header}); total chunks done={len(_done())}", flush=True)
    print(f"DONE. final cache: {FINAL}", flush=True)


if __name__ == "__main__":
    main()
