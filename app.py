import streamlit as st
import pandas as pd
import gspread
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Cloud Terminal", page_icon="☁️", layout="wide")

# 🛑 PASTE YOUR GOOGLE SHEET URL HERE 
# (Make sure this is YOUR actual sheet link)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1jf810Q3V5XquNE9cI7kjyC6kwxs0dxnw1moNLk1Wtqw/edit" 

# Fees
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- CONNECTION FUNCTION ---
def get_google_sheet_data(worksheet_name):
    """Connects to Google Sheets using standard gspread library"""
    try:
        # Load credentials from secrets.toml
        credentials = st.secrets["gspread_credentials"]
        gc = gspread.service_account_from_dict(credentials)
        sh = gc.open_by_url(SHEET_URL)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data), worksheet
    except Exception as e:
        return pd.DataFrame(), None

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
df_portfolio, portfolio_worksheet = get_google_sheet_data("Portfolio")
df_sales, sales_worksheet = get_google_sheet_data("Sales")

# Ensure columns exist
if df_portfolio.empty:
    df_portfolio = pd.DataFrame(columns=["Symbol", "Units", "Total_Cost", "WACC", "Notes"])
else:
    # Convert numeric columns safely
    df_portfolio["Units"] = pd.to_numeric(df_portfolio["Units"], errors='coerce').fillna(0)
    df_portfolio["Total_Cost"] = pd.to_numeric(df_portfolio["Total_Cost"], errors='coerce').fillna(0)
    df_portfolio["WACC"] = pd.to_numeric(df_portfolio["WACC"], errors='coerce').fillna(0)

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
            if ltp == 0: ltp = row["WACC"] # Fallback
            
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
            if portfolio_worksheet is None:
                st.error("Error: Could not connect to Google Sheet.")
                st.stop()

            # Calculate Costs
            raw_cost = units * price
            comm = get_broker_commission(raw_cost)
            fees = comm + (raw_cost * SEBON_FEE) + DP_CHARGE
            total_buy_cost = raw_cost + fees
            
            # Check if stock exists
            # We refresh data just in case
            df_curr, ws = get_google_sheet_data("Portfolio")
            existing_rows = df_curr[df_curr['Symbol'] == sym]
            
            if not existing_rows.empty:
                # Average Out logic
                idx = existing_rows.index[0]
                row_num = idx + 2 
                
                old_units = float(existing_rows.iloc[0]['Units'])
                old_cost = float(existing_rows.iloc[0]['Total_Cost'])
                
                new_units = old_units + units
                new_cost = old_cost + total_buy_cost
                new_wacc = new_cost / new_units
                
                # Update specific cells
                ws.update_cell(row_num, 2, new_units) # Col 2 = Units
                ws.update_cell(row_num, 3, new_cost)  # Col 3 = Total Cost
                ws.update_cell(row_num, 4, new_wacc)  # Col 4 = WACC
                st.success(f"Averaged {sym}! New WACC: {new_wacc:.2f}")
            else:
                # Append Row
                row_data = [sym, units, total_buy_cost, total_buy_cost / units, note]
                ws.append_row(row_data)
                st.success(f"Added {sym} to Portfolio!")
            
            st.cache_data.clear()

# ==========================================
# PAGE: SELL STOCK
# ==========================================
elif menu == "Sell Stock":
    st.title("💰 Sell Stock")
    
    if df_portfolio.empty:
        st.warning("No stocks to sell.")
    else:
        stock_list = df_portfolio['Symbol'].tolist()
        selected = st.selectbox("Select Stock", stock_list)
        
        if selected:
            row = df_portfolio[df_portfolio['Symbol'] == selected].iloc[0]
            avail = float(row['Units'])
            wacc = float(row['WACC'])
            
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
                    
                    # Locate Row
                    idx = df_portfolio.index[df_portfolio['Symbol'] == selected][0]
                    row_num = idx + 2
                    
                    rem_units = avail - u_sell
                    
                    if rem_units == 0:
                        # Delete Row
                        portfolio_worksheet.delete_rows(row_num)
                    else:
                        # Update Row
                        portfolio_worksheet.update_cell(row_num, 2, rem_units)
                        # We reduce total cost proportionally
                        new_total_cost = float(row['Total_Cost']) - cost_portion
                        portfolio_worksheet.update_cell(row_num, 3, new_total_cost)
                    
                    # Add to Sales History
                    sale_row = [str(datetime.now().date()), selected, u_sell, p_sell, net_pl, remark]
                    sales_worksheet.append_row(sale_row)
                    
                    st.success(f"Sold! Net P/L: Rs. {net_pl:.2f}")
                    st.balloons()
                    st.cache_data.clear()

# ==========================================
# PAGE: HISTORY
# ==========================================
elif menu == "History":
    st.title("📜 Trade History")
    st.dataframe(df_sales, use_container_width=True)
