import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from github import Github
from io import StringIO

# --- CONFIGURATION ---
st.set_page_config(page_title="NEPSE GitHub Terminal", page_icon="🚀", layout="wide")

# Fees
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25

# --- GITHUB CONNECTION ---
def get_github_repo():
    """Connects to your repository using the Token"""
    try:
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo_name"]
        g = Github(token)
        return g.get_repo(repo_name)
    except Exception as e:
        st.error(f"❌ GitHub Connection Error: {e}")
        return None

def load_data():
    """Reads portfolio.csv directly from GitHub"""
    try:
        repo = get_github_repo()
        if not repo: return pd.DataFrame()
        
        # Get file content
        contents = repo.get_contents("portfolio.csv")
        csv_data = contents.decoded_content.decode("utf-8")
        return pd.read_csv(StringIO(csv_data))
    except:
        return pd.DataFrame(columns=["Symbol", "Units", "Total_Cost", "WACC", "Notes"])

def save_data(df):
    """Pushes updated CSV back to GitHub"""
    try:
        repo = get_github_repo()
        if not repo: return False
        
        # Get current file to get its 'sha' (ID)
        contents = repo.get_contents("portfolio.csv")
        
        # Convert DataFrame back to CSV string
        updated_csv = df.to_csv(index=False)
        
        # Update file on GitHub
        repo.update_file(contents.path, "Updated via App", updated_csv, contents.sha)
        return True
    except Exception as e:
        st.error(f"❌ Save Error: {e}")
        return False

# --- HELPER FUNCTIONS ---
def get_broker_commission(amount):
    if amount <= 50000: rate = 0.36 / 100
    elif amount <= 500000: rate = 0.33 / 100
    else: rate = 0.27 / 100
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

def calculate_pl(units, total_cost, current_price):
    if units <= 0: return 0, 0
    current_val = units * current_price
    # Simple Net Receivable Approx
    comm = get_broker_commission(current_val)
    receivable = current_val - comm - DP_CHARGE - (current_val * SEBON_FEE)
    net_pl = receivable - total_cost
    return current_val, net_pl

# --- LOAD DATA ---
df = load_data()

# --- SIDEBAR ---
st.sidebar.title("🚀 NEPSE Terminal")
menu = st.sidebar.radio("Menu", ["Dashboard", "Add Trade", "Delete Trade"])

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ==========================================
# PAGE: DASHBOARD
# ==========================================
if menu == "Dashboard":
    st.title("📊 Live Portfolio")
    
    if df.empty:
        st.info("Portfolio is empty. Go to 'Add Trade' to start.")
    else:
        # Metrics
        total_inv = df["Total_Cost"].sum()
        current_val_total = 0
        total_pl = 0
        
        display_data = []
        
        # Progress Bar
        bar = st.progress(0, text="Fetching Prices...")
        
        for i, row in df.iterrows():
            bar.progress((i + 1) / len(df))
            sym = row["Symbol"]
            units = row["Units"]
            cost = row["Total_Cost"]
            wacc = row["WACC"]
            
            ltp = fetch_live_price(sym)
            if ltp == 0: ltp = wacc
            
            curr_val, net_pl = calculate_pl(units, cost, ltp)
            
            current_val_total += curr_val
            total_pl += net_pl
            
            display_data.append({
                "Symbol": sym,
                "Units": units,
                "LTP": ltp,
                "WACC": wacc,
                "Invested": cost,
                "Value": curr_val,
                "Profit": net_pl
            })
            
        bar.empty()
        
        # Top Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investment", f"Rs. {total_inv:,.0f}")
        c2.metric("Current Value", f"Rs. {current_val_total:,.0f}", delta=f"{current_val_total-total_inv:,.0f}")
        c3.metric("Total Profit", f"Rs. {total_pl:,.0f}")

        # Table
        # Create the DataFrame
        final_df = pd.DataFrame(display_data)

        # Apply specific formatting only to the number columns
        st.dataframe(
            final_df.style.format({
                "Units": "{:.0f}",
                "LTP": "{:.2f}",
                "WACC": "{:.2f}",
                "Invested": "{:,.2f}",
                "Value": "{:,.2f}",
                "Profit": "{:,.2f}"
            }), 
            use_container_width=True
        )

# ==========================================
# PAGE: ADD TRADE
# ==========================================
elif menu == "Add Trade":
    st.title("➕ Add New Stock")
    
    with st.form("add_form"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("Symbol (e.g. NICA)").upper()
        units = c2.number_input("Units", min_value=1)
        price = c1.number_input("Buy Price per Unit", min_value=1.0)
        note = c2.text_input("Note (Optional)")
        
        if st.form_submit_button("Save to Portfolio"):
            # Calculate Costs
            raw = units * price
            comm = get_broker_commission(raw)
            total_cost = raw + comm + DP_CHARGE + (raw * SEBON_FEE)
            wacc = total_cost / units
            
            # Create new row
            new_row = pd.DataFrame([{
                "Symbol": sym,
                "Units": units,
                "Total_Cost": total_cost,
                "WACC": wacc,
                "Notes": note
            }])
            
            # Combine with existing data
            updated_df = pd.concat([df, new_row], ignore_index=True)
            
            # Save to GitHub
            if save_data(updated_df):
                st.success(f"✅ Saved {sym} to GitHub!")
                st.cache_data.clear()
            else:
                st.error("Failed to save.")

# ==========================================
# PAGE: DELETE TRADE
# ==========================================
elif menu == "Delete Trade":
    st.title("🗑 Delete / Clear Stock")
    
    if df.empty:
        st.warning("Nothing to delete.")
    else:
        stock_to_del = st.selectbox("Select Stock to Remove", df["Symbol"].unique())
        
        if st.button("Confirm Delete"):
            # Filter out the selected stock
            updated_df = df[df["Symbol"] != stock_to_del]
            
            if save_data(updated_df):
                st.success(f"🗑 Deleted {stock_to_del} from GitHub.")
                st.cache_data.clear()
            else:
                st.error("Failed to delete.")

