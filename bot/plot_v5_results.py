# plot_v5_results.py — visualize trading the V5 fade config (drop failed_c + active
# exit, 0DTE debit spread) over the 3-yr backtest as a real $10k account risking 1%
# per trade. Two panels: equity curve + underwater drawdown. Offline on cache.
# Run: .venv/bin/python bot/plot_v5_results.py  -> results/v5_equity_curve.png
import os
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["text.parse_math"] = False   # treat "$" as a literal dollar sign
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from backtest_fade_variants import collect_fade_trades, apply_variant, Variant, weighted_returns

ACCOUNT0 = 10_000.0          # starting account
RISK_PCT = 0.01              # risk 1% of the STARTING capital per trade
R = ACCOUNT0 * RISK_PCT      # = $100 risked per trade (fixed-fractional on initial)

# --- V5 trades in date order ---
trades = collect_fade_trades()
rows = apply_variant(trades, Variant("V5", "no_failed_c", "active", "flat", "0DTE"))
pairs = weighted_returns(rows, 0.0)                       # [(date, return-on-risk)]
dates = [datetime.strptime(d, "%Y-%m-%d") for d, _ in pairs]
rets = [w for _, w in pairs]

# --- account equity ($) after each trade + drawdown ---
equity, peak = [], ACCOUNT0
eq, pk = ACCOUNT0, ACCOUNT0
dd_dollar, dd_pct = [], []
for r in rets:
    eq += R * r                                          # $ P&L = return-on-risk x $100
    equity.append(eq)
    pk = max(pk, eq)
    dd_dollar.append(eq - pk)
    dd_pct.append((eq - pk) / pk * 100)

final = equity[-1]
total_pct = (final - ACCOUNT0) / ACCOUNT0 * 100
worst_dd_dollar = min(dd_dollar)
worst_dd_pct = min(dd_pct)
wins = sum(1 for r in rets if r > 0)
by_year = defaultdict(float)
for (d, _), r in zip(pairs, rets):
    by_year[d[:4]] += R * r

# --- plot ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                               gridspec_kw={"height_ratios": [3, 1]})

ax1.plot(dates, equity, color="#1a7f37", lw=2.2, zorder=3)
ax1.fill_between(dates, ACCOUNT0, equity, where=[e >= ACCOUNT0 for e in equity],
                 color="#1a7f37", alpha=0.10, zorder=1)
ax1.axhline(ACCOUNT0, color="gray", ls="--", lw=1, zorder=2)
ax1.scatter([dates[-1]], [final], color="#1a7f37", zorder=4)
ax1.annotate(f"  ${final:,.0f}", (dates[-1], final), va="center", fontsize=12,
             weight="bold", color="#1a7f37")
ax1.annotate("start $10,000", (dates[0], ACCOUNT0), xytext=(0, -16),
             textcoords="offset points", fontsize=9, color="gray")
ax1.set_title("V5 fade strategy — $10,000 account, risking 1% ($100) per trade   "
              "(Jul 2023 – Jun 2026)", fontsize=13, weight="bold")
ax1.set_ylabel("Account value ($)")
ax1.yaxis.set_major_formatter(lambda x, _: f"${x:,.0f}")

box = (f"Total return    +{total_pct:.0f}%   (${ACCOUNT0:,.0f} -> ${final:,.0f})\n"
       f"Worst drawdown  ${worst_dd_dollar:,.0f}  ({worst_dd_pct:.1f}%)\n"
       f"Win rate        {wins / len(rets) * 100:.0f}%   over {len(rets)} trades\n"
       f"By year         " + "   ".join(f"{y} +${by_year[y]:,.0f}" for y in sorted(by_year)))
ax1.text(0.015, 0.97, box, transform=ax1.transAxes, va="top", ha="left",
         fontsize=10, family="monospace",
         bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#1a7f37", alpha=0.95))

ax2.fill_between(dates, dd_pct, 0, color="#cf222e", alpha=0.45)
ax2.plot(dates, dd_pct, color="#cf222e", lw=1)
ax2.set_ylabel("Drawdown (%)")
ax2.set_xlabel("Date")
ax2.axhline(0, color="gray", lw=0.8)

for ax in (ax1, ax2):
    for yr in ("2024", "2025", "2026"):
        ax.axvline(datetime(int(yr), 1, 1), color="gray", ls=":", lw=0.8, alpha=0.6)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, alpha=0.15)

fig.tight_layout()
os.makedirs("results", exist_ok=True)
out = "results/v5_equity_curve.png"
fig.savefig(out, dpi=130)
print(f"saved {out}")
print(f"  ${ACCOUNT0:,.0f} -> ${final:,.0f}  (+{total_pct:.0f}%)  worst drawdown "
      f"${worst_dd_dollar:,.0f} ({worst_dd_pct:.1f}%)  win {wins/len(rets)*100:.0f}%  n={len(rets)}")
print("  by year: " + ", ".join(f"{y} +${by_year[y]:,.0f}" for y in sorted(by_year)))
