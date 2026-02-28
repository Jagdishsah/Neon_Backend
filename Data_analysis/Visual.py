import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from github import Github
import io

st.subheader("🎨 Dynamic Visualization Studio")
st.markdown("High-performance quantitative charting engine.")

@st.cache_data(ttl=60)
def fetch_github_files():
    try:
        g = Github(st.secrets["github"]["token"]) 
        repo = g.get_repo(st.secrets["github"]["repo_name"])
        return [f.name for f in repo.get_contents("Data_analysis") if f.name.endswith(".csv")], repo
    except: return None, None

saved_files, repo = fetch_github_files()

if saved_files:
    selected_file = st.selectbox("Select Data Source:", saved_files)
    if selected_file:
        file_data = repo.get_contents(f"Data_analysis/{selected_file}")
        df = pd.read_csv(io.StringIO(file_data.decoded_content.decode('utf-8')))
        df["Date"] = pd.to_datetime(df["Date"])
        
        # --- DYNAMIC DATE FILTER ---
        min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
        date_range = st.date_input("🗓️ Filter Chart Dates:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        if len(date_range) == 2:
            mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
            df = df.loc[mask].copy().reset_index(drop=True)
            
            # Re-calculate dynamic columns for the charts
            df["Net_Qty"] = df["Buy_Qty"] - df["Sell_Qty"]
            df["Cum_Net_Qty"] = df["Net_Qty"].cumsum()
            df["Total_Vol"] = df["Buy_Qty"] + df["Sell_Qty"]
            df["Daily_VWAP"] = np.where(df["Total_Vol"] > 0, (df["Buy_Amount"] + df["Sell_Amount"]) / df["Total_Vol"], 0)

            st.write("---")

            # ==========================================
            # CHART 1: DUAL-AXIS BAR + LINE CHART
            # ==========================================
            st.markdown("### 1. Volume & Inventory Accumulation")
            fig1 = make_subplots(specs=[[{"secondary_y": True}]])
            fig1.add_trace(go.Bar(x=df["Date"], y=df["Buy_Qty"], name="Buy Qty", marker_color="rgba(39, 174, 96, 0.7)"), secondary_y=False)
            fig1.add_trace(go.Bar(x=df["Date"], y=-df["Sell_Qty"], name="Sell Qty", marker_color="rgba(231, 76, 60, 0.7)"), secondary_y=False)
            fig1.add_trace(go.Scatter(x=df["Date"], y=df["Cum_Net_Qty"], name="Cum. Inventory", line=dict(color="#2980b9", width=4)), secondary_y=True)
            fig1.update_layout(barmode='relative', height=500, hovermode="x unified", margin=dict(t=30))
            st.plotly_chart(fig1, use_container_width=True)

            # ==========================================
            # CHART 2: HORIZONTAL VOLUME PROFILE
            # ==========================================
            st.write("---")
            st.markdown("### 2. Volume by Price (Support & Resistance Zones)")
            vp_df = df[df["Daily_VWAP"] > 0].copy()
            if not vp_df.empty:
                bins = np.linspace(vp_df["Daily_VWAP"].min(), vp_df["Daily_VWAP"].max(), 15)
                vp_df['Price_Zone'] = pd.cut(vp_df['Daily_VWAP'], bins=bins)
                profile = vp_df.groupby('Price_Zone', observed=False).agg({'Buy_Qty': 'sum', 'Sell_Qty': 'sum'}).reset_index()
                profile['Price_Level'] = profile['Price_Zone'].apply(lambda x: f"Rs {int(x.mid)}" if pd.notnull(x) else "Unknown")
                
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(y=profile['Price_Level'], x=profile['Buy_Qty'], name='Buy Vol', orientation='h', marker_color='rgba(39, 174, 96, 0.8)'))
                fig2.add_trace(go.Bar(y=profile['Price_Level'], x=-profile['Sell_Qty'], name='Sell Vol', orientation='h', marker_color='rgba(231, 76, 60, 0.8)'))
                fig2.update_layout(barmode='relative', yaxis=dict(autorange="reversed"), height=500, hovermode="y unified", margin=dict(t=30))
                st.plotly_chart(fig2, use_container_width=True)

            # ==========================================
            # CHART 3: IMPROVED BUBBLE CHART (Whale Finder)
            # ==========================================
            st.write("---")
            st.markdown("### 3. Whale Action Bubble Chart")
            st.caption("X=Date | Y=Average Price | Size=Total Volume | Color=Net Accumulation (Green) vs Distribution (Red)")
            
            fig3 = px.scatter(
                df, x="Date", y="Daily_VWAP", size=df["Total_Vol"].abs(), color="Net_Qty",
                color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                hover_data=["Buy_Qty", "Sell_Qty"]
            )
            # Improve UI formatting
            fig3.update_traces(marker=dict(line=dict(width=1, color='DarkSlateGrey')), selector=dict(mode='markers'))
            fig3.update_layout(height=500, yaxis_title="Daily VWAP (Rs)", xaxis_title="Date")
            st.plotly_chart(fig3, use_container_width=True)

            # ==========================================
            # CHART 4 & 5: GAUGE AND PIE CHARTS (Side-by-Side)
            # ==========================================
            st.write("---")
            c_gauge, c_pie = st.columns(2)
            
            with c_gauge:
                st.markdown("### 4. Market Sentiment Gauge")
                total_net = df["Net_Qty"].sum()
                max_vol = df["Total_Vol"].sum() if df["Total_Vol"].sum() > 0 else 1
                
                fig4 = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=total_net,
                    title={'text': "Total Net Accumulation"},
                    gauge={
                        'axis': {'range': [-max_vol, max_vol]},
                        'bar': {'color': "rgba(0,0,0,0.5)"},
                        'steps': [
                            {'range': [-max_vol, 0], 'color': "rgba(231, 76, 60, 0.4)"},  # Light Red
                            {'range': [0, max_vol], 'color': "rgba(39, 174, 96, 0.4)"}    # Light Green
                        ],
                    }
                ))
                fig4.update_layout(height=350, margin=dict(t=50, b=0))
                st.plotly_chart(fig4, use_container_width=True)

            with c_pie:
                st.markdown("### 5. Dynamic Breakdown (Pie)")
                pie_type = st.selectbox("Select Metric:", ["Total Buy vs Sell Qty", "Net Accumulation by Month"])
                
                if pie_type == "Total Buy vs Sell Qty":
                    b_sum, s_sum = df["Buy_Qty"].sum(), df["Sell_Qty"].sum()
                    fig5 = px.pie(values=[b_sum, s_sum], names=["Buy Volume", "Sell Volume"], hole=0.4, color_discrete_sequence=["#27ae60", "#e74c3c"])
                else:
                    df_month = df.copy()
                    df_month["Month"] = df_month["Date"].dt.strftime('%b %Y')
                    month_group = df_month[df_month["Net_Qty"] > 0].groupby("Month")["Net_Qty"].sum().reset_index()
                    fig5 = px.pie(month_group, values="Net_Qty", names="Month", hole=0.4, title="Months with Heaviest Buying")
                
                fig5.update_layout(height=350, margin=dict(t=30, b=0))
                st.plotly_chart(fig5, use_container_width=True)

            # ==========================================
            # CHART 6: PRICE VS NET QTY SCATTER PLOT
            # ==========================================
            st.write("---")
            st.markdown("### 6. Trading Behavior (Price vs Net Quantity)")
            st.caption("Are they buying when the price is low (Smart Money) or high (Dumb Money/FOMO)?")
            
            fig6 = px.scatter(
                df, x="Daily_VWAP", y="Net_Qty", 
                color="Net_Qty", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                hover_data=["Date"], trendline="ols"  # Adds a trendline to see the correlation!
            )
            # Add a zero-line to easily separate buys and sells
            fig6.add_hline(y=0, line_width=2, line_dash="dash", line_color="black")
            fig6.update_layout(height=500, xaxis_title="Daily Average Price (VWAP)", yaxis_title="Net Quantity (Buy - Sell)")
            st.plotly_chart(fig6, use_container_width=True)
