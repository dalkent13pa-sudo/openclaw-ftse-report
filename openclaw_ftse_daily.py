# openclaw_ftse_daily.py
# Daily FTSE 100 OpenClaw valuation report + auto GitHub push + Discord notification
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime
import git # pip install gitpython
import requests # for Discord webhook
# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────
WORKING_DIR = "/home/dalkent13/.openclaw/workspace-data-analyst/Data"
TICKER_FILE = os.path.join(WORKING_DIR, "ftse100_tickers.csv")
REPORT_HTML = os.path.join(WORKING_DIR, "openclaw_ftse_report.html")
INDEX_HTML = os.path.join(WORKING_DIR, "index.html")
REPO_URL = "https://github.com/dalkent13pa-sudo/openclaw-ftse-report.git"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1478668502448603136/9NpO1TlSwgcZh3VFt3Hqo_LDFg7LuAL8nYCQ-acN2bVcXzUECyIJx5pNRZYq8j-WhlKV"
# ────────────────────────────────────────────────
# Load tickers
# ────────────────────────────────────────────────
with open(TICKER_FILE, 'r') as f:
    tickers = [line.strip() for line in f if line.strip() and line.strip().endswith('.L')]
print(f"Loaded {len(tickers)} FTSE 100 tickers (.L)")
# ────────────────────────────────────────────────
# Data collection
# ────────────────────────────────────────────────
data = []
print("Pulling data from Yahoo Finance...")
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
            'Forward Looking EPS': info.get('forwardEps') or info.get('forwardEPS'),
            'Forecast Dividend per Share': info.get('dividendRate'),
            'WACC': round(0.043 + (info.get('beta', 1.0) * 0.050) * 0.6 + 0.060 * 0.4 * 0.75, 4),
            'Trailing EPS': info.get('trailingEps'),
        }
        data.append(row)
    except Exception as e:
        print(f" {t}: skipped ({str(e)})")
        data.append({'Ticker': t, 'Name': 'Error', 'Sector': 'Unknown'})

df = pd.DataFrame(data)
# Convert to numeric
numeric_cols = ['Current Price', 'Forward PE', 'Forward Looking EPS',
                'Forecast Dividend per Share', 'WACC', 'Trailing EPS']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# ────────────────────────────────────────────────
# SAVE RAW EXTRACT BEFORE FILTERING SECTORS
# ────────────────────────────────────────────────
raw_csv_path = os.path.join(WORKING_DIR, "Daily_FTSE_Extract.csv")
df.to_csv(raw_csv_path, index=False)
print(f"Raw extract (before sector filter) saved to: {raw_csv_path}")

# ────────────────────────────────────────────────
# Remove rows with missing / unknown Sector
# ────────────────────────────────────────────────
df = df[df['Sector'].notna() & (df['Sector'] != 'Unknown') & (df['Sector'] != '')].copy()
print(f"After removing unknown sectors: {len(df)} stocks remain")
# ────────────────────────────────────────────────
# Valuation logic
# ────────────────────────────────────────────────
g = 0.03
g5 = 1.03 ** 5
mask = df['WACC'] > g
df['Int Val Div'] = np.where(
    mask,
    100 * df['Forecast Dividend per Share'].fillna(0) / (df['WACC'] - g),
    np.nan
)
eps_used = df['Forward Looking EPS'].fillna(df['Trailing EPS'])
df['Int Val PE'] = 100 * df['Forward PE'].fillna(0) * eps_used.fillna(0) * g5
vals = df[['Int Val Div', 'Int Val PE']].copy()
vals[vals == 0] = np.nan
df['Target Price'] = vals.mean(axis=1, skipna=True)
df['Value'] = df['Target Price'] / df['Current Price']
# Yield as percentage (×100)
df['Yield'] = (df['Forecast Dividend per Share'] / df['Current Price']) * 10000
# Sort within each sector by Value descending
df = df.sort_values(['Sector', 'Value'], ascending=[True, False])
# ────────────────────────────────────────────────
# Prepare display dataframe with renamed columns
# ────────────────────────────────────────────────
df_display = df.copy()
df_display = df_display.rename(columns={
    'Forecast Dividend per Share': 'For Dividend',
})
# Final column order (no Sector column)
final_columns_ordered = [
    'Ticker',
    'Name',
    'WACC',
    'Forward PE',
    'Forward Looking EPS',
    'Trailing EPS',
    'For Dividend',
    'Int Val Div',
    'Int Val PE',
    'Target Price',
    'Current Price',
    'Value',
    'Yield'
]
# Round numeric columns to 2 decimal places (except Yield which we handle in formatting)
numeric_display_cols = [
    'WACC', 'Forward PE', 'Forward Looking EPS', 'Trailing EPS',
    'For Dividend', 'Int Val Div', 'Int Val PE', 'Target Price',
    'Current Price', 'Value'
]
for col in numeric_display_cols:
    if col in df_display.columns:
        df_display[col] = df_display[col].round(2)
# Round Yield to 2 decimal places too
df_display['Yield'] = df_display['Yield'].round(2)
# ────────────────────────────────────────────────
# Build HTML report with sector sections
# ────────────────────────────────────────────────
html_sections = ""
for sector, group in df_display.groupby('Sector'):
    if group.empty:
        continue
    # Select only the display columns
    group_display = group[final_columns_ordered]
    table_html = group_display.to_html(
        index=False,
        escape=False,
        classes="table table-striped table-hover",
        float_format="%.2f"
    )
    # Apply alignment:
    # Ticker & Name → left, others → center
    table_html = table_html.replace(
        '<th>Ticker</th>', '<th style="text-align:left;">Ticker</th>'
    ).replace(
        '<th>Name</th>', '<th style="text-align:left;">Name</th>'
    ).replace(
        '<th>', '<th style="text-align:center;">'
    ).replace(
        '<td>', '<td style="text-align:center;">'
    )
    # Override Ticker & Name cells to left align
    for i in range(len(group_display)):
        ticker = group_display.iloc[i]['Ticker']
        name = group_display.iloc[i]['Name']
        table_html = table_html.replace(
            f'<td>{ticker}</td>',
            f'<td style="text-align:left;">{ticker}</td>',
            1
        ).replace(
            f'<td>{name}</td>',
            f'<td style="text-align:left;">{name}</td>',
            1
        )
    # Apply row coloring based on Value
    for i, value in enumerate(group_display['Value']):
        if pd.isna(value):
            color = ""
        elif value > 1:
            color = 'background-color:#dbeafe; color:#1e40af;'
        elif value < 1:
            color = 'background-color:#fee2e2; color:#991b1b;'
        else:
            color = 'background-color:#f3f4f6;'
        table_html = table_html.replace(
            f'<tr>\n <td style="text-align:left;">{group_display.iloc[i]["Ticker"]}</td>',
            f'<tr style="{color}">\n <td style="text-align:left;">{group_display.iloc[i]["Ticker"]}</td>',
            1
        )
    # Format Yield column with % symbol
    table_html = table_html.replace(
        '<th>Yield</th>', '<th style="text-align:center;">Yield</th>'
    )
    html_sections += f"""
<h2>{sector}</h2>
<p>{len(group)} companies – sorted by Value (higher = better)</p>
{table_html}
<hr>
"""
# Post-process Yield column to add % symbol
html_sections = html_sections.replace(
    '<td style="text-align:center;">', '<td style="text-align:center;">', -1
)
# This is tricky with to_html – better to format Yield as string before to_html
# Better approach: format Yield as string with % before to_html
df_display['Yield'] = df_display['Yield'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
# Re-generate table_html with formatted Yield
html_sections = ""
for sector, group in df_display.groupby('Sector'):
    if group.empty:
        continue
    group_display = group[final_columns_ordered]
    table_html = group_display.to_html(
        index=False,
        escape=False,
        classes="table table-striped table-hover",
        float_format="%.2f"
    )
    # Alignment
    table_html = table_html.replace(
        '<th>Ticker</th>', '<th style="text-align:left;">Ticker</th>'
    ).replace(
        '<th>Name</th>', '<th style="text-align:left;">Name</th>'
    ).replace(
        '<th>', '<th style="text-align:center;">'
    ).replace(
        '<td>', '<td style="text-align:center;">'
    )
    # Left-align Ticker & Name
    for i in range(len(group_display)):
        ticker = group_display.iloc[i]['Ticker']
        name = group_display.iloc[i]['Name']
        table_html = table_html.replace(
            f'<td style="text-align:center;">{ticker}</td>',
            f'<td style="text-align:left;">{ticker}</td>',
            1
        ).replace(
            f'<td style="text-align:center;">{name}</td>',
            f'<td style="text-align:left;">{name}</td>',
            1
        )
    # Row coloring
    for i, value in enumerate(group_display['Value']):
        if pd.isna(value):
            color = ""
        elif value > 1:
            color = 'background-color:#dbeafe; color:#1e40af;'
        elif value < 1:
            color = 'background-color:#fee2e2; color:#991b1b;'
        else:
            color = 'background-color:#f3f4f6;'
        table_html = table_html.replace(
            f'<tr>\n <td style="text-align:left;">{group_display.iloc[i]["Ticker"]}</td>',
            f'<tr style="{color}">\n <td style="text-align:left;">{group_display.iloc[i]["Ticker"]}</td>',
            1
        )
    html_sections += f"""
<h2>{sector}</h2>
<p>{len(group)} companies – sorted by Value (higher = better)</p>
{table_html}
<hr>
"""
full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenClaw FTSE Report – {datetime.now().strftime('%d %b %Y')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 30px; background: #f9fafb; line-height: 1.5; }}
        h1 {{ color: #1e40af; }}
        h2 {{ color: #1e3a8a; margin-top: 2.5em; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
        th, td {{ padding: 10px 12px; border: 1px solid #d1d5db; }}
        th {{ background: #1e3a8a; color: white; }}
        tr:nth-child(even) {{ background: #f3f4f6; }}
    </style>
</head>
<body>
    <h1>OpenClaw FTSE 100 Report</h1>
    <p><strong>Generated:</strong> {datetime.now().strftime('%d %B %Y at %H:%M')}</p>
    {html_sections}
</body>
</html>"""
with open(REPORT_HTML, "w", encoding="utf-8") as f:
    f.write(full_html)
print(f"Report saved: {REPORT_HTML}")
with open(INDEX_HTML, "w", encoding="utf-8") as f:
    f.write(full_html)
print(f"Also created index.html for root URL")
# ────────────────────────────────────────────────
# GitHub auto-push using gitpython
# ────────────────────────────────────────────────
try:
    repo = git.Repo(WORKING_DIR)
    gitignore_path = os.path.join(WORKING_DIR, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write("""# Ignore temp files
*.xlsx
*.pyc
__pycache__/
*.log
.DS_Store
""")
        print("Created .gitignore")
    repo.index.add([REPORT_HTML, INDEX_HTML, gitignore_path])
    if repo.is_dirty(untracked_files=True):
        commit_msg = f"Daily OpenClaw FTSE report update – {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        repo.index.commit(commit_msg)
        print(f"Committed: {commit_msg}")
    else:
        print("No changes to commit (report identical to last push)")
    origin = repo.remotes.origin
    origin.push('main')
    print("Pushed successfully to GitHub main branch")
    print("\nLive report should be available in 1–5 minutes at:")
    print("→ https://dalkent13pa-sudo.github.io/openclaw-ftse-report/")
    print("→ Direct file: https://dalkent13pa-sudo.github.io/openclaw-ftse-report/openclaw_ftse_report.html")
    # ────────────────────────────────────────────────
    # Send Discord confirmation
    # ────────────────────────────────────────────────
    report_url = "https://dalkent13pa-sudo.github.io/openclaw-ftse-report/"
    direct_url = "https://dalkent13pa-sudo.github.io/openclaw-ftse-report/openclaw_ftse_report.html"
    commit_url = f"https://github.com/dalkent13pa-sudo/openclaw-ftse-report/commit/{repo.head.commit.hexsha}"
    message = (
        f"**OpenClaw FTSE Report updated!**\n"
        f"Generated: {datetime.now().strftime('%d %B %Y at %H:%M')}\n\n"
        f"📊 **Live report**: {report_url}\n"
        f"📄 **Direct HTML**: {direct_url}\n"
        f"🔗 **GitHub commit**: {commit_url}"
    )
    payload = {"content": message, "username": "OpenClaw Report"}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in (200, 204):
            print("Discord notification sent successfully")
        else:
            print(f"Discord failed: HTTP {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"Discord webhook error: {e}")
except git.exc.InvalidGitRepositoryError:
    print("\nERROR: Not a git repository. Run git init and add remote first.")
except git.exc.GitCommandError as e:
    print(f"Git error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
