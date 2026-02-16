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

# Custom CSS for Professional Look
st.markdown("""
<style>
    .metric-card {background-color: #0E1117; border: 1px solid #262730; padding: 15px; border-radius: 5px;}
    .profit {color: #00FF00;}
    .loss {color: #FF4B4B;}
    .stDataFrame {font-size: 14px;}
</style>
""", unsafe_allow_html=True)

# --- GITHUB DATABASE ENGINE ---
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
        # Define schemas for new files
        if "portfolio" in filename: cols = ["Symbol", "Sector", "Units", "Total_Cost", "WACC", "Stop_Loss", "Notes"]
        elif "watchlist" in filename: cols = ["Symbol", "Target", "Remark"]
        elif "history" in filename: cols = ["Date", "Symbol", "Units", "Sell_Price", "Net_PL", "Reason"]
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

# --- MARKET ENGINE (CACHING) ---
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
        
        # Change & 52W (Scraping table)
        for row in soup.find_all('tr'):
            text = row.text.strip()
            if "52 Weeks High - Low" in text:
                tds = row.find_all('td')
                if tds:
                    nums = tds[-1].text.split("-")
                    if len(nums) == 2:
                        data['high'] = float(nums[0].strip().replace(",", ""))
                        data['low'] = float(nums[1].strip().replace(",", ""))
            if "Change" in text and "%" not in text: # Absolute change
                tds = row.find_all('td')
                if tds:
                    try: data['change'] = float(tds[-1].text.strip().replace(",", ""))
                    except: pass
    except: pass
    return data

def refresh_market_cache():
    """Updates cache.csv with fresh data for ALL symbols"""
    port = get_data("portfolio.csv")
    watch = get_data("watchlist.csv")
    
    # Get unique symbols
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
        time.sleep(0.1) # Be polite to server
        
    progress.empty()
    new_cache = pd.DataFrame(cache_list)
    save_data("cache.csv", new_cache)
    st.toast("Market Data Updated!", icon="✅")
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
    
    # Break Even Calc (Approx selling price to cover cost + taxes)
    # BE = (Total Cost + DP) / (Units * (1 - Tax_Rate_Approx - Comm_Rate))
    # Simplified: We just add ~0.5% buffer for selling costs
    be_price = (cost + DP_CHARGE) / (units * 0.994) 
    
    sell_comm = get_broker_commission(curr_val)
    sebon = curr_val * SEBON_FEE
    receivable = curr_val - sell_comm - sebon - DP_CHARGE
    
    net_pl = receivable - cost
    # Tax only on profit
    if net_pl > 0:
        tax = net_pl * CGT_SHORT # Assuming short term for conservative view
        net_pl -= tax
        
    return curr_val, net_pl, be_price, day_gain

# --- UI LAYOUT ---
st.sidebar.title("🚀 NEPSE Pro")
menu = st.sidebar.radio("Navigation", 
    ["Dashboard", "Portfolio", "Watchlist", "Manage Data", "What If Analysis"])

if st.sidebar.button("🔄 Refresh Market Data"):
    refresh_market_cache()
    st.rerun()

# ================= DASHBOARD =================
if menu == "Dashboard":
    # Load Data
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    
    # Merge Portfolio with Cache
    if not port.empty and not cache.empty:
        df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
    elif not port.empty:
        df = port
        df[["LTP", "Change", "LastUpdated"]] = 0
    else:
        df = pd.DataFrame()

    # Welcome Section
    last_up = df["LastUpdated"].iloc[0] if not df.empty and "LastUpdated" in df.columns else "Never"
    st.markdown(f"### 👋 Welcome back, Trader!")
    st.caption(f"Last Market Sync: {last_up}")
    
    if df.empty:
        st.info("Portfolio is empty. Go to 'Manage Data' to add stocks.")
    else:
        # Calculate Aggregates
        total_inv = df["Total_Cost"].sum()
        total_val = 0
        total_pl = 0
        day_change = 0
        alerts = []
        
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"] # Fallback
            
            val, pl, _, d_chg = calculate_metrics(row["Units"], row["Total_Cost"], ltp, row.get("Change", 0))
            
            total_val += val
            total_pl += pl
            day_change += d_chg
            
            # SL Alert
            sl = row.get("Stop_Loss", 0)
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT**: {row['Symbol']} is at {ltp} (SL: {sl})")

        # 1. Summary Cards
        ret_pct = (total_pl / total_inv * 100) if total_inv else 0
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Investment", f"Rs {total_inv:,.0f}")
        c2.metric("Current Value", f"Rs {total_val:,.0f}")
        c3.metric("Day Change", f"Rs {day_change:,.0f}", delta=day_change)
        c4.metric("Total P/L", f"Rs {total_pl:,.0f}", delta_color="normal")
        c5.metric("Return %", f"{ret_pct:.2f}%", delta_color="normal")
        
        # 2. Alerts
        if alerts:
            st.error("\n".join(alerts))
            
        # 3. Watchlist Alerts
        wl = get_data("watchlist.csv")
        if not wl.empty and not cache.empty:
            wl_merged = pd.merge(wl, cache, on="Symbol", how="left")
            hits = wl_merged[(wl_merged["LTP"] <= wl_merged["Target"]) & (wl_merged["LTP"] > 0)]
            if not hits.empty:
                for _, hit in hits.iterrows():
                    st.success(f"🎯 **TARGET HIT**: {hit['Symbol']} is at {hit['LTP']} (Target: {hit['Target']})")

# ================= PORTFOLIO =================
elif menu == "Portfolio":
    st.title("💼 Portfolio Holdings")
    
    port = get_data("portfolio.csv")
    cache = get_data("cache.csv")
    
    if port.empty:
        st.warning("No Holdings Found.")
    else:
        # Prepare Data
        if not cache.empty:
            df = pd.merge(port, cache, on="Symbol", how="left").fillna(0)
        else:
            df = port.copy()
            df["LTP"] = 0
        
        display_rows = []
        notes_map = {}
        
        total_inv = 0
        total_val = 0
        day_chg = 0
        total_pl = 0
        
        for _, row in df.iterrows():
            sym_display = f"{row['Symbol']} [N]" if row.get("Notes") else row['Symbol']
            if row.get("Notes"): notes_map[row['Symbol']] = row['Notes']
            
            ltp = row.get("LTP", 0)
            if ltp == 0: ltp = row["WACC"]
            
            val, pl, be, d_chg = calculate_metrics(row["Units"], row["Total_Cost"], ltp, row.get("Change", 0))
            
            pct = (pl / row["Total_Cost"] * 100) if row["Total_Cost"] else 0
            
            total_inv += row["Total_Cost"]
            total_val += val
            day_chg += d_chg
            total_pl += pl
            
            display_rows.append({
                "Stock": sym_display,
                "Sector": row.get("Sector", "-"),
                "Qty": int(row["Units"]),
                "WACC": float(row["WACC"]),
                "LTP": float(ltp),
                "Value": float(val),
                "BE": float(be),
                "SL": float(row.get("Stop_Loss", 0)),
                "P/L": float(pl),
                "%": float(pct)
            })
            
        final_df = pd.DataFrame(display_rows)
        
        # Sorting
        sort_col = st.selectbox("Sort By", ["Value", "P/L", "%", "Stock"], index=0)
        if sort_col == "Value": final_df = final_df.sort_values("Value", ascending=False)
        elif sort_col == "P/L": final_df = final_df.sort_values("P/L", ascending=False)
        elif sort_col == "%": final_df = final_df.sort_values("%", ascending=False)
        else: final_df = final_df.sort_values("Stock")
        
        # MAIN TABLE
        st.dataframe(
            final_df.style.format({
                "WACC": "{:.1f}", "LTP": "{:.1f}", "Value": "{:,.0f}", 
                "BE": "{:.1f}", "SL": "{:.0f}", "P/L": "{:,.0f}", "%": "{:.1f}%"
            }).map(lambda x: "color: red" if x < 0 else "color: green", subset=["P/L", "%"]),
            use_container_width=True,
            hide_index=True
        )
        
        # SUMMARY TABLE (Bottom)
        st.markdown("### 📋 Portfolio Summary")
        sum_df = pd.DataFrame([{
            "Total Investment": f"Rs {total_inv:,.0f}",
            "Current Value": f"Rs {total_val:,.0f}",
            "Day Change": f"Rs {day_chg:,.0f}",
            "Total P/L": f"Rs {total_pl:,.0f}",
            "Return %": f"{(total_pl/total_inv*100):.2f}%"
        }])
        st.table(sum_df)
        
        # NOTES SECTION
        if notes_map:
            st.markdown("---")
            st.markdown("#### 📝 Stock Notes")
            for s, n in notes_map.items():
                st.caption(f"**{s}**: {n}")

# ================= WATCHLIST =================
elif menu == "Watchlist":
    st.title("👀 Market Watch")
    
    wl = get_data("watchlist.csv")
    cache = get_data("cache.csv")
    
    if wl.empty:
        st.info("Watchlist is empty.")
    else:
        if not cache.empty:
            df = pd.merge(wl, cache, on="Symbol", how="left").fillna(0)
        else:
            df = wl.copy()
            df[["LTP", "High52", "Low52"]] = 0
            
        res = []
        for _, row in df.iterrows():
            ltp = row.get("LTP", 0)
            hi = row.get("High52", 0)
            lo = row.get("Low52", 0)
            tgt = row["Target"]
            
            # Position Calculation
            pos_pct = 0
            if hi > lo: pos_pct = (ltp - lo) / (hi - lo)
            
            signal = "WAIT"
            if ltp > 0 and tgt > 0 and ltp <= tgt: signal = "🟢 BUY"
            
            res.append({
                "Symbol": row["Symbol"],
                "LTP": ltp,
                "Target": tgt,
                "52W High": hi,
                "52W Low": lo,
                "Position": pos_pct,
                "Signal": signal,
                "Remark": row["Remark"]
            })
            
        wd = pd.DataFrame(res)
        st.dataframe(
            wd.style.format({
                "LTP": "{:.1f}", "Target": "{:.1f}", "52W High": "{:.0f}", "52W Low": "{:.0f}",
                "Position": "{:.0%}"
            }).bar(subset=["Position"], color=["#FF4B4B", "#00FF00"], vmin=0, vmax=1),
            use_container_width=True, hide_index=True
        )

# ================= MANAGE DATA =================
elif menu == "Manage Data":
    st.title("🛠 Admin Management")
    
    tab1, tab2, tab3 = st.tabs(["Current Holdings", "Sales History", "Watchlist"])
    
    with tab1:
        st.info("Edit your Holdings directly. Click 'Save Changes' to update GitHub.")
        port = get_data("portfolio.csv")
        edited_port = st.data_editor(port, num_rows="dynamic", use_container_width=True)
        if st.button("Save Portfolio Changes"):
            if save_data("portfolio.csv", edited_port):
                st.success("Portfolio Updated!")
                st.cache_data.clear()
                
    with tab2:
        st.info("Edit your Sales History.")
        hist = get_data("history.csv")
        edited_hist = st.data_editor(hist, num_rows="dynamic", use_container_width=True)
        if st.button("Save History Changes"):
            if save_data("history.csv", edited_hist):
                st.success("History Updated!")
                st.cache_data.clear()

    with tab3:
        st.info("Edit Watchlist.")
        wl = get_data("watchlist.csv")
        edited_wl = st.data_editor(wl, num_rows="dynamic", use_container_width=True)
        if st.button("Save Watchlist Changes"):
            if save_data("watchlist.csv", edited_wl):
                st.success("Watchlist Updated!")
                st.cache_data.clear()

# ================= WHAT IF =================
elif menu == "What If Analysis":
    st.title("🧮 Trade Simulator")
    
    c1, c2, c3, c4 = st.columns(4)
    price = c1.number_input("Buy Price", 100.0)
    qty = c2.number_input("Quantity", 10)
    target = c3.number_input("Target Price", 0.0)
    stop_loss = c4.number_input("Stop Loss", 0.0)
    
    if st.button("Simulate Trade"):
        cost = price * qty
        comm_buy = get_broker_commission(cost)
        total_cost = cost + comm_buy + DP_CHARGE + (cost * SEBON_FEE)
        
        wacc = total_cost / qty
        
        st.markdown("---")
        st.markdown(f"#### 📊 Trade Setup")
        st.write(f"**Total Investment Required:** Rs {total_cost:,.2f}")
        st.write(f"**Effective WACC:** Rs {wacc:.2f}")
        
        c_win, c_loss = st.columns(2)
        
        # Win Scenario
        with c_win:
            if target > 0:
                val, pl, _, _ = calculate_metrics(qty, total_cost, target)
                pct = (pl / total_cost) * 100
                st.markdown(f"### 🟢 If Target Met ({target})")
                st.metric("Net Profit", f"Rs {pl:,.0f}", delta=f"{pct:.2f}%")
                st.write(f"Risk/Reward: 1 : {(target-price)/(price-stop_loss) if stop_loss > 0 else 0:.1f}")
            else:
                st.info("Set Target to see Profit scenario")

        # Loss Scenario
        with c_loss:
            if stop_loss > 0:
                val, pl, _, _ = calculate_metrics(qty, total_cost, stop_loss)
                pct = (pl / total_cost) * 100
                st.markdown(f"### 🔴 If SL Hit ({stop_loss})")
                st.metric("Net Loss", f"Rs {pl:,.0f}", delta=f"{pct:.2f}%")
            else:
                st.info("Set SL to see Loss scenario")
