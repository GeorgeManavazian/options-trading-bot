# pull_data.py — my first real market data pull
# Run from the project folder with:  .venv/bin/python pull_data.py
#   (or: source .venv/bin/activate  then  python pull_data.py)

import yfinance as yf   # "import" loads a tool. "as yf" gives it a short nickname.

# Pick what we want to look at. SPY = the ETF that tracks the S&P 500.
ticker = "SPY"

# Ask Yahoo Finance for the last 5 trading days of daily prices.
# This returns a "DataFrame" — basically a spreadsheet that lives in code.
data = yf.download(ticker, period="5d", interval="1d", auto_adjust=True)

print("=== Last 5 trading days for", ticker, "===")
print(data)

# Pull out just the most recent closing price to show we can grab one number.
latest_close = data["Close"].iloc[-1].item()
print()
print(f"Most recent closing price: ${latest_close:,.2f}")
