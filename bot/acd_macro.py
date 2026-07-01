# acd_macro.py — the ACD MACRO engine (Fisher's multi-day layer). Consumes a chronological
# history of days (each = daily OHLC + the Micro Engine's DayResult) and, per day, produces a
# MacroContext (number line, chop filter, pivot-MA regime, momentum, plus/minus, macro setups)
# and filters/sizes the micro setups via apply_macro(). No lookahead (uses days <= i).
#
# Spec: docs/superpowers/specs/2026-06-30-acd-macro-engine.md   Rules: strategies/ACD.md Part D
# Run:  .venv/bin/python bot/acd_macro.py
from dataclasses import dataclass, field

from acd_micro import Setup, DayResult, ACDEvent


# ---------------------------------------------------------------- structures
@dataclass
class DayEntry:
    date: str
    ohlc: tuple                     # (High, Low, Close) of the day
    day_result: DayResult           # from acd_micro.build_day


@dataclass
class MacroContext:
    date: str
    score: int                      # today's number-line value (+4/+2/0/-2/-4)
    cum: int                        # 30-day cumulative
    trend_state: str                # trend_up|trend_down|chop|neutral|system_failure
    regime: str                     # bullish|bearish|neutral|confused (pivot-MA slopes)
    momentum: int                   # +1/0/-1 (close vs close 8 days ago)
    plus_minus: int                 # +1/-1/0
    macro_setups: list = field(default_factory=list)


BREAKOUT = {"a_held", "a_through_pivot", "c", "c_through_pivot", "late_day_c", "first_hour"}
FADES = {"failed_a", "failed_a_pivot", "failed_c"}
_TREND_DIR = {"trend_up": "long", "trend_down": "short", "bullish": "long", "bearish": "short"}


# ---------------------------------------------------------------- A1: daily score
def score_day(entry):
    dr = entry.day_result
    close = entry.ohlc[2]
    held = {e.type for e in dr.events if e.held}
    if "C_up" in held and close > dr.or_high:
        return 4
    if "C_down" in held and close < dr.or_low:
        return -4
    if "A_up" in held and close > dr.or_high:
        return 2
    if "A_down" in held and close < dr.or_low:
        return -2
    return 0


# ---------------------------------------------------------------- A2: number line
def _cum(history, i):
    if i < 0:
        return 0
    return sum(score_day(history[j]) for j in range(max(0, i - 29), i + 1))


def number_line_state(history, i):
    cum = _cum(history, i)
    prev = _cum(history, i - 1)
    if cum >= 9 and prev >= 9:
        state = "trend_up"
    elif cum <= -9 and prev <= -9:
        state = "trend_down"
    elif abs(cum) < 4:
        state = "chop"
    else:
        state = "neutral"
    if state in ("neutral", "chop") and abs(cum) < 9:
        recent = [_cum(history, j) for j in range(max(0, i - 3), i)]     # last few, excl. today
        if any(abs(c) >= 9 for c in recent):
            state = "system_failure"                                     # hit ±9 then fell back
    return cum, state


# ---------------------------------------------------------------- A3: plus/minus day
def plus_minus(entry):
    dr = entry.day_result
    close = entry.ohlc[2]
    lo, hi = dr.pivot_band
    if dr.or_vs_pivot == "below" and close > hi:        # opened below the pivot, closed above
        return 1
    if dr.or_vs_pivot == "above" and close < lo:        # opened above, closed below
        return -1
    return 0


# ---------------------------------------------------------------- A4: pivot moving averages
def daily_pivot(ohlc):
    h, l, c = ohlc[0], ohlc[1], ohlc[2]
    return (h + l + c) / 3.0


def _sma(vals, n, i):
    if i - n + 1 < 0:
        return None
    return sum(vals[i - n + 1:i + 1]) / n


def pivot_ma_regime(history, i, eps=1e-6):
    pivots = [daily_pivot(e.ohlc) for e in history]
    slopes = []
    for n in (14, 30, 50):
        cur, prev = _sma(pivots, n, i), _sma(pivots, n, i - 1)
        if cur is None or prev is None:
            return "neutral"                            # insufficient data -> stand aside
        d = cur - prev
        slopes.append(1 if d > eps else (-1 if d < -eps else 0))
    if all(s == 1 for s in slopes):
        return "bullish"
    if all(s == -1 for s in slopes):
        return "bearish"
    if all(s == 0 for s in slopes):
        return "neutral"
    return "confused"


# ---------------------------------------------------------------- A5: momentum
def momentum(history, i, lookback=8):
    if i - lookback < 0:
        return 0
    d = history[i].ohlc[2] - history[i - lookback].ohlc[2]
    return 1 if d > 0 else (-1 if d < 0 else 0)


# ---------------------------------------------------------------- B: macro setups
def _held_a(entry):
    for e in entry.day_result.events:
        if e.type in ("A_up", "A_down") and e.held:
            return e
    return None


def reversal_trade(i, history):
    """Two consecutive same-direction held A's, then the opposite held A (today) beyond the
    pair's extreme. Invalidated by 3+ same-direction A's. (ACD.md D2 — Fisher's best.)"""
    a_days = [(j, _held_a(history[j])) for j in range(max(0, i - 6), i + 1)]
    a_days = [(j, e) for j, e in a_days if e is not None]
    if len(a_days) < 3 or a_days[-1][0] != i:
        return None
    (_, e1), (_, e2), (_, e3) = a_days[-3], a_days[-2], a_days[-1]
    if e1.type != e2.type or e3.type == e1.type:
        return None
    if len(a_days) >= 4 and a_days[-4][1].type == e1.type:
        return None                                     # 3+ consecutive same-dir -> reset
    if e1.type == "A_up" and e3.price < min(e1.price, e2.price):
        return Setup("reversal_trade", "short", e3.time, e3.price, None, 3, "intraday",
                     {"a_pair": (e1.price, e2.price)})
    if e1.type == "A_down" and e3.price > max(e1.price, e2.price):
        return Setup("reversal_trade", "long", e3.time, e3.price, None, 3, "intraday",
                     {"a_pair": (e1.price, e2.price)})
    return None


def trt(i, history):
    """After a strong trend, a new extreme in the trend direction + a held A AGAINST the trend
    + a failed C in the trend direction -> fade. (ACD.md D3; approximate — no Open/gap or holiday
    calendar yet.)"""
    if i < 5:
        return None
    cum, _ = number_line_state(history, i)
    e = history[i]
    dr = e.day_result
    held = {ev.type for ev in dr.events if ev.held}
    types = {ev.type for ev in dr.events}
    recent = history[max(0, i - 10):i]
    if cum >= 6 and e.ohlc[0] > max(x.ohlc[0] for x in recent) and \
            "A_down" in held and "failed_C_up" in types:
        return Setup("trt", "short", "12:00", e.ohlc[2], None, 3, "intraday", {"note": "approx"})
    if cum <= -6 and e.ohlc[1] < min(x.ohlc[1] for x in recent) and \
            "A_up" in held and "failed_C_down" in types:
        return Setup("trt", "long", "12:00", e.ohlc[2], None, 3, "intraday", {"note": "approx"})
    return None


def sushi(i, history, n=5):
    """Latest n days take out BOTH the prior n's high and low, and CLOSE beyond the prior n's
    extreme -> reversal warning. (ACD.md D5.)"""
    if i < 2 * n - 1:
        return None
    prev = history[i - 2 * n + 1:i - n + 1]
    cur = history[i - n + 1:i + 1]
    prev_hi = max(x.ohlc[0] for x in prev)
    prev_lo = min(x.ohlc[1] for x in prev)
    cur_hi = max(x.ohlc[0] for x in cur)
    cur_lo = min(x.ohlc[1] for x in cur)
    close = history[i].ohlc[2]
    if cur_hi > prev_hi and cur_lo < prev_lo:
        if close < prev_lo:
            return Setup("sushi", "short", history[i].date, close, None, 3, "intraday",
                         {"prev": (prev_lo, prev_hi)})
        if close > prev_hi:
            return Setup("sushi", "long", history[i].date, close, None, 3, "intraday",
                         {"prev": (prev_lo, prev_hi)})
    return None


# ---------------------------------------------------------------- integrator
def macro_context(i, history):
    e = history[i]
    cum, state = number_line_state(history, i)
    macro = [s for s in (reversal_trade(i, history), trt(i, history), sushi(i, history)) if s]
    return MacroContext(e.date, score_day(e), cum, state, pivot_ma_regime(history, i),
                        momentum(history, i), plus_minus(e), macro)


def apply_macro(setups, ctx):
    """Drop micro setups that fight the regime/number line (chop filter + regime gate); boost
    conviction on macro confluence. Fades are always kept (chop is where mean-reversion belongs)."""
    tdir = _TREND_DIR.get(ctx.trend_state)              # number-line direction (or None)
    rdir = _TREND_DIR.get(ctx.regime)                   # pivot-MA-regime direction (or None)
    gate_dir = tdir or rdir                             # number line takes precedence for the gate
    drop_breakouts = ctx.trend_state in ("chop", "system_failure") or ctx.regime == "confused"
    out = []
    for s in setups:
        if drop_breakouts and s.name in BREAKOUT:
            continue                                    # chop / confused / failed-macro -> no breakouts
        if gate_dir and s.name in BREAKOUT and s.direction != gate_dir:
            continue                                    # regime gate (breakouts only)
        # confluence: count trend, PMA regime, momentum, plus/minus separately (spec A6)
        agrees = sum([
            bool(tdir and s.direction == tdir),
            bool(rdir and s.direction == rdir),
            (ctx.momentum == 1 and s.direction == "long") or (ctx.momentum == -1 and s.direction == "short"),
            (ctx.plus_minus == 1 and s.direction == "long") or (ctx.plus_minus == -1 and s.direction == "short"),
        ])
        out.append(Setup(s.name, s.direction, s.entry_time, s.entry_price, s.stop,
                         min(5, s.conviction + agrees), s.horizon, dict(s.refs)))
    return out


# ---------------------------------------------------------------- self-tests
def _names(items):
    return sorted(x.name for x in items)


def _dr(events, or_high=5010, or_low=4998, band=(4970.0, 4976.667), ovp="above"):
    return DayResult("d", or_high, or_low, band, ovp, events, [])


def _score_day(date, atype, close):
    ev = [ACDEvent(atype, "10:00", close, True)] if atype else []
    return DayEntry(date, (close + 5, close - 5, close), _dr(ev))


if __name__ == "__main__":
    mk = lambda name, direction, conv=1: Setup(name, direction, "10:00", 5000, 4990, conv,
                                                "intraday", {})

    # --- A2: number line reaches +9 held two days -> trend_up ---
    hist = [_score_day(f"d{k}", "A_up", 5020) for k in range(6)]   # each +2
    assert number_line_state(hist, 3)[0] == 8                      # 4 days -> +8 (not yet trend)
    c5, s5 = number_line_state(hist, 5)
    assert c5 == 12 and s5 == "trend_up", (c5, s5)
    print("A2 OK: number line trend_up on ±9 held 2 days")

    # --- A6: chop filter drops breakouts, keeps fades ---
    ctx_chop = MacroContext("d", 0, 2, "chop", "neutral", 0, 0)
    res = apply_macro([mk("a_held", "long"), mk("failed_a", "short")], ctx_chop)
    assert _names(res) == ["failed_a"], _names(res)
    print("A6 OK: chop filter keeps fades, drops breakouts")

    # --- A6: regime gate + confluence sizing ---
    ctx_up = MacroContext("d", 2, 12, "trend_up", "bullish", 1, 1)
    res = apply_macro([mk("a_held", "long"), mk("a_held", "short")], ctx_up)
    assert len(res) == 1 and res[0].direction == "long", res
    assert res[0].conviction == 5, res[0].conviction         # base 1 + trend + regime + momentum + plus_minus
    print("A6 OK: regime gate drops counter-trend; confluence boosts conviction")

    # system_failure (failed macro trend) also drops breakouts, keeps fades
    ctx_sf = MacroContext("d", 0, 5, "system_failure", "neutral", 0, 0)
    assert _names(apply_macro([mk("a_held", "long"), mk("failed_a", "short")], ctx_sf)) == ["failed_a"]
    print("A6 OK: system_failure drops breakouts")

    # --- A4/A5: bullish PMA regime + momentum on a rising pivot series ---
    rising = [_score_day(f"r{k}", None, 5000 + k) for k in range(51)]  # pivots 5000..5050 rising
    assert pivot_ma_regime(rising, 50) == "bullish", pivot_ma_regime(rising, 50)
    assert momentum(rising, 50) == 1
    # warm-up: neutral (stand aside) until the 50-day MA exists, NOT 'confused'
    assert pivot_ma_regime(rising, 20) == "neutral", pivot_ma_regime(rising, 20)
    print("A4/A5 OK: bullish PMA regime + momentum; warm-up = neutral")

    # --- A3: plus day ---
    dr_pm = DayResult("pm", 4990, 4980, (4995.0, 5005.0), "below", [], [])
    assert plus_minus(DayEntry("pm", (5010, 4980, 5010), dr_pm)) == 1
    print("A3 OK: plus day")

    # --- B1: reversal trade (two A_up then a lower A_down today) ---
    def _aday(date, atype, price):
        return DayEntry(date, (price + 5, price - 5, price),
                        _dr([ACDEvent(atype, "10:00", price, True)]))
    def _neut(date):
        return DayEntry(date, (5008, 5002, 5005), _dr([]))
    rev = [_aday("d1", "A_up", 5020), _neut("d2"), _aday("d3", "A_up", 5025),
           _aday("d4", "A_down", 5015)]                     # 5015 < min(5020,5025) -> reversal short
    mc = macro_context(3, rev)
    assert any(s.name == "reversal_trade" and s.direction == "short" for s in mc.macro_setups), \
        mc.macro_setups
    # 3 consecutive A_up before the A_down -> NOT a reversal
    rev3 = [_aday("d0", "A_up", 5018), _aday("d1", "A_up", 5020), _aday("d2", "A_up", 5025),
            _aday("d3", "A_down", 5015)]
    assert not any(s.name == "reversal_trade" for s in macro_context(3, rev3).macro_setups)
    # reversal LONG: two A_down then a higher A_up today
    revL = [_aday("e1", "A_down", 4980), _neut("e2"), _aday("e3", "A_down", 4975),
            _aday("e4", "A_up", 4990)]                       # 4990 > max(4980,4975) -> long
    assert any(s.name == "reversal_trade" and s.direction == "long"
               for s in macro_context(3, revL).macro_setups), "reversal long"
    print("B1 OK: reversal trade (short + long + 3-consecutive-A invalidation)")

    # --- B3: bearish sushi roll ---
    def _od(date, h, l, c):
        return DayEntry(date, (h, l, c), _dr([]))
    sush = [_od(f"p{k}", 5050, 5030, 5040) for k in range(5)]        # prior 5: hi 5050 lo 5030
    sush += [_od("c1", 5060, 5055, 5058), _od("c2", 5058, 5020, 5025), _od("c3", 5030, 5010, 5015),
             _od("c4", 5020, 5005, 5010), _od("c5", 5015, 5000, 5005)]  # latest 5 engulf, close 5005<5030
    mc = macro_context(9, sush)
    assert any(s.name == "sushi" and s.direction == "short" for s in mc.macro_setups), mc.macro_setups
    print("B3 OK: bearish sushi roll")

    print("\nAll ACD macro-engine self-tests passed.")
