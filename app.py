import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from github import Github
from io import StringIO
import plotly.express as px
from datetime import datetime
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Pro Terminal", page_icon="📈", layout="wide")

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
        if "portfolio" in filename: cols = ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Stop_Loss", "Notes"]
        elif "watchlist" in filename: cols = ["Symbol", "Target", "Remark"]
            # Update this line inside get_data():
        elif "history" in filename: cols = ["Date", "Symbol", "Units", "Buy_Price", "Sell_Price", "Net_PL", "Reason"]
        # Update this line inside get_data():
        elif "diary" in filename: cols = ["Date", "Symbol", "Note", "Emotion", "Mistake", "Strategy"]
        elif "cache" in filename: cols = ["Symbol", "LTP", "Change", "High52", "Low52", "LastUpdated"]
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

# --- MARKET ENGINE ---
def fetch_live_single(symbol):
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # LTP
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag: data['price'] = float(price_tag.text.strip().replace(",", ""))
        
        # Change & 52W
        for row in soup.find_all('tr'):
            text = row.text.strip()
            if "52 Weeks High - Low" in text:
                tds = row.find_all('td')
                if tds:
                    nums = tds[-1].text.split("-")
                    if len(nums) == 2:
                        data['high'] = float(nums[0].strip().replace(",", ""))
                        data['low'] = float(nums[1].strip().replace(",", ""))
            if "Change" in text and "%" not in text: 
                tds = row.find_all('td')
                if tds:
                    try: data['change'] = float(tds[-1].text.strip().replace(",", ""))
                    except: pass
    except: pass
    return data

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
    today_str = datetime.now().strftime("%Y-%m-%d")
    
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

def refresh_market_cache():
    port = get_data("portfolio.csv")
    watch = get_data("watchlist.csv")
    symbols = set(port["Symbol"].tolist() + watch["Symbol"].tolist())
    
    if not symbols: return
    
    cache_list = []
    progress = st.progress(0, "Connecting to Market...")
    
    for i, sym in enumerate(symbols):
        progress.progress((i+1)/len(symbols), f"Fetching {sym}...")
        live = fetch_live_single(sym)
        cache_list.append({
            "Symbol": sym,
            "LTP": live['price'],
            "Change": live['change'],
            "High52": live['high'],
            "Low52": live['low'],
            "LastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        time.sleep(0.1)
        
    progress.empty()
    new_cache = pd.DataFrame(cache_list)
    save_data("cache.csv", new_cache)
    
    # --- TRIGGER WEALTH LOG UPDATE ---
    update_wealth_log(port, new_cache)
    
    st.toast("Market Data & Wealth Log Updated!", icon="✅")
    st.cache_data.clear()

# --- CALCULATORS ---
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
    [ "Dashboard", "Portfolio", "Watchlist", "Add Trade", "Sell Stock", "History", "Wealth Graph", "WACC Projection", "What If Analysis", "Reports", "Manage Data", "Trading Journal", "Risk Manager" ] )
if st.sidebar.button("🔄 Refresh Market Data"):
    refresh_market_cache()
    st.rerun()

# ================= DASHBOARD =================
if menu == "Dashboard":
    # Load
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    
    if not port.empty and not cache.empty:
        df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    else:
        df = port.copy() if not port.empty else pd.DataFrame()
        if not df.empty: df["LTP"] = 0

    # Welcome
    last_up = cache["LastUpdated"].iloc[0] if not cache.empty else "Never"
    st.title("📊 Market Dashboard")
    st.caption(f"Last Updated: {last_up}")

    if df.empty:
        st.info("Portfolio is empty. Start by adding trades.")
    else:
        # Aggregation
        total_inv = df["Total_Cost"].sum()
        total_val = 0
        total_pl = 0
        day_change = 0
        alerts = []
        
        # Sector Data Prep
        sector_data = {}

        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            val, pl, _, d_chg = calculate_metrics(row["Units"], row["Total_Cost"], ltp, row.get("Change", 0))
            
            total_val += val
            total_pl += pl
            day_change += d_chg
            
            # Sector
            sec = row.get("Sector", "Unclassified")
            sector_data[sec] = sector_data.get(sec, 0) + val
            
            # SL Alert
            sl = row.get("Stop_Loss", 0)
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT:** {row['Symbol']} @ {ltp} (SL: {sl})")

        # 1. Main Metrics
        ret_pct = (total_pl / total_inv * 100) if total_inv else 0
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Investment", f"Rs {total_inv:,.0f}")
        c2.metric("Current Value", f"Rs {total_val:,.0f}")
        c3.metric("Day Change", f"Rs {day_change:,.0f}", delta=day_change)
        c4.metric("Total P/L", f"Rs {total_pl:,.0f}", delta_color="normal")
        c5.metric("Return %", f"{ret_pct:.2f}%", delta_color="normal")
        
        st.markdown("---")
        
        # 2. Visuals & Alerts
        col_chart, col_alert = st.columns([2, 1])
        
        # ... inside Dashboard ...
        with col_chart:
            st.subheader("Sector Analysis")
            
            # 1. Selector for Chart Type
            chart_metric = st.selectbox(
                "View By:", 
                ["Current Value", "Total Investment", "Profit/Loss", "Quantity"], 
                index=0,
                label_visibility="collapsed"
            )
            
            # 2. Map Selector to DataFrame Columns
            # We need to build a sector_df based on the selection
            sec_groups = {}
            
            for _, row in df.iterrows():
                sec = row.get("Sector", "Unclassified")
                ltp = row.get("LTP", 0) if row.get("LTP", 0) > 0 else row["WACC"]
                
                val = 0
                if chart_metric == "Current Value":
                    val = row["Units"] * ltp
                elif chart_metric == "Total Investment":
                    val = row["Total_Cost"]
                elif chart_metric == "Profit/Loss":
                    val = (row["Units"] * ltp) - row["Total_Cost"]
                    if val < 0: val = 0 # Pie charts don't like negative numbers
                elif chart_metric == "Quantity":
                    val = row["Units"]

                sec_groups[sec] = sec_groups.get(sec, 0) + val

            # 3. Plot
            if sec_groups:
                sec_df = pd.DataFrame(list(sec_groups.items()), columns=["Sector", "Metric"])
                fig = px.pie(sec_df, values="Metric", names="Sector", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No data for this metric.")
                
        with col_alert:
            st.subheader("📢 Notifications")
            if alerts:
                for a in alerts: st.error(a)
            
            # Watchlist Scan
            wl = get_data("watchlist.csv")
            if not wl.empty and not cache.empty:
                wl_m = pd.merge(wl, cache, on="Symbol", how="left")
                hits = wl_m[(wl_m["LTP"] <= wl_m["Target"]) & (wl_m["LTP"] > 0)]
                if not hits.empty:
                    for _, h in hits.iterrows():
                        st.success(f"🎯 **BUY SIGNAL:** {h['Symbol']} @ {h['LTP']}")
                else:
                    st.info("No Watchlist targets hit.")
            else:
                st.info("Watchlist is clear.")

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
        sector = c1.text_input("Sector (e.g. Hydro, Banking)")
        sl = c2.number_input("Stop Loss", 0.0)
        note = c1.text_input("Note")
        
        if st.form_submit_button("Save Trade"):
            port = get_data("portfolio.csv")
            
            raw = units * price
            comm = get_broker_commission(raw)
            total = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            
            if not port.empty and sym in port["Symbol"].values:
                idx = port[port["Symbol"] == sym].index[0]
                old_u = port.at[idx, "Units"]
                old_c = port.at[idx, "Total_Cost"]
                
                port.at[idx, "Units"] = old_u + units
                port.at[idx, "Total_Cost"] = old_c + total
                port.at[idx, "WACC"] = (old_c + total) / (old_u + units)
                if sector: port.at[idx, "Sector"] = sector
                if sl > 0: port.at[idx, "Stop_Loss"] = sl
                st.info(f"Averaged {sym} successfully.")
            else:
                new = pd.DataFrame([{
                    "Symbol": sym, "Sector": sector, "Units": units, 
                    "Total_Cost": total, "WACC": total/units, "Stop_Loss": sl, "Notes": note
                }])
                port = pd.concat([port, new], ignore_index=True)
                st.success(f"Added {sym} to Portfolio.")
            
            save_data("portfolio.csv", port)

# ================= SELL STOCK =================
elif menu == "Sell Stock":
    st.title("💰 Sell Stock")
    port = get_data("portfolio.csv")
    
    if port.empty:
        st.warning("Nothing to sell.")
    else:
        sel_sym = st.selectbox("Select Stock", port["Symbol"].unique())
        row = port[port["Symbol"] == sel_sym].iloc[0]
        
        st.info(f"Holding: {row['Units']} units | WACC: {row['WACC']:.2f}")
        
        with st.form("sell_form"):
            u_sell = st.number_input("Units to Sell", 1, int(row['Units']))
            p_sell = st.number_input("Selling Price", 1.0)
            is_long = st.checkbox("Long Term (>1 yr)? (5% Tax)")
            reason = st.text_input("Reason")
            
            if st.form_submit_button("Confirm Sale"):
                cost_portion = (row['Total_Cost'] / row['Units']) * u_sell
                _, net_pl, _, _ = calculate_metrics(u_sell, cost_portion, p_sell)
                
                # Update Portfolio
                if u_sell == row['Units']:
                    port = port[port["Symbol"] != sel_sym]
                else:
                    idx = port[port["Symbol"] == sel_sym].index[0]
                    port.at[idx, "Units"] -= u_sell
                    port.at[idx, "Total_Cost"] -= cost_portion
                
                # Update History
                hist = get_data("history.csv")
                # Update History Record creation
                new_rec = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Symbol": sel_sym, 
                    "Units": u_sell, 
                    "Buy_Price": row['WACC'],  # <--- NEW FIELD ADDED
                    "Sell_Price": p_sell,
                    "Net_PL": net_pl, 
                    "Reason": reason
                }])
                hist = pd.concat([hist, new_rec], ignore_index=True)
                
                save_data("portfolio.csv", port)
                save_data("history.csv", hist)
                st.success(f"Sold! Net Profit: Rs {net_pl:.2f}")
                st.balloons()

# ================= HISTORY TAB (NEW) =================
# ================= HISTORY (INTELLIGENT) =================
elif menu == "History":
    st.title("📜 Trade Intelligence")
    hist = get_data("history.csv")
    
    if hist.empty:
        st.info("No transaction history found.")
    else:
        # --- INTELLIGENCE ENGINE ---
        total_trades = len(hist)
        wins = hist[hist["Net_PL"] > 0]
        losses = hist[hist["Net_PL"] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100
        total_profit = wins["Net_PL"].sum()
        total_loss = abs(losses["Net_PL"].sum())
        
        # Profit Factor (Avoid division by zero)
        profit_factor = total_profit / total_loss if total_loss > 0 else total_profit
        
        best_trade = hist.loc[hist["Net_PL"].idxmax()] if not hist.empty else None
        worst_trade = hist.loc[hist["Net_PL"].idxmin()] if not hist.empty else None

        # --- KPI CARDS ---
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Win Rate", f"{win_rate:.1f}%", help="% of trades that were profitable")
        k2.metric("Profit Factor", f"{profit_factor:.2f}", help="Gross Profit / Gross Loss ( > 1.5 is Good)")
        k3.metric("Avg Profit/Trade", f"Rs {hist['Net_PL'].mean():.0f}")
        k4.metric("Net Realized P/L", f"Rs {hist['Net_PL'].sum():,.2f}", delta_color="normal")
        
        st.markdown("---")
        
        # --- HALL OF FAME ---
        c1, c2 = st.columns(2)
        with c1:
            st.success(f"🏆 **Best Trade:** {best_trade['Symbol']} (+Rs {best_trade['Net_PL']:,.0f})")
        with c2:
            st.error(f"💀 **Worst Trade:** {worst_trade['Symbol']} ({worst_trade['Net_PL']:,.0f})")

        # --- DATA TABLE ---
        st.markdown("### Transaction Log")
        # Ensure compatibility
        if "Buy_Price" not in hist.columns: hist["Buy_Price"] = 0.0
            
        st.dataframe(
            hist.style.format({
                "Buy_Price": "{:,.2f}", "Sell_Price": "{:,.2f}", "Net_PL": "{:,.2f}"
            }).background_gradient(subset=["Net_PL"], cmap="RdYlGn", vmin=-5000, vmax=5000),
            use_container_width=True, hide_index=True
        )
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
                self.cell(0, 10, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
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
    
    tab1, tab2, tab3 = st.tabs(["Portfolio", "History", "Watchlist"])
    
    with tab1:
        port = get_data("portfolio.csv")
        edit_port = st.data_editor(port, num_rows="dynamic", use_container_width=True)
        c1, c2 = st.columns(2)
        if c1.button("Save Portfolio"):
            save_data("portfolio.csv", edit_port)
            st.success("Saved.")
        if c2.button("Discard Changes", key="d1"): st.rerun()
            
    with tab2:
        hist = get_data("history.csv")
        edit_hist = st.data_editor(hist, num_rows="dynamic", use_container_width=True)
        c3, c4 = st.columns(2)
        if c3.button("Save History"):
            save_data("history.csv", edit_hist)
            st.success("Saved.")
        if c4.button("Discard Changes", key="d2"): st.rerun()

    with tab3:
        st.warning("⚠️ DANGER ZONE")
        del_opt = st.selectbox("Select File to Wipe", ["None", "Portfolio", "History", "Watchlist"])
        if del_opt != "None":
            if st.button(f"🔴 CONFIRM DELETE ALL {del_opt.upper()} DATA"):
                fname = f"{del_opt.lower()}.csv"
                save_data(fname, pd.DataFrame()) # Save empty
                st.error(f"{del_opt} has been wiped.")
                st.cache_data.clear()







