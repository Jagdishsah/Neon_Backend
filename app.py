import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Simple Terminal", page_icon="📈", layout="wide")

# Fees
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- HELPER FUNCTIONS ---
def get_broker_commission(amount):
    if amount <= 50000: rate = 0.36 / 100
    elif amount <= 500000: rate = 0.33 / 100
    elif amount <= 2000000: rate = 0.31 / 100
    elif amount <= 10000000: rate = 0.27 / 100
    else: rate = 0.24 / 100
    return max(10, amount * rate)

@st.cache_data(ttl=60)
def fetch_live_price(symbol):
    try:
        url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return 0.0
        soup = BeautifulSoup(response.text, 'html.parser')
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag:
            return float(price_tag.text.strip().replace(",", ""))
    except:
        pass
    return 0.0

def calculate_metrics(units, total_buy_cost, current_price):
    if units <= 0: return 0, 0, 0
    sell_amount = units * current_price
    commission = get_broker_commission(sell_amount)
    deductions = commission + (sell_amount * SEBON_FEE) + DP_CHARGE
    net_receivable = sell_amount - deductions
    gross_pl = net_receivable - total_buy_cost
    pl_percent = (gross_pl / total_buy_cost) * 100 if total_buy_cost > 0 else 0
    return net_receivable, gross_pl, pl_percent

# --- MAIN APP ---
st.title("📈 NEPSE Portfolio (CSV Mode)")

# 1. LOAD DATA
try:
    # We read the file directly from the repo
    df = pd.read_csv("portfolio.csv")
except Exception as e:
    st.error("❌ Could not find 'portfolio.csv'. Make sure you created it in GitHub!")
    st.stop()

if df.empty:
    st.info("Portfolio is empty.")
else:
    # 2. DASHBOARD LOGIC
    total_invested = 0
    current_value = 0
    total_pl = 0
    
    dashboard_data = []
    
    progress_bar = st.progress(0, text="Fetching Live Prices...")
    
    for index, row in df.iterrows():
        progress_bar.progress((index + 1) / len(df))
        
        sym = str(row["Symbol"]).upper()
        units = float(row["Units"])
        cost = float(row["Total_Cost"])
        wacc = float(row["WACC"])
        
        # Live Price
        ltp = fetch_live_price(sym)
        if ltp == 0: ltp = wacc  # Fallback if offline
        
        curr_val = units * ltp
        _, net_pl, pl_pct = calculate_metrics(units, cost, ltp)
        
        total_invested += cost
        current_value += curr_val
        total_pl += net_pl
        
        dashboard_data.append({
            "Symbol": sym,
            "Units": units,
            "WACC": wacc,
            "LTP": ltp,
            "Invested": cost,
            "Value": curr_val,
            "Profit/Loss": net_pl,
            "% Change": pl_pct
        })
        
    progress_bar.empty()

    # 3. DISPLAY METRICS
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Investment", f"Rs. {total_invested:,.0f}")
    c2.metric("Current Value", f"Rs. {current_value:,.0f}", delta=f"{current_value-total_invested:,.0f}")
    c3.metric("Net Profit", f"Rs. {total_pl:,.0f}", delta_color="normal")
    
    # 4. DATA TABLE
    final_df = pd.DataFrame(dashboard_data)
    st.dataframe(final_df.style.format({
        "WACC": "{:.1f}", 
        "LTP": "{:.1f}", 
        "Invested": "{:,.0f}", 
        "Value": "{:,.0f}", 
        "Profit/Loss": "{:,.0f}", 
        "% Change": "{:.2f}%"
    }), use_container_width=True)

    st.markdown("---")
    st.info("📝 **How to add stocks:** Go to GitHub -> Edit `portfolio.csv` -> Commit Changes -> Reboot App.")
