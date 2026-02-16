import streamlit as st
import pandas as pd
import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="NEPSE Terminal", page_icon="📈", layout="wide")

# File Paths
PORTFOLIO_FILE = "portfolio.json"
HISTORY_FILE = "sales_history.json"

# Fees
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- DATA MANAGER ---
def load_data(filename, default=None):
    if not os.path.exists(filename):
        return default if default is not None else {}
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_data(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# --- CALCULATION ENGINE ---
def get_broker_commission(amount):
    if amount <= 50000: rate = 0.36 / 100
    elif amount <= 500000: rate = 0.33 / 100
    elif amount <= 2000000: rate = 0.31 / 100
    elif amount <= 10000000: rate = 0.27 / 100
    else: rate = 0.24 / 100
    return max(10, amount * rate)

def calculate_metrics(units, total_buy_cost, current_price, is_long_term=False):
    if units <= 0: return [0, 0, 0, 0, 0]
    
    sell_amount = units * current_price
    commission = get_broker_commission(sell_amount)
    deductions = commission + (sell_amount * SEBON_FEE) + DP_CHARGE
    net_receivable = sell_amount - deductions
    
    gross_pl = net_receivable - total_buy_cost
    tax_rate = CGT_LONG if is_long_term else CGT_SHORT
    
    tax_amount = gross_pl * tax_rate if gross_pl > 0 else 0
    net_pl = gross_pl - tax_amount
    
    pl_percent = (net_pl / total_buy_cost) * 100 if total_buy_cost > 0 else 0
    est_rate = 0.0036 + SEBON_FEE
    be_price = (total_buy_cost + DP_CHARGE) / (units * (1 - est_rate))
    
    return net_receivable, net_pl, pl_percent, be_price, tax_amount

# --- SCRAPING (Cached for Speed) ---
@st.cache_data(ttl=60)  # Cache data for 60 seconds to save RAM/Internet
def fetch_live_price(symbol):
    try:
        url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return 0.0
        
        soup = BeautifulSoup(response.text, 'html.parser')
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if not price_tag:
             # Backup selector
             label = soup.find('th', string=lambda t: t and "Market Price" in t)
             if label: price_tag = label.find_next('td')

        if price_tag:
            return float(price_tag.text.strip().replace(",", ""))
    except:
        pass
    return 0.0

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🐺 NEPSE Terminal")
menu = st.sidebar.radio("Go to", ["Dashboard", "Portfolio", "WACC Calculator", "Add Trade", "Sell Stock", "History"])

# --- LOAD DATA ---
portfolio = load_data(PORTFOLIO_FILE, {})
history = load_data(HISTORY_FILE, [])

# ==========================================
# PAGE: DASHBOARD
# ==========================================
if menu == "Dashboard":
    st.title("📊 Market Dashboard")
    
    if st.button("🔄 Refresh Prices"):
        st.cache_data.clear()
        st.rerun()
        
    # Calculate Totals
    total_invested = 0
    current_value = 0
    total_pl = 0
    portfolio_list = []
    
    # Progress bar for loading
    progress_text = "Fetching live prices..."
    my_bar = st.progress(0, text=progress_text)
    total_stocks = len(portfolio)
    idx = 0

    for sym, data in portfolio.items():
        # Update progress
        idx += 1
        if total_stocks > 0: my_bar.progress(idx / total_stocks, text=f"Fetching {sym}...")

        ltp = fetch_live_price(sym)
        if ltp == 0: ltp = data.get('cached_ltp', 0) # Fallback
        
        units = data['units']
        cost = data['total_cost']
        
        if units > 0:
            val = units * ltp
            metrics = calculate_metrics(units, cost, ltp)
            net_pl = metrics[1]
            
            total_invested += cost
            current_value += val
            total_pl += net_pl
            
            portfolio_list.append({
                "Symbol": sym,
                "LTP": ltp,
                "Invested": cost,
                "Current Val": val,
                "Net P/L": net_pl,
                "P/L %": metrics[2]
            })
    
    my_bar.empty() # Clear progress bar

    # Top Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Invested", f"Rs. {total_invested:,.0f}")
    col2.metric("Current Value", f"Rs. {current_value:,.0f}", delta=f"{current_value-total_invested:,.0f}")
    col3.metric("Total Net P/L", f"Rs. {total_pl:,.0f}", delta_color="normal")

    st.markdown("### 📈 Details")
    if portfolio_list:
        df = pd.DataFrame(portfolio_list)
        st.dataframe(df.style.format({
            "LTP": "{:.1f}", 
            "Invested": "{:,.0f}", 
            "Current Val": "{:,.0f}",
            "Net P/L": "{:,.0f}",
            "P/L %": "{:.2f}%"
        }), width="stretch")
    else:
        st.info("Portfolio is empty.")

# ==========================================
# PAGE: PORTFOLIO
# ==========================================
elif menu == "Portfolio":
    st.title("💼 Portfolio Holdings")
    
    if not portfolio:
        st.warning("No stocks found.")
    else:
        rows = []
        for sym, data in portfolio.items():
            units = data['units']
            cost = data['total_cost']
            wacc = cost / units if units else 0
            ltp = fetch_live_price(sym)
            if ltp == 0: ltp = data.get('cached_ltp', 0)
            
            metrics = calculate_metrics(units, cost, ltp)
            
            rows.append({
                "Symbol": sym,
                "Units": units,
                "WACC": wacc,
                "LTP": ltp,
                "Break Even": metrics[3],
                "Total Cost": cost,
                "Current Val": units * ltp,
                "Profit/Loss": metrics[1],
                "%": metrics[2],
                "Notes": data.get('note', '-')
            })
            
        df = pd.DataFrame(rows)
        
        def color_pl(val):
            try:
                v = float(str(val).replace(',','').replace('%',''))
                color = '#d4edda' if v > 0 else '#f8d7da'
                return f'background-color: {color}'
            except: return ''

        st.dataframe(
            df.style.format({
                "WACC": "{:.2f}", "LTP": "{:.1f}", "Break Even": "{:.2f}",
                "Total Cost": "{:,.0f}", "Current Val": "{:,.0f}", 
                "Profit/Loss": "{:,.0f}", "%": "{:.2f}%"
            }),
            width="stretch",
            height=500
        )

# ==========================================
# PAGE: WACC CALCULATOR
# ==========================================
elif menu == "WACC Calculator":
    st.title("🧮 Project WACC")
    
    col1, col2 = st.columns(2)
    
    with col1:
        stock_list = list(portfolio.keys())
        selected_stock = st.selectbox("Select Stock", stock_list)
        
        if selected_stock:
            curr = portfolio[selected_stock]
            curr_units = curr['units']
            curr_cost = curr['total_cost']
            curr_wacc = curr_cost / curr_units if curr_units else 0
            
            st.info(f"**Current:** {curr_units} units @ Rs. {curr_wacc:.2f}")
            
            new_units = st.number_input("Units to Buy", min_value=1, value=10)
            new_price = st.number_input("Price per Unit", min_value=1.0, value=float(curr.get('cached_ltp', 0)))
    
    with col2:
        st.subheader("Projection")
        if selected_stock:
            new_cost_raw = new_units * new_price
            fees = get_broker_commission(new_cost_raw) + (new_cost_raw * SEBON_FEE) + DP_CHARGE
            total_new_block = new_cost_raw + fees
            
            final_units = curr_units + new_units
            final_cost = curr_cost + total_new_block
            final_wacc = final_cost / final_units
            
            est_rate = 0.0036 + SEBON_FEE
            new_be = (final_cost + DP_CHARGE) / (final_units * (1 - est_rate))
            
            diff = curr_wacc - final_wacc
            
            st.metric("New WACC", f"Rs. {final_wacc:.2f}", delta=f"{diff:.2f} (Improvement)" if diff > 0 else f"{diff:.2f}")
            st.write(f"**New Break Even:** Rs. {new_be:.2f}")
            st.write(f"**Total Investment Required:** Rs. {total_new_block:,.2f}")

# ==========================================
# PAGE: ADD TRADE
# ==========================================
elif menu == "Add Trade":
    st.title("➕ Add / Average Stock")
    
    with st.form("add_stock_form"):
        col1, col2 = st.columns(2)
        sym = col1.text_input("Symbol").upper()
        units = col2.number_input("Units", min_value=1, step=1)
        price = col1.number_input("Price", min_value=1.0, step=0.1)
        date = col2.date_input("Buy Date", datetime.now())
        note = st.text_input("Note / Remark")
        
        submitted = st.form_submit_button("Add to Portfolio")
        
        if submitted and sym:
            cost = units * price
            comm = get_broker_commission(cost)
            fees = comm + (cost * SEBON_FEE) + DP_CHARGE
            total = cost + fees
            
            if sym in portfolio:
                portfolio[sym]['units'] += units
                portfolio[sym]['total_cost'] += total
                portfolio[sym]['note'] = note
                portfolio[sym]['buy_date'] += f", {date}"
                st.success(f"Averaged {sym}! New Total Cost: {portfolio[sym]['total_cost']:.2f}")
            else:
                portfolio[sym] = {
                    'units': units, 'total_cost': total, 'sector': 'Unknown',
                    'stop_loss': 0, 'note': note, 'buy_date': str(date),
                    'cached_ltp': price # Init with buy price
                }
                st.success(f"Added {sym} to Portfolio!")
            
            save_data(PORTFOLIO_FILE, portfolio)

# ==========================================
# PAGE: SELL STOCK
# ==========================================
elif menu == "Sell Stock":
    st.title("💰 Sell Stock")
    
    stock_list = list(portfolio.keys())
    sym = st.selectbox("Select Stock to Sell", stock_list)
    
    if sym:
        curr = portfolio[sym]
        avail = curr['units']
        avg_cost = curr['total_cost'] / avail if avail else 0
        
        st.write(f"Available: **{avail} units** | Avg Cost: **Rs. {avg_cost:.2f}**")
        
        with st.form("sell_form"):
            col1, col2 = st.columns(2)
            u_sell = col1.number_input("Units to Sell", min_value=1, max_value=avail)
            price = col2.number_input("Sell Price", min_value=1.0)
            is_long = st.checkbox("Held > 1 Year? (5% Tax)")
            sell_date = st.date_input("Sell Date", datetime.now())
            remarks = st.text_input("Remarks (Lesson)")
            
            confirm = st.form_submit_button("Confirm Sell")
            
            if confirm:
                # Calc
                cost_share = (curr['total_cost'] / avail) * u_sell
                metrics = calculate_metrics(u_sell, cost_share, price, is_long_term=is_long)
                net_receivable, net_pl, _, _, tax_paid = metrics
                
                # Update History
                rec = {
                    'sell_date': str(sell_date),
                    'symbol': sym,
                    'units': u_sell,
                    'sell_price': price,
                    'net_pl': net_pl,
                    'tax_paid': tax_paid,
                    'sell_remark': remarks
                }
                history.append(rec)
                save_data(HISTORY_FILE, history)
                
                # Update Portfolio
                rem_units = avail - u_sell
                if rem_units == 0:
                    del portfolio[sym]
                else:
                    portfolio[sym]['units'] = rem_units
                    portfolio[sym]['total_cost'] -= cost_share
                
                save_data(PORTFOLIO_FILE, portfolio)
                
                st.success(f"SOLD {sym}! Net P/L: Rs. {net_pl:,.2f}")
                if net_pl > 0: st.balloons()

# ==========================================
# PAGE: HISTORY
# ==========================================
elif menu == "History":
    st.title("📜 Trade History")
    
    if not history:
        st.info("No sales yet.")
    else:
        df_hist = pd.DataFrame(history)
        
        total_profit = sum(h['net_pl'] for h in history)
        total_tax = sum(h.get('tax_paid', 0) for h in history)
        
        col1, col2 = st.columns(2)
        col1.metric("Total Realized Profit", f"Rs. {total_profit:,.2f}")
        col2.metric("Total Tax Paid", f"Rs. {total_tax:,.2f}")
        
        st.dataframe(df_hist, width="stretch")