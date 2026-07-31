import io
import pandas as pd
import streamlit as st
import yfinance as yf

# Configurazione Pagina
st.set_page_config(
    page_title="Rebalance Tracker",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.title("📈 Asset Allocation Tracker")
st.caption("Monitoraggio dello scostamento per Categoria / Asset Class.")

# --- 1. FONTE DATI PRIVATA ---
st.subheader("1. Portafoglio e Liquidità")

if "PORTFOLIO" in st.secrets:
    csv_data = st.secrets["PORTFOLIO"]
    df = pd.read_csv(io.StringIO(csv_data))
    # Assicuriamoci che Is_Primary sia booleano
    df['Is_Primary'] = df['Is_Primary'].astype(str).str.upper().map({'TRUE': True, '1': True, 'FALSE': False, '0': False}).fillna(True)
    st.success("🔒 Dati portafoglio caricati dai Secrets privati.")
else:
    uploaded_file = st.file_uploader("Carica un file Excel (Opzionale)", type=["xlsx"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        if 'Is_Primary' not in df.columns:
            df['Is_Primary'] = True
    else:
        # Dati di esempio con 2 ETF Bitcoin
        default_data = {
            "Ticker": ["BITC.MI", "21BC.DE", "VWCE.DE", "AGGH.MI"],
            "Nome Asset": ["WisdomTree Bitcoin", "21Shares Bitcoin", "Vanguard All-World", "iShares Global Aggregate"],
            "Categoria": ["Bitcoin", "Bitcoin", "Azionario Globale", "Obbligazionario"],
            "Quantita": [30, 50, 250, 1800],
            "Target_Pct": [5.0, 5.0, 65.0, 30.0],
            "Is_Primary": [False, True, True, True]
        }
        df = pd.DataFrame(default_data)
        st.info("💡 Stai usando i dati di esempio. Inserisci i Secrets o carica un file Excel.")

cash_injection = st.number_input("Nuova Liquidità da aggiungere (€)", min_value=0.0, value=1000.0, step=100.0)

# --- 2. RECUPERO PREZZI LIVE ---
@st.cache_data(ttl=300)
def get_live_prices(tickers):
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            price = t.fast_info.get('lastPrice', None)
            if price is None or pd.isna(price):
                hist = t.history(period="1d")
                price = hist['Close'].iloc[-1] if not hist.empty else 0.0
            prices[ticker] = float(price)
        except Exception:
            prices[ticker] = 0.0
    return prices

with st.spinner("Aggiornamento prezzi di mercato in tempo reale..."):
    tickers = df['Ticker'].tolist()
    live_prices = get_live_prices(tickers)

df['Prezzo_Live'] = df['Ticker'].map(live_prices)
df['Valore_Attuale'] = df['Quantita'] * df['Prezzo_Live']

# --- 3. CALCOLO AGGREGATO PER CATEGORIA ---
# Raggruppiamo i valori per Categoria
cat_df = df.groupby('Categoria', as_index=False).agg({
    'Valore_Attuale': 'sum',
    'Target_Pct': 'first'  # Prende il target della categoria
})

valore_totale = cat_df['Valore_Attuale'].sum()
valore_futuro = valore_totale + cash_injection

cat_df['Peso_Attuale_%'] = (cat_df['Valore_Attuale'] / valore_totale * 100) if valore_totale > 0 else 0
cat_df['Scostamento_%'] = cat_df['Peso_Attuale_%'] - cat_df['Target_Pct']
cat_df['Valore_Target_€'] = valore_futuro * (cat_df['Target_Pct'] / 100)
cat_df['Deficit_€'] = cat_df['Valore_Target_€'] - cat_df['Valore_Attuale']

# --- 4. DISPLAY KPI ---
st.divider()
st.subheader("2. Riepilogo Portafoglio")

col1, col2 = st.columns(2)
col1.metric("Valore Portafoglio", f"€ {valore_totale:,.2f}")
col2.metric("Valore Post-Versamento", f"€ {valore_futuro:,.2f}")

# --- 5. TABELLA SCOSTAMENTI PER CATEGORIA ---
st.subheader("3. Scostamento per Categoria / Asset Class")

display_cat = cat_df.copy()
display_cat['Valore (€)'] = display_cat['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
display_cat['Peso Att.'] = display_cat['Peso_Attuale_%'].apply(lambda x: f"{x:.2f}%")
display_cat['Target'] = display_cat['Target_Pct'].apply(lambda x: f"{x:.1f}%")
display_cat['Delta %'] = display_cat['Scostamento_%'].apply(lambda x: f"{x:+.2f}%")
display_cat['Deficit / Surplus (€)'] = display_cat['Deficit_€'].apply(lambda x: f"€ {x:,.2f}" if x > 0 else f"- € {abs(x):,.2f}")

def color_delta(val):
    try:
        num = float(str(val).replace('%', ''))
        if num < -1.0:
            return 'background-color: #fce8e6; color: #a50e0e; font-weight: bold;'
        elif num > 1.0:
            return 'background-color: #e6f4ea; color: #137333;'
    except:
        pass
    return ''

styler = display_cat[['Categoria', 'Valore (€)', 'Peso Att.', 'Target', 'Delta %', 'Deficit / Surplus (€)']].style

if hasattr(styler, 'map'):
    styled_cat = styler.map(color_delta, subset=['Delta %'])
else:
    styled_cat = styler.applymap(color_delta, subset=['Delta %'])

st.dataframe(styled_cat, use_container_width=True, hide_index=True)

# --- 6. RACCOMANDAZIONE D'ACQUISTO ---
st.divider()
st.subheader("🎯 Su quale ETF versare la liquidità?")

max_deficit_cat = cat_df.loc[cat_df['Deficit_€'].idxmax()]

if max_deficit_cat['Deficit_€'] > 0:
    target_category = max_deficit_cat['Categoria']
    
    # Identifichiamo l'ETF primario per quella categoria
    primary_etf = df[(df['Categoria'] == target_category) & (df['Is_Primary'] == True)]
    
    if primary_etf.empty:
        # Fallback se nessun ETF è segnato come primario
        primary_etf = df[df['Categoria'] == target_category]
        
    recommended_ticker = primary_etf.iloc[0]['Ticker']
    recommended_name = primary_etf.iloc[0]['Nome Asset']
    
    st.success(
        f"La categoria più sottopesata è **{target_category}**.\n\n"
        f"• **Scostamento Categoria:** `{max_deficit_cat['Scostamento_%']:+.2f}%` dal target\n\n"
        f"• **Mancanti al target di Categoria:** `€ {max_deficit_cat['Deficit_€']:,.2f}`\n\n"
        f"👉 **ETF Consigliato per l'acquisto:** `{recommended_ticker}` ({recommended_name})"
    )
else:
    st.info("Tutte le categorie sono perfettamente bilanciate o sopra il target.")

# --- 7. DETTAGLIO POSIZIONI SINGOLE ---
with st.expander("🔍 Mostra Dettaglio Singoli Titoli held"):
    df_detail = df[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Prezzo_Live', 'Valore_Attuale', 'Is_Primary']].copy()
    df_detail['Prezzo Live'] = df_detail['Prezzo_Live'].apply(lambda x: f"€ {x:,.2f}")
    df_detail['Valore Totale'] = df_detail['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
    st.dataframe(df_detail[['Ticker', 'Nome Asset', 'Categoria', 'Quantita', 'Prezzo Live', 'Valore Totale', 'Is_Primary']], hide_index=True)

st.caption("Pulsante di aggiornamento manuale dati:")
if st.button("🔄 Ricarica Prezzi Live"):
    st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()
