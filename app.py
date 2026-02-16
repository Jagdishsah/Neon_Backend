import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from github import Github
from io import StringIO
import plotly.express as px
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE Pro Terminal", page_icon="🚀", layout="wide")

# Constants
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

# --- GITHUB DATABASE ENGINE ---
def get_repo():
    """Connects to GitHub Repo"""
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        g = Github(token)
        return g.get_repo(repo_name)
    except:
        st.error("❌ GitHub Token Error! Check your Secrets.")
        return None

def get_data(filename):
    """Loads CSV from GitHub, creates it if missing"""
    repo = get_repo()
    if not repo: return pd.DataFrame()
    
    try:
        content = repo.get_contents(filename)
        return pd.read_csv(StringIO(content.decoded_content.decode("utf-8")))
    except:
        # File doesn't exist, return empty DF with correct columns
        if "portfolio" in filename: cols = ["Symbol", "Units", "Total_Cost", "WACC", "Sector", "Stop_Loss", "Notes"]
        elif "watchlist" in filename: cols = ["Symbol", "Target", "Remark"]
        elif "history" in filename: cols = ["Date", "Symbol", "Units", "Sell_Price", "Net_PL", "Reason"]
        elif "diary" in filename: cols = ["Date", "Note"]
        else: cols = []
        return pd.DataFrame(columns=cols)

def save_data(filename, df):
    """Saves DataFrame to GitHub CSV"""
    repo = get_repo()
    if not repo: return False
    
    try:
        csv_content = df.to_csv(index=False)
        try:
            # Update existing
            file = repo.get_contents(filename)
            repo.update_file(file.path, f"Update {filename}", csv_content, file.sha)
        except:
            # Create new
            repo.create_file(filename, f"Create {filename}", csv_content)
        return True
    except Exception as e:
        st.error(f"Save Failed: {e}")
        return False

# --- LIVE SCRAPER ---
@st.cache_data(ttl=300) # Cache for 5 mins
def fetch_live_data(symbol):
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = {'price': 0.0, 'high': 0.0, 'low': 0.0, 'diff': 0.0}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Price
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag:
            data['price'] = float(price_tag.text.strip().replace(",", ""))
            
        # 52 Week High/Low (Scraping from table)
        # This is a basic search, might need adjustment if site changes
        for row in soup.find_all('tr'):
            if "52 Weeks High - Low" in row.text:
                tds = row.find_all('td')
                if tds:
                    nums = tds[-1].text.split("-")
                    if len(nums) == 2:
                        data['high'] = float(nums[0].strip().replace(",", ""))
                        data['low'] = float(nums[1].strip().replace(",", ""))
    except:
        pass
    return data

# --- CALCULATORS ---
def calculate_pl_metrics(units, cost, current_price, is_long=False):
    if units == 0: return 0, 0, 0
    
    sell_amt = units * current_price
    
    # Commission Tier
    if sell_amt <= 50000: comm_rate = 0.36
    elif sell_amt <= 500000: comm_rate = 0.33
    else: comm_rate = 0.27
    
    comm = max(10, sell_amt * comm_rate / 100)
    sebon = sell_amt * SEBON_FEE
    
    receivable = sell_amt - comm - sebon - DP_CHARGE
    gross_pl = receivable - cost
    
    tax_rate = CGT_LONG if is_long else CGT_SHORT
    tax = gross_pl * tax_rate if gross_pl > 0 else 0
    
    net_pl = gross_pl - tax
    return net_pl, tax, receivable

# --- UI LAYOUT ---
st.sidebar.title("🚀 NEPSE Terminal")
menu = st.sidebar.radio("Navigation", 
    ["Dashboard", "Portfolio", "Watchlist", "Add Trade", "Sell/History", "WACC Calc", "Diary"])

if st.sidebar.button("🔄 Force Refresh"):
    st.cache_data.clear()
    st.rerun()

# ================= DASHBOARD =================
if menu == "Dashboard":
    st.title("📊 Market Dashboard")
    df = get_data("portfolio.csv")
    
    if df.empty:
        st.info("Portfolio is empty.")
    else:
        # Live Updates
        total_inv = 0
        total_val = 0
        total_pl = 0
        alerts = []
        
        progress = st.progress(0, "Scanning Market...")
        
        for i, row in df.iterrows():
            progress.progress((i+1)/len(df))
            sym = row["Symbol"]
            units = row["Units"]
            cost = row["Total_Cost"]
            sl = row.get("Stop_Loss", 0)
            
            live = fetch_live_data(sym)
            ltp = live['price'] if live['price'] > 0 else (cost/units)
            
            # SL Check
            if sl > 0 and ltp < sl:
                alerts.append(f"⚠️ **STOP LOSS HIT:** {sym} is at {ltp} (SL: {sl})")
            
            net_pl, _, _ = calculate_pl_metrics(units, cost, ltp)
            
            total_inv += cost
            total_val += (units * ltp)
            total_pl += net_pl
            
        progress.empty()
        
        # 1. Top Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Net Worth", f"Rs {total_val:,.0f}", delta=f"{total_val-total_inv:,.0f}")
        c2.metric("Investment", f"Rs {total_inv:,.0f}")
        c3.metric("Total P/L", f"Rs {total_pl:,.0f}", delta_color="normal")
        c4.metric("Return", f"{(total_pl/total_inv)*100:.2f}%" if total_inv else "0%")
        
        # 2. Alerts
        for a in alerts: st.error(a)
        
        # 3. Sector Allocation Chart
        st.subheader("Sector Allocation")
        if "Sector" in df.columns:
            # Group by Sector
            sec_df = df.groupby("Sector")["Total_Cost"].sum().reset_index()
            fig = px.pie(sec_df, values="Total_Cost", names="Sector", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Update stock details to see Sector charts.")

# ================= PORTFOLIO =================
elif menu == "Portfolio":
    st.title("💼 Live Portfolio")
    df = get_data("portfolio.csv")
    
    if not df.empty:
        # Prepare Display Data
        display = []
        for i, row in df.iterrows():
            live = fetch_live_data(row["Symbol"])
            ltp = live['price'] if live['price'] > 0 else row["WACC"]
            
            net_pl, _, _ = calculate_pl_metrics(row["Units"], row["Total_Cost"], ltp)
            pl_pct = (net_pl / row["Total_Cost"] * 100) if row["Total_Cost"] else 0
            
            display.append({
                "Symbol": row["Symbol"],
                "Sector": row.get("Sector", "-"),
                "Units": row["Units"],
                "WACC": row["WACC"],
                "LTP": ltp,
                "Value": row["Units"] * ltp,
                "P/L": net_pl,
                "%": pl_pct,
                "High52": live['high'],
                "Low52": live['low'],
                "Note": row.get("Notes", "")
            })
            
        # Show Table
        st.dataframe(pd.DataFrame(display).style.format({
            "WACC": "{:.2f}", "LTP": "{:.2f}", "Value": "{:,.0f}", 
            "P/L": "{:,.0f}", "%": "{:.2f}%", "High52": "{:.0f}", "Low52": "{:.0f}"
        }), use_container_width=True)
    else:
        st.info("No stocks found.")

# ================= WATCHLIST =================
elif menu == "Watchlist":
    st.title("👀 Watchlist")
    wl = get_data("watchlist.csv")
    
    # Input Form
    with st.form("wl_add"):
        c1, c2, c3 = st.columns(3)
        sym = c1.text_input("Symbol").upper()
        tgt = c2.number_input("Target Price", min_value=0.0)
        rem = c3.text_input("Remark")
        if st.form_submit_button("Add to Watchlist"):
            new_row = pd.DataFrame([{"Symbol": sym, "Target": tgt, "Remark": rem}])
            wl = pd.concat([wl, new_row], ignore_index=True)
            save_data("watchlist.csv", wl)
            st.success("Added!")
            st.rerun()

    if not wl.empty:
        # Live Scan
        res = []
        for i, row in wl.iterrows():
            live = fetch_live_data(row["Symbol"])
            ltp = live['price']
            signal = "WAIT"
            
            if ltp > 0 and row["Target"] > 0:
                if ltp <= row["Target"]: signal = "🟢 BUY NOW"
            
            res.append({
                "Symbol": row["Symbol"],
                "LTP": ltp,
                "Target": row["Target"],
                "Signal": signal,
                "Remark": row["Remark"]
            })
            
        st.dataframe(pd.DataFrame(res), use_container_width=True)
        
        # Delete Option
        del_sym = st.selectbox("Remove from Watchlist", wl["Symbol"].unique())
        if st.button("Remove Stock"):
            wl = wl[wl["Symbol"] != del_sym]
            save_data("watchlist.csv", wl)
            st.rerun()

# ================= ADD TRADE =================
elif menu == "Add Trade":
    st.title("➕ Add / Average Stock")
    
    with st.form("add_trade"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("Symbol (e.g. NICA)").upper()
        units = c1.number_input("Units", min_value=1)
        price = c2.number_input("Buy Price", min_value=1.0)
        sector = c1.text_input("Sector (e.g. Hydro, Bank)")
        sl = c2.number_input("Stop Loss (Optional)", min_value=0.0)
        note = c1.text_input("Note")
        
        if st.form_submit_button("Save Trade"):
            df = get_data("portfolio.csv")
            
            # Cost Calc
            raw = units * price
            comm = max(10, raw * (0.36/100) if raw < 50000 else raw * (0.33/100)) # Simplified
            total = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            
            # Logic: Average if exists, else Append
            if not df.empty and sym in df["Symbol"].values:
                idx = df[df["Symbol"] == sym].index[0]
                old_u = df.at[idx, "Units"]
                old_c = df.at[idx, "Total_Cost"]
                
                df.at[idx, "Units"] = old_u + units
                df.at[idx, "Total_Cost"] = old_c + total
                df.at[idx, "WACC"] = (old_c + total) / (old_u + units)
                if sector: df.at[idx, "Sector"] = sector
                if sl > 0: df.at[idx, "Stop_Loss"] = sl
                st.info(f"Averaged {sym}!")
            else:
                new = pd.DataFrame([{
                    "Symbol": sym, "Units": units, "Total_Cost": total, 
                    "WACC": total/units, "Sector": sector, "Stop_Loss": sl, "Notes": note
                }])
                df = pd.concat([df, new], ignore_index=True)
            
            save_data("portfolio.csv", df)
            st.success("Saved successfully!")

# ================= SELL / HISTORY =================
elif menu == "Sell/History":
    st.title("💰 Sell Stock & History")
    
    tab1, tab2 = st.tabs(["Sell Stock", "Trade History"])
    
    with tab1:
        df = get_data("portfolio.csv")
        if df.empty:
            st.warning("Portfolio is empty.")
        else:
            sel_sym = st.selectbox("Select Stock", df["Symbol"].unique())
            row = df[df["Symbol"] == sel_sym].iloc[0]
            
            st.info(f"Available: {row['Units']} units | WACC: {row['WACC']:.2f}")
            
            with st.form("sell_form"):
                u_sell = st.number_input("Units to Sell", 1, int(row['Units']))
                p_sell = st.number_input("Selling Price", 1.0)
                is_long = st.checkbox("Long Term (>1 yr)? (5% Tax)")
                reason = st.text_input("Reason for Selling")
                
                if st.form_submit_button("Confirm Sell"):
                    # 1. Calc P/L
                    cost_portion = (row['Total_Cost'] / row['Units']) * u_sell
                    net_pl, tax, val = calculate_pl_metrics(u_sell, cost_portion, p_sell, is_long)
                    
                    # 2. Update Portfolio
                    if u_sell == row['Units']:
                        df = df[df["Symbol"] != sel_sym] # Delete row
                    else:
                        idx = df[df["Symbol"] == sel_sym].index[0]
                        df.at[idx, "Units"] -= u_sell
                        df.at[idx, "Total_Cost"] -= cost_portion
                    save_data("portfolio.csv", df)
                    
                    # 3. Add to History
                    hist = get_data("history.csv")
                    new_rec = pd.DataFrame([{
                        "Date": datetime.now().strftime("%Y-%m-%d"),
                        "Symbol": sel_sym, "Units": u_sell, "Sell_Price": p_sell,
                        "Net_PL": net_pl, "Reason": reason
                    }])
                    hist = pd.concat([hist, new_rec], ignore_index=True)
                    save_data("history.csv", hist)
                    
                    st.success(f"Sold! Profit: Rs {net_pl:.2f}")
                    st.balloons()
                    st.rerun()

    with tab2:
        hist = get_data("history.csv")
        if not hist.empty:
            st.dataframe(hist.style.format({"Net_PL": "{:,.2f}", "Sell_Price": "{:,.2f}"}), use_container_width=True)
            st.metric("Total Realized Profit", f"Rs {hist['Net_PL'].sum():,.2f}")
        else:
            st.info("No history yet.")

# ================= WACC CALC =================
elif menu == "WACC Calc":
    st.title("🧮 Project WACC")
    
    df = get_data("portfolio.csv")
    sym = st.selectbox("Select Stock to Average", df["Symbol"].unique()) if not df.empty else None
    
    if sym:
        row = df[df["Symbol"] == sym].iloc[0]
        cur_u = row["Units"]
        cur_wacc = row["WACC"]
        cur_cost = row["Total_Cost"]
        
        st.write(f"**Current:** {cur_u} units @ {cur_wacc:.2f}")
        
        c1, c2 = st.columns(2)
        new_u = c1.number_input("New Units", 1)
        new_p = c2.number_input("New Price", 1.0)
        
        if st.button("Calculate"):
            raw = new_u * new_p
            comm = max(10, raw * 0.0036) # Approx
            new_cost = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            
            tot_u = cur_u + new_u
            tot_cost = cur_cost + new_cost
            new_wacc = tot_cost / tot_u
            
            st.success(f"New WACC: **Rs {new_wacc:.2f}**")
            st.metric("Price Drop", f"{cur_wacc - new_wacc:.2f}")

# ================= DIARY =================
elif menu == "Diary":
    st.title("📔 Trading Diary")
    
    diary = get_data("diary.csv")
    
    with st.form("note"):
        txt = st.text_area("Log your thought/plan:")
        if st.form_submit_button("Save Note"):
            new_note = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Note": txt
            }])
            diary = pd.concat([diary, new_note], ignore_index=True)
            save_data("diary.csv", diary)
            st.success("Saved.")
            st.rerun()
            
    if not diary.empty:
        for i, row in diary[::-1].iterrows(): # Show newest first
            st.info(f"**{row['Date']}**: {row['Note']}")
