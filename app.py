import streamlit as st
import gspread
import pandas as pd

st.set_page_config(page_title="System Doctor", page_icon="🩺")

st.title("🩺 NEPSE Terminal Diagnostic Tool")

# 1. CHECK SECRETS
st.header("1. Checking Secrets")
if "gspread_credentials" in st.secrets:
    st.success("✅ Secrets found!")
    creds = st.secrets["gspread_credentials"]
    st.write(f"**Bot Email:** `{creds.get('client_email', 'UNKNOWN')}`")
    st.info("👉 PLEASE VERIFY: Did you share your Google Sheet with the email above?")
else:
    st.error("❌ Secrets NOT found in Streamlit Cloud. Go to App Settings -> Secrets.")
    st.stop()

# 2. CHECK GOOGLE CONNECTION
st.header("2. Connecting to Google")
try:
    gc = gspread.service_account_from_dict(creds)
    st.success("✅ Authenticated with Google!")
except Exception as e:
    st.error(f"❌ Authentication Failed: {e}")
    st.stop()

# 3. CHECK SPREADSHEET ACCESS
st.header("3. Finding Spreadsheet")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1jf810Q3V5XquNE9cI7kjyC6kwxs0dxnw1moNLk1Wtqw/edit"

try:
    sh = gc.open_by_url(SHEET_URL)
    st.success(f"✅ Found Spreadsheet: '{sh.title}'")
except Exception as e:
    st.error(f"❌ Could not open Spreadsheet.\nError: {e}")
    st.warning("👉 Fix: Open your Google Sheet, click 'Share', and paste the Bot Email from Step 1 as an 'Editor'.")
    st.stop()

# 4. CHECK WORKSHEETS
st.header("4. Checking Tabs (Worksheets)")
worksheet_list = [ws.title for ws in sh.worksheets()]
st.write(f"**Tabs Found:** {worksheet_list}")

if "Portfolio" in worksheet_list:
    st.success("✅ 'Portfolio' tab exists.")
    
    # Check Data
    ws = sh.worksheet("Portfolio")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    if df.empty:
        st.warning("⚠️ 'Portfolio' tab is EMPTY. Add a header row!")
    else:
        st.success(f"✅ Found {len(df)} rows of data.")
        st.dataframe(df)
        st.write("Does this data look correct?")
else:
    st.error("❌ 'Portfolio' tab NOT found.")
    st.info(f"👉 Fix: Rename your main tab to 'Portfolio' (Capital P). Currently, it is probably named '{worksheet_list[0]}'.")

if "Sales" in worksheet_list:
    st.success("✅ 'Sales' tab exists.")
else:
    st.warning("⚠️ 'Sales' tab missing. Please create a tab named 'Sales'.")
