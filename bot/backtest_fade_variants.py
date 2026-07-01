# backtest_fade_variants.py — drawdown BAKE-OFF: race ~8 variants of the debit-spread
# fade strategy (filter/exit/sizing/diversify switches) and rank them by RISK-ADJUSTED
# return + year-by-year robustness (NOT raw total). Offline on the ④b cache.
# Spec: docs/superpowers/specs/2026-07-01-fade-drawdown-bakeoff.md
# Run:  .venv/bin/python bot/backtest_fade_variants.py
import statistics
from dataclasses import dataclass

from acd_fade_signals import collect_fades, grid_cells
from backtest_acd_fades import price_cell
from run_acd_signal import daily_hlc
from backtest_acd_full import _stats

_TRADES = None


def collect_fade_trades():
    """Tagged debit-spread fade trades (both horizons), built once from cache."""
    global _TRADES
    if _TRADES is not None:
        return _TRADES
    closes = {d: v[2] for d, v in daily_hlc().items()}
    cal = sorted(closes)
    out = []
    for date, s in collect_fades():
        for cell in grid_cells(date, s, cal):
            if cell["structure"]["kind"] != "debit_spread":
                continue
            t = price_cell(cell, s, closes)
            if t is None:
                continue
            out.append({"date": date, "name": s.name, "conviction": s.conviction,
                        "horizon": cell["horizon"], "nlegs": t["nlegs"],
                        "max_loss": t["max_loss"], "pnl_hold": t["pnl0"],
                        "pnl_active": t.get("pnl0_ts", t["pnl0"])})
    _TRADES = out
    return out


@dataclass
class Variant:
    name: str
    filt: str = "all"          # all | no_failed_c | failed_a_only
    exit_rule: str = "hold"    # hold | active
    sizing: str = "flat"       # flat | conviction | throttle
    horizons: str = "0DTE"     # 0DTE | overnight | blend


_FILTERS = {
    "all": lambda t: True,
    "no_failed_c": lambda t: t["name"] != "failed_c",
    "failed_a_only": lambda t: t["name"] == "failed_a",
}


def _weights_from(pnls, convs, sizing):
    """Per-trade weights (date-ordered), then mean-normalized to 1.0."""
    if sizing == "flat":
        w = [1.0] * len(pnls)
    elif sizing == "conviction":
        w = [float(c) for c in convs]
    elif sizing == "throttle":                    # anti-martingale: halve after 2 losses
        w, streak = [], 0
        for p in pnls:
            w.append(0.5 if streak >= 2 else 1.0)  # decided by losses BEFORE this trade
            streak = streak + 1 if p <= 0 else 0
    else:
        raise ValueError(f"unknown sizing {sizing!r}")
    m = sum(w) / len(w) if w else 1.0
    return [x / m for x in w] if m else w


def apply_variant(trades, v):
    picked = [t for t in trades if _FILTERS[v.filt](t)]
    if v.horizons != "blend":
        picked = [t for t in picked if t["horizon"] == v.horizons]
    picked = sorted(picked, key=lambda t: t["date"])
    pnls = [t["pnl_active"] if v.exit_rule == "active" else t["pnl_hold"] for t in picked]
    ws = _weights_from(pnls, [t["conviction"] for t in picked], v.sizing)
    return [{"date": t["date"], "weight": w, "pnl": p,
             "nlegs": t["nlegs"], "max_loss": t["max_loss"]}
            for t, p, w in zip(picked, pnls, ws)]


if __name__ == "__main__":
    trades = collect_fade_trades()
    assert len(trades) > 250, len(trades)
    assert {t["horizon"] for t in trades} == {"0DTE", "overnight"}, "both horizons expected"
    assert any(t["name"] == "failed_c" for t in trades), "failed_c expected"
    need = {"date", "name", "conviction", "horizon", "nlegs", "max_loss", "pnl_hold", "pnl_active"}
    assert all(need <= t.keys() for t in trades)
    assert all(t["pnl_active"] == t["pnl_hold"] for t in trades if t["horizon"] == "overnight")
    print(f"OK collect_fade_trades: {len(trades)} trades "
          f"(0DTE {sum(1 for t in trades if t['horizon']=='0DTE')}, "
          f"overnight {sum(1 for t in trades if t['horizon']=='overnight')})")

    def _mk(date, name, hz, ph, pa=None, conv=1, nlegs=2, ml=100.0):
        return {"date": date, "name": name, "conviction": conv, "horizon": hz,
                "nlegs": nlegs, "max_loss": ml, "pnl_hold": ph,
                "pnl_active": ph if pa is None else pa}

    syn = [_mk("2024-01-01", "failed_a", "0DTE", 50, 20),
           _mk("2024-01-02", "failed_c", "0DTE", -100, -30),
           _mk("2024-01-03", "failed_a", "overnight", 40)]
    r = apply_variant(syn, Variant("t", filt="no_failed_c", horizons="blend"))
    assert [x["date"] for x in r] == ["2024-01-01", "2024-01-03"], r      # failed_c dropped
    r = apply_variant(syn, Variant("t", exit_rule="active", horizons="0DTE"))
    assert [x["pnl"] for x in r] == [20, -30], r                          # active uses pnl_active
    r = apply_variant(syn, Variant("t", horizons="blend"))
    assert len(r) == 3 and abs(sum(x["weight"] for x in r) / len(r) - 1.0) < 1e-9  # mean weight 1
    print("OK apply_variant: filter / active / blend / normalize")

    losers = [_mk(f"2024-02-0{i}", "failed_a", "0DTE", -10) for i in range(1, 5)] \
        + [_mk("2024-02-05", "failed_a", "0DTE", 100)]
    r = apply_variant(losers, Variant("t", sizing="throttle", horizons="0DTE"))
    raw = [1.0, 1.0, 0.5, 0.5, 0.5]                                       # halve after 2 losses
    m = sum(raw) / len(raw)
    assert all(abs(r[i]["weight"] - raw[i] / m) < 1e-9 for i in range(5)), [x["weight"] for x in r]
    print("OK apply_variant: throttle sizing")
