import streamlit as st
import pandas as pd
from datetime import datetime
import time
from app.utils import get_data, save_data, log_error
from scrape import get_market_data
from app import config

# --- FINANCIAL CALCULATIONS ---
def get_broker_commission(amount):
    if amount <= 50000: return max(10, amount * 0.36 / 100)
    elif amount <= 500000: return amount * 0.33 / 100
    elif amount <= 2000000: return amount * 0.31 / 100
    elif amount <= 10000000: return amount * 0.27 / 100
    else: return amount * 0.24 / 100

def calculate_metrics(df, cache_df):
    """Calculates portfolio metrics based on current market prices."""
    if df.empty: return 0, 0, 0, 0
    merged = pd.merge(df, cache_df[['Symbol', 'LTP']], on='Symbol', how='left')
    merged['Current_Value'] = merged['Units'] * merged['LTP']
    total_investment = merged['Total_Cost'].sum()
    current_value = merged['Current_Value'].sum()
    net_pl = current_value - total_investment
    pl_pct = (net_pl / total_investment * 100) if total_investment > 0 else 0
    return total_investment, current_value, net_pl, pl_pct

# --- UPDATE LOGIC ---
def update_wealth_log():
    try:
        port_df = get_data("portfolio.csv")
        cache_df = get_data("cache.csv")
        inv, val, pl, pct = calculate_metrics(port_df, cache_df)
        
        wealth_df = get_data("wealth.csv")
        today = datetime.now().strftime("%Y-%m-%d")
        
        new_record = {"Date": today, "Total_Investment": inv, "Current_Value": val, "Total_PL": pl}
        if not wealth_df.empty and wealth_df.iloc[-1]['Date'] == today:
            wealth_df.iloc[-1] = new_record
        else:
            wealth_df = pd.concat([wealth_df, pd.DataFrame([new_record])], ignore_index=True)
        
        save_data("wealth.csv", wealth_df, f"Wealth update: {today}")
    except Exception as e:
        log_error("update_wealth_log", str(e))

def refresh_market_cache():
    """Scrapes new data and updates the cache.csv file."""
    try:
        new_data = get_market_data()
        if new_data:
            cache_df = pd.DataFrame(new_data)
            cache_df['LastUpdated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_data("cache.csv", cache_df, "Market cache refresh")
            st.success("✅ Market Data Refreshed")
            return True
    except Exception as e:
        log_error("refresh_market_cache", str(e))
    return False
