import streamlit as st
import sqlite3
import pandas as pd
import json
import os

st.set_page_config(page_title="FatQul AI Trader", layout="wide")

st.title("FatQul AI Trader Dashboard")
st.subheader("Freqtrade Hybrid AI Trading System - Indodax Spot")

# Connect to Freqtrade SQLite DB
DB_PATH = "/app/user_data/tradesv3.sqlite"
CONFIG_PATH = "/app/user_data/config.json"

try:
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        
        # Open Trades
        st.header("🟢 Active Positions")
        trades_df = pd.read_sql_query("SELECT id, pair, is_open, amount, stake_amount, open_rate, open_date FROM trades WHERE is_open=1", conn)
        
        if not trades_df.empty:
            st.dataframe(trades_df, use_container_width=True)
        else:
            st.info("No active open positions.")
            
        # Closed Trades
        st.header("📓 Trade History")
        history_df = pd.read_sql_query("SELECT id, pair, close_profit_abs, close_profit, open_date, close_date FROM trades WHERE is_open=0 ORDER BY id DESC LIMIT 10", conn)
        if not history_df.empty:
            st.dataframe(history_df, use_container_width=True)
        else:
            st.info("No closed trades yet.")
            
        conn.close()
    else:
        st.warning("Database not found. Freqtrade might still be initializing.")
except Exception as e:
    st.error(f"Error connecting to database: {e}")

# System Health
st.sidebar.header("System Health")
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    st.sidebar.success(f"Trading Mode: {config.get('trading_mode', 'Unknown').upper()}")
    st.sidebar.success(f"Exchange: {config.get('exchange', {}).get('name', 'Unknown').upper()}")
    st.sidebar.info(f"Dry Run: {config.get('dry_run', True)}")
else:
    st.sidebar.warning("Config not found")
