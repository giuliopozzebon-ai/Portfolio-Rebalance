import io
import json
import altair as alt
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# --- CONTROLLO ACCESSO CON PASSWORD ---
def check_password():
    if "PASSWORD" not in st.secrets:
        return True

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

if not check_password():
    st.stop()
# -------------------------------------

st.set_page_config(
    page_title="Rebalance Tracker",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.title("📈 Asset Allocation Tracker")
st.caption("Asset allocation tracking con supporto per titoli Live & Manuali.")

# --- CARICAMENTO DATI ---
if "PORTFOLIO" in st.secrets:
    csv_data = st.secrets["PORTFOLIO"]
    df = pd.read_csv(io.StringIO(csv_data))
else:
    uploaded_file = st.file_uploader("Upload an Excel file (Optional)", type=["xlsx"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
    else:
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
        if not ticker or str(ticker).upper() in ["MANUAL", "NONE", "NAN", "CASH", "BOND"]:
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

# --- CALCOLO PERFORMANCE 1 ANNO PER TICKER ---
@st.cache_data(ttl=3600)
def get_ticker_1y_performance(tickers):
    perf_dict = {}
    for ticker in tickers:
        t = str(ticker).strip()
        if not t or t.upper() in ["MANUAL", "NONE", "NAN", "CASH", "BOND"] or "BOND" in t.upper():
            perf_dict[ticker] = None
            continue
        try:
            hist = yf.Ticker(t).history(period="1y")
            if not hist.empty and len(hist) > 1:
                p_start = hist['Close'].iloc[0]
                p_end = hist['Close'].iloc[-1]
                perf_dict[ticker] = ((p_end - p_start) / p_start) * 100
            else:
                perf_dict[ticker] = None
        except Exception:
            perf_dict[ticker] = None
    return perf_dict

# --- 1-YEAR NORMALIZED TREND CHART (BASE 100 - WEEKLY FREQUENCY) ---
@st.cache_data(ttl=3600)
def get_historical_normalized_trends(df_assets):
    series_dict = {}
    
    for _, row in df_assets.iterrows():
        t = str(row['Ticker']).strip()
        cat = str(row['Categoria']).strip().upper()
        
        if (not t or 
            t.upper() in ["MANUAL", "NONE", "NAN", "CASH", "BOND"] or 
            "BOND" in t.upper() or 
            "BOND" in cat or 
            row['Prezzo_Fisso'] > 0):
            continue
            
        label = f"{row['Nome Asset']} ({t})"
        
        try:
            hist = yf.Ticker(t).history(period="1y")
            if not hist.empty and 'Close' in hist.columns:
                s = hist['Close'].dropna()
                s_weekly = s.resample('W').last().dropna()
                if not s_weekly.empty and s_weekly.iloc[0] > 0:
                    s_norm = (s_weekly / s_weekly.iloc[0]) * 100
                    s_norm.index = s_norm.index.tz_localize(None)
                    series_dict[label] = s_norm
        except Exception:
            pass
                
    if not series_dict:
        return pd.DataFrame()
        
    hist_df = pd.DataFrame(series_dict)
    return hist_df.ffill().bfill()

with st.spinner("Aggiornamento prezzi di mercato..."):
    tickers = df['Ticker'].tolist()
    live_prices = get_live_prices(tickers)
    perf_1y_dict = get_ticker_1y_performance(tickers)

# Prezzi e Valore
df['Prezzo_Live_YF'] = df['Ticker'].map(live_prices).fillna(0.0)
df['Prezzo_Finale'] = df.apply(
    lambda row: row['Prezzo_Fisso'] if row['Prezzo_Fisso'] > 0 else row['Prezzo_Live_YF'], 
    axis=1
)
df['Perf_1Y_%'] = df['Ticker'].map(perf_1y_dict)
df['Valore_Attuale'] = df['Quantita'] * df['Prezzo_Finale']

# --- CATEGORY AGGREGATION & SORTING ---
cat_df = df.groupby('Categoria', as_index=False).agg({
    'Valore_Attuale': 'sum',
    'Target_Pct': 'sum'
})

valore_totale = cat_df['Valore_Attuale'].sum()

def calc_cat_perf(cat_name):
    cat_rows = df[df['Categoria'] == cat_name]
    valid_rows = cat_rows.dropna(subset=['Perf_1Y_%'])
    if valid_rows.empty or valid_rows['Valore_Attuale'].sum() == 0:
        return None
    return (valid_rows['Perf_1Y_%'] * valid_rows['Valore_Attuale']).sum() / valid_rows['Valore_Attuale'].sum()

cat_df['Perf_1Y_%'] = cat_df['Categoria'].apply(calc_cat_perf)
cat_df['Peso_Attuale_%'] = (cat_df['Valore_Attuale'] / valore_totale * 100) if valore_totale > 0 else 0
cat_df['Scostamento_%'] = cat_df['Peso_Attuale_%'] - cat_df['Target_Pct']
cat_df['Delta_Euro'] = valore_totale * (cat_df['Scostamento_%'] / 100)
cat_df['Variazione_Relativa_%'] = cat_df.apply(
    lambda r: (r['Scostamento_%'] / r['Target_Pct'] * 100) if r['Target_Pct'] > 0 else 0.0, 
    axis=1
)

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

# --- CATEGORY BREAKDOWN TABLE MAIN ---
st.subheader("Asset Class Allocation")

display_cat = cat_df.copy()
display_cat['Valore (€)'] = display_cat['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
display_cat['Peso Att.'] = display_cat['Peso_Attuale_%'].apply(lambda x: f"{x:.2f}%")
display_cat['Perf. 12M %'] = display_cat['Perf_1Y_%'].apply(
    lambda x: f"{x:+.2f}%" if pd.notna(x) and x is not None else "N/D"
)
display_cat['Delta %'] = display_cat['Scostamento_%'].apply(lambda x: f"{x:+.2f}%")
display_cat['Var. Rel. %'] = display_cat['Variazione_Relativa_%'].apply(lambda x: f"{x:+.2f}%")
display_cat['Delta (€)'] = display_cat['Delta_Euro'].apply(
    lambda x: f"+ € {x:,.2f}" if x > 0 else (f"- € {abs(x):,.2f}" if x < 0 else "€ 0.00")
)

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

styler = display_cat[['Categoria', 'Valore (€)', 'Peso Att.', 'Perf. 12M %', 'Delta %', 'Var. Rel. %', 'Delta (€)']].style

if hasattr(styler, 'map'):
    styled_cat = styler.map(color_delta, subset=['Delta %'])
    styled_cat = styled_cat.map(color_var_rel, subset=['Var. Rel. %'])
else:
    styled_cat = styler.applymap(color_delta, subset=['Delta %'])
    styled_cat = styled_cat.applymap(color_var_rel, subset=['Var. Rel. %'])

table_height = (len(display_cat) + 1) * 35 + 10
st.dataframe(styled_cat, use_container_width=True, hide_index=True, height=table_height)

# --- 1-YEAR NORMALIZED TREND CHART WITH TICKER SELECTOR ---
st.subheader("📊 1-Year Performance Comparison (Base 100 - Settimanale)")
st.caption("Performance relativa degli ETF/titoli a frequenza settimanale (Base 100 = 1 anno fa).")

with st.spinner("Caricamento performance normalizzata a 1 anno..."):
    hist_chart_df = get_historical_normalized_trends(df)

if not hist_chart_df.empty:
    available_assets = list(hist_chart_df.columns)
    
    selected_assets = st.multiselect(
        "Seleziona o deseleziona i titoli da visualizzare:",
        options=available_assets,
        default=available_assets
    )
    
    if selected_assets:
        df_chart = hist_chart_df[selected_assets].reset_index()
        date_col = df_chart.columns[0]
        df_melted = df_chart.melt(id_vars=[date_col], var_name='Asset', value_name='Valore')

        chart = (
            alt.Chart(df_melted)
            .mark_line()  # Linee senza pallini
            .encode(
                x=alt.X(f'{date_col}:T', title='Data'),
                y=alt.Y('Valore:Q', title='Performance (Base 100)', scale=alt.Scale(zero=False)),
                color='Asset:N',
                tooltip=[
                    alt.Tooltip(f'{date_col}:T', title='Data'),
                    'Asset:N',
                    alt.Tooltip('Valore:Q', format='.2f', title='Base 100')
                ]
            )
            .configure_legend(disable=True)
            .properties(height=500)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("Seleziona almeno un titolo dal menu a tendina per mostrare il grafico.")
else:
    st.info("Dati storici di prezzo non disponibili al momento.")

# --- GEMINI AI COPILOT ---
def call_gemini_copilot(summary_payload, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
    
    prompt = f"""
    Sei un assistente ed esecutivo di portafoglio d'investimento. Analizza i dati del portafoglio calcolati in tempo reale ed elabora un breve report di sintesi esecutivo in italiano.

    DATI DI PORTAFOGLIO AGGIORNATI:
    {json.dumps(summary_payload, indent=2, ensure_ascii=False)}

    ISTRUZIONI DI STRUTTURA:
    Organizza la risposta in 3 paragrafi concisi:
    1. **Sentiment di mercato**: Fammi un'analisi di mercato sintentica ad oggi con il sentiment di mercato per ciascun asset class, non basato sui pesi del mio portafoglio, ma in generale
    2. **News**: dammi le news più importanti che possono impattare il mio portafoglio
    3. **Suggerimenti tattici**: dammi 2-3 suggerimenti tattici che possono essere utili, legati ai pesi attuali del mio portafoglio, ma senza porre il focus sugli scostamenti attuali che sono già evidenti
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
        st.error("⚠️ Nessuna `GEMINI_API_KEY` trovata nei Secrets di Streamlit.")
    else:
        with st.spinner("Elaborazione analisi di portafoglio con Gemini..."):
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
    df_detail = df[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Prezzo_Finale', 'Valore_Attuale', 'Perf_1Y_%', 'Is_Primary']].copy()
    df_detail['Unit Price'] = df_detail['Prezzo_Finale'].apply(lambda x: f"€ {x:,.2f}")
    df_detail['Total Value'] = df_detail['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
    df_detail['Perf. 12M %'] = df_detail['Perf_1Y_%'].apply(
        lambda x: f"{x:+.2f}%" if pd.notna(x) and x is not None else "N/D"
    )
    
    st.dataframe(
        df_detail[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Unit Price', 'Total Value', 'Perf. 12M %', 'Is_Primary']], 
        hide_index=True
    )

st.caption("Manual Data Refresh:")
if st.button("🔄 Refresh Live Prices"):
    st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()
