# acd_micro.py — the COMPLETE intraday ACD engine (Mark Fisher's "micro" system),
# instrument-agnostic. Pipeline:  levels -> events -> pivot-context -> setups -> DayResult.
# It reports WHAT ACD SAW each day (levels, the ordered events, the qualified setups); it
# does not place trades, filter by macro context, size, or touch options (later sub-projects).
#
# Spec: docs/superpowers/specs/2026-06-30-acd-micro-engine.md   Rules: strategies/ACD.md
# Run:  .venv/bin/python bot/acd_micro.py
from dataclasses import dataclass, field

from acd_rules import opening_range, pivot_range, _to_min


# ---------------------------------------------------------------- config + structures
@dataclass
class InstrumentSpec:
    """Everything instrument-specific. A/C values are % of the opening-range midpoint
    (Fisher's exact formula is proprietary -> we anchor + backtest-tune later)."""
    symbol: str = "SPX"
    or_minutes: int = 15
    a_pct: float = 0.0018
    c_pct: float = 0.0021
    hold_fraction: float = 0.5      # signal must hold >= hold_fraction * or_minutes
    cutoff: str = "12:00"           # latest A entry
    tick: float = 0.01
    session_open: str = "09:30"
    late_day: str = "14:30"         # a C-through-pivot at/after this time -> overnight carry


SPX = InstrumentSpec()


@dataclass
class Levels:
    or_high: float
    or_low: float
    a_up: float
    a_down: float
    c_up: float
    c_down: float
    pivot_band: tuple               # (low, high) from prior day's H/L/C


@dataclass
class ACDEvent:
    type: str                       # A_up|A_down|C_up|C_down|failed_A_up|failed_A_down|
                                    # failed_C_up|failed_C_down|B|D
    time: str
    price: float
    held: bool


@dataclass
class Setup:
    name: str                       # a_held|a_through_pivot|c|c_through_pivot|late_day_c|
                                    # failed_a|failed_a_pivot|failed_c|first_hour
    direction: str                  # long|short
    entry_time: str
    entry_price: float
    stop: float                     # None for failed_c (time-stop only)
    conviction: int                 # 1..3 by confluence
    horizon: str                    # intraday|overnight
    refs: dict = field(default_factory=dict)


@dataclass
class DayResult:
    date: str
    or_high: float
    or_low: float
    pivot_band: tuple
    or_vs_pivot: str                # above|below|inside (Stage-3 context)
    events: list
    setups: list


def _add_minutes(hhmm, mins):
    m = _to_min(hhmm) + int(mins)
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------- Stage 1: levels
def compute_levels(bars, prior_hlc, spec):
    """bars = [(t 'HH:MM', price)]; prior_hlc = (High, Low, Close) of the prior day."""
    or_end = _add_minutes(spec.session_open, spec.or_minutes)
    hi, lo = opening_range(bars, spec.session_open, or_end)
    mid = (hi + lo) / 2.0
    a, c = mid * spec.a_pct, mid * spec.c_pct
    return Levels(hi, lo, hi + a, lo - a, hi + c, lo - c, pivot_range(*prior_hlc))


# ---------------------------------------------------------------- Stage 2: events
def _check_hold(bars_sorted, t_min, beyond, hold_min):
    """Return the confirm bar (t, price) once price has stayed `beyond` the level for
    >= hold_min minutes from t_min, and the confirm bar is itself still beyond. None if
    it snaps back inside within the window (a failure)."""
    for t2, p2 in bars_sorted:
        tm2 = _to_min(t2)
        if tm2 < t_min:
            continue
        if tm2 - t_min >= hold_min:
            return (t2, p2) if beyond(p2) else None
        if not beyond(p2):
            return None
    return None


def detect_a_events(bars, lv, spec):
    """A_up/A_down (held, one per day) + the first failed_A of each side, after the OR
    window and at/before the cutoff."""
    hold_min = spec.hold_fraction * spec.or_minutes
    or_end_m = _to_min(_add_minutes(spec.session_open, spec.or_minutes))
    cut_m = _to_min(spec.cutoff)
    bs = sorted((t, float(p)) for t, p in bars)
    events = []
    failed = {"A_up": False, "A_down": False}
    for t, price in bs:
        tm = _to_min(t)
        if tm <= or_end_m or tm > cut_m:
            continue
        if any(e.type in ("A_up", "A_down") for e in events):
            break                                       # one A per day
        if price >= lv.a_up:
            typ, beyond = "A_up", (lambda s: s >= lv.a_up)
        elif price <= lv.a_down:
            typ, beyond = "A_down", (lambda s: s <= lv.a_down)
        else:
            continue
        confirm = _check_hold(bs, tm, beyond, hold_min)
        if confirm is not None:
            events.append(ACDEvent(typ, confirm[0], confirm[1], True))
        elif not failed[typ]:
            events.append(ACDEvent("failed_" + typ, t, price, False))
            failed[typ] = True
    return events


def detect_c_events(bars, lv, spec, a_event):
    """After a held A: B (return to opposite OR edge) -> C (held) / failed_C -> D."""
    if a_event is None:
        return []
    hold_min = spec.hold_fraction * spec.or_minutes
    a_min = _to_min(a_event.time)
    bs = sorted((t, float(p)) for t, p in bars if _to_min(t) >= a_min)
    events = []
    if a_event.type == "A_up":                          # bias long -> watch for C_down
        b_hit = (lambda s: s <= lv.or_low)
        c_beyond, c_typ = (lambda s: s <= lv.c_down), "C_down"
    else:                                               # bias short -> watch for C_up
        b_hit = (lambda s: s >= lv.or_high)
        c_beyond, c_typ = (lambda s: s >= lv.c_up), "C_up"

    b_min = None
    for t, p in bs:
        if b_hit(p):
            events.append(ACDEvent("B", t, p, False))
            b_min = _to_min(t)
            break
    if b_min is None:
        return events                                   # never reversed through the OR

    failed_c = False
    for t, p in bs:
        if _to_min(t) < b_min:
            continue
        if any(e.type in ("C_up", "C_down") for e in events):
            break
        if c_beyond(p):
            confirm = _check_hold(bs, _to_min(t), c_beyond, hold_min)
            if confirm is not None:
                events.append(ACDEvent(c_typ, confirm[0], confirm[1], True))
            elif not failed_c:
                events.append(ACDEvent("failed_" + c_typ, t, p, False))
                failed_c = True

    c_ev = next((e for e in events if e.type in ("C_up", "C_down") and e.held), None)
    if c_ev is not None:
        if c_ev.type == "C_down":
            d_hit = (lambda s: s >= lv.or_high + spec.tick)
        else:
            d_hit = (lambda s: s <= lv.or_low - spec.tick)
        cm = _to_min(c_ev.time)
        for t, p in bs:
            if _to_min(t) < cm:
                continue
            if d_hit(p):
                events.append(ACDEvent("D", t, p, False))
                break
    return events


# ---------------------------------------------------------------- Stage 3: pivot context
def or_vs_pivot(lv):
    lo, hi = lv.pivot_band
    if lv.or_low > hi:
        return "above"
    if lv.or_high < lo:
        return "below"
    return "inside"


def through_pivot(direction, level, band, or_high, or_low):
    """True only if the signal clears the ENTIRE band AND the band lies in the PATH of the
    move (not behind it). Long: level above the band top AND the band isn't entirely below
    the OR. Short: level below the band bottom AND the band isn't entirely above the OR."""
    lo, hi = band
    if direction == "long":
        return level > hi and not (or_low > hi)
    return level < lo and not (or_high < lo)


# ---------------------------------------------------------------- Stage 4: setups
def setups_from_a(a_event, lv, spec):
    if a_event is None or not a_event.held:
        return []
    direction = "long" if a_event.type == "A_up" else "short"
    stop_or = lv.or_low if direction == "long" else lv.or_high
    out = [Setup("a_held", direction, a_event.time, a_event.price, stop_or, 1, "intraday",
                 {"or_low": lv.or_low, "or_high": lv.or_high})]
    level = lv.a_up if direction == "long" else lv.a_down
    if through_pivot(direction, level, lv.pivot_band, lv.or_high, lv.or_low):
        lo, hi = lv.pivot_band
        out.append(Setup("a_through_pivot", direction, a_event.time, a_event.price,
                         lo if direction == "long" else hi, 2, "intraday",
                         {"pivot_band": lv.pivot_band}))
    return out


def setups_from_c(c_event, lv, spec, close):
    """`close` = the day's last price (for the late-day overnight-carry condition)."""
    if c_event is None or not c_event.held:
        return []
    direction = "long" if c_event.type == "C_up" else "short"
    d_stop = (lv.or_low - spec.tick) if direction == "long" else (lv.or_high + spec.tick)
    out = [Setup("c", direction, c_event.time, c_event.price, d_stop, 1, "intraday", {"d": d_stop})]
    level = lv.c_up if direction == "long" else lv.c_down
    if through_pivot(direction, level, lv.pivot_band, lv.or_high, lv.or_low):
        lo, hi = lv.pivot_band
        late = _to_min(c_event.time) >= _to_min(spec.late_day)
        if direction == "long":
            carry = close is not None and close > hi and close > lv.c_up
        else:
            carry = close is not None and close < lo and close < lv.c_down
        overnight = late and carry            # ACD.md: carry only if close beyond BOTH pivot & C
        out.append(Setup("late_day_c" if overnight else "c_through_pivot", direction,
                         c_event.time, c_event.price, lo if direction == "long" else hi, 3,
                         "overnight" if overnight else "intraday", {"pivot_band": lv.pivot_band}))
    return out


def setups_from_failed(events, lv, spec):
    """Fade failed A/C. A failed-A fade is invalidated ONLY if a SAME-side A has ALREADY
    held by the time the fade fires (its confirm time <= the fade's time). An A that holds
    LATER is unknowable at the fade's entry, so it must NOT retroactively delete the fade —
    that was a look-ahead bug that flattered every fade backtest (V5, crude); see the replay
    audit. (This engine breaks on the first held A, so a same-side hold always confirms after
    the failed-A that preceded it — this rule therefore keeps those genuine live fades.)"""
    lo, hi = lv.pivot_band
    held_up_times = [_to_min(e.time) for e in events if e.type == "A_up" and e.held]
    held_down_times = [_to_min(e.time) for e in events if e.type == "A_down" and e.held]
    held_by = lambda times, t: any(h <= t for h in times)   # same-side A already held at/before t?
    out = []
    for e in events:
        if e.type == "failed_A_up" and not held_by(held_up_times, _to_min(e.time)):   # fade a failed up-breakout -> short
            if lo <= lv.a_up <= hi:
                out.append(Setup("failed_a_pivot", "short", e.time, lv.a_up, hi, 2, "intraday",
                                 {"pivot_band": lv.pivot_band}))
            else:
                out.append(Setup("failed_a", "short", e.time, lv.a_up, lv.a_up + spec.tick, 1,
                                 "intraday", {"a": lv.a_up}))
        elif e.type == "failed_A_down" and not held_by(held_down_times, _to_min(e.time)):  # fade a failed down-breakout -> long
            if lo <= lv.a_down <= hi:
                out.append(Setup("failed_a_pivot", "long", e.time, lv.a_down, lo, 2, "intraday",
                                 {"pivot_band": lv.pivot_band}))
            else:
                out.append(Setup("failed_a", "long", e.time, lv.a_down, lv.a_down - spec.tick, 1,
                                 "intraday", {"a": lv.a_down}))
        elif e.type == "failed_C_up":                   # treacherous: fade toward the OR -> short
            out.append(Setup("failed_c", "short", e.time, e.price, None, 1, "intraday", {}))
        elif e.type == "failed_C_down":
            out.append(Setup("failed_c", "long", e.time, e.price, None, 1, "intraday", {}))
    return out


def setups_first_hour(bars, lv, a_event, spec):
    """Pivot band engulfs the first-hour extreme, an A forms in the first hour, and the
    first-hour close sits within 15% of the extreme in the trade direction."""
    if a_event is None or not a_event.held:
        return []
    fh_end = _add_minutes(spec.session_open, 60)
    fh = [(t, float(p)) for t, p in sorted(bars) if spec.session_open <= t <= fh_end]
    if not fh or _to_min(a_event.time) > _to_min(fh_end):
        return []
    prices = [p for _, p in fh]
    fh_high, fh_low, fh_close = max(prices), min(prices), fh[-1][1]
    rng = fh_high - fh_low
    if rng <= 0:
        return []
    lo, hi = lv.pivot_band
    if a_event.type == "A_up" and lo <= fh_low <= hi and (fh_high - fh_close) <= 0.15 * rng:
        return [Setup("first_hour", "long", fh[-1][0], fh_close, fh_low, 2, "intraday",
                      {"fh_high": fh_high, "fh_low": fh_low})]
    if a_event.type == "A_down" and lo <= fh_high <= hi and (fh_close - fh_low) <= 0.15 * rng:
        return [Setup("first_hour", "short", fh[-1][0], fh_close, fh_high, 2, "intraday",
                      {"fh_high": fh_high, "fh_low": fh_low})]
    return []


# ---------------------------------------------------------------- orchestrator
def build_day(date, bars, prior_hlc, spec=SPX):
    lv = compute_levels(bars, prior_hlc, spec)
    a_events = detect_a_events(bars, lv, spec)
    a_held = next((e for e in a_events if e.type in ("A_up", "A_down") and e.held), None)
    c_events = detect_c_events(bars, lv, spec, a_held)
    events = a_events + c_events
    c_held = next((e for e in c_events if e.type in ("C_up", "C_down") and e.held), None)
    close = sorted(bars)[-1][1] if bars else None
    setups = (setups_from_a(a_held, lv, spec)
              + setups_from_c(c_held, lv, spec, close)
              + setups_from_failed(events, lv, spec)
              + setups_first_hour(bars, lv, a_held, spec))
    return DayResult(date, lv.or_high, lv.or_low, lv.pivot_band, or_vs_pivot(lv), events, setups)


# ---------------------------------------------------------------- self-tests
def _names(items, attr="name"):
    return sorted(getattr(x, attr) for x in items)


if __name__ == "__main__":
    OR = [("09:30", 5005), ("09:38", 5010), ("09:44", 4998), ("09:45", 5002)]  # hi 5010 lo 4998
    # mid 5004 -> a=9.007 (a_up 5019.01, a_down 4988.99); c=10.508 (c_up 5020.51, c_down 4987.49)
    PIV_BELOW    = (4990.0, 4950.0, 4980.0)  # band (4970, 4976.67): entirely below the OR
    PIV_STRADDLE = (5030.0, 4980.0, 5020.0)  # band (5005, 5015): straddles the OR (in the long path)
    PIV_C_PATH   = (5030.0, 4970.0, 4985.0)  # band (4990, 5000): straddles OR, in the C-down path
    PIV_ENGULF_A = (5040.0, 5008.0, 5009.0)  # band (5014, 5024) engulfs a_up 5019.01 (failed_a_pivot)

    # --- Task 1: levels ---
    lv = compute_levels(OR, PIV_BELOW, SPX)
    assert lv.or_high == 5010 and lv.or_low == 4998, lv
    assert abs(lv.a_up - 5019.0072) < 1e-3, lv.a_up
    assert abs(lv.c_down - 4987.4916) < 1e-3, lv.c_down
    assert abs(lv.pivot_band[1] - 4976.6667) < 1e-3, lv.pivot_band
    print("Task 1 OK: compute_levels")

    # --- Stage 3: through_pivot respects band POSITION; or_vs_pivot ---
    assert through_pivot("long", 5019, (5005, 5015), 5010, 4998) is True     # band straddles OR
    assert through_pivot("long", 5019, (4970, 4976), 5010, 4998) is False    # band behind (below OR)
    assert through_pivot("short", 4987, (4990, 5000), 5010, 4998) is True    # band in the short path
    assert through_pivot("short", 4987, (5055, 5065), 5010, 4998) is False   # band above the market
    assert or_vs_pivot(lv) == "above"
    print("Stage 3 OK: through_pivot geometry + or_vs_pivot")

    # --- a_held + a_through_pivot; band in path -> stop TIGHTENS for the long ---
    up = OR + [("09:50", 5020), ("09:52", 5021), ("09:58", 5023)]
    d = build_day("D1", up, PIV_STRADDLE)
    assert any(e.type == "A_up" and e.held and e.time == "09:58" for e in d.events), d.events
    a_h = [s for s in d.setups if s.name == "a_held"][0]
    a_tp = [s for s in d.setups if s.name == "a_through_pivot"][0]
    assert a_h.stop == 4998 and a_tp.stop == 5005 and a_tp.conviction == 2
    assert a_tp.stop > a_h.stop, "through-pivot stop must be tighter (higher) for a long"
    print("A OK: a_held + a_through_pivot (tighter stop)")

    # a_through_pivot must NOT fire when the band is behind the move
    d = build_day("D1b", up, PIV_BELOW)
    assert _names(d.setups) == ["a_held"], _names(d.setups)
    print("A OK: no a_through_pivot when band is below the OR")

    # --- failed A up -> failed_a short (entry AT the A level) ---
    fa = OR + [("09:50", 5020), ("09:52", 5000)]
    d = build_day("D2", fa, PIV_BELOW)
    assert any(e.type == "failed_A_up" for e in d.events) and not any(
        e.type == "A_up" and e.held for e in d.events)
    fs = [s for s in d.setups if s.name == "failed_a"][0]
    assert fs.direction == "short" and abs(fs.entry_price - 5019.0072) < 1e-2
    assert abs(fs.stop - 5019.0172) < 1e-2, fs
    print("failed_a OK: rubber-band fade at the A level")

    # --- failed_a_pivot: failed A up with a_up INSIDE the band ---
    d = build_day("D2b", fa, PIV_ENGULF_A)
    fp = [s for s in d.setups if s.name == "failed_a_pivot"]
    assert fp and fp[0].direction == "short" and fp[0].conviction == 2, _names(d.setups)
    print("failed_a_pivot OK")

    # --- LIVE-SAFE: a failed-A fade that fired BEFORE the same-side A later holds is KEPT ---
    # The fade fires at 09:50 (A_up not yet held); A_up only holds at ~10:30. Live you cannot
    # know the 10:30 hold at 09:50, so it must NOT retroactively delete the fade. Dropping it
    # was a look-ahead bug that flattered every fade backtest (V5, crude) — see replay_audit_cl.
    fa_then_a = OR + [("09:50", 5020), ("09:52", 5000), ("10:20", 5020), ("10:30", 5023)]
    d = build_day("D2c", fa_then_a, PIV_BELOW)
    a_hold = next(e for e in d.events if e.type == "A_up" and e.held)
    fade = [s for s in d.setups if s.name == "failed_a"]
    assert fade, "failed_a fade that fired before a LATER A-hold must be KEPT (live-safe)"
    assert _to_min(fade[0].entry_time) < _to_min(a_hold.time), "fade fired before the A-hold"
    print("failed_a OK: KEPT when same-side A holds LATER (live-safe; was a look-ahead drop)")

    # --- A up held, B, C_down held: plain c (band below -> NOT through pivot) ---
    seq = OR + [("09:50", 5020), ("09:58", 5023), ("10:10", 4996),
                ("10:20", 4985), ("10:22", 4984), ("10:30", 4983)]
    d = build_day("D3", seq, PIV_BELOW)
    assert any(e.type == "B" for e in d.events) and any(
        e.type == "C_down" and e.held for e in d.events)
    assert [s for s in d.setups if s.name == "c"] and not any(
        s.name in ("c_through_pivot", "late_day_c") for s in d.setups)
    print("c OK: B + C_down held (plain c)")

    # --- c_through_pivot INTRADAY (band in the C-down path, confirmed before late_day) ---
    d = build_day("D3b", seq, PIV_C_PATH)
    ctp = [s for s in d.setups if s.name == "c_through_pivot"]
    assert ctp and ctp[0].conviction == 3 and ctp[0].horizon == "intraday", _names(d.setups)
    print("c_through_pivot OK (intraday)")

    # --- late_day_c: through pivot, late, close beyond BOTH pivot & C -> overnight ---
    late = OR + [("09:50", 5020), ("09:58", 5023), ("10:10", 4996),
                 ("14:40", 4985), ("14:44", 4984), ("14:52", 4983)]   # close 4983 < 4990 & < 4987.49
    d = build_day("D4", late, PIV_C_PATH)
    ld = [s for s in d.setups if s.name == "late_day_c"]
    assert ld and ld[0].horizon == "overnight" and ld[0].conviction == 3, _names(d.setups)
    print("late_day_c OK: overnight carry when close confirms")

    # --- failed_C: A up held, B, C_down touched but NOT held -> failed_c long, no stop ---
    fc = OR + [("09:50", 5020), ("09:58", 5023), ("10:10", 4996),
               ("10:20", 4985), ("10:22", 4996)]        # touches C_down then snaps back inside
    d = build_day("D4b", fc, PIV_BELOW)
    assert any(e.type == "failed_C_down" for e in d.events), [e.type for e in d.events]
    fcs = [s for s in d.setups if s.name == "failed_c"]
    assert fcs and fcs[0].direction == "long" and fcs[0].stop is None, _names(d.setups)
    print("failed_c OK: treacherous fade, time-stop only")

    # --- pivot first_hour (long) ---
    fh = [("09:30", 5055), ("09:38", 5060), ("09:44", 5050), ("09:45", 5052),
          ("09:50", 5075), ("09:58", 5078), ("10:29", 5079)]
    PIV_FH = (5065.0, 5025.0, 5060.0)   # band (5045, 5055) engulfs the first-hour low 5050
    d = build_day("D5", fh, PIV_FH)
    assert [s for s in d.setups if s.name == "first_hour"][0].direction == "long", _names(d.setups)
    print("first_hour OK")

    # --- chop day: no A, no setups ---
    chop = [("09:30", 5005), ("09:45", 5002), ("10:00", 5004), ("11:00", 5003)]
    d = build_day("D6", chop, PIV_BELOW)
    assert d.setups == [] and d.or_vs_pivot == "above", (d.setups, d.or_vs_pivot)
    print("chop OK: no signal, no setups")

    print("\nAll ACD micro-engine self-tests passed (9/9 setups covered).")
