import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Cloud Terminal", page_icon="☁️", layout="wide")

# Fees
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- GOOGLE SHEETS CONNECTION ---
# This looks for secrets.toml automatically
conn = st.connection("gsheets", type=GSheetsConnection)

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

def calculate_metrics(units, total_buy_cost, current_price, is_long_term=False):
    if units <= 0: return 0, 0, 0, 0, 0
    sell_amount = units * current_price
    commission = get_broker_commission(sell_amount)
    deductions = commission + (sell_amount * SEBON_FEE) + DP_CHARGE
    net_receivable = sell_amount - deductions
    gross_pl = net_receivable - total_buy_cost
    tax_rate = CGT_LONG if is_long_term else CGT_SHORT
    tax_amount = gross_pl * tax_rate if gross_pl > 0 else 0
    net_pl = gross_pl - tax_amount
    pl_percent = (net_pl / total_buy_cost) * 100 if total_buy_cost > 0 else 0
    return net_receivable, net_pl, pl_percent, tax_amount

# --- LOAD DATA ---
def load_data():
    # Load Portfolio
    try:
        df_p = conn.read(worksheet="Portfolio", ttl=0)
        # Ensure columns exist and types are correct
        if df_p.empty:
            df_p = pd.DataFrame(columns=["Symbol", "Units", "Total_Cost", "WACC", "Notes"])
        else:
            df_p["Units"] = pd.to_numeric(df_p["Units"], errors='coerce').fillna(0)
            df_p["Total_Cost"] = pd.to_numeric(df_p["Total_Cost"], errors='coerce').fillna(0)
            df_p["WACC"] = pd.to_numeric(df_p["WACC"], errors='coerce').fillna(0)
    except:
        df_p = pd.DataFrame(columns=["Symbol", "Units", "Total_Cost", "WACC", "Notes"])

    # Load Sales History
    try:
        df_s = conn.read(worksheet="Sales", ttl=0)
        if df_s.empty:
            df_s = pd.DataFrame(columns=["Date", "Symbol", "Units", "Sell_Price", "Net_PL", "Remarks"])
    except:
        df_s = pd.DataFrame(columns=["Date", "Symbol", "Units", "Sell_Price", "Net_PL", "Remarks"])
        
    return df_p, df_s

df_portfolio, df_sales = load_data()

# --- SIDEBAR ---
st.sidebar.title("☁️ NEPSE Cloud")
menu = st.sidebar.radio("Menu", ["Dashboard", "Portfolio", "Add Trade", "Sell Stock", "History"])

if st.sidebar.button("🔄 Force Sync"):
    st.cache_data.clear()
    st.rerun()

# ==========================================
# PAGE: DASHBOARD
# ==========================================
if menu == "Dashboard":
    st.title("📊 Cloud Dashboard")
    
    if df_portfolio.empty:
        st.info("Portfolio is empty. Go to 'Add Trade' to start.")
    else:
        # Progress Bar
        total_stocks = len(df_portfolio)
        progress_text = "Fetching live prices..."
        my_bar = st.progress(0, text=progress_text)
        
        total_invested = 0
        current_value = 0
        total_pl = 0
        
        dashboard_data = []
        
        for index, row in df_portfolio.iterrows():
            my_bar.progress((index + 1) / total_stocks)
            
            sym = row["Symbol"]
            units = row["Units"]
            cost = row["Total_Cost"]
            
            ltp = fetch_live_price(sym)
            if ltp == 0: ltp = row["WACC"] # Fallback if offline
            
            curr_val = units * ltp
            _, net_pl, pl_pct, _ = calculate_metrics(units, cost, ltp)
            
            total_invested += cost
            current_value += curr_val
            total_pl += net_pl
            
            dashboard_data.append({
                "Symbol": sym,
                "LTP": ltp,
                "Invested": cost,
                "Value": curr_val,
                "Net P/L": net_pl,
                "Change": pl_pct
            })
            
        my_bar.empty()
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Invested", f"Rs. {total_invested:,.0f}")
        col2.metric("Current Value", f"Rs. {current_value:,.0f}", delta=f"{current_value-total_invested:,.0f}")
        col3.metric("Total Net P/L", f"Rs. {total_pl:,.0f}", delta_color="normal")
        
        # Table
        st.dataframe(pd.DataFrame(dashboard_data).style.format({
            "LTP": "{:.1f}", "Invested": "{:,.0f}", "Value": "{:,.0f}", 
            "Net P/L": "{:,.0f}", "Change": "{:.2f}%"
        }), width=1000)

# ==========================================
# PAGE: PORTFOLIO
# ==========================================
elif menu == "Portfolio":
    st.title("💼 Live Holdings")
    st.dataframe(df_portfolio, use_container_width=True)

# ==========================================
# PAGE: ADD TRADE
# ==========================================
elif menu == "Add Trade":
    st.title("➕ Buy / Average Stock")
    
    with st.form("buy_form"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("Symbol").upper()
        units = c2.number_input("Units", min_value=1)
        price = c1.number_input("Price per Unit", min_value=1.0)
        note = c2.text_input("Note")
        
        if st.form_submit_button("Add to Cloud Portfolio"):
            # Calculate Costs
            raw_cost = units * price
            comm = get_broker_commission(raw_cost)
            fees = comm + (raw_cost * SEBON_FEE) + DP_CHARGE
            total_buy_cost = raw_cost + fees
            
            # Check if stock exists
            existing_idx = df_portfolio.index[df_portfolio['Symbol'] == sym].tolist()
            
            if existing_idx:
                # Average Out
                idx = existing_idx[0]
                old_units = df_portfolio.at[idx, 'Units']
                old_cost = df_portfolio.at[idx, 'Total_Cost']
                
                new_units = old_units + units
                new_cost = old_cost + total_buy_cost
                new_wacc = new_cost / new_units
                
                df_portfolio.at[idx, 'Units'] = new_units
                df_portfolio.at[idx, 'Total_Cost'] = new_cost
                df_portfolio.at[idx, 'WACC'] = new_wacc
                st.success(f"Averaged {sym}! New WACC: {new_wacc:.2f}")
            else:
                # New Entry
                new_row = pd.DataFrame([{
                    "Symbol": sym,
                    "Units": units,
                    "Total_Cost": total_buy_cost,
                    "WACC": total_buy_cost / units,
                    "Notes": note
                }])
                df_portfolio = pd.concat([df_portfolio, new_row], ignore_index=True)
                st.success(f"Added {sym} to Portfolio!")
            
            # PUSH TO GOOGLE SHEETS
            conn.update(worksheet="Portfolio", data=df_portfolio)
            st.cache_data.clear() # Force refresh

# ==========================================
# PAGE: SELL STOCK
# ==========================================
elif menu == "Sell Stock":
    st.title("💰 Sell Stock")
    
    stock_list = df_portfolio['Symbol'].tolist()
    selected = st.selectbox("Select Stock", stock_list)
    
    if selected:
        row = df_portfolio[df_portfolio['Symbol'] == selected].iloc[0]
        avail = row['Units']
        wacc = row['WACC']
        
        st.info(f"Available: {avail} units | WACC: Rs. {wacc:.2f}")
        
        with st.form("sell_form"):
            u_sell = st.number_input("Units to Sell", 1, int(avail))
            p_sell = st.number_input("Selling Price", 1.0)
            is_long = st.checkbox("Long Term (>1 yr)?")
            remark = st.text_input("Remark")
            
            if st.form_submit_button("Confirm Sell"):
                # Calc P/L
                cost_portion = u_sell * wacc
                _, net_pl, _, _ = calculate_metrics(u_sell, cost_portion, p_sell, is_long)
                
                # 1. Update Portfolio
                idx = df_portfolio.index[df_portfolio['Symbol'] == selected][0]
                rem_units = avail - u_sell
                
                if rem_units == 0:
                    df_portfolio = df_portfolio.drop(idx)
                else:
                    df_portfolio.at[idx, 'Units'] = rem_units
                    df_portfolio.at[idx, 'Total_Cost'] -= cost_portion
                
                # 2. Add to History
                new_sale = pd.DataFrame([{
                    "Date": str(datetime.now().date()),
                    "Symbol": selected,
                    "Units": u_sell,
                    "Sell_Price": p_sell,
                    "Net_PL": net_pl,
                    "Remarks": remark
                }])
                df_sales = pd.concat([df_sales, new_sale], ignore_index=True)
                
                # PUSH BOTH TO GOOGLE SHEETS
                conn.update(worksheet="Portfolio", data=df_portfolio)
                conn.update(worksheet="Sales", data=df_sales)
                
                st.success(f"Sold! Net P/L: Rs. {net_pl:.2f}")
                st.balloons()
                st.cache_data.clear()

# ==========================================
# PAGE: HISTORY
# ==========================================
elif menu == "History":
    st.title("📜 Trade History")
    st.dataframe(df_sales, use_container_width=True)
