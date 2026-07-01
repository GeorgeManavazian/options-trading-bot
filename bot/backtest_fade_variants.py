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
