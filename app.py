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
            "Is_Primary": [False, True, True, True, True],
            "Prezzo_Fisso": [None, None, None, None, 20000.0]
        }
        df = pd.DataFrame(default_data)

# --- DATA SANITIZATION ---
df.columns = df.columns.astype(str).str.strip()

if "Categoria" not in df.columns:
    df["Categoria"] = df["Nome Asset"]

if "Is_Primary" not in df.columns:
    df["Is_Primary"] = True
else:
    df["Is_Primary"] = (
        df["Is_Primary"]
        .astype(str)
        .str.strip()
        .str.upper()
        .map({"TRUE": True, "1": True, "FALSE": False, "0": False})
        .fillna(True)
    )

if "Prezzo_Fisso" not in df.columns:
    df["Prezzo_Fisso"] = 0.0
else:
    df["Prezzo_Fisso"] = pd.to_numeric(df["Prezzo_Fisso"], errors="coerce").fillna(0.0)

# --- LIVE PRICES & MANUAL PRICE OVERRIDE ---
@st.cache_data(ttl=300)
def get_live_prices(tickers):
    prices = {}
    for ticker in tickers:
        if not ticker or str(ticker).upper() in ["MANUAL", "NONE", "NAN", "CASH"]:
            prices[ticker] = 0.0
            continue
        try:
            t = yf.Ticker(str(ticker))
            price = t.fast_info.get('lastPrice', None)
            if price is None or pd.isna(price):
                hist = t.history(period="1d")
                price = hist['Close'].iloc[-1] if not hist.empty else 0.0
            prices[ticker] = float(price)
        except Exception:
            prices[ticker] = 0.0
    return prices

with st.spinner("Fetching live market prices..."):
    tickers = df['Ticker'].tolist()
    live_prices = get_live_prices(tickers)

# Determine final unit price
df['Prezzo_Live_YF'] = df['Ticker'].map(live_prices).fillna(0.0)
df['Prezzo_Finale'] = df.apply(
    lambda row: row['Prezzo_Fisso'] if row['Prezzo_Fisso'] > 0 else row['Prezzo_Live_YF'], 
    axis=1
)

df['Valore_Attuale'] = df['Quantita'] * df['Prezzo_Finale']

# --- CATEGORY AGGREGATION & SORTING ---
cat_df = df.groupby('Categoria', as_index=False).agg({
    'Valore_Attuale': 'sum',
    'Target_Pct': 'sum'
})

valore_totale = cat_df['Valore_Attuale'].sum()

cat_df['Peso_Attuale_%'] = (cat_df['Valore_Attuale'] / valore_totale * 100) if valore_totale > 0 else 0
cat_df['Scostamento_%'] = cat_df['Peso_Attuale_%'] - cat_df['Target_Pct']
cat_df['Delta_Euro'] = valore_totale * (cat_df['Scostamento_%'] / 100)

# Calcolo Variazione Relativa % al Target
cat_df['Variazione_Relativa_%'] = cat_df.apply(
    lambda r: (r['Scostamento_%'] / r['Target_Pct'] * 100) if r['Target_Pct'] > 0 else 0.0, 
    axis=1
)

# Ordina in ordine crescente per Delta % (Scostamento_%)
cat_df = cat_df.sort_values(by='Scostamento_%', ascending=True).reset_index(drop=True)

# --- DISPLAY KPI ---
st.divider()
st.subheader("Portfolio Summary")

col1, col2 = st.columns(2)
col1.metric("Current Portfolio Value", f"€ {valore_totale:,.2f}")

if not cat_df.empty:
    most_underweight = cat_df.iloc[0]
    col2.metric(
        "Più Sottopesato", 
        f"{most_underweight['Categoria']}", 
        f"{most_underweight['Scostamento_%']:+.2f}%"
    )

# --- CATEGORY BREAKDOWN TABLE ---
st.subheader("Asset Class Allocation")

display_cat = cat_df.copy()
display_cat['Valore (€)'] = display_cat['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
display_cat['Peso Att.'] = display_cat['Peso_Attuale_%'].apply(lambda x: f"{x:.2f}%")
display_cat['Delta %'] = display_cat['Scostamento_%'].apply(lambda x: f"{x:+.2f}%")
display_cat['Var. Rel. %'] = display_cat['Variazione_Relativa_%'].apply(lambda x: f"{x:+.2f}%")
display_cat['Delta (€)'] = display_cat['Delta_Euro'].apply(
    lambda x: f"+ € {x:,.2f}" if x > 0 else (f"- € {abs(x):,.2f}" if x < 0 else "€ 0.00")
)

# Funzione per evidenziare Delta %
def color_delta(val):
    try:
        num = float(str(val).replace('%', '').replace('+', '').strip())
        if num < -1.0:
            return 'background-color: #fce8e6; color: #a50e0e; font-weight: bold;'
        elif num > 1.0:
            return 'background-color: #e6f4ea; color: #137333;'
    except:
        pass
    return ''

# Funzione per evidenziare Var. Rel. % (+10% verde, -10% rosso)
def color_var_rel(val):
    try:
        num = float(str(val).replace('%', '').replace('+', '').strip())
        if num < -10.0:
            return 'background-color: #fce8e6; color: #a50e0e; font-weight: bold;'
        elif num > 10.0:
            return 'background-color: #e6f4ea; color: #137333; font-weight: bold;'
    except:
        pass
    return ''

styler = display_cat[['Categoria', 'Valore (€)', 'Peso Att.', 'Delta %', 'Var. Rel. %', 'Delta (€)']].style

if hasattr(styler, 'map'):
    styled_cat = styler.map(color_delta, subset=['Delta %'])
    styled_cat = styled_cat.map(color_var_rel, subset=['Var. Rel. %'])
else:
    styled_cat = styler.applymap(color_delta, subset=['Delta %'])
    styled_cat = styled_cat.applymap(color_var_rel, subset=['Var. Rel. %'])

# Calcolo dinamico dell'altezza per adattare la tabella ed evitare la barra di scorrimento
table_height = (len(display_cat) + 1) * 35 + 10

st.dataframe(styled_cat, use_container_width=True, hide_index=True, height=table_height)


# --- INTEGRATING GEMINI AI COPILOT ---
def call_gemini_copilot(summary_payload, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
    Sei un assistente analista di portafoglio professionale. Analizza i dati aggiornati del portafoglio di investimento ed elabora un report di sintesi esecutivo e diretto.

    DATI PORTAFOGLIO COMPLETAMENTE AGGIORNATI:
    {json.dumps(summary_payload, indent=2, ensure_ascii=False)}

    ISTRUZIONI DI STRUTTURA:
    Organizza la risposta in 3 sezioni chiare:
    1. **Quadro Asset Allocation**: Sintesi dello stato attuale del portafoglio ed eventuali squilibri principali.
    2. **Analisi Scostamenti e Rischio**: Valuta l'impatto dei pesi correnti (sovrappesi/sottopesi sia in % assoluta sia in Delta Euro).
    3. **Suggerimenti di Ribilanciamento**: Priorità operative dettagliate per i prossimi acquisti o riallineamenti verso i pesi target.
    """

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text']
    else:
        return f"❌ Errore API Gemini (Codice {response.status_code}): {response.text}"

st.divider()
st.subheader("💡 AI Copilot Portfolio Brief")

if st.button("✨ Genera Analisi AI Ribilanciamento", type="primary"):
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    
    if not api_key:
        st.error("⚠️ Nessuna `GEMINI_API_KEY` trovata nei Secrets di Streamlit. Aggiungila per abilitare il Copilot.")
    else:
        with st.spinner("Elaborazione analisi esecutiva in corso..."):
            # Costruzione payload dinamico estratto da cat_df
            portfolio_summary = {
                "valore_totale_eur": round(valore_totale, 2),
                "asset_classes": []
            }
            for idx, row in cat_df.iterrows():
                portfolio_summary["asset_classes"].append({
                    "categoria": row['Categoria'],
                    "valore_eur": round(row['Valore_Attuale'], 2),
                    "peso_attuale_pct": round(row['Peso_Attuale_%'], 2),
                    "target_pct": round(row['Target_Pct'], 2),
                    "scostamento_pct": round(row['Scostamento_%'], 2),
                    "delta_euro": round(row['Delta_Euro'], 2),
                    "var_relativa_pct": round(row['Variazione_Relativa_%'], 2)
                })

            ai_response = call_gemini_copilot(portfolio_summary, api_key)
            st.markdown(ai_response)


# --- DETAILED POSITIONS EXPANDER ---
st.divider()
with st.expander("🔍 Show Detailed Holdings"):
    df_detail = df[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Prezzo_Finale', 'Valore_Attuale', 'Is_Primary']].copy()
    df_detail['Unit Price'] = df_detail['Prezzo_Finale'].apply(lambda x: f"€ {x:,.2f}")
    df_detail['Total Value'] = df_detail['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
    st.dataframe(df_detail[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Unit Price', 'Total Value', 'Is_Primary']], hide_index=True)

st.caption("Manual Data Refresh:")
if st.button("🔄 Refresh Live Prices"):
    st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()
