# openclaw_etoro_simple.py
# Portfolio viewer with ticker matching + eToro-based daily % change from price history

from dotenv import load_dotenv
import os
import requests
import uuid
from collections import defaultdict
import csv
import json
from datetime import datetime, timedelta
import yfinance as yf

load_dotenv("etoro.env")

PUBLIC_API_KEY = os.getenv("ETORO_PUBLIC_API_KEY")
USER_KEY       = os.getenv("ETORO_USER_KEY")

if not PUBLIC_API_KEY or not USER_KEY:
    raise ValueError("Missing keys in etoro.env")

BASE_URL = "https://public-api.etoro.com/api/v1"
HEADERS = {
    "x-api-key": PUBLIC_API_KEY,
    "x-user-key": USER_KEY,
    "x-request-id": str(uuid.uuid4()),
    "Accept": "application/json"
}

MATCH_CSV     = "etoro_portfolio_tickermatch.csv"
OUTPUT_CSV    = "etoro_portfolio_output.csv"
PRICE_HISTORY = "etoro_price_history.json"   # stores daily closeRate per ID

# ────────────────────────────────────────────────
# Load ticker/exchange mapping
# ────────────────────────────────────────────────
def load_mapping():
    mapping = {}
    try:
        with open(MATCH_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    iid = int(row['Asset_ID'])
                    ticker = row['Ticker'].strip()
                    exc = row.get('Exchange', 'N/A').strip()
                    mapping[iid] = (ticker, exc)
                except:
                    continue
        print(f"Loaded {len(mapping)} ticker mappings")
    except Exception as e:
        print(f"Mapping CSV error: {e}")
    return mapping

# ────────────────────────────────────────────────
# Price history (eToro closeRate) load & save
# ────────────────────────────────────────────────
def load_price_history():
    if os.path.exists(PRICE_HISTORY):
        with open(PRICE_HISTORY, 'r') as f:
            return json.load(f)
    return {}

def save_price_history(positions, history):
    today = datetime.now().strftime("%Y-%m-%d")
    today_prices = {}
    for pos in positions:
        iid = pos.get("instrumentID")
        if iid and "closeRate" in pos.get("unrealizedPnL", {}):
            today_prices[iid] = pos["unrealizedPnL"]["closeRate"]
    
    history[today] = today_prices
    
    with open(PRICE_HISTORY, 'w') as f:
        json.dump(history, f, indent=2)
    
    print(f"Saved today's prices to {PRICE_HISTORY}")

# ────────────────────────────────────────────────
# yfinance lookup (name + sector only)
# ────────────────────────────────────────────────
def get_yf_info(ticker):
    if not ticker or ticker == "N/A":
        return "N/A", "N/A"
    
    try:
        yft = yf.Ticker(ticker)
        info = yft.info
        name   = info.get('longName') or info.get('shortName') or 'N/A'
        sector = info.get('sector') or info.get('category') or 'N/A'
        return name, sector
    except Exception as e:
        print(f"yfinance name/sector failed for {ticker}: {str(e)[:80]}...")
        return "Lookup failed", "N/A"

# ────────────────────────────────────────────────
# Main function
# ────────────────────────────────────────────────
def get_portfolio():
    url = f"{BASE_URL}/trading/info/real/pnl"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        port = data.get("clientPortfolio", {})
        if not port:
            print("No portfolio data.")
            return
        
        credit = port.get("credit", 0)
        total_pnl = port.get("unrealizedPnL", 0)
        positions = port.get("positions", [])
        
        print(f"\n=== OpenClaw Portfolio Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        print(f"Credit: ${credit:,.2f} | Total PnL: ${total_pnl:,.2f} | Positions: {len(positions)}")
        
        if not positions:
            print("No open positions.")
            return
        
        mapping = load_mapping()
        history = load_price_history()
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yest_prices = history.get(yesterday, {})
        
        # Group
        grouped = defaultdict(lambda: {"amt":0, "value":0, "pnl":0, "units":0, "count":0, "close_rate":None})
        for pos in positions:
            iid = pos.get("instrumentID")
            if not isinstance(iid, int): continue
            u = pos.get("unrealizedPnL", {})
            grouped[iid]["amt"]   += pos.get("amount", 0)
            grouped[iid]["value"] += u.get("exposureInAccountCurrency", 0)
            grouped[iid]["pnl"]   += u.get("pnL", 0)
            grouped[iid]["units"] += pos.get("units", 0)
            grouped[iid]["count"] += 1
            if "closeRate" in u:
                grouped[iid]["close_rate"] = u["closeRate"]
        
        # Sort by value desc
        sorted_g = sorted(grouped.items(), key=lambda x: x[1]["value"], reverse=True)
        
        print("-"*140)
        print(f"{'Ticker/Exc (ID)':<40} {'Company':<35} {'Sector':<18} {'Trades':<6} {'Invested':<12} {'Value':<14} {'PnL $':<10} {'PnL %':<8} {'Daily % (eToro)':<14} {'Units':<12}")
        print("-"*140)
        
        rows = []
        for iid, g in sorted_g:
            ticker, exc = mapping.get(iid, (f"ID {iid}", "N/A"))
            company, sector = get_yf_info(ticker)
            
            curr_price = g["close_rate"]
            prev_price = yest_prices.get(str(iid))
            daily_pct = None
            if curr_price is not None and prev_price is not None and prev_price != 0:
                daily_pct = ((curr_price - prev_price) / prev_price) * 100
            
            invested = g["amt"]
            value    = g["value"]
            pnl      = g["pnl"]
            pnl_pct  = (pnl / invested * 100) if invested else 0
            units    = g["units"]
            trades   = g["count"]
            
            daily_str = f"{daily_pct:>+8.2f}%" if daily_pct is not None else "N/A"
            
            display = f"{ticker} / {exc} ({iid})"
            
            print(f"{display:<40} {company[:34]:<35} {sector[:17]:<18} {trades:<6} " +
                  f"${invested:>11,.2f} ${value:>13,.2f} ${pnl:>9,.2f} " +
                  f"{pnl_pct:>+8.2f}% {daily_str:<14} {units:>11,.6f}")
            
            rows.append({
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Asset_ID": iid,
                "Ticker": ticker,
                "Exchange": exc,
                "Company_Name": company,
                "Sector": sector,
                "Trades": trades,
                "Invested_USD": round(invested, 2),
                "Current_Value_USD": round(value, 2),
                "PnL_USD": round(pnl, 2),
                "PnL_Percent": round(pnl_pct, 2),
                "Daily_Change_%_eToro": round(daily_pct, 2) if daily_pct is not None else "N/A",
                "Units_Held": round(units, 6),
                "Current_Price_eToro": round(curr_price, 4) if curr_price is not None else "N/A"
            })
        
        print("-"*140)
        
        # Save output CSV
        if rows:
            with open(OUTPUT_CSV, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"Saved to {OUTPUT_CSV}")
        
        # Save today's prices for tomorrow's daily change
        save_price_history(positions, history)
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_portfolio()
