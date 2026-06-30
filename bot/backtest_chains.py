# backtest_chains.py — the REAL backtest loop: run the condor day-by-day over a
# historical option-chain dataset (IVolatility-shaped), settling each 1DTE trade
# at the underlying's level on the expiration day.
#
# This is the production version of the fake-data loop in backtest.py. Here each
# day has its OWN chain (different strikes, different credit), and the settlement
# is the SPX close on the next day — not a made-up number. It runs end-to-end on
# a mock multi-day dataset now; swap in real IVolatility data and it just works.
#
# Run with:  .venv/bin/python bot/backtest_chains.py

import os
import time
from datetime import date, timedelta

import pandas as pd

from condor_rules import build_condor, payoff_at, net_credit
from load_ivolai import COLUMN_MAP
from backtest import max_drawdown
from sizing import position_size
from config import DEFAULT


def run_backtest_chains(chain_df, price_series, wing_width=50, target_delta=0.16):
    """Walk every trading day in `chain_df`, trade the 1DTE condor, settle it.

    chain_df     : option records across many dates (IVolatility column names).
    price_series : {date_str -> underlying close} — used for BOTH the entry spot
                   and the settlement (the close on the expiration day).
    Returns a list of per-trade dicts: date, expiration, spot, settle, credit, pnl.
    """
    df = chain_df.rename(columns=COLUMN_MAP)
    trades = []

    for D in sorted(df["date"].unique()):
        day = df[df["date"] == D]

        # 1DTE = the nearest expiration after today.
        future_exps = sorted(e for e in day["expiration"].unique() if e > D)
        if not future_exps:
            continue
        expiration = future_exps[0]

        # We can only score the trade if we know where it settled.
        if D not in price_series or expiration not in price_series:
            continue

        chain = day[day["expiration"] == expiration]
        puts = chain[chain["type"].isin(["P", "put", "Put"])].copy()
        calls = chain[chain["type"].isin(["C", "call", "Call"])].copy()
        if puts.empty or calls.empty:
            continue

        spot = price_series[D]
        settle = price_series[expiration]
        condor = build_condor(puts, calls, spot, expiration, symbol="SPX",
                              wing_width=wing_width, target_delta=target_delta,
                              today=date.fromisoformat(D))
        credit = net_credit(condor) * 100
        max_loss = wing_width * 100 - credit
        pnl = payoff_at(condor, settle)
        trades.append({
            "date": D, "expiration": expiration, "spot": spot, "settle": settle,
            "credit": credit, "max_loss": max_loss, "pnl": pnl,
            "ret_pct": pnl / max_loss if max_loss else 0.0,
        })
    return trades


def report_chains(trades):
    """Report performance in % RETURN ON CAPITAL-AT-RISK (account-independent).

    Each trade's return = P&L / max_loss (the collateral the broker locks up).
    Everything below is in those % terms, so it holds for any account size.
    """
    if not trades:
        print("No tradable days found.")
        return

    # Backfill max_loss / return-on-risk if loading an older CSV (SPX 50-wide).
    for t in trades:
        if "max_loss" not in t or t.get("max_loss") in (None, ""):
            t["max_loss"] = 5000 - t["credit"]
        if "ret_pct" not in t or t.get("ret_pct") in (None, ""):
            t["ret_pct"] = (t["pnl"] / t["max_loss"]) if t["max_loss"] else 0.0

    rets = [t["ret_pct"] for t in trades]            # decimals, e.g. 0.115 = +11.5%
    n = len(rets)
    wins = sum(1 for r in rets if r > 0)
    equity, running = [], 0.0
    for r in rets:
        running += r                                 # cumulative return, in units of risk
        equity.append(running)

    avg_win = sum(r for r in rets if r > 0) / max(wins, 1)
    losses = [r for r in rets if r <= 0]
    avg_loss = sum(losses) / max(len(losses), 1)
    breakeven = -avg_loss / (avg_win - avg_loss) if (avg_win - avg_loss) else 0

    print(f"=== BACKTEST: {n} trading days — % return on capital-at-risk ===\n")

    if n <= 15:
        print(f"  {'date':<12}{'spot':>8}{'settle':>8}{'credit%':>9}{'return%':>9}")
        for t in trades:
            cr = t["credit"] / (t["credit"] + t["max_loss"])
            print(f"  {t['date']:<12}{t['spot']:>8,.0f}{t['settle']:>8,.0f}"
                  f"{cr:>8.1%}{t['ret_pct']:>9.1%}")
    else:
        print("Cumulative return (sum of per-trade % on risk, sampled):")
        scale = max(abs(min(equity)), abs(max(equity)), 1e-9)
        step = max(1, n // 20)
        for i in range(step - 1, n, step):
            bar = "#" * int(abs(equity[i]) / scale * 30)
            print(f"  {trades[i]['date']}  {equity[i]:>+8.0%}  {bar}")
        print("\nWorst 5 days (% on risk):")
        for t in sorted(trades, key=lambda x: x["ret_pct"])[:5]:
            print(f"  {t['date']}  spot {t['spot']:,.0f} -> {t['settle']:,.0f}"
                  f"   return {t['ret_pct']:+.0%}")

    print(f"\nWin rate:        {wins/n:.0%}   ({wins} wins / {n-wins} losses)")
    print(f"Avg WIN:         {avg_win:+.1%} on risk   |   Avg LOSS: {avg_loss:+.1%} on risk")
    print(f"Breakeven win rate needed: {breakeven:.0%}   (you have {wins/n:.0%})")
    print(f"Total return:    {sum(rets):+.0%} on risk   (avg {sum(rets)/n:+.2%}/trade)")
    print(f"Best / Worst day: {max(rets):+.0%} / {min(rets):+.0%}")
    print(f"Max drawdown:    {max_drawdown(equity):.0%} of risk capital")


def _mock_dataset():
    """A pretend multi-day SPX dataset: a price path + a 1DTE chain each day."""
    dates = ["2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07",
             "2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13"]
    closes = [5000, 5010, 4990, 5005, 5035, 4960, 5000, 5020, 4995]   # a down day in there
    price_series = {d: float(c) for d, c in zip(dates, closes)}

    rows = []
    for i in range(len(dates) - 1):                  # last day has no next-day settle
        D, E, spot = dates[i], dates[i + 1], price_series[dates[i]]
        center = round(spot / 25) * 25
        for step in range(-8, 9):                    # strikes: center +/- 200, 25 apart
            strike = center + 25 * step
            dist_steps = abs(strike - spot) / 25
            mid = max(0.50, 30 * (0.85 ** dist_steps))   # premium fades away from spot
            for cp in ("P", "C"):                         # column names match the live API
                rows.append({"c_date": D, "expiration_date": E, "price_strike": float(strike),
                             "call_put": cp, "Bid": round(mid - 0.5, 2),
                             "Ask": round(mid + 0.5, 2), "iv": 0.15})
    return pd.DataFrame(rows), price_series


def _spx_ohlc(from_date, to_date):
    """SPX daily OHLC over a window, as a DataFrame (date/open/high/low/close)."""
    import ivolatility as ivol
    ivol.setLoginParams(apiKey=os.environ["IVOL_API_KEY"])
    get = ivol.setMethod("/equities/eod/stock-prices")
    df = get(symbol="SPX", from_=from_date, to=to_date)
    return df[["date", "open", "high", "low", "close"]].copy()


def _spx_prices(from_date, to_date):
    """SPX EOD closes over a window: {date_str -> close}. Used for settlement."""
    df = _spx_ohlc(from_date, to_date)
    return {row["date"]: float(row["close"]) for _, row in df.iterrows()}


def compute_iv_rich(symbol, dates, entry="eod", window=20, moneyness=6.0):
    """Dates where ATM implied vol is 'rich' (>= its trailing median).

    The premium-richness filter: only sell when the market is paying you more
    than usual. ATM IV = the IV of the call nearest spot each day. Causal — uses
    only each day's own value vs. the prior `window` days' median.
    """
    import load_ivolai
    atm = {}
    for D in dates:
        try:
            _puts, calls, spot, _exp, _ = load_ivolai.load_chain(
                symbol, D, entry=entry, moneyness=moneyness)
        except Exception:
            continue
        idx = (calls["strike"] - spot).abs().idxmin()
        atm[D] = float(calls.loc[idx, "impliedVolatility"])
    s = pd.Series(atm).sort_index()
    med = s.rolling(window, min_periods=5).median().shift(1)   # prior days only (no peek)
    return {d for d in s.index if not pd.isna(med[d]) and s[d] >= med[d]}


def run_real_backtest(from_date, to_date, profile=DEFAULT, apply_filters=False,
                      slippage_per_leg=0.05, entry="eod", commission=0.0,
                      iv_rich_dates=None):
    """Backtest the 1DTE condor on REAL IVolatility data over [from, to].

    apply_filters    : if True, only trade days that pass Kirk's filter stack.
    slippage_per_leg : $ slippage per leg on entry (4 legs). 0.05 = Kirk's 5 cents.
    entry            : "eod" or "1545" (3:45pm chain — closer to Kirk's 3:30).
    commission       : $ per trade (round trip, all 4 legs).
    iv_rich_dates    : if given, ALSO require the day to be in this set (IV filter).
    """
    import load_ivolai
    from filters import add_indicators, trade_ok

    price_to = (date.fromisoformat(to_date) + timedelta(days=7)).isoformat()
    ohlc = _spx_ohlc(from_date, price_to)
    price_series = {r["date"]: float(r["close"]) for _, r in ohlc.iterrows()}
    ind = add_indicators(ohlc).set_index("date") if apply_filters else None

    slip_cost = slippage_per_leg * 4 * 100        # entry slippage, all 4 legs, x100
    trade_dates = sorted(d for d in price_series if from_date <= d <= to_date)

    trades, skipped = [], 0
    for D in trade_dates:
        if apply_filters:
            if D not in ind.index:
                continue
            ok, _reasons = trade_ok(ind.loc[D], D)
            if not ok:
                skipped += 1
                continue
        if iv_rich_dates is not None and D not in iv_rich_dates:   # premium not rich enough
            skipped += 1
            continue
        try:
            puts, calls, spot, expiration, _ = load_ivolai.load_chain(
                profile.symbol, D, moneyness=profile.moneyness, entry=entry)
        except Exception as e:
            print(f"  skip {D}: {repr(e)[:70]}")
            continue
        settle = price_series.get(expiration)
        if settle is None:
            continue
        condor = build_condor(puts, calls, spot, expiration, symbol=profile.symbol,
                              method=profile.strike_method,
                              otm_dollars=profile.otm_dollars,
                              wing_width=profile.wing_width,
                              target_delta=profile.target_delta,
                              today=date.fromisoformat(D))
        credit = net_credit(condor) * 100
        max_loss = profile.wing_width * 100 - credit
        pnl = payoff_at(condor, settle) - slip_cost - commission
        trades.append({
            "date": D, "expiration": expiration, "spot": spot, "settle": settle,
            "credit": credit, "max_loss": max_loss, "pnl": pnl,
            "ret_pct": pnl / max_loss if max_loss else 0.0,
        })
    if apply_filters or iv_rich_dates is not None:
        print(f"  (skipped {skipped} days; traded {len(trades)})", flush=True)
    return trades


def yearly_report(trades, label=""):
    """Per-year + total $ P&L per contract, win rate, and max drawdown."""
    years = sorted({t["date"][:4] for t in trades})
    print(f"\n--- {label} ---")
    print(f"  {'period':<8}{'trades':>8}{'win%':>7}{'P&L/contract':>15}{'maxDD':>10}")
    for y in years + ["TOTAL"]:
        sub = trades if y == "TOTAL" else [t for t in trades if t["date"].startswith(y)]
        if not sub:
            continue
        n = len(sub)
        wins = sum(1 for t in sub if t["pnl"] > 0)
        pnls = [t["pnl"] for t in sub]
        eq, run, peak, dd = [], 0.0, 0.0, 0.0
        for p in pnls:
            run += p
            peak = max(peak, run)
            dd = max(dd, peak - run)
        print(f"  {y:<8}{n:>8}{wins/n:>6.0%}{sum(pnls):>+14,.0f}{dd:>10,.0f}")


def account_report(trades, profile):
    """Apply a profile's position sizing to per-condor trades → ACCOUNT view.

    Shows total return and max drawdown as a % of YOUR account, at the contract
    count the sizer picks. Lets us try different profiles on the same backtest.
    """
    if not trades:
        print("No trades to size.")
        return

    sized = []
    for t in trades:
        n, _, note = position_size(t["max_loss"], profile.account, profile.risk_pct)
        sized.append({**t, "contracts": n, "pnl_acct": t["pnl"] * n})

    if all(s["contracts"] == 0 for s in sized):
        _, _, note = position_size(trades[0]["max_loss"], profile.account, profile.risk_pct)
        print(f"--- ACCOUNT VIEW: {profile.symbol} {profile.wing_width:.0f}-wide on "
              f"${profile.account:,.0f} @ {profile.risk_pct:.0%}/trade ---")
        print(f"  Can't trade this: {note}")
        return

    acct_pnls = [s["pnl_acct"] for s in sized]
    total = sum(acct_pnls)
    equity, running = [], 0.0
    for p in acct_pnls:
        running += p
        equity.append(running)
    dd = max_drawdown(equity)
    avg_n = sum(s["contracts"] for s in sized) / len(sized)

    print(f"--- ACCOUNT VIEW: {profile.symbol} {profile.wing_width:.0f}-wide on "
          f"${profile.account:,.0f} @ {profile.risk_pct:.0%}/trade ---")
    print(f"  Typical size:          ~{avg_n:.0f} contract(s)/trade")
    print(f"  Total account return:  {total/profile.account:+.1%}   (${total:,.0f})")
    print(f"  Max drawdown:          {dd/profile.account:.1%} of account   (${dd:,.0f})")


if __name__ == "__main__":
    if os.environ.get("IVOL_API_KEY"):
        # REAL backtest. Window from env (BT_FROM / BT_TO), default a 2-week test.
        frm = os.environ.get("BT_FROM", "2024-06-03")
        to = os.environ.get("BT_TO", "2024-06-14")
        print(f"Running real SPX 1DTE condor backtest: {frm} -> {to}\n", flush=True)
        trades = run_real_backtest(frm, to)
        if trades:                               # save results so we never re-pull
            os.makedirs("results", exist_ok=True)
            out = f"results/backtest_{frm}_to_{to}.csv"
            pd.DataFrame(trades).to_csv(out, index=False)
            print(f"\nSaved {len(trades)} trades -> {out}")
    else:
        # Offline mock (no key).
        chain_df, price_series = _mock_dataset()
        trades = run_backtest_chains(chain_df, price_series)
    report_chains(trades)
