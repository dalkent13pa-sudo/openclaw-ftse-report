# openclaw_ftse_daily_report.py
# Simplified table + sector split + sorting + Value column + colour coding

import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime

working_dir = "/home/dalkent13/.openclaw/workspace-data-analyst/Data"
ticker_file = os.path.join(working_dir, "ftse100_tickers.csv")  # adjust name if different
output_html = os.path.join(working_dir, "openclaw_ftse_report.html")

# Load tickers
with open(ticker_file, 'r') as f:
    tickers = [line.strip() for line in f if line.strip() and line.strip().endswith('.L')]

print(f"Loaded {len(tickers)} tickers")

data = []
print("Pulling latest data...")

for idx, t in enumerate(tickers):
    if idx % 15 == 0 and idx > 0:
        time.sleep(3)

    try:
        ticker = yf.Ticker(t)
        info = ticker.info
        hist = ticker.history(period="5d")
        current_price = hist['Close'].iloc[-1] if not hist.empty else np.nan

        row = {
            'Ticker': t,
            'Name': info.get('longName', 'N/A'),
            'Sector': info.get('sector', 'Unknown'),
            'Current Price': current_price,
            'Forward PE': info.get('forwardPE'),
            'Forward Looking EPS': info.get('forwardEps'),
            'Forecast Dividend per Share': info.get('dividendRate'),
            'WACC': round(0.043 + (info.get('beta', 1.0) * 0.050) * 0.6 + 0.060 * 0.4 * 0.75, 4),
        }
        data.append(row)

    except:
        data.append({'Ticker': t, 'Name': 'Error'})

df = pd.DataFrame(data)

# Numeric conversion
for col in ['Current Price', 'Forward PE', 'Forward Looking EPS',
            'Forecast Dividend per Share', 'WACC']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Ratios
g = 0.03
g5 = 1.03 ** 5
mask = df['WACC'] > g

df['Int Val Div'] = np.where(
    mask,
    100 * df['Forecast Dividend per Share'].fillna(0) / (df['WACC'] - g),
    np.nan
)

df['Int Val PE'] = 100 * df['Forward PE'].fillna(0) * df['Forward Looking EPS'].fillna(0) * g5

# Target Price = average of the two
df['Target Price'] = df[['Int Val Div', 'Int Val PE']].mean(axis=1, skipna=True)

# Value = Target Price / Current Price
df['Value'] = df['Target Price'] / df['Current Price']

# Sort by Value descending within each sector
df = df.sort_values(['Sector', 'Value'], ascending=[True, False])

# ==================== HTML REPORT ====================
html = ""

for sector, group in df.groupby('Sector'):
    if group.empty:
        continue

    sector_html = group.to_html(
        index=False,
        escape=False,
        classes="table table-striped table-hover",
        float_format="%.4f"
    )

    # Apply colour to Value column
    sector_html = sector_html.replace(
        '<td>', '<td style="text-align:right;">'
    ).replace(
        '<th>Value</th>', '<th style="text-align:right;">Value</th>'
    )

    # Colour Value cells
    for i, value in enumerate(group['Value']):
        if pd.isna(value):
            color = ""
        elif value > 1:
            color = 'background-color:#dbeafe; color:#1e40af;'  # blue
        elif value < 1:
            color = 'background-color:#fee2e2; color:#991b1b;'  # red
        else:
            color = 'background-color:#f3f4f6;'  # grey

        sector_html = sector_html.replace(
            f'<tr>\n    <td>{group.iloc[i]["Ticker"]}</td>',
            f'<tr style="{color}">\n    <td>{group.iloc[i]["Ticker"]}</td>',
            1
        )

    html += f"""
<h2>{sector}</h2>
<p>{len(group)} companies – sorted by Value (higher = better)</p>
{sector_html}
<hr>
"""

full_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>OpenClaw FTSE Report – {datetime.now().strftime('%d %b %Y')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 30px; background: #f9fafb; }}
        h1 {{ color: #1e40af; }}
        h2 {{ color: #1e3a8a; margin-top: 40px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
        th, td {{ padding: 10px 12px; text-align: right; border: 1px solid #d1d5db; }}
        th {{ background: #1e3a8a; color: white; }}
        tr:nth-child(even) {{ background: #f3f4f6; }}
        .highlight-blue {{ background-color: #dbeafe !important; color: #1e40af !important; font-weight: bold; }}
        .highlight-red {{ background-color: #fee2e2 !important; color: #991b1b !important; font-weight: bold; }}
        .highlight-grey {{ background-color: #f3f4f6 !important; }}
    </style>
</head>
<body>
    <h1>OpenClaw FTSE 100 Report</h1>
    <p>Generated: {datetime.now().strftime('%d %B %Y at %H:%M')}</p>
    {html}
</body>
</html>
"""

with open(output_html, "w", encoding="utf-8") as f:
    f.write(full_html)

print(f"Daily report saved: {output_html}")
print("You can open this file in any browser (phone, laptop, etc.).")

# ==================== PUSH TO GITHUB ====================

import subprocess

repo_path = working_dir  # your Data folder
html_file_name = "openclaw_report.html"  # the file we just created

try:
    # Initialize git if not already (only first time)
    if not os.path.exists(os.path.join(repo_path, ".git")):
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/YOUR_GITHUB_USERNAME/openclaw-ftse-report.git"], cwd=repo_path, check=True)

    # Copy the report to repo root (or keep it there)
    # If your report is already in working_dir, skip copy

    # Add, commit, push
    subprocess.run(["git", "add", html_file_name], cwd=repo_path, check=True)
    commit_msg = f"Daily update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, check=True)
    subprocess.run(["git", "push", "origin", "main", "--force"], cwd=repo_path, check=True)

    print(f"Successfully pushed to GitHub Pages")
    print(f"View report here: https://YOUR_GITHUB_USERNAME.github.io/openclaw-ftse-report/{html_file_name}")

except Exception as git_err:
    print(f"Git push failed: {git_err}")
    print("Make sure git is installed and you have set up SSH or PAT for push.")
