# pull_options.py — peeking at a real option chain
# Run with:  .venv/bin/python pull_options.py

import yfinance as yf

ticker = "SPY"
spy = yf.Ticker(ticker)   # a Ticker object = a "handle" we can ask questions of

# 1) What expiration dates are even available to trade right now?
expirations = spy.options
print("=== Available expiration dates for", ticker, "===")
print(expirations)
print()

# 2) Grab the full option chain for the SOONEST expiration.
nearest = expirations[0]
chain = spy.option_chain(nearest)   # this has two parts: .calls and .puts
# What is SPY trading at right now? We'll center the chain on this.
spot = spy.fast_info["last_price"]
print(f"SPY is trading near ${spot:,.2f} right now.\n")

print(f"=== PUTS expiring {nearest} (the 6 strikes nearest the money) ===")

# Each row is one option contract. Show just the columns that matter to us.
cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest"]
puts = chain.puts[cols]

# Find the row whose strike is closest to the current price, show 3 on each side.
atm_index = (puts["strike"] - spot).abs().idxmin()
pos = puts.index.get_loc(atm_index)
print(puts.iloc[pos - 3 : pos + 3].to_string(index=False))
