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
    st.toast("Market Data Synced!", icon="✅")
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
    ["Dashboard", "Portfolio", "Watchlist", "Add Trade", "Sell Stock", "History", "WACC Projection", "What If Analysis", "Manage Data"])

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
        
        with col_chart:
            st.subheader("Sector Allocation")
            if sector_data:
                sec_df = pd.DataFrame(list(sector_data.items()), columns=["Sector", "Value"])
                fig = px.pie(sec_df, values="Value", names="Sector", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                st.plotly_chart(fig, use_container_width=True)
                
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
elif menu == "History":
    st.title("📜 Transaction History")
    hist = get_data("history.csv")
    
    if hist.empty:
        st.info("No transaction history found.")    
    else:
        # Metrics
        total_profit = hist["Net_PL"].sum()
        total_sales_val = (hist["Units"] * hist["Sell_Price"]).sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Total Realized Profit", f"Rs {total_profit:,.2f}")
        c2.metric("Total Sales Volume", f"Rs {total_sales_val:,.0f}")
        
        # Ensure compatibility with old data that didn't have Buy_Price
        if "Buy_Price" not in hist.columns:
            hist["Buy_Price"] = 0.0

        # Updated Table with Buy Price
        st.dataframe(
            hist.style.format({
                "Buy_Price": "{:,.2f}", 
                "Sell_Price": "{:,.2f}", 
                "Net_PL": "{:,.2f}"
            }),
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



