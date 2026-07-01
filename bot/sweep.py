# sweep.py — test MANY strategy variants in a single pass over the data.
#
# For each trading day we pull the chain ONCE (cached after the first time) and
# build a condor for every variant — so comparing deltas/wings is one data pass,
# not one per variant. After the first run the chains are cached, so re-running
# any sweep is instant and uses zero API calls.
#
# Run with:  IVOL_API_KEY=... BT_FROM=2024-01-01 BT_TO=2024-12-31 \
#            .venv/bin/python bot/sweep.py

import os
from datetime import date, timedelta

from condor_rules import build_condor, net_credit, payoff_at
from backtest import max_drawdown
from backtest_chains import _spx_prices
import load_ivolai

# The 5 variants to compare: spanning the two main knobs (how far OTM we sell,
# and how wide the wings are). Tested over the full ~3 years, broken down by year.
VARIANTS = [
    {"label": "16Δ/50w (base)", "target_delta": 0.16, "wing_width": 50},
    {"label": "10Δ/50w",        "target_delta": 0.10, "wing_width": 50},
    {"label": "05Δ/50w",        "target_delta": 0.05, "wing_width": 50},
    {"label": "16Δ/25w",        "target_delta": 0.16, "wing_width": 25},
    {"label": "16Δ/100w",       "target_delta": 0.16, "wing_width": 100},
]


def run_sweep(from_date, to_date, variants=VARIANTS, symbol="SPX"):
    price_to = (date.fromisoformat(to_date) + timedelta(days=7)).isoformat()
    prices = _spx_prices(from_date, price_to)
    dates = sorted(d for d in prices if from_date <= d <= to_date)

    results = {v["label"]: [] for v in variants}
    for i, D in enumerate(dates):
        try:
            puts, calls, spot, expiration, _ = load_ivolai.load_chain(symbol, D)
        except Exception as e:
            print(f"  skip {D}: {repr(e)[:60]}", flush=True)
            continue
        settle = prices.get(expiration)
        if settle is None:
            continue
        for v in variants:                       # same chain, every variant
            c = build_condor(puts, calls, spot, expiration, symbol=symbol,
                             wing_width=v["wing_width"],
                             target_delta=v["target_delta"],
                             today=date.fromisoformat(D))
            credit = net_credit(c) * 100
            max_loss = v["wing_width"] * 100 - credit
            pnl = payoff_at(c, settle)
            results[v["label"]].append({
                "date": D, "ret_pct": pnl / max_loss if max_loss else 0.0,
                "credit": credit, "pnl": pnl,
            })
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(dates)} days", flush=True)
    return results


def _stats(trades):
    rets = [t["ret_pct"] for t in trades]
    n = len(rets)
    wins = sum(1 for r in rets if r > 0)
    avg_w = sum(r for r in rets if r > 0) / max(wins, 1)
    losses = [r for r in rets if r <= 0]
    avg_l = sum(losses) / max(len(losses), 1)
    be = -avg_l / (avg_w - avg_l) if (avg_w - avg_l) else 0
    equity, run = [], 0.0
    for r in rets:
        run += r
        equity.append(run)
    avg_credit = sum(t["credit"] for t in trades) / max(n, 1)
    return {"n": n, "win": wins / n if n else 0, "be": be, "avg_w": avg_w,
            "avg_l": avg_l, "total": sum(rets), "dd": max_drawdown(equity),
            "credit": avg_credit}


def compare(results):
    """Overall (whole-period) comparison table across variants."""
    print(f"\n{'variant':<16}{'win%':>6}{'beEven%':>9}{'margin':>8}"
          f"{'avgCr$':>8}{'total%':>9}{'maxDD%':>9}")
    print("-" * 65)
    # rank best-to-worst by total return on risk
    for label, trades in sorted(results.items(), key=lambda kv: -_stats(kv[1])["total"]):
        s = _stats(trades)
        margin = s["win"] - s["be"]
        flag = "  <== PROFITABLE" if s["total"] > 0 else ""
        print(f"{label:<16}{s['win']:>6.0%}{s['be']:>9.0%}{margin:>+8.0%}"
              f"{s['credit']:>8.0f}{s['total']:>+9.0%}{s['dd']:>9.0%}{flag}")


def compare_by_year(results):
    """Per-variant, per-YEAR breakdown — the robustness check across regimes."""
    years = sorted({t["date"][:4] for trades in results.values() for t in trades})
    print("\n=== Year-by-year (win% / total% on risk) ===")
    header = "variant".ljust(16) + "".join(f"{y:>16}" for y in years)
    print(header)
    print("-" * len(header))
    for label, trades in results.items():
        row = label.ljust(16)
        for y in years:
            yt = [t for t in trades if t["date"].startswith(y)]
            if yt:
                s = _stats(yt)
                row += f"{s['win']:.0%}/{s['total']:+.0%}".rjust(16)
            else:
                row += "—".rjust(16)
        print(row)


if __name__ == "__main__":
    frm = os.environ.get("BT_FROM", "2023-07-01")
    to = os.environ.get("BT_TO", "2026-06-27")
    print(f"Sweeping {len(VARIANTS)} variants on {frm} -> {to}\n", flush=True)
    results = run_sweep(frm, to)
    compare(results)
    compare_by_year(results)
    # Save raw per-trade results for each variant (so we never recompute blind).
    import json
    os.makedirs("results/spx", exist_ok=True)
    with open(f"results/spx/sweep_{frm}_to_{to}.json", "w") as fh:
        json.dump(results, fh)
    print(f"\nSaved -> results/sweep_{frm}_to_{to}.json")
