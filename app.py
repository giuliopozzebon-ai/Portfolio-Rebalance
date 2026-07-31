import streamlit as st
import pandas as pd
import yfinance as yf

# Configurazione Pagina (Mobile Friendly)
st.set_page_config(
    page_title="Rebalance Tracker",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.title("📈 Asset Allocation Tracker")
st.caption("Visualizza in tempo reale lo scostamento degli ETF dal target allocation.")

# --- 1. FONTE DATI ---
st.subheader("1. Portafoglio e Liquidità")

uploaded_file = st.file_uploader("Carica il tuo file 'portafoglio.xlsx' (Opzionale)", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
else:
    # Dati di default se non viene caricato alcun file
    default_data = {
        "Ticker": ["VWCE.DE", "AGGH.MI", "MEUD.PA"],
        "Nome Asset": ["Vanguard All-World", "iShares Global Aggregate", "Amundi Europe 600"],
        "Quantita": [250, 1800, 120],
        "Target_Pct": [60.0, 30.0, 10.0]
    }
    df = pd.DataFrame(default_data)
    st.info("💡 Stai usando i dati di esempio. Carica il tuo file Excel sopra per personalizzare.")

# Possibilità di modificare la liquidità disponibile
cash_injection = st.number_input("Nuova Liquidità da aggiungere (€)", min_value=0.0, value=1000.0, step=100.0)

# --- 2. RECUPERO PREZZI LIVE ---
@st.cache_data(ttl=300)  # Cache per 5 minuti per evitare troppe richieste
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

# --- 3. CALCOLI E MATEMATICA ---
df['Valore_Attuale'] = df['Quantita'] * df['Prezzo_Live']
valore_totale = df['Valore_Attuale'].sum()
valore_futuro = valore_totale + cash_injection

df['Peso_Attuale_%'] = (df['Valore_Attuale'] / valore_totale * 100) if valore_totale > 0 else 0
df['Scostamento_%'] = df['Peso_Attuale_%'] - df['Target_Pct']  # Negativo = Sottopesato, Positivo = Sovrapesato

# Target in Euro considerando la nuova liquidità
df['Valore_Target_€'] = valore_futuro * (df['Target_Pct'] / 100)
df['Deficit_€'] = df['Valore_Target_€'] - df['Valore_Attuale']

# --- 4. DISPLAY KPI ---
st.divider()
st.subheader("2. Riepilogo Portafoglio")

col1, col2 = st.columns(2)
col1.metric("Valore Portafoglio", f"€ {valore_totale:,.2f}")
col2.metric("Valore Post-Versamento", f"€ {valore_futuro:,.2f}")

# --- 5. TABELLA SCOSTAMENTI ---
st.subheader("3. Scostamento dal Target Allocation")

display_df = df.copy()

display_df['Prezzo Live'] = display_df['Prezzo_Live'].apply(lambda x: f"€ {x:,.2f}")
display_df['Valore (€)'] = display_df['Valore_Attuale'].apply(lambda x: f"€ {x:,.2f}")
display_df['Peso Att.'] = display_df['Peso_Attuale_%'].apply(lambda x: f"{x:.2f}%")
display_df['Target'] = display_df['Target_Pct'].apply(lambda x: f"{x:.1f}%")
display_df['Delta %'] = display_df['Scostamento_%'].apply(lambda x: f"{x:+.2f}%")
display_df['Deficit / Surplus (€)'] = display_df['Deficit_€'].apply(lambda x: f"€ {x:,.2f}" if x > 0 else f"- € {abs(x):,.2f}")

# Funzione per evidenziare chi è sottopesato (rosso) e sovrapesato (verde)
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

# Gestione della compatibilità con nuove e vecchie versioni di Pandas
styler = display_df[['Ticker', 'Nome Asset', 'Prezzo Live', 'Peso Att.', 'Target', 'Delta %', 'Deficit / Surplus (€)']].style

if hasattr(styler, 'map'):
    styled_df = styler.map(color_delta, subset=['Delta %'])
else:
    styled_df = styler.applymap(color_delta, subset=['Delta %'])

st.dataframe(styled_df, use_container_width=True, hide_index=True)

# --- 6. RACCOMANDAZIONE SOTTOPESATO ---
st.divider()
st.subheader("🎯 Su cosa versare la liquidità?")

max_deficit_row = df.loc[df['Deficit_€'].idxmax()]

if max_deficit_row['Deficit_€'] > 0:
    st.success(
        f"L'asset più distante (sottopesato) dal target è **{max_deficit_row['Ticker']}** ({max_deficit_row['Nome Asset']}).\n\n"
        f"• **Scostamento attuale:** `{max_deficit_row['Scostamento_%']:+.2f}%` dal target\n\n"
        f"• **Mancanti al target:** `€ {max_deficit_row['Deficit_€']:,.2f}`"
    )
else:
    st.info("Tutti gli asset sono perfettamente bilanciati o sopra il target.")

st.caption("Pulsante di aggiornamento manuale dati:")
if st.button("🔄 Ricarica Prezzi Live"):
    st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()
