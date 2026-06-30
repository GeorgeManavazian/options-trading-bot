# backtest.py — run the iron condor against historical (or fake) chains.
#
# STEP A proved the pipe on ONE fake day:
#     fake chain -> build_condor (pick 4 legs) -> payoff_at (P&L)
# STEP B (now): wrap a LOOP around it for many fake days, scatter where the
# market "settles" each day, and report the three things that matter:
#     WIN RATE  ·  EQUITY CURVE  ·  MAX DRAWDOWN
#
# Numbers are still INVENTED — but tuned to be honest: a THIN credit against a
# WIDE wing, so we don't fool ourselves into thinking condors print money.
# Real prices plug into this same scaffold later (IVolatility/ThetaData).
#
# Run with:  .venv/bin/python bot/backtest.py

import random
from datetime import date, timedelta

import pandas as pd

from condor_rules import build_condor, summarize, net_credit, payoff_at


def fake_chain(spot=100.0, iv=0.20):
    """Build a PRETEND option chain centered on `spot`.

    Columns match what the engine expects: strike / bid / ask / impliedVolatility.
    Premium peaks at-the-money and DECAYS fast as strikes move out (so the
    far-out wings are cheap and the credit you collect is realistically thin).
    """
    put_rows, call_rows = [], []
    for k in range(int(spot) - 10, int(spot) + 11):     # strikes: spot-10 .. spot+10
        mid = 0.90 * (0.78 ** abs(k - spot))             # fake premium, fades with distance
        bid, ask = round(max(0.01, mid - 0.03), 2), round(mid + 0.03, 2)
        row = {"strike": float(k), "bid": bid, "ask": ask, "impliedVolatility": iv}
        put_rows.append(row)
        call_rows.append(dict(row))
    return pd.DataFrame(put_rows), pd.DataFrame(call_rows)


def max_drawdown(equity_curve):
    """Worst peak-to-trough drop along a running-total curve (a positive $ number).

    Walk left to right, remember the highest point seen so far, and track the
    biggest fall below that high. This is the 'how deep did it dig' pain metric.
    """
    peak, worst = equity_curve[0], 0.0
    for value in equity_curve:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def run_backtest(n_days=100, spot=100.0, daily_move_pct=0.01, seed=42):
    """Trade the SAME fake 1DTE condor for n_days, varying only where it settles.

    daily_move_pct : size of a typical 1-day move (1% = a calm index day).
    Returns (condor, list_of_pnls). We freeze one chain/condor so the only
    moving part is the settlement price — keeps the lesson clean.
    """
    random.seed(seed)                                    # same run every time, so we can discuss it
    expiration = (date.today() + timedelta(days=1)).isoformat()
    puts, calls = fake_chain(spot)
    condor = build_condor(puts, calls, spot, expiration, symbol="FAKE")

    pnls = []
    for _ in range(n_days):
        move = random.gauss(0, daily_move_pct * spot)    # bell-curve daily move, in $
        settle = spot + move                             # where it "closes" at expiration
        pnls.append(payoff_at(condor, settle))
    return condor, pnls


def report(condor, pnls):
    """Print the three deliverables: win rate, equity curve, max drawdown."""
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    equity = []                                          # running total, day by day
    running = 0.0
    for p in pnls:
        running += p
        equity.append(running)

    print(f"\n=== BACKTEST: {n} fake days ===")
    print(f"Same trade each day: short {condor['short_put']['strike']:.0f}/"
          f"{condor['short_call']['strike']:.0f}, wings "
          f"{condor['long_put']['strike']:.0f}/{condor['long_call']['strike']:.0f}, "
          f"credit ${net_credit(condor)*100:,.0f}.\n")

    print(f"Win rate:       {wins/n:.0%}   ({wins} wins / {n-wins} losses)")
    print(f"Total P&L:      ${total:,.0f}   over {n} days")
    print(f"Average/day:    ${total/n:,.2f}")
    print(f"Best day:       ${max(pnls):,.0f}")
    print(f"Worst day:      ${min(pnls):,.0f}")
    print(f"Max drawdown:   ${max_drawdown(equity):,.0f}   (worst peak-to-trough slide)")

    # A little text picture of the equity curve, sampled every 10 days.
    print("\nEquity curve (running total):")
    span = max(abs(min(equity)), abs(max(equity)), 1.0)  # scale so the biggest bar ~30 chars
    for i in range(9, n, 10):
        bar = "#" * int(abs(equity[i]) / span * 30)
        print(f"  day {i+1:>3}:  ${equity[i]:>8,.0f}  {bar}")


if __name__ == "__main__":
    condor, pnls = run_backtest(n_days=100)
    summarize(condor)                                    # show the box we repeat
    report(condor, pnls)
