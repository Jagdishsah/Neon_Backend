import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import numpy as np
from github import Github
import io

SAVE_DIR = "Data_analysis"
os.makedirs(SAVE_DIR, exist_ok=True)

st.title("📈 Advanced Data Analysis Studio")

# --- TABS FOR NAVIGATION ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📤 Upload & Analyze", 
    "📂 Browse Saved Data", 
    "🚀 Advanced Analysis", 
    "📊 Visualization",
    "🤖 AI Advisor"
])

with tab1:
    uploaded_file = st.file_uploader("Upload raw data file (JSON or TXT)", type=["txt", "json"])
    if uploaded_file is not None:
        try:
            raw_data = json.load(uploaded_file)
            df = pd.DataFrame(raw_data.get("data", raw_data))
                
            num_cols = ["b_qty", "s_qty", "b_amt", "s_amt"]
            for col in num_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    
            df["Date"] = pd.to_datetime(df["date"], errors='coerce')
            df = df.sort_values(by="Date").reset_index(drop=True)
            df.rename(columns={"b_qty": "Buy_Qty", "s_qty": "Sell_Qty", "b_amt": "Buy_Amount", "s_amt": "Sell_Amount"}, inplace=True, errors='ignore')
            
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Net_Amount"] = df["Buy_Amount"] - df["Sell_Amount"]
            df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
            df["Avg_30D_Vol"] = df["Total_Vol"].rolling(window=30, min_periods=1).mean()

            st.write("---")
            min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
            date_range = st.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                mask = (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)
                filtered_df = df.loc[mask].copy()
                
                # --- COLOR STRENGTH STYLING ---
                def apply_color_strength(row):
                    net, avg_vol = row["Net_Qty"], row["Avg_30D_Vol"]
                    if avg_vol == 0 or pd.isna(avg_vol): return [''] * len(row)
                    alpha = min(max((abs(net) / avg_vol) * 0.5, 0.15), 0.85)
                    color = f"rgba(0, 200, 0, {alpha})" if net > 0 else f"rgba(255, 0, 0, {alpha})" if net < 0 else "rgba(128, 128, 128, 0.2)"
                    return [f"background-color: {color}; color: white;"] * len(row)

                display_df = filtered_df.copy()
                display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d')
                fmt_df = display_df[["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Buy_Amount", "Sell_Amount", "Net_Amount", "Avg_30D_Vol"]]
                
                st.write("### 🧮 Detailed Breakdown (Color-coded by Aggression)")
                styled_df = fmt_df.style.apply(apply_color_strength, axis=1).format(precision=0)
                st.dataframe(styled_df, use_container_width=True, height=400)

                # --- SMART SAVE TO GITHUB ---
                st.write("---")
                st.subheader("💾 Save to GitHub (Permanent)")
                c_stock, c_tms, c_custom = st.columns(3)
                stock_name = c_stock.text_input("Stock Symbol (e.g., NABIL)", "").upper()
                tms_no = c_tms.text_input("TMS/Broker No (e.g., 58)", "")
                custom_name = c_custom.text_input("Or Custom Filename", "")
                
                save_name = custom_name if custom_name else (f"{stock_name}_{tms_no}" if stock_name and tms_no else "")

                if st.button("Commit to GitHub", use_container_width=True, type="primary"):
                    if save_name:
                        file_path = f"Data_analysis/{save_name}.csv"
                        cols_to_save = ["Date", "Buy_Qty", "Sell_Qty", "Net_Qty", "Buy_Amount", "Sell_Amount", "Net_Amount"]
                        save_df = display_df[cols_to_save].copy()
                        
                        try:
                            g = Github(st.secrets["github"]["token"]) 
                            repo = g.get_repo(st.secrets["github"]["repo_name"]) # FIXED REPO_NAME
                            
                            try:
                                file_contents = repo.get_contents(file_path)
                                existing_df = pd.read_csv(io.StringIO(file_contents.decoded_content.decode('utf-8')))
                                combined_df = pd.concat([existing_df, save_df]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
                                repo.update_file(file_contents.path, f"Updated {save_name}", combined_df.to_csv(index=False), file_contents.sha)
                                st.success(f"🎉 Merged and saved `{save_name}.csv`!")
                            except: 
                                repo.create_file(file_path, f"Created {save_name}", save_df.to_csv(index=False))
                                st.success(f"🎉 Created `{save_name}.csv`!")
                        except Exception as e: st.error(f"❌ Error: {e}")
                    else: st.error("Provide a filename.")
        except Exception as e: st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("📂 Browse Saved Data")
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"]) # FIXED REPO_NAME
        try:
            saved_files = [f.name for f in repo.get_contents("Data_analysis") if f.name.endswith(".csv")]
            selected_file = st.selectbox("Select file:", saved_files) if saved_files else None
            if selected_file:
                file_data = repo.get_contents(f"Data_analysis/{selected_file}")
                hist_df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
                st.dataframe(hist_df, use_container_width=True)
                if st.button(f"🗑️ Delete {selected_file}"):
                    repo.delete_file(file_data.path, f"Deleted {selected_file}", file_data.sha)
                    st.rerun()
        except: st.info("No files found.")
    except: st.error("❌ GitHub auth failed.")

with tab3:
    try:
        with open("Data_analysis/Advanced_analysis.py", encoding="utf-8") as f: exec(compile(f.read(), "Advanced_analysis.py", 'exec'), globals())
    except Exception as e: st.error(f"❌ Error loading Advanced Analysis: {e}")

with tab4:
    try:
        with open("Data_analysis/Visual.py", encoding="utf-8") as f: exec(compile(f.read(), "Visual.py", 'exec'), globals())
    except FileNotFoundError: st.warning("Create `Visual.py` inside `Data_analysis` folder.")
    except Exception as e: st.error(f"❌ Error loading Visualizations: {e}")

with tab5:
    try:
        with open("Advisor.py", encoding="utf-8") as f: exec(compile(f.read(), "Advisor.py", 'exec'), globals())
    except: st.info("Create `Advisor.py` in the main folder to use AI.")
