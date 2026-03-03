# openclaw_ftse_latest.py
# OpenClaw version: forward-looking metrics + current price + WACC + target price
# No market cap, no sector weights, no cashflow, no historicals

import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
import glob
from datetime import datetime

# ==================== CONFIG ====================
# Use current working directory (OpenClaw notebook folder)
working_dir = os.getcwd()
print(f"Working directory: {working_dir}")

# Automatically find the tickers file (any file with 'tickers' in name)
ticker_files = glob.glob(os.path.join(working_dir, "*tickers*.csv")) + \
               glob.glob(os.path.join(working_dir, "*tickers*.txt"))

if not ticker_files:
    print("No ticker file found in current directory.")
    print("Please place a file with one ticker per line (e.g. RIO.L) in this folder.")
    exit()

ticker_file = ticker_files[0]  # take the first one found
print(f"Using ticker file: {ticker_file}")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = os.path.join(working_dir, f'ftse100_openclaw_latest_{timestamp}.xlsx')

# Load tickers
with open(ticker_file, 'r') as f:
    tickers = [line.strip() for line in f if line.strip() and line.strip().endswith('.L')]

print(f"Loaded {len(tickers)} tickers")

data = []
print("Pulling data from yfinance...")

for idx, t in enumerate(tickers):
    if idx % 10 == 0 and idx > 0:
        print(f"Progress: {idx+1}/{len(tickers)}")
        time.sleep(3)  # gentle rate limit

    try:
        ticker = yf.Ticker(t)
        info = ticker.info

        # Current price (latest close)
        hist = ticker.history(period="5d")
        current_price = hist['Close'].iloc[-1] if not hist.empty else np.nan

        forward_pe = info.get('forwardPE')
        forward_eps = info.get('forwardEps')
        forecast_div = info.get('dividendRate')  # forward annualized dividend

        # WACC (simple model)
        rf = 0.043
        erp = 0.050
        kd = 0.060
        tax = 0.25

        beta = info.get('beta', 1.0)
        cost_equity = rf + beta * erp
        w_equity = 0.6
        w_debt = 0.4
        wacc = cost_equity * w_equity + kd * w_debt * (1 - tax)

        # Price required for 4.5% yield (×100 for pence scale)
        price_for_4_5_yield = (forecast_div / 0.045) * 100 if forecast_div and forecast_div > 0 else np.nan

        row = {
            'Ticker': t,
            'Name': info.get('longName', 'N/A'),
            'Current Price': current_price,
            'Forward PE': forward_pe,
            'Forward Looking EPS': forward_eps,
            'Forecast Dividend per Share': forecast_div,
            'WACC': wacc,
            'Price for 4.5% Dividend Yield (×100)': price_for_4_5_yield,
        }

        data.append(row)

    except Exception as e:
        print(f"{t} failed: {str(e)[:80]}")
        data.append({'Ticker': t, 'Name': 'Error'})

df = pd.DataFrame(data)

# Numeric conversion
numeric_cols = [
    'Current Price', 'Forward PE', 'Forward Looking EPS',
    'Forecast Dividend per Share', 'WACC', 'Price for 4.5% Dividend Yield (×100)'
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Selected ratios
g = 0.03
g5 = 1.03 ** 5
mask = df['WACC'] > g

df['100* Forward_Dividend_Per_Share/(WACC-0.03)'] = np.where(
    mask,
    100 * df['Forecast Dividend per Share'].fillna(0) / (df['WACC'] - g),
    np.nan
)

df['100*Forecast P/E * Forecast EPS * 1.03^5'] = (
    100 * df['Forward PE'].fillna(0) * df['Forward Looking EPS'].fillna(0) * g5
)

# Target Price = mean of the two ratios
ratio_div = df['100* Forward_Dividend_Per_Share/(WACC-0.03)']
ratio_pe = df['100*Forecast P/E * Forecast EPS * 1.03^5']

df['Target Price'] = np.where(
    ratio_div.notna() & ratio_pe.notna(),
    (ratio_div + ratio_pe) / 2,
    np.where(ratio_div.notna(), ratio_div,
             np.where(ratio_pe.notna(), ratio_pe, np.nan))
)

df.round(4).to_excel(output_file, index=False, sheet_name='OpenClaw')

print(f"\nDone! Output saved to:")
print(output_file)
print("\nColumns in output:")
print(df.columns.tolist())
print("\nFirst few rows preview:")
print(df.head())
