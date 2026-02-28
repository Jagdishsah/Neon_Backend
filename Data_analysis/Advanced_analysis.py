import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from github import Github
import io

st.subheader("🚀 Advanced Quantitative Analysis")

@st.cache_data(ttl=60)
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        return [f.name for f in repo.get_contents("Data_analysis") if f.name.endswith(".csv")], repo
    except Exception as e: return None, str(e)

saved_files, repo_or_error = fetch_github_files()

if saved_files:
    selected_file = st.selectbox("Select Broker Data to Analyze:", saved_files)
    if selected_file:
        file_data = repo_or_error.get_contents(f"Data_analysis/{selected_file}")
        raw_df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        raw_df["Date"] = pd.to_datetime(raw_df["Date"])

        # --- DYNAMIC DATE FILTER ---
        min_date, max_date = raw_df["Date"].min().date(), raw_df["Date"].max().date()
        date_range = st.date_input("🗓️ Select Range (Calculations adjust to range)", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        if len(date_range) == 2:
            mask = (raw_df["Date"].dt.date >= date_range[0]) & (raw_df["Date"].dt.date <= date_range[1])
            df = raw_df.loc[mask].copy().reset_index(drop=True)
            
            if not df.empty:
                df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
                df["Cum_Net_Qty"] = df["Net_Qty"].cumsum() 
                df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
                df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

                # --- ADVANCED BROKER KPI CALCULATIONS ---
                total_buy_qty = df["Buy_Qty"].sum()
                total_buy_amt = df["Buy_Amount"].sum()
                total_sell_qty = df["Sell_Qty"].sum()
                total_sell_amt = df["Sell_Amount"].sum()
                current_inventory = df["Cum_Net_Qty"].iloc[-1]
                
                # WACC Calculations
                buy_wacc = (total_buy_amt / total_buy_qty) if total_buy_qty > 0 else 0
                sell_wacc = (total_sell_amt / total_sell_qty) if total_sell_qty > 0 else 0
                
                # Realized P/L on Cleared Trades (Approximation assuming FIFO)
                # Formula: Sell Qty * (Sell Price - Average Buy Price)
                realized_pl = total_sell_qty * (sell_wacc - buy_wacc)
                
                # Remaining Break Even Price
                # Formula: (Total Money Spent - Total Money Recovered) / Remaining Shares
                net_capital_flow = total_buy_amt - total_sell_amt
                break_even = (net_capital_flow / current_inventory) if current_inventory > 0 else 0

                st.write("---")
                st.markdown("### 💰 Profitability & WACC Metrics")
                m1, m2, m3 = st.columns(3)
                m1.metric("Average Buy WACC", f"Rs {buy_wacc:,.2f}")
                m2.metric("Average Sell WACC", f"Rs {sell_wacc:,.2f}")
                m3.metric("Inventory Left", f"{current_inventory:,.0f} Units")

                m4, m5, m6 = st.columns(3)
                # Green if profit, Red if Loss
                m4.metric("Realized P/L (Cleared Trades)", f"Rs {realized_pl:,.2f}", delta="Profit" if realized_pl > 0 else "Loss")
                
                # Break-Even Analysis
                if current_inventory > 0:
                    if break_even < 0:
                        m5.metric("Remaining Break-Even", "Risk Free!", delta="Fully Recovered Initial Capital", delta_color="normal")
                    else:
                        m5.metric("Remaining Break-Even", f"Rs {break_even:,.2f}", delta="Target Price to Recover Money", delta_color="off")
                else:
                    m5.metric("Remaining Break-Even", "N/A", delta="No inventory left")

                # --- IMPROVED DAY HEATMAP ---
                st.write("---")
                st.markdown("### 🗓️ Improved Day-of-Week Heatmap")
                
                with st.expander("📖 How to Read this Heatmap", expanded=False):
                    st.info("""
                    **What it tells you:**
                    This chart shows exactly which days of the week the broker is most active, broken down by month.
                    - 🟩 **Green Boxes:** The broker was aggressively buying (Net Accumulation). The darker the green, the heavier the buy volume.
                    - 🟥 **Red Boxes:** The broker was aggressively dumping/selling. 
                    - **Numbers inside:** Show the exact Net Quantity for that specific day and month combination.
                    
                    **Pro Trading Tip:** Look for patterns. If a broker always shows deep red on Thursdays, they might be systematically booking profits before the weekend. If Sundays are always deep green, they are front-running the week's news!
                    """)
                
                df_heat = df.copy()
                df_heat['Day'] = df_heat['Date'].dt.day_name()
                df_heat['Month'] = df_heat['Date'].dt.strftime('%b %Y') # e.g., Jan 2026
                
                # Filter strictly for NEPSE trading days and sort them
                nepse_days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
                df_heat = df_heat[df_heat['Day'].isin(nepse_days)]
                df_heat['Day'] = pd.Categorical(df_heat['Day'], categories=nepse_days, ordered=True)
                
                heat_pivot = df_heat.groupby(['Month', 'Day'], observed=False)['Net_Qty'].sum().unstack().fillna(0)
                
                fig_heat = px.imshow(
                    heat_pivot, 
                    color_continuous_scale="RdYlGn", 
                    color_continuous_midpoint=0, 
                    text_auto=".0f", # Shows the exact numbers inside the boxes
                    aspect="auto"
                )
                fig_heat.update_layout(height=450, margin=dict(t=20, b=20))
                st.plotly_chart(fig_heat, use_container_width=True)
