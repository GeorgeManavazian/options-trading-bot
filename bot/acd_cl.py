# acd_cl.py — crude-oil InstrumentSpec + a smoke test that the UNMODIFIED ACD engine
# (acd_micro.build_day) runs on a real cached crude day. Isolated from SPX/V5.
# Run: .venv/bin/python bot/acd_cl.py
from acd_micro import InstrumentSpec, build_day

# Crude RTH open 09:00 ET (confirmed). A/C anchored as % of the OR midpoint; crude is more
# volatile than SPX (SPX=0.18%/0.21%) so start wider — TUNE via the Task 6 sweep, don't trust
# a single value. tick=$0.01. cutoff/late_day in ET.
CL = InstrumentSpec(
    symbol="CL",
    session_open="09:00",
    or_minutes=15,
    a_pct=0.0025,
    c_pct=0.0030,
    hold_fraction=0.5,
    cutoff="12:00",
    tick=0.01,
    late_day="14:30",
)

if __name__ == "__main__":
    assert CL.symbol == "CL" and CL.session_open == "09:00" and CL.tick == 0.01
    assert 0 < CL.a_pct < CL.c_pct < 0.02, "sane crude A/C anchors"
    print("acd_cl spec OK:", CL)

    # loader -> unmodified engine seam on one real cached day (needs Task 2's smoke pull cached)
    from load_cl_databento import pull_cl_daily, pull_cl_minutes, cl_day_path, cl_daily_hlc
    dp = pull_cl_daily("2024-06-03", "2024-06-08")
    mp = pull_cl_minutes("2024-06-03", "2024-06-08")
    hlc = cl_daily_hlc(dp)
    days = sorted(hlc)
    D = days[1]                                  # a day with a prior day for the pivot
    dr = build_day(D, cl_day_path(D, mp), hlc[days[0]], CL)
    assert dr.date == D and dr.or_high >= dr.or_low, dr
    print(f"seam OK: build_day({D}) -> OR[{dr.or_low},{dr.or_high}] "
          f"events={len(dr.events)} setups={[s.name for s in dr.setups]}")
