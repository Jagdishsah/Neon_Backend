import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from github import Github
from io import StringIO
import plotly.express as px
from datetime import datetime
import time
from scrape import get_market_data
import plotly.graph_objects as go

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Pro Terminal", page_icon="📈", layout="wide")

# --- AUTHENTICATION ENGINE (USERNAME + PASSWORD) ---
def check_login():
    """Forces the user to log in with a username and password."""
    # Initialize session state for login
    if "login_correct" not in st.session_state:
        st.session_state["login_correct"] = False

    # If not logged in, show the login form
    if not st.session_state["login_correct"]:
        st.header("🔒 NEPSE Pro Terminal")
        st.caption("Secure Access Required")
        
        # Use a form so the app doesn't reload until you click "Log In"
        with st.form("credentials_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", type="primary")

            if submitted:
                # Check both Username and Password against Secrets
                if (user_input == st.secrets["app_username"] and 
                    pass_input == st.secrets["app_password"]):
                    
                    st.session_state["login_correct"] = True
                    st.rerun()  # Reload to unlock the app immediately
                else:
                    st.error("😕 Incorrect Username or Password")
        
        # Stop the app here if not logged in
        return False

    # If logged in, return True to let the app run
    return True

# --- BLOCK APP IF NOT LOGGED IN ---
if not check_login():
    st.stop()


# Constants
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {background-color: #0E1117; border: 1px solid #262730; padding: 15px; border-radius: 5px; margin-bottom: 10px;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .success-text {color: #00FF00;}
    .danger-text {color: #FF4B4B;}
    div.block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# --- GITHUB ENGINE ---
def get_repo():
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        g = Github(token)
        return g.get_repo(repo_name)
    except:
        st.error("❌ GitHub Connection Failed. Check Secrets.")
        return None

def get_data(filename):
    repo = get_repo()
    if not repo: return pd.DataFrame()
    try:
        content = repo.get_contents(filename)
        return pd.read_csv(StringIO(content.decoded_content.decode("utf-8")))
    except:
        # Define schemas
        if "portfolio" in filename: 
            cols = ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Buy_Date", "Stop_Loss", "Notes"]
        elif "watchlist" in filename: cols = ["Symbol", "Target", "Remark"]
            # Add this line inside get_data schema:
        elif "activity_log" in filename:
            cols = ["Timestamp", "Category", "Symbol", "Action", "Details", "Amount"]
        elif "history" in filename: 
            cols = ["Date", "Buy_Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Invested_Amount", "Received_Amount", "Net_PL", "PL_Pct", "Reason"]
        elif "diary" in filename: cols = ["Date", "Symbol", "Note", "Emotion", "Mistake", "Strategy"]
        elif "cache" in filename: cols = ["Symbol", "LTP", "Change", "High52", "Low52", "LastUpdated"]
        elif "wealth" in filename: cols = ["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"]
        # 👇 ADD THIS NEW LINE 👇
        elif "price_log" in filename: cols = ["Date", "Symbol", "LTP"]
        # Add this line inside the get_data function schema list:

        elif "Data" in filename: 
            cols = ["Date", "Realized_PL", "Realized_PL_Pct", "Unrealized_PL", "Unrealized_PL_Pct"]
        # 👇 NEW TMS SCHEMAS 👇
        elif "tms_ledger_master" in filename:
            cols = ["Date", "Type", "Category", "Amount", "Status", "Due_Date", "Ref_ID", "Description", "Is_Non_Cash", "Dispute_Note", "Fiscal_Year"]
        elif "tms_holdings" in filename:
            cols = ["Symbol", "Total_Qty", "Pledged_Qty", "LTP", "Haircut"]

        elif "wealth" in filename: cols = ["Date", "Total_Investment", "Current_Value", "Total_PL", "Day_Change", "Sold_Volume"]
        elif "price_log" in filename: cols = ["Date", "Symbol", "LTP"]
        elif "Data" in filename: cols = ["Date", "Realized_PL", "Realized_PL_Pct", "Unrealized_PL", "Unrealized_PL_Pct"]
        
        # 👇 NEW TMS SCHEMA 👇
        elif "tms_trx" in filename:
            cols = ["Date", "Stock", "Type", "Medium", "Amount", "Charge", "Remark", "Reference"]
        # 👆 NEW TMS SCHEMA 👆
        
        
        # 👆 NEW TMS SCHEMAS 👆
        else: cols = []
        return pd.DataFrame(columns=cols)

def save_data(filename, df):
    repo = get_repo()
    if not repo: return False
    try:
        csv_content = df.to_csv(index=False)
        try:
            file = repo.get_contents(filename)
            repo.update_file(file.path, f"Update {filename}", csv_content, file.sha)
        except:
            repo.create_file(filename, f"Create {filename}", csv_content)
        return True
    except Exception as e:
        st.error(f"Save Failed: {e}")
        return False



def update_wealth_log(port, cache):
    """Calculates daily snapshot and saves to wealth.csv"""
    if port.empty: return

    # Merge to get latest values
    df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    
    total_inv = df["Total_Cost"].sum()
    total_val = 0
    day_pl = 0
    
    for _, row in df.iterrows():
        ltp = row.get("LTP", 0)
        if ltp == 0: ltp = row["WACC"]
        
        # Calc Value
        val = row["Units"] * ltp
        total_val += val
        
        # Calc Day Change
        chg = row.get("Change", 0)
        day_pl += (row["Units"] * chg)

    total_pl = total_val - total_inv
    
    # Get Daily Buy/Sell Volume from History
    hist = get_data("history.csv")
    # Nepal Time (UTC + 5:45)
    today_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d")
    
    bought_today = 0 # (Logic would need a 'buys.csv' or filtering portfolio notes, simplifying for now)
    sold_today = 0
    if not hist.empty and "Date" in hist.columns:
        todays_sales = hist[hist["Date"] == today_str]
        sold_today = (todays_sales["Units"] * todays_sales["Sell_Price"]).sum()

    # Create Snapshot
    new_row = {
        "Date": today_str,
        "Total_Investment": round(total_inv, 2),
        "Current_Value": round(total_val, 2),
        "Total_PL": round(total_pl, 2),
        "Day_Change": round(day_pl, 2),
        "Sold_Volume": round(sold_today, 2)
    }
    
    # Load Existing Log
    log = get_data("wealth.csv")
    
    # Remove existing entry for today (so we don't duplicate if you refresh 10 times)
    if not log.empty and "Date" in log.columns:
        log = log[log["Date"] != today_str]
    
    log = pd.concat([log, pd.DataFrame([new_row])], ignore_index=True)
    save_data("wealth.csv", log)

def update_data_log(port, hist, cache):
    """Calculates Realized vs Unrealized metrics and saves to Data.csv"""
    # 1. Calculate UNREALIZED (Paper Profit)
    unrealized_pl = 0
    unrealized_inv = 0
    
    if not port.empty:
        # Merge with cache to get latest LTP
        df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            curr_val = row["Units"] * ltp
            cost = row["Total_Cost"]
            
            unrealized_pl += (curr_val - cost)
            unrealized_inv += cost
            
    unrealized_pct = (unrealized_pl / unrealized_inv * 100) if unrealized_inv > 0 else 0.0

    # 2. Calculate REALIZED (Booked Profit)
    realized_pl = 0
    realized_inv = 0
    
    if not hist.empty:
        realized_pl = hist["Net_PL"].sum()
        # Compatibility check for Invested_Amount
        if "Invested_Amount" in hist.columns:
            realized_inv = hist["Invested_Amount"].sum()
        else:
            # Fallback for old data
            realized_inv = (hist["Units"] * hist["Buy_Price"]).sum() if "Buy_Price" in hist.columns else 0

    realized_pct = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0.0

    # 3. Prepare Data Entry
    today_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d")
    
    new_row = {
        "Date": today_str,
        "Realized_PL": round(realized_pl, 2),
        "Realized_PL_Pct": round(realized_pct, 2),
        "Unrealized_PL": round(unrealized_pl, 2),
        "Unrealized_PL_Pct": round(unrealized_pct, 2)
    }

    # 4. Save to Data.csv
    log = get_data("Data.csv")
    
    # Overwrite if entry exists for today (to update with latest market data)
    if not log.empty and "Date" in log.columns:
        log = log[log["Date"] != today_str]
    
    log = pd.concat([log, pd.DataFrame([new_row])], ignore_index=True)
    save_data("Data.csv", log)

def refresh_market_cache():
    # 1. Load ALL required data
    port = get_data("portfolio.csv")
    watch = get_data("watchlist.csv")
    price_log = get_data("price_log.csv")
    hist = get_data("history.csv") 
    
    symbols = set(port["Symbol"].tolist() + watch["Symbol"].tolist())
    
    if not symbols: return
    
    cache_list = []
    new_log_entries = []
    
    progress = st.progress(0, "Connecting to High-Speed API...")
    
    # Nepal Time
    now_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M")
    
    # --- FETCH EVERYTHING ONCE VIA API ---
    market_data = get_market_data(list(symbols))
    
    for i, sym in enumerate(symbols):
        progress.progress((i+1)/len(symbols), f"Processing {sym}...")
        
        # Get data from our dictionary instead of scraping 
        live = market_data.get(sym, {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0})
        current_ltp = live['price']
        
        # --- SMART CHANGE LOGIC ---
        calculated_change = 0.0
        
        # Check Price History
        if not price_log.empty:
            sym_hist = price_log[price_log["Symbol"] == sym]
        else:
            sym_hist = pd.DataFrame()

        if not sym_hist.empty:
            last_stored_ltp = float(sym_hist.iloc[-1]["LTP"])
            
            if current_ltp != last_stored_ltp:
                # Price MOVED: Calculate real change and log it
                calculated_change = current_ltp - last_stored_ltp
                new_log_entries.append({
                    "Date": now_str,
                    "Symbol": sym,
                    "LTP": current_ltp
                })
            else:
                # Price SAME: Compare with PREVIOUS log to keep the change visible
                if len(sym_hist) >= 2:
                    prev_stored_ltp = float(sym_hist.iloc[-2]["LTP"])
                    calculated_change = current_ltp - prev_stored_ltp
                else:
                    calculated_change = 0.0
        else:
            # First time seeing stock
            new_log_entries.append({
                "Date": now_str,
                "Symbol": sym,
                "LTP": current_ltp
            })
            calculated_change = 0.0
            
        # ---------------------------

        cache_list.append({
            "Symbol": sym,
            "LTP": current_ltp,
            "Change": calculated_change,
            "High52": live['high'],
            "Low52": live['low'],
            "LastUpdated": now_str
        })
        
    progress.empty()
    
    # 2. Save Market Cache
    new_cache = pd.DataFrame(cache_list)
    save_data("cache.csv", new_cache)
    
    # 3. Save Price Log (Only if movement happened)
    if new_log_entries:
        new_entries_df = pd.DataFrame(new_log_entries)
        price_log = pd.concat([price_log, new_entries_df], ignore_index=True)
        save_data("price_log.csv", price_log)
    
    # 4. Update Background Logs
    update_wealth_log(port, new_cache)       # Tracks Total Net Worth
    update_data_log(port, hist, new_cache)   # Tracks P/L %
    
    st.toast("⚡ Market Data synced via API!", icon="✅")
    st.cache_data.clear()

# --- CALCULATORS ---
def log_activity(category, symbol, action, details, amount=0.0):
    """
    Logs an event to activity_log.csv
    Category: TRADE, ALERT, SYSTEM, NOTE
    Action: BUY, SELL, STOP_LOSS, TARGET, UPDATE
    """
    log = get_data("activity_log.csv")
    
    # Nepal Time
    now_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
    
    new_entry = pd.DataFrame([{
        "Timestamp": now_str,
        "Category": category,
        "Symbol": symbol,
        "Action": action,
        "Details": details,
        "Amount": amount
    }])
    
    log = pd.concat([new_entry, log], ignore_index=True) # Add new at top
    save_data("activity_log.csv", log)

def get_broker_commission(amount):
    if amount <= 50000: rate = 0.36
    elif amount <= 500000: rate = 0.33
    elif amount <= 2000000: rate = 0.31
    else: rate = 0.27
    return max(10, amount * rate / 100)

def calculate_metrics(units, cost, ltp, change=0):
    if units == 0: return 0, 0, 0, 0, 0
    
    curr_val = units * ltp
    day_gain = units * change
    
    # Break Even (Approximate Selling Price needed to Net 0)
    # Gross Required = Cost + DP
    # Denominator = Units * (1 - Comm - Tax_Short)
    # Simplified approximation for speed: Cost + 0.6% overhead
    overhead = cost * 0.006 + 25
    be_price = (cost + overhead) / units
    
    sell_comm = get_broker_commission(curr_val)
    sebon = curr_val * SEBON_FEE
    receivable = curr_val - sell_comm - sebon - DP_CHARGE
    
    net_pl = receivable - cost
    if net_pl > 0:
        net_pl -= (net_pl * CGT_SHORT)
        
    return curr_val, net_pl, be_price, day_gain

# --- NAVIGATION ---
st.sidebar.title("🚀 NEPSE Terminal")
menu = st.sidebar.radio("Main Menu", 
    [ "Dashboard", "My TMS", "Portfolio", "Watchlist", "Add Trade", "Sell Stock", "History", "Activity Log", "Wealth Graph", "WACC Projection", "What If Analysis", "Reports", "Manage Data", "Trading Journal", "Risk Manager" ] )
if st.sidebar.button("🔄 Refresh Market Data"):
    refresh_market_cache()
    st.rerun()

# ================= DASHBOARD =================
elif menu == "Dashboard":
    # 1. Load All Data
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    hist = get_data("history.csv")
    
    # 2. Merge Portfolio with Market Data
    if not port.empty and not cache.empty:
        df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    else:
        df = port.copy() if not port.empty else pd.DataFrame()
        if not df.empty: df["LTP"] = 0

    last_up = cache["LastUpdated"].iloc[0] if not cache.empty else "Never"
    st.title("📊 Market Dashboard")
    st.caption(f"Last Updated: {last_up} (Nepal Time)")

    if df.empty:
        st.info("Portfolio is empty. Start by adding trades.")
    else:
        # --- METRIC CALCULATIONS ---
        
        # A. Current Holdings (Unrealized)
        curr_inv = df["Total_Cost"].sum()
        curr_val = 0
        day_change = 0
        alerts = []
        
        sector_data = {}
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            val = row["Units"] * ltp
            d_chg = row["Units"] * row.get("Change", 0)
            
            curr_val += val
            day_change += d_chg
            
            # Sector
            sec = row.get("Sector", "Unclassified")
            sector_data[sec] = sector_data.get(sec, 0) + val
            
            # Stop Loss
            sl = row.get("Stop_Loss", 0)
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT:** {row['Symbol']} @ {ltp} (SL: {sl})")
        
        curr_pl = curr_val - curr_inv
        curr_ret = (curr_pl / curr_inv * 100) if curr_inv else 0

        # B. Closed Holdings (Realized)
        realized_pl = 0
        realized_inv = 0
        realized_recv = 0
        
        if not hist.empty:
            realized_pl = hist["Net_PL"].sum()
            # Handle compatibility
            if "Invested_Amount" in hist.columns:
                realized_inv = hist["Invested_Amount"].sum()
                realized_recv = hist["Received_Amount"].sum()
            elif "Buy_Price" in hist.columns:
                realized_inv = (hist["Units"] * hist["Buy_Price"]).sum()
                realized_recv = (hist["Units"] * hist["Sell_Price"]).sum()

        realized_ret = (realized_pl / realized_inv * 100) if realized_inv > 0 else 0

        # C. Lifetime Stats (The New Feature)
        lifetime_invested = curr_inv + realized_inv
        lifetime_received = realized_recv # Cash back in pocket
        net_exposure = lifetime_received - lifetime_invested 
        # (Net Exposure: If negative, that amount is still "stuck" in the market)

        # --- DISPLAY ---
        
        # Row 1: Snapshot
        st.markdown("### 🏦 Net Worth Snapshot")
        m1, m2, m3 = st.columns(3)
        m1.metric("Current Portfolio Value", f"Rs {curr_val:,.0f}")
        m2.metric("Total Active Investment", f"Rs {curr_inv:,.0f}")
        m3.metric("Today's Change", f"Rs {day_change:,.0f}", delta=day_change)
        
        st.markdown("---")
        
        # Row 2: P/L Analysis
        st.markdown("### ⚖️ Profit/Loss Analysis")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Net Realized P/L", f"Rs {realized_pl:,.0f}", delta=f"{realized_ret:.2f}%")
        c2.metric("📈 Unrealized P/L", f"Rs {curr_pl:,.0f}", delta=f"{curr_ret:.2f}%")
        c3.metric("🏆 Lifetime P/L", f"Rs {realized_pl + curr_pl:,.0f}", help="Realized + Unrealized")
        
        # Best Winner Logic
        best_stock = "-"
        if not hist.empty:
            best_trade = hist.loc[hist["Net_PL"].idxmax()]
            best_stock = f"{best_trade['Symbol']} (+{best_trade['Net_PL']:.0f})"
        c4.metric("🥇 Best Trade", best_stock)

        st.markdown("---")

        # Row 3: Investment Snapshot (New Feature)
        st.markdown("### 💼 Investment Cycle (Lifetime)")
        i1, i2, i3, i4 = st.columns(4)
        
        i1.metric("Total Capital Deployed", f"Rs {lifetime_invested:,.0f}", 
                  help="Sum of (Cost of Sold Stocks + Cost of Held Stocks). The total money you have ever put to work.")
        
        i2.metric("Total Cash Recycled", f"Rs {lifetime_received:,.0f}", 
                  help="Total money returned to bank from sales.")
                  
        i3.metric("Net Cash Flow", f"Rs {net_exposure:,.0f}", 
                  help="Total Received - Total Invested. Negative means this amount is currently 'at risk' in the market.")
        
        turnover = (realized_inv / curr_inv * 100) if curr_inv else 0
        i4.metric("Capital Turnover", f"{turnover:.1f}%", help="How many times you have rotated your capital.")

        st.markdown("---")
        
        # --- VISUALS & ALERTS ---
        col_chart, col_alert = st.columns([2, 1])
        
        with col_chart:
            st.subheader("Sector Allocation")
            sec_df = pd.DataFrame(list(sector_data.items()), columns=["Sector", "Value"])
            if not sec_df.empty:
                fig = px.pie(sec_df, values="Value", names="Sector", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No data.")
                
        with col_alert:
            st.subheader("📢 Alerts")
            if alerts:
                for a in alerts: st.error(a)
            else:
                st.info("System Normal.")
                
            # Watchlist
            wl = get_data("watchlist.csv")
            if not wl.empty and not cache.empty:
                wl_m = pd.merge(wl, cache, on="Symbol", how="left")
                hits = wl_m[(wl_m["LTP"] <= wl_m["Target"]) & (wl_m["LTP"] > 0)]
                if not hits.empty:
                    st.markdown("---")
                    for _, h in hits.iterrows():
                        st.success(f"🎯 **BUY:** {h['Symbol']} @ {h['LTP']}")


# ================= MY TMS =================
elif menu == "My TMS":
    st.title("🏦 TMS Command Center")
    st.caption("Central hub for Broker Ledger, Cash Flows, and T+2 Settlements")

    # Creating the Nested Tabs
    tms_tabs = st.tabs(["📊 Dashboard", "✍️ Add Transactions", "📜 View Transactions", "🛠️ Manage Data", "⬇️ Export", "📈 Smart Graph", "📝 Action Logs"])
    
   # --- TAB 1: THE DASHBOARD ---
    with tms_tabs[0]:
        st.subheader("💸 TMS Cash Flow & Solvency")
        trx_df = get_data("tms/tms_trx.csv")
        
        if not trx_df.empty:
            trx_df["Date"] = pd.to_datetime(trx_df["Date"])
            
            # --- 1. CORE FINANCIAL CALCULATIONS ---
            # Define logic for Cash Flow (Excluding Collateral movements)
            is_collateral_entry = (trx_df["Medium"].astype(str).str.upper() == "COLLATERAL") | \
                                 (trx_df["Type"].astype(str).str.upper() == "COLLATERAL LOAD")
            
            real_cash_df = trx_df[~is_collateral_entry]
            
            # Real Cash In: Deposits + Sales
            cash_in = real_cash_df[real_cash_df["Amount"] > 0]["Amount"].sum()
            # Real Cash Out: Withdraws + Buys + Fines (Convert to positive for display)
            cash_out = abs(real_cash_df[real_cash_df["Amount"] < 0]["Amount"].sum())
            
            total_charges = trx_df["Charge"].sum()
            
            # Net Balance = Total Cash In - Total Cash Out - Fees
            net_balance = (cash_in - cash_out) - total_charges
            
            # Buying Power Logic
            # Base Collateral = 10,824. Buying Power = (Collateral) + Net Balance
            base_free_collateral = 10824.0
            # Include any 'Collateral Load' transactions added by user
            loaded_collateral = trx_df[trx_df["Type"].astype(str).str.upper() == "COLLATERAL LOAD"]["Amount"].sum()
            total_collateral = base_free_collateral + loaded_collateral
            
            # Final Buying Power Calculation
            buying_power = (total_collateral) 
            
            # --- UI: MAIN METRICS ---
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Net Balance", f"Rs {net_balance:,.0f}", 
                      delta="Deficit" if net_balance < 0 else "Surplus", 
                      delta_color="inverse" if net_balance < 0 else "normal")
            
            # Highlight Buying Power in Green if positive, Red if used up
            c2.metric("🔋 Buying Power", f"Rs {buying_power:,.0f}", 
                      help=f"Calculation: (Rs {total_collateral:,.0f} Collateral x 4) + (Rs {net_balance:,.0f} Cash Balance)")
            
            c3.metric("Real Cash Out", f"Rs {cash_out:,.0f}", help="Sum of Buys, Withdrawals, and Fines")
            c4.metric("Real Cash In", f"Rs {cash_in:,.0f}", help="Sum of Deposits and Sales")
            
            st.markdown("---")
            
            # --- 2. THE RADAR & ALERTS ROW ---
            r1, r2 = st.columns([1, 1])
            
            with r1:
                st.markdown("#### 🚨 Account Alerts")
                if net_balance < 0:
                    today = pd.to_datetime(datetime.now().date())
                    # Check how long it has been negative
                    daily_bal = real_cash_df.groupby("Date")["Amount"].sum().cumsum()
                    neg_days = (today - daily_bal[daily_bal < 0].index.min()).days if not daily_bal[daily_bal < 0].empty else 0
                    
                    if neg_days >= 2:
                        st.error(f"🔥 **CRITICAL T+2:** Negative for {neg_days} days! Deposit Rs {abs(net_balance):,.0f} now.")
                    else:
                        st.warning(f"⚠️ **Notice:** Negative Balance (Rs {net_balance:,.2f}). Settle within 2 days.")
                else:
                    st.success("✅ Account settled. No pending deficits.")

            with r2:
                st.markdown("#### 📡 Upcoming Payout Radar")
                def get_payout_date(sell_date):
                    days_added, current = 0, sell_date
                    while days_added < 3:
                        current += pd.Timedelta(days=1)
                        if current.weekday() not in [4, 5]: days_added += 1 # Skip Fri/Sat
                    return current
                
                sells = trx_df[trx_df["Type"].astype(str).str.upper() == "SELL"].copy()
                if not sells.empty:
                    sells["Payout"] = sells["Date"].apply(get_payout_date)
                    pending = sells[sells["Payout"] >= pd.to_datetime(datetime.now().date())]
                    if not pending.empty:
                        for _, row in pending.iterrows():
                            st.info(f"💸 **Rs {row['Amount']:,.0f}** due {row['Payout'].strftime('%A')} (from {row['Stock']})")
                    else: st.write("No pending payouts.")
                else: st.write("No recent sells.")
                    
            st.markdown("---")
            
            # --- 3. RECENT ACTIVITY ---
            st.markdown("#### 🕒 Recent Activity")
            st.dataframe(trx_df.sort_values("Date", ascending=False).head(5)[["Date", "Type", "Stock", "Amount", "Medium"]], 
                         use_container_width=True, hide_index=True)
                
        else:
            st.info("No transaction data yet.")

    # --- TAB 2: ADD TRANSACTIONS ---
    with tms_tabs[1]:
        st.subheader("➕ Record TMS Transaction")
        with st.form("add_tms_trx"):
            c1, c2, c3 = st.columns(3)
            date = c1.date_input("Date", datetime.now().date())
            stock = c2.text_input("Stock Symbol (Optional)", placeholder="e.g. NABIL").upper()
            
            # Type Selection
            type_sel = c3.selectbox(
                "Transaction Type", 
                ["Buy", "Sell", "Deposit", "Withdraw", "Fine", "IPO", "Collateral Load", "Other"]
            )
            trx_type = st.text_input("Specify Other Type", placeholder="Type custom here...") if type_sel == "Other" else type_sel
            
            c4, c5, c6 = st.columns(3)
            
            # Medium Selection
            med_sel = c4.selectbox(
                "Medium", 
                ["Nabil", "Global", "Esewa", "CIPS", "Khalti", "Collateral", "Other"]
            )
            medium = st.text_input("Specify Other Medium") if med_sel == "Other" else med_sel
                
            # Financials (User only inputs positive absolute value now)
            amount_input = c5.number_input(
                "Amount (Rs)", 
                min_value=0.0, 
                value=0.0, 
                help="Type the absolute amount. We will auto-apply + or - based on the Transaction Type."
            )
            
            # Direction toggle for ambiguous transactions (like IPO or custom Other)
            direction = c6.selectbox(
                "Flow Direction (For IPO/Other)", 
                ["Auto", "Inflow to TMS (+)", "Outflow from TMS (-)"], 
                help="Only matters if Type is 'IPO' or 'Other'."
            )
            
            c7, c8 = st.columns(2)
            charge = c7.number_input("Charge / Fee", min_value=0.0, value=0.0)
            remark = c8.text_input("Remark")
            
            ref = st.text_input("Reference / Txn ID", placeholder="e.g. ConnectIPS ID")
            
            st.markdown("---")
            confirm = st.checkbox("I confirm the details above are correct.")
            
            if st.form_submit_button("💾 Save Transaction"):
                # 1. Error Checking
                if type_sel == "Other" and not trx_type.strip():
                    st.error("❌ Please specify the custom Transaction Type.")
                elif med_sel == "Other" and not medium.strip():
                    st.error("❌ Please specify the custom Medium.")
                elif amount_input == 0:
                    st.error("❌ Amount cannot be 0.")
                elif confirm:
                    
                    # 2. AUTO SIGN CALCULATION MAGIC
                    if type_sel in ["Buy", "Withdraw", "Fine"]:
                        final_amount = -abs(amount_input)
                    elif type_sel in ["Sell", "Deposit"]:
                        final_amount = abs(amount_input)
                    else:
                        # Fallback for IPO or Custom types based on user selection
                        if direction == "Outflow from TMS (-)":
                            final_amount = -abs(amount_input)
                        else:
                            final_amount = abs(amount_input)
                            
                    # 3. Save Data
                    new_trx = pd.DataFrame([{
                        "Date": date, "Stock": stock, "Type": trx_type, 
                        "Medium": medium, "Amount": final_amount, "Charge": charge, 
                        "Remark": remark, "Reference": ref
                    }])
                    
                    trx_df = get_data("tms/tms_trx.csv")
                    trx_df = pd.concat([trx_df, new_trx], ignore_index=True)
                    save_data("tms/tms_trx.csv", trx_df)
                    # 👇 NEW: LOG THE ADDITION 👇
                    log_activity("TMS", stock if stock else "N/A", "ADD", f"Recorded {trx_type} via {medium}", final_amount)
                    
                    st.success(f"✅ Saved! Recorded Rs {final_amount:,.2f} to the ledger.")
                else:
                    st.warning("⚠️ Please check the confirmation box before saving.")

    # --- TAB 3: VIEW TRANSACTIONS ---
    with tms_tabs[2]:
        st.subheader("📜 Transaction Ledger")
        trx_df = get_data("tms/tms_trx.csv")
        
        if not trx_df.empty:
            # Filtering Options
            f1, f2, f3 = st.columns(3)
            f_type = f1.multiselect("Filter by Type", trx_df["Type"].unique())
            f_med = f2.multiselect("Filter by Medium", trx_df["Medium"].unique())
            f_stock = f3.text_input("Search Stock")
            
            # Processing Data
            view_df = trx_df.copy()
            view_df["Date"] = pd.to_datetime(view_df["Date"])
            view_df = view_df.sort_values("Date")
            
            # Calculate Running Net Balance
            view_df["Net_Balance"] = view_df["Amount"].cumsum()
            
            # Apply Filters
            if f_type: view_df = view_df[view_df["Type"].isin(f_type)]
            if f_med: view_df = view_df[view_df["Medium"].isin(f_med)]
            if f_stock: view_df = view_df[view_df["Stock"].str.contains(f_stock.upper(), na=False)]
            
            # Apply Color Coding (Using Pandas Styler)
            def color_rows(row):
                t = str(row["Type"]).upper()
                if "DEPOSIT" in t: return ["color: #00FF00"] * len(row) # Green
                if "WITHDRAW" in t: return ["color: #DAA520"] * len(row) # Gold
                if "BUY" in t: return ["color: #A9A9A9"] * len(row) # Gray (Black blends into dark mode)
                if "SELL" in t: return ["color: #1E90FF"] * len(row) # Blue
                if "FINE" in t: return ["color: #FF4B4B"] * len(row) # Red
                return ["color: #FFC0CB"] * len(row) # Pink for IPO/Other
            
            st.dataframe(
                view_df.style.apply(color_rows, axis=1).format({
                    "Amount": "{:,.2f}", 
                    "Charge": "{:,.2f}", 
                    "Net_Balance": "{:,.2f}"
                }), 
                use_container_width=True, hide_index=True
            )
            
            # Bottom Totals
            st.markdown("### 📊 Filtered Totals")
            t1, t2, t3 = st.columns(3)
            t1.metric("Total Rows in View", len(view_df))
            t2.metric("Total Amount in View", f"Rs {view_df['Amount'].sum():,.2f}")
            t3.metric("Total Charges in View", f"Rs {view_df['Charge'].sum():,.2f}")
        else:
            st.info("No transactions to display.")

   # --- TAB 4: MANAGE DATA ---
    with tms_tabs[3]:
        st.subheader("🛠️ Manage Data (Admin Zone)")
        st.error("🚨 **DANGER ZONE: FORCE EDITING DATA** 🚨\n\nEditing data here forcefully overwrites the raw CSV files. If you change a transaction amount, date, or type, it will alter your entire Net Balance, Solvency calculations, and historical ledgers permanently. **Proceed with extreme caution!**")
        
        trx_df = get_data("tms/tms_trx.csv")
        if not trx_df.empty:
            # Render the interactive data editor
            edited_df = st.data_editor(trx_df, num_rows="dynamic", use_container_width=True, key="tms_admin_editor")
            
            st.markdown("---")
            c1, c2 = st.columns([1, 2])
            confirm_danger = c1.checkbox("⚠️ I understand the consequences of altering raw database files.", key="danger_check")
            
            if c1.button("🔥 FORCE SAVE CHANGES", type="primary"):
                if confirm_danger:
                    # Detect if rows were deleted or modified (optional logging logic)
                    save_data("tms/tms_trx.csv", edited_df)
                    
                    # 👇 NEW: LOG THE FORCE EDIT 👇
                    log_activity("TMS", "SYSTEM", "FORCE_EDIT", "Forcefully edited raw TMS data", 0)
                    
                    st.success("✅ Raw data forcefully overwritten. System logic will update on next refresh.")
                    st.rerun()
                else:
                    st.warning("You must check the confirmation box to proceed.")
        else:
            st.info("No data to manage.")

    
        
   # --- TAB 5: EXPORT ---
    with tms_tabs[4]:
        st.subheader("⬇️ Export TMS Data")
        st.write("Download your entire TMS transaction ledger for local backup, Excel analysis, or tax purposes.")
        
        # Get the TMS Ledger Data
        trx_df = get_data("tms/tms_trx.csv")
        
        if not trx_df.empty:
            # Convert DataFrame to CSV bytes for the download button
            csv = trx_df.to_csv(index=False).encode('utf-8')
            
            c1, c2 = st.columns(2)
            c1.download_button(
                label="📥 Download TMS Ledger (CSV)",
                data=csv,
                file_name=f"TMS_Trx_Ledger_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True
            )
            c1.caption(f"Contains {len(trx_df)} total transaction records.")
            
            # --- Bonus: Export Master Holdings too ---
            holdings_df = get_data("tms/tms_holdings.csv")
            if not holdings_df.empty:
                holdings_csv = holdings_df.to_csv(index=False).encode('utf-8')
                c2.download_button(
                    label="📥 Download Collateral Holdings (CSV)",
                    data=holdings_csv,
                    file_name=f"TMS_Collateral_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    type="secondary",
                    use_container_width=True
                )
                c2.caption(f"Contains {len(holdings_df)} collateral records.")
        else:
            st.info("No TMS transaction data available to export yet.")
    
        
   # --- TAB 6: SMART GRAPH ---
    with tms_tabs[5]:
        import plotly.graph_objects as go # Required for Waterfall
        
        st.subheader("📈 Smart Financial Visuals")
        trx_df = get_data("tms/tms_trx.csv")
        
        if not trx_df.empty:
            trx_df["Date"] = pd.to_datetime(trx_df["Date"])
            trx_df = trx_df.sort_values("Date")
            trx_df["Net_Balance"] = trx_df["Amount"].cumsum()
            
            # --- GRAPH 1: Pulse Line (Cumulative Net Balance) ---
            st.markdown("#### 💓 The Pulse: Cumulative Net Balance")
            fig_pulse = px.line(trx_df, x="Date", y="Net_Balance", markers=True, title="Account Health Trajectory")
            fig_pulse.update_traces(line_color="#00FF00", line_width=3)
            st.plotly_chart(fig_pulse, use_container_width=True)
            
            st.markdown("---")
            
            # --- GRAPH 2: Multi-Line Graph (Cash Flows) ---
            st.markdown("#### 📊 Cash In vs Cash Out Trends")
            
            # Group data by date to calculate daily totals
            flow_df = trx_df.groupby("Date").apply(
                lambda x: pd.Series({
                    "Cash In (Dep/Sell)": x[x["Amount"] > 0]["Amount"].sum(),
                    "Cash Out (Wth/Buy)": x[x["Amount"] < 0]["Amount"].abs().sum(),
                    "Charges": x["Charge"].sum(),
                    "Fines": x[x["Type"].astype(str).str.upper() == "FINE"]["Amount"].abs().sum()
                })
            ).reset_index()
            
            fig_flow = px.line(
                flow_df, x="Date", 
                y=["Cash In (Dep/Sell)", "Cash Out (Wth/Buy)", "Charges", "Fines"], 
                markers=True, title="Daily Financial Flows"
            )
            # Customizing colors for clarity
            fig_flow.update_traces(patch={"line": {"width": 2}})
            st.plotly_chart(fig_flow, use_container_width=True)

            st.markdown("---")

            # --- GRAPH 3 & 4: Donut & Cost Heatmap ---
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("#### 🔄 Transaction Mediums")
                fig_donut = px.pie(trx_df, names="Medium", values=trx_df["Amount"].abs(), hole=0.4, title="Money Flow by Medium")
                st.plotly_chart(fig_donut, use_container_width=True)
                
            with c2:
                st.markdown("#### 💸 Cost of Trading (Fines & Charges)")
                cost_df = trx_df[(trx_df["Charge"] > 0) | (trx_df["Type"].astype(str).str.upper() == "FINE")].copy()
                if not cost_df.empty:
                    # Combine charges and absolute fines into a total cost column
                    cost_df["Total_Cost"] = cost_df["Charge"] + (cost_df["Amount"].abs() if "FINE" in cost_df["Type"].values else 0)
                    fig_cost = px.bar(cost_df, x="Date", y="Total_Cost", color="Type", title="Daily Money Lost to Fees/Fines")
                    st.plotly_chart(fig_cost, use_container_width=True)
                else:
                    st.success("No charges or fines paid yet! 🎉")

            st.markdown("---")

            # --- GRAPH 5: Liquidity Waterfall ---
            st.markdown("#### 🌊 Liquidity Waterfall (Current Month)")
            current_month = datetime.now().month
            water_df = trx_df[trx_df["Date"].dt.month == current_month].copy()
            
            if not water_df.empty:
                # Setup waterfall data array
                measures = ["relative"] * len(water_df)
                measures.append("total") # The final bar is the total
                
                x_labels = water_df["Date"].dt.strftime('%b %d').tolist() + ["Current Balance"]
                y_values = water_df["Amount"].tolist() + [0] # Plotly auto-calculates the 0
                text_values = water_df["Type"].tolist() + ["Total"]
                
                fig_water = go.Figure(go.Waterfall(
                    name="20", orientation="v",
                    measure=measures,
                    x=x_labels,
                    textposition="outside",
                    text=text_values,
                    y=y_values,
                    decreasing={"marker":{"color":"#FF4B4B"}}, # Red for outflow
                    increasing={"marker":{"color":"#00FF00"}}, # Green for inflow
                    totals={"marker":{"color":"#1E90FF"}}      # Blue for total
                ))
                fig_water.update_layout(title="Monthly Cash Flow Waterfall")
                st.plotly_chart(fig_water, use_container_width=True)
            else:
                st.info("No transactions this month for the waterfall chart.")
                
        else:
            st.info("No data available for graphs.")




      # --- TAB 7: ACTION LOGS ---
    with tms_tabs[6]:
        st.subheader("📝 TMS Security & Activity Logs")
        st.write("Tracks exactly when transactions were added to the system and warns you when a forceful raw data edit occurred.")
        
        # Load the global activity log
        full_log = get_data("activity_log.csv")
        
        if not full_log.empty and "TMS" in full_log["Category"].values:
            # Filter specifically for TMS actions
            tms_logs = full_log[full_log["Category"] == "TMS"].copy()
            
            # Apply color coding to highlight Danger (Force Edits)
            def color_log(row):
                if row["Action"] == "FORCE_EDIT": return ["color: #FF4B4B"] * len(row) # Red alert
                if row["Action"] == "ADD": return ["color: #00FF00"] * len(row) # Green success
                return [""] * len(row)
            
            st.dataframe(
                tms_logs.style.apply(color_log, axis=1), 
                use_container_width=True, 
                hide_index=True
            )
            
            st.markdown("---")
            
            # Export Button for Logs
            csv_log = tms_logs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export TMS Security Logs (CSV)",
                data=csv_log,
                file_name=f"TMS_Security_Logs_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                type="primary"
            )
        else:
            st.info("No TMS activity logged yet. Add a transaction to see it appear here.")      





# ================= PORTFOLIO =================
elif menu == "Portfolio":
    st.title("💼 Holdings Report")
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    
    if port.empty:
        st.warning("No data found.")
    else:
        if not cache.empty:
            df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
        else:
            df = port.copy()
            df["LTP"] = 0

        display_rows = []
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            val, pl, be, _ = calculate_metrics(row["Units"], row["Total_Cost"], ltp)
            pct = (pl / row["Total_Cost"] * 100) if row["Total_Cost"] else 0
            
            display_rows.append({
                "Stock": row['Symbol'],
                "Sector": row.get("Sector", "-"),
                "Qty": int(row["Units"]),
                "WACC": float(row["WACC"]),
                "LTP": float(ltp),
                "Value": float(val),
                "BE Price": float(be),
                "SL": float(row.get("Stop_Loss", 0)),
                "P/L": float(pl),
                "%": float(pct)
            })
            
        final_df = pd.DataFrame(display_rows)
        
        # Advanced Table
        st.dataframe(
            final_df.style.format({
                "WACC": "{:.1f}", "LTP": "{:.1f}", "Value": "{:,.0f}", 
                "BE Price": "{:.1f}", "SL": "{:.0f}", "P/L": "{:,.0f}", "%": "{:.1f}%"
            }).background_gradient(subset=["%"], cmap="RdYlGn", vmin=-10, vmax=10),
            use_container_width=True, hide_index=True
        )

# ================= WATCHLIST =================
elif menu == "Watchlist":
    st.title("👀 Watchlist Manager")
    wl = get_data("watchlist.csv")
    
    col_add, col_view = st.columns([1, 2])
    
    with col_add:
        st.markdown("### ➕ Add Stock")
        with st.form("add_wl"):
            sym = st.text_input("Symbol").upper()
            tgt = st.number_input("Target Price", min_value=0.0)
            rem = st.text_input("Remark")
            if st.form_submit_button("Add to List"):
                new = pd.DataFrame([{"Symbol": sym, "Target": tgt, "Remark": rem}])
                wl = pd.concat([wl, new], ignore_index=True)
                save_data("watchlist.csv", wl)
                st.success(f"Added {sym}")
                st.rerun()

    with col_view:
        st.markdown("### 📋 Current List")
        if not wl.empty:
            # Add Delete Buttons by iterating
            for i, row in wl.iterrows():
                c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
                c1.write(f"**{row['Symbol']}**")
                c2.write(f"🎯 {row['Target']}")
                c3.write(f"_{row['Remark']}_")
                if c4.button("❌", key=f"del_{i}"):
                    wl = wl.drop(i)
                    save_data("watchlist.csv", wl)
                    st.rerun()
        else:
            st.info("Watchlist is empty.")

# ================= ADD TRADE =================
elif menu == "Add Trade":
    st.title("➕ Add / Average Stock")
    with st.form("add_trade"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("Symbol").upper()
        units = c1.number_input("Units", min_value=1)
        price = c2.number_input("Buy Price", min_value=1.0)
        
        c3, c4 = st.columns(2)
        sector = c3.text_input("Sector")
        # NEW: Buy Date Input
        buy_dt = c4.date_input("Buy Date")
        
        c5, c6 = st.columns(2)
        sl = c5.number_input("Stop Loss", 0.0)
        note = c6.text_input("Note")
        
        if st.form_submit_button("Save Trade"):
            port = get_data("portfolio.csv")
            
            # Migration check: If old portfolio file doesn't have Buy_Date, add it
            if not port.empty and "Buy_Date" not in port.columns:
                port["Buy_Date"] = datetime.now().strftime("%Y-%m-%d")

            raw = units * price
            comm = get_broker_commission(raw)
            total = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            
            if not port.empty and sym in port["Symbol"].values:
                # AVERAGING LOGIC
                idx = port[port["Symbol"] == sym].index[0]
                old_u = port.at[idx, "Units"]
                old_c = port.at[idx, "Total_Cost"]
                
                port.at[idx, "Units"] = old_u + units
                port.at[idx, "Total_Cost"] = old_c + total
                port.at[idx, "WACC"] = (old_c + total) / (old_u + units)
                
                if sector: port.at[idx, "Sector"] = sector
                if sl > 0: port.at[idx, "Stop_Loss"] = sl
                # Note: We do NOT update Buy_Date here to preserve the original entry date for tax purposes.
                
                st.info(f"Averaged {sym} successfully. Kept original Buy Date: {port.at[idx, 'Buy_Date']}")
            else:
                # NEW ENTRY LOGIC
                new = pd.DataFrame([{
                    "Symbol": sym, 
                    "Sector": sector, 
                    "Units": units, 
                    "Total_Cost": total, 
                    "WACC": total/units, 
                    "Buy_Date": str(buy_dt),  # <--- Saving Date Here
                    "Stop_Loss": sl, 
                    "Notes": note
                }])
                port = pd.concat([port, new], ignore_index=True)
                st.success(f"Added {sym} to Portfolio with date {buy_dt}.")
            
            save_data("portfolio.csv", port)
            # ... inside Add Trade, after save_data("portfolio.csv", port) ...
            log_activity("TRADE", sym, "BUY", f"Added/Averaged {units} units @ Rs {price}", -total)

# ================= SELL STOCK =================
elif menu == "Sell Stock":
    st.title("💰 Sell Stock")
    port = get_data("portfolio.csv")
    
    if port.empty:
        st.warning("Nothing to sell.")
    else:
        # Check for Buy_Date column compatibility
        if "Buy_Date" not in port.columns:
            port["Buy_Date"] = "Unknown"

        sel_sym = st.selectbox("Select Stock", port["Symbol"].unique())
        row = port[port["Symbol"] == sel_sym].iloc[0]
        
        # Calculate Holding Period for Tax
        is_long_term = False
        holding_days = 0
        tax_rate = 0.075 # Default Short Term
        
        try:
            buy_dt_obj = datetime.strptime(str(row['Buy_Date']), "%Y-%m-%d")
            # Use Nepal Time for "Today"
            today_obj = datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)
            holding_days = (today_obj - buy_dt_obj).days
            
            if holding_days > 365:
                is_long_term = True
                tax_rate = 0.05 # Long Term
        except:
            pass # Keep default if date is invalid/unknown

        # Display Info
        tax_label = "Long Term (5%)" if is_long_term else "Short Term (7.5%)"
        st.info(f"Holding: {row['Units']} units | WACC: {row['WACC']:.2f} | Buy Date: {row['Buy_Date']} ({holding_days} days - {tax_label})")
        
        with st.form("sell_form"):
            c1, c2 = st.columns(2)
            u_sell = c1.number_input("Units to Sell", 1, int(row['Units']))
            p_sell = c2.number_input("Selling Price", 1.0)
            reason = st.text_input("Reason")
            
            if st.form_submit_button("Confirm Sale"):
                # 1. Invested Amount (Your Cost)
                # Formula: Units * WACC (This includes buy commission/fees already)
                invested_amt = u_sell * row['WACC']
                
                # 2. Selling Expenses Calculation
                gross_sell_amt = u_sell * p_sell
                commission = get_broker_commission(gross_sell_amt)
                sebon_fee = gross_sell_amt * SEBON_FEE
                dp_charge = DP_CHARGE
                
                # Money before Tax
                receivable_pre_tax = gross_sell_amt - commission - sebon_fee - dp_charge
                
                # 3. Tax Calculation
                profit_pre_tax = receivable_pre_tax - invested_amt
                cgt_tax = 0
                if profit_pre_tax > 0:
                    cgt_tax = profit_pre_tax * tax_rate
                
                # 4. Final Received Amount (Cash in Hand)
                received_amt = receivable_pre_tax - cgt_tax
                
                # 5. Net Profit/Loss
                net_pl = received_amt - invested_amt
                pl_pct = (net_pl / invested_amt * 100) if invested_amt > 0 else 0
                
                # --- UPDATE DATABASE ---
                
                # Update Portfolio
                cost_portion_to_remove = (row['Total_Cost'] / row['Units']) * u_sell
                
                if u_sell == row['Units']:
                    port = port[port["Symbol"] != sel_sym]
                else:
                    idx = port[port["Symbol"] == sel_sym].index[0]
                    port.at[idx, "Units"] -= u_sell
                    port.at[idx, "Total_Cost"] -= cost_portion_to_remove
                
                # Update History
                hist = get_data("history.csv")
                sell_date_str = (datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d")
                
                new_rec = pd.DataFrame([{
                    "Date": sell_date_str,
                    "Buy_Date": row['Buy_Date'],
                    "Symbol": sel_sym, 
                    "Units": u_sell, 
                    "Buy_Price": row['WACC'], 
                    "Sell_Price": p_sell,
                    "Invested_Amount": round(invested_amt, 2),
                    "Received_Amount": round(received_amt, 2), # Now Net Receivable
                    "Net_PL": round(net_pl, 2), 
                    "PL_Pct": round(pl_pct, 2),
                    "Reason": reason
                }])
                
                hist = pd.concat([hist, new_rec], ignore_index=True)
                
                save_data("portfolio.csv", port)
                save_data("history.csv", hist)
                # ... inside Sell Stock, after save_data("history.csv", hist) ...
                log_activity("TRADE", sel_sym, "SELL", f"Sold {u_sell} units @ Rs {p_sell} ({reason})", received_amt)
                
                # Success Message Breakdown
                st.success(f"Sold! Net Profit: Rs {net_pl:.2f}")
                with st.expander("See Transaction Breakdown"):
                    st.write(f"Gross Amount: Rs {gross_sell_amt:,.2f}")
                    st.write(f"(-) Commission: Rs {commission:.2f}")
                    st.write(f"(-) SEBON/DP: Rs {sebon_fee + dp_charge:.2f}")
                    st.write(f"(-) Capital Gain Tax: Rs {cgt_tax:.2f}")
                    st.markdown(f"**(=) Net Received:** **Rs {received_amt:,.2f}**")
                
                st.balloons()

# ================= HISTORY =================
elif menu == "History":
    st.title("📜 Trade Intelligence")
    hist = get_data("history.csv")
    
    if hist.empty:
        st.info("No transaction history found.")
    else:
        # --- MIGRATION/COMPATIBILITY ---
        # Ensure new columns exist in dataframe even if reading old file
        required_cols = ["Invested_Amount", "Received_Amount", "Buy_Date", "PL_Pct"]
        for col in required_cols:
            if col not in hist.columns:
                hist[col] = 0 if col != "Buy_Date" else "-"
        
        # Recalculate P/L Pct for old records if missing
        for i, row in hist.iterrows():
            if row["PL_Pct"] == 0 and row["Invested_Amount"] == 0 and row["Buy_Price"] > 0:
                 inv = row["Units"] * row["Buy_Price"]
                 hist.at[i, "Invested_Amount"] = inv
                 hist.at[i, "Received_Amount"] = row["Units"] * row["Sell_Price"]
                 if inv > 0:
                    hist.at[i, "PL_Pct"] = (row["Net_PL"] / inv) * 100

        # --- METRICS ---
        total_trades = len(hist)
        wins = hist[hist["Net_PL"] > 0]
        losses = hist[hist["Net_PL"] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        total_loss = abs(losses["Net_PL"].sum())
        profit_factor = wins["Net_PL"].sum() / total_loss if total_loss > 0 else wins["Net_PL"].sum()
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Win Rate", f"{win_rate:.1f}%")
        k2.metric("Profit Factor", f"{profit_factor:.2f}")
        k3.metric("Total Invested", f"Rs {hist['Invested_Amount'].sum():,.0f}")
        k4.metric("Net Realized P/L", f"Rs {hist['Net_PL'].sum():,.2f}")
        
        st.markdown("---")
        
        # --- TABLE DISPLAY ---
        st.markdown("### Transaction Log")
        
        # Column Order
        disp_cols = ["Date", "Buy_Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Invested_Amount", "Received_Amount", "Net_PL", "PL_Pct", "Reason"]
        final_cols = [c for c in disp_cols if c in hist.columns]
        
        st.dataframe(
            hist[final_cols].style.format({
                "Buy_Price": "{:,.1f}", 
                "Sell_Price": "{:,.1f}", 
                "Invested_Amount": "{:,.0f}",
                "Received_Amount": "{:,.0f}",
                "Net_PL": "{:,.0f}",
                "PL_Pct": "{:.2f}%"
            }).background_gradient(subset=["Net_PL", "PL_Pct"], cmap="RdYlGn", vmin=-20, vmax=20),
            use_container_width=True, hide_index=True
        )

# ================= ACTIVITY LOG =================
elif menu == "Activity Log":
    st.title("🗂 Trade Audit Log")
    st.caption("A chronological record of all actions and system events.")
    
    df = get_data("activity_log.csv")
    
    if df.empty:
        st.info("No activity recorded yet.")
    else:
        # --- FILTERS ---
        with st.expander("🔍 Filter Logs", expanded=False):
            c1, c2 = st.columns(2)
            cats = ["All"] + list(df["Category"].unique())
            sel_cat = c1.selectbox("Category", cats)
            search_sym = c2.text_input("Search Symbol").upper()
        
        # Apply Filters
        filtered_df = df.copy()
        if sel_cat != "All":
            filtered_df = filtered_df[filtered_df["Category"] == sel_cat]
        if search_sym:
            filtered_df = filtered_df[filtered_df["Symbol"].str.contains(search_sym, na=False)]
            
        # --- DISPLAY ---
        def highlight_action(val):
            color = 'white'
            if val == 'BUY': color = '#ffcccb' # Light Red
            elif val == 'SELL': color = '#90ee90' # Light Green
            return f'background-color: {color}; color: black'

        st.dataframe(
            filtered_df.style.map(highlight_action, subset=['Action'])
            .format({"Amount": "Rs {:,.2f}"}),
            use_container_width=True,
            height=500
        )
        
        # --- TOTALS (New Feature) ---
        st.markdown("### 💰 Cash Flow Summary")
        
        total_inflow = filtered_df[filtered_df["Amount"] > 0]["Amount"].sum()
        total_outflow = filtered_df[filtered_df["Amount"] < 0]["Amount"].sum()
        net_flow = filtered_df["Amount"].sum()
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Credit (Sales)", f"Rs {total_inflow:,.2f}")
        k2.metric("Total Debit (Buys)", f"Rs {total_outflow:,.2f}")
        k3.metric("Net Cash Flow", f"Rs {net_flow:,.2f}", 
                  delta=f"{net_flow:,.2f}", 
                  help="Positive = You took out more money than you put in.\nNegative = Money is still invested.")

        # Export
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download CSV", csv, "activity_log.csv", "text/csv")


# ================= WACC PROJECTION (NEW) =================
elif menu == "WACC Projection":
    st.title("🧮 WACC Projector")
    st.caption("Calculate how buying more shares affects your average price.")
    
    port = get_data("portfolio.csv")
    
    if port.empty:
        st.warning("Portfolio empty.")
    else:
        sym = st.selectbox("Select Stock", port["Symbol"].unique())
        row = port[port["Symbol"] == sym].iloc[0]
        
        col_curr, col_new = st.columns(2)
        
        with col_curr:
            st.markdown("#### Current Status")
            st.write(f"Units: **{row['Units']}**")
            st.write(f"WACC: **Rs {row['WACC']:.2f}**")
            st.write(f"Total Cost: **Rs {row['Total_Cost']:,.2f}**")
            
        with col_new:
            st.markdown("#### Buy Scenario")
            new_u = st.number_input("New Units", 1)
            new_p = st.number_input("New Price", 1.0)

        if st.button("Calculate Projection"):
            # New Cost
            raw = new_u * new_p
            comm = get_broker_commission(raw)
            add_cost = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            
            # Combined Data
            final_u = row['Units'] + new_u
            final_cost = row['Total_Cost'] + add_cost
            final_wacc = final_cost / final_u
            
            # Calculate New Break Even (Approximate: Cost + 0.6% Overhead + DP)
            overhead = final_cost * 0.006 + 25
            new_be = (final_cost + overhead) / final_u
            
            st.markdown("---")
            res_c1, res_c2, res_c3 = st.columns(3)
            
            res_c1.metric("New WACC", f"Rs {final_wacc:.2f}", 
                          delta=f"{row['WACC'] - final_wacc:.2f} Drop")
            
            res_c2.metric("New Break Even", f"Rs {new_be:.2f}")
            
            res_c3.metric("Extra Capital Needed", f"Rs {add_cost:,.2f}")
        

# ================= WHAT IF =================
elif menu == "What If Analysis":
    st.title("🔮 Trade Simulator")
    
    c1, c2, c3, c4 = st.columns(4)
    price = c1.number_input("Buy Price", 100.0)
    qty = c2.number_input("Quantity", 10)
    target = c3.number_input("Target Price", 0.0)
    stop_loss = c4.number_input("Stop Loss", 0.0)
    
    if st.button("Simulate"):
        raw = price * qty
        comm = get_broker_commission(raw)
        total_cost = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
        
        # Break Even Calc
        be_price = total_cost / qty
        
        st.markdown(f"#### 📊 Result")
        st.write(f"Total Invested: **Rs {total_cost:,.2f}**")
        st.info(f"⚖️ **Break-Even Price:** Rs {be_price:.2f} (You must sell above this to profit)")
        
        c_win, c_loss = st.columns(2)
        with c_win:
            if target > 0:
                _, pl, _, _ = calculate_metrics(qty, total_cost, target)
                st.markdown(f"### 🟢 Target @ {target}")
                st.metric("Net Profit", f"Rs {pl:,.0f}")
        with c_loss:
            if stop_loss > 0:
                _, pl, _, _ = calculate_metrics(qty, total_cost, stop_loss)
                st.markdown(f"### 🔴 SL @ {stop_loss}")
                st.metric("Net Loss", f"Rs {pl:,.0f}")


# ================= WEALTH GRAPH =================
elif menu == "Wealth Graph":
    st.title("📈 Wealth Growth")
    
    log = get_data("wealth.csv")
    
    if log.empty:
        st.info("No wealth history yet. Click 'Refresh Market Data' to create your first snapshot.")
    else:
        # Convert Date to datetime for better sorting
        log["Date"] = pd.to_datetime(log["Date"])
        log = log.sort_values("Date")
        
        # View Selector
        metric = st.selectbox("Select Metric to View", 
                             ["Current_Value", "Total_Investment", "Total_PL", "Day_Change", "Sold_Volume"])
        
        # Chart
        st.subheader(f"{metric.replace('_', ' ')} Over Time")
        
        # Color logic
        line_color = "#00FF00" if metric in ["Current_Value", "Total_PL"] else "#00CCFF"
        
        fig = px.line(log, x="Date", y=metric, markers=True, title=None)
        fig.update_traces(line_color=line_color, line_width=3)
        st.plotly_chart(fig, use_container_width=True)
        
        # Data Table below
        with st.expander("View Raw Data Log"):
            st.dataframe(log.style.format("{:.2f}", subset=log.columns.drop("Date")), use_container_width=True)

# ================= REPORTS =================
elif menu == "Reports":
    st.title("🖨️ Report Center")
    from fpdf import FPDF
    import base64

    st.write("Generate professional PDF reports of your trading terminal.")

    report_type = st.radio("Select Report Type", ["Full Portfolio Report", "Transaction History", "Combined Record"])

    if st.button("Generate PDF"):
        # Load Data
        port = get_data("portfolio.csv")
        hist = get_data("history.csv")
        cache = get_data("cache.csv")
        
        # Merge Portfolio for latest values
        if not port.empty and not cache.empty:
            full_port = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
        else:
            full_port = port

        # --- PDF CLASS ---
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 15)
                self.cell(0, 10, 'NEPSE Professional Terminal - User Report', 0, 1, 'C')
                self.set_font('Arial', 'I', 10)
                self.cell(0, 10, f'Generated on: {(datetime.utcnow() + pd.Timedelta(hours=5, minutes=45)).strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)

        # --- PORTFOLIO SECTION ---
        if report_type in ["Full Portfolio Report", "Combined Record"] and not full_port.empty:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, "Current Holdings", 0, 1)
            pdf.set_font("Arial", 'B', 9)
            
            # Table Header
            cols = ["Symbol", "Qty", "WACC", "LTP", "Value", "P/L"]
            widths = [25, 20, 30, 30, 35, 35]
            
            for i, col in enumerate(cols):
                pdf.cell(widths[i], 10, col, 1, 0, 'C')
            pdf.ln()
            
            # Table Body
            pdf.set_font("Arial", size=9)
            total_val = 0
            total_pl = 0
            
            for _, row in full_port.iterrows():
                ltp = row.get("LTP", 0)
                if ltp == 0: ltp = row["WACC"]
                val = row["Units"] * ltp
                pl = val - row["Total_Cost"]
                total_val += val
                total_pl += pl
                
                data = [
                    str(row["Symbol"]), str(int(row["Units"])), 
                    f"{row['WACC']:.1f}", f"{ltp:.1f}", 
                    f"{val:,.0f}", f"{pl:,.0f}"
                ]
                for i, datum in enumerate(data):
                    pdf.cell(widths[i], 10, datum, 1, 0, 'C')
                pdf.ln()

            pdf.ln(5)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 10, f"Total Portfolio Value: Rs {total_val:,.2f}", 0, 1)
            pdf.cell(0, 10, f"Total Unrealized P/L: Rs {total_pl:,.2f}", 0, 1)
            pdf.ln(10)

        # --- HISTORY SECTION ---
        if report_type in ["Transaction History", "Combined Record"] and not hist.empty:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, "Sales History", 0, 1)
            pdf.set_font("Arial", 'B', 9)
            
            cols = ["Date", "Symbol", "Qty", "Sell Price", "Net P/L"]
            widths = [35, 25, 20, 30, 35]
            
            for i, col in enumerate(cols):
                pdf.cell(widths[i], 10, col, 1, 0, 'C')
            pdf.ln()
            
            pdf.set_font("Arial", size=9)
            for _, row in hist.iterrows():
                data = [
                    str(row["Date"]), str(row["Symbol"]), str(int(row["Units"])),
                    f"{row['Sell_Price']:.1f}", f"{row['Net_PL']:,.1f}"
                ]
                for i, datum in enumerate(data):
                    pdf.cell(widths[i], 10, datum, 1, 0, 'C')
                pdf.ln()

        # Output
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        b64 = base64.b64encode(pdf_bytes).decode()
        href = f'<a href="data:application/octet-stream;base64,{b64}" download="NEPSE_Report.pdf" style="text-decoration:none; padding:10px; background-color:#4CAF50; color:white; border-radius:5px;">📥 Click to Download PDF</a>'
        st.markdown(href, unsafe_allow_html=True)

# ================= PSYCHOLOGY JOURNAL (NEW) =================
elif menu == "Trading Journal":
    st.title("🧠 Psychology Journal")
    
    diary = get_data("diary.csv")
    
    with st.form("journal_entry"):
        c1, c2 = st.columns(2)
        d_date = c1.date_input("Date")
        d_sym = c2.text_input("Symbol (Optional)").upper()
        
        c3, c4 = st.columns(2)
        d_emo = c3.selectbox("Primary Emotion", ["Calm/Focused", "Fear/Anxiety", "Greed/Overconfidence", "FOMO", "Boredom", "Revenge"])
        d_strat = c4.selectbox("Strategy Used", ["Trend Following", "Swing Trade", "Breakout", "Fundamental", "Impulse/Gamble"])
        
        d_note = st.text_area("Detailed Thought Process")
        d_mistake = st.text_input("Did you make a mistake?", placeholder="e.g., Sold too early, Moved SL")
        
        if st.form_submit_button("Log Entry"):
            new_entry = pd.DataFrame([{
                "Date": str(d_date),
                "Symbol": d_sym,
                "Note": d_note,
                "Emotion": d_emo,
                "Strategy": d_strat,
                "Mistake": d_mistake
            }])
            diary = pd.concat([diary, new_entry], ignore_index=True)
            save_data("diary.csv", diary)
            st.success("Journal Updated!")
            st.rerun()
            
    if not diary.empty:
        st.markdown("---")
        st.subheader("Your Mindset Analysis")
        
        # Simple Analytics
        emo_counts = diary["Emotion"].value_counts().reset_index()
        emo_counts.columns = ["Emotion", "Count"]
        
        col_chart, col_list = st.columns([1, 2])
        
        with col_chart:
            fig = px.pie(emo_counts, values="Count", names="Emotion", title="Emotional State", hole=0.4)
            fig.update_layout(showlegend=False, height=250, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
            
        with col_list:
            st.markdown("#### Recent Entries")
            # Show latest first
            for i, row in diary[::-1].head(5).iterrows():
                emoji = "🧘" if "Calm" in row["Emotion"] else "😨" if "Fear" in row["Emotion"] else "🤑"
                st.info(f"{emoji} **{row['Date']}** ({row['Symbol']}): {row['Note']} _[{row['Strategy']}]_")

# ================= RISK MANAGER (NEW) =================
elif menu == "Risk Manager":
    st.title("🛡️ Position Size Calculator")
    st.caption("Never lose more than you can afford.")
    
    # Auto-fetch Portfolio Value for calculation
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    total_capital = 0
    if not port.empty:
        if not cache.empty:
            df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
            for _, r in df.iterrows():
                p = r.get("LTP", 0) if r.get("LTP", 0) > 0 else r["WACC"]
                total_capital += r["Units"] * p
        else:
            total_capital = port["Total_Cost"].sum()
            
    # Inputs
    c1, c2, c3 = st.columns(3)
    capital = c1.number_input("Total Capital", value=float(total_capital) if total_capital > 0 else 100000.0)
    risk_pct = c2.number_input("Risk per Trade (%)", min_value=0.1, max_value=5.0, value=2.0, step=0.1)
    entry = c3.number_input("Entry Price", min_value=1.0, value=100.0)
    
    sl = st.number_input("Stop Loss Price", min_value=0.0, max_value=entry-0.1, value=entry*0.95)
    
    if st.button("Calculate Position Size"):
        # Logic
        risk_amount = capital * (risk_pct / 100)
        loss_per_share = entry - sl
        
        if loss_per_share > 0:
            max_qty = int(risk_amount / loss_per_share)
            total_investment = max_qty * entry
            
            st.markdown("---")
            col_res1, col_res2, col_res3 = st.columns(3)
            
            col_res1.metric("Max Quantity to Buy", f"{max_qty} Units")
            col_res2.metric("Total Investment", f"Rs {total_investment:,.0f}")
            col_res3.metric("Max Potential Loss", f"Rs {risk_amount:,.0f}", help="If SL hits, you lose exactly this amount.")
            
            if total_investment > capital:
                st.warning(f"⚠️ Warning: You need Rs {total_investment:,.0f} but only have Rs {capital:,.0f}. Reduce position or tighten SL.")
        else:
            st.error("Stop Loss must be lower than Entry Price.")

# ================= MANAGE DATA =================
elif menu == "Manage Data":
    st.title("🛠 Data Editor")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Portfolio", "History", "Watchlist", "Activity Log"])
    
    # 1. PORTFOLIO EDITOR
    with tab1:
        port = get_data("portfolio.csv")
        edit_port = st.data_editor(port, num_rows="dynamic", use_container_width=True, key="port_edit")
        
        c1, c2 = st.columns(2)
        if c1.button("Save Portfolio Changes"):
            # Detect Changes
            if len(edit_port) < len(port):
                diff = len(port) - len(edit_port)
                log_activity("SYSTEM", "PORTFOLIO", "DELETE", f"Manually deleted {diff} rows via Data Editor", 0)
            elif len(edit_port) > len(port):
                diff = len(edit_port) - len(port)
                log_activity("SYSTEM", "PORTFOLIO", "ADD", f"Manually added {diff} rows via Data Editor", 0)
            elif not edit_port.equals(port):
                log_activity("SYSTEM", "PORTFOLIO", "EDIT", "Manually modified values via Data Editor", 0)
                
            save_data("portfolio.csv", edit_port)
            st.success("Portfolio Saved & Logged.")
            
        if c2.button("Discard Changes", key="d1"): st.rerun()
            
    # 2. HISTORY EDITOR
    with tab2:
        hist = get_data("history.csv")
        edit_hist = st.data_editor(hist, num_rows="dynamic", use_container_width=True, key="hist_edit")
        
        c3, c4 = st.columns(2)
        if c3.button("Save History Changes"):
            # Detect Changes
            if len(edit_hist) < len(hist):
                diff = len(hist) - len(edit_hist)
                log_activity("SYSTEM", "HISTORY", "DELETE", f"Manually deleted {diff} rows via Data Editor", 0)
            elif not edit_hist.equals(hist):
                log_activity("SYSTEM", "HISTORY", "EDIT", "Manually modified History via Data Editor", 0)
                
            save_data("history.csv", edit_hist)
            st.success("History Saved & Logged.")
            
        if c4.button("Discard Changes", key="d2"): st.rerun()

    # 3. WATCHLIST EDITOR
    with tab3:
        wl = get_data("watchlist.csv")
        edit_wl = st.data_editor(wl, num_rows="dynamic", use_container_width=True, key="wl_edit")
        if st.button("Save Watchlist"):
            save_data("watchlist.csv", edit_wl)
            st.success("Watchlist Saved.")
            
    # 4. ACTIVITY LOG EDITOR (Manual Fixes)
    with tab4:
        st.warning("⚠️ Editing Logs directly is not recommended.")
        log_df = get_data("activity_log.csv")
        edit_log = st.data_editor(log_df, num_rows="dynamic", use_container_width=True, key="log_edit")
        if st.button("Save Log Changes"):
            save_data("activity_log.csv", edit_log)
            st.success("Logs Saved.")





























