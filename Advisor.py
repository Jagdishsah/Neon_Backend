import streamlit as st
import pandas as pd
from github import Github
import io
import google.generativeai as genai

st.header("🤖 AI Quantitative Advisor")
st.markdown("Your personal AI analyst powered by Google Gemini. Select a dataset, and let the AI find hidden patterns in the broker's behavior.")

# --- 1. CONFIGURE GEMINI API ---
try:
    genai.configure(api_key=st.secrets["gemini"]["api_key"])
    model = genai.GenerativeModel('gemini-2.0-flash') # Fast, smart, and efficient
except KeyError:
    st.error("❌ Gemini API Key not found. Please add `[gemini]` and `api_key = 'YOUR_KEY'` to your `.streamlit/secrets.toml` file.")
    st.stop()
except Exception as e:
    st.error(f"❌ Error configuring AI: {e}")
    st.stop()

# --- 2. FETCH SAVED DATA FROM GITHUB ---

def get_repo_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        contents = repo.get_contents("Data_analysis")
        return [f.name for f in contents if f.name.endswith(".csv")], repo
    except Exception:
        return [], None

files, repo = get_repo_files()

if not files:
    st.info("No saved data found in GitHub. Go to Data Analysis and save a file first!")
else:
    selected_file = st.selectbox("Select Broker Data for AI Analysis:", files)
    
    if selected_file:
        try:
            # Download file
            file_data = repo.get_contents(f"Data_analysis/{selected_file}")
            df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
            df["Date"] = pd.to_datetime(df["Date"])
            
            # --- 3. PREPARE CONTEXT FOR AI ---
            # We don't send the whole CSV (too large), we send a highly detailed summary
            total_days = len(df)
            net_inventory = (df["Buy_Qty"] - df["Sell_Qty"]).sum()
            total_buy_amt = df["Buy_Amount"].sum()
            total_buy_qty = df["Buy_Qty"].sum()
            wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
            
            # Get the last 5 days of activity for recent momentum
            recent_df = df.tail(5).copy()
            recent_df["Net_Qty"] = recent_df["Buy_Qty"] - recent_df["Sell_Qty"]
            recent_trend = recent_df[["Date", "Net_Qty"]].to_string(index=False)
            
            st.write(f"**Analyzing:** `{selected_file}` | **Total Days:** `{total_days}`")
            
            # User Prompt
            user_question = st.text_input("Ask the AI a specific question, or leave blank for a general report:", 
                                          placeholder="E.g., Are they accumulating or distributing? What is their WACC?")
            
            if st.button("🧠 Generate AI Analysis", type="primary"):
                with st.spinner("The AI is analyzing the data..."):
                    
                    # The System Prompt instructs the AI on its role
                    prompt = f"""
                    You are an elite quantitative analyst for the Nepal Stock Exchange (NEPSE). 
                    I am providing you with the trading summary of a specific broker.
                    
                    DATA SUMMARY:
                    - Broker File: {selected_file}
                    - Trading Days Logged: {total_days}
                    - Current Holding Inventory (Net Qty): {net_inventory}
                    - Estimated Weighted Average Cost (WACC): Rs {wacc:.2f}
                    
                    RECENT 5-DAY MOMENTUM (Net Qty):
                    {recent_trend}
                    
                    Based on this data, provide a professional, highly analytical response. 
                    If the Net Inventory is highly positive, they are accumulating. If negative, they are dumping.
                    Look at the recent 5 days to see if their behavior changed recently.
                    Keep the response concise, formatted with bullet points, and act like a Wall Street advisor.
                    
                    User's specific question: {user_question if user_question else "Provide a general accumulation/distribution analysis and strategic advice."}
                    """
                    
                    # Call Gemini
                    response = model.generate_content(prompt)
                    
                    st.write("---")
                    st.markdown("### 🤖 AI Analyst Report")
                    st.write(response.text)
                    
        except Exception as e:
            st.error(f"Error reading data or contacting AI: {e}")
