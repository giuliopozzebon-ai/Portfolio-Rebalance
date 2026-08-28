Skip to content
giuliopozzebon-ai
Portfolio-Rebalance
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Security and quality
Insights
Settings
Files
Go to file
t
T
app.py
requirements.txt
Portfolio-Rebalance
/
app.py
in
main

Edit

Preview
Indent mode

Spaces
Indent size

4
Line wrap mode

No wrap
Editing app.py file contents
  1
  2
  3
  4
  5
  6
  7
  8
  9
 10
 11
 12
 13
 14
 15
 16
 17
 18
 19
 20
 21
 22
 23
 24
 25
 26
 27
 28
 29
 30
 31
 32
 33
 34
 35
 36
 37
 38
 39
 40
 41
 42
 43
 44
 45
 46
 47
 48
 49
 50
 51
 52
 53
 54
 55
 56
 57
 58
 59
 60
 61
 62
import io
import json
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# --- CONTROLLO ACCESSO CON PASSWORD ---
def check_password():
    if "PASSWORD" not in st.secrets:
        return True  # Se non hai impostato nessuna password nei Secrets, l'app si apre normalmente

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Accesso Riservato")
        user_password = st.text_input("Inserisci la password per accedere al portafoglio:", type="password")
        
        if st.button("Accedi"):
            if user_password == st.secrets["PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Password errata!")
        return False
        
    return True

# Blocca l'esecuzione dell'app finché la password non è corretta
if not check_password():
    st.stop()
# -------------------------------------


# Page Configuration
st.set_page_config(
    page_title="Rebalance Tracker",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.title("📈 Asset Allocation Tracker")
st.caption("Asset allocation tracking with support for manual & live assets.")

# --- CARICAMENTO DATI (IN BACKGROUND SILENZIOSO) ---
if "PORTFOLIO" in st.secrets:
    csv_data = st.secrets["PORTFOLIO"]
    df = pd.read_csv(io.StringIO(csv_data))
else:
    uploaded_file = st.file_uploader("Upload an Excel file (Optional)", type=["xlsx"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
    else:
        # Default fallback sample data
        default_data = {
            "Ticker": ["BITC.MI", "21BC.DE", "VWCE.DE", "AGGH.MI", "MANUAL"],
            "Nome Asset": ["WisdomTree Bitcoin", "21Shares Bitcoin", "Vanguard All-World", "iShares Global Aggregate", "Unlisted Bond"],
            "Categoria": ["Bitcoin", "Bitcoin", "Azionario Globale", "Obbligazionario", "Obbligazionario"],
            "Quantita": [30, 50, 250, 1800, 1],
            "Target_Pct": [5.0, 5.0, 50.0, 20.0, 20.0],
Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
