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
            "Ticker": ["BITC.MI", "21BC.DE", "SWDA.MI", "EXUS.MI", "IWQU.MI", "IWMO.MI", "IWVL.MI", "AVWS.DE", "EIMI.MI", "AGGH.MI", "MANUAL"],
            "Nome Asset": ["WisdomTree Bitcoin", "21Shares Bitcoin", "iShares Core MSCI World", "Amundi MSCI World Ex-USA", "iShares MSCI World Quality", "iShares MSCI World Momentum", "iShares MSCI World Value", "Avantis Small Cap Value", "iShares MSCI EM IMI", "iShares Global Aggregate", "Unlisted Bond"],
            "Categoria": ["Bitcoin", "Bitcoin", "Azioni Globali", "Azioni Ex-USA", "Azioni Quality", "Azioni Momentum", "Azioni Value", "Azioni Small Cap", "Azioni Emergenti", "Obbligazionario", "Obbligazionario"],
            "Quantita": [30, 50, 200, 150, 100, 100, 100, 100, 400, 1800, 1],
            "Target_Pct": [5.0, 5.0, 25.0, 15.0, 10.0, 10.0, 10.0, 5.0, 5.0, 5.0, 5.0],
            "Is_Primary": [False, True, True, True, True, True, True, True, True, True, True],
            "Prezzo_Fisso": [None, None, None, None, None, None, None, None, None, None, 20000.0]
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

# --- CALCOLO PERFORMANCE 1 ANNO PER TICKER ---
@st.cache_data(ttl=3600)
def get_ticker_1y_performance(tickers):
    perf_dict = {}
    for ticker in tickers:
        t = str(ticker).strip()
        if not t or t.upper() in ["MANUAL", "NONE", "NAN", "CASH"]:
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

# --- MAPPATURA ESPOSIZIONE GEOGRAFICA E PAESI SPECIFICI ---
@st.cache_data(ttl=30 * 86400)
def get_etf_geographic_exposure(ticker_str, asset_name, category_name):
    t = str(ticker_str).upper().strip()
    cat = str(category_name).upper().strip()
    name = str(asset_name).upper().strip()

    # 1. Esclusione asset non azionari
    non_equity_keywords = ["OBBLIGAZIONARIO", "BOND", "BITCOIN", "CRYPTO", "LIQUIDITA", "CASH", "FUTURES", "COMMODITY", "GOLD", "ORO"]
    if any(k in cat for k in non_equity_keywords):
        return {"Is_Equity": False}

    # 2. Verifica se è azionario
    equity_keywords = [
        "AZION", "AZIONI", "AZIONARIO", "EQUITY", "STOCK", "STOXX", "MSCI",
        "EMERGENTI", "EMERGING", "WORLD", "S&P", "NASDAQ", "SMALL CAP", "VALUE",
        "QUALITY", "MOMENTUM", "FACTOR", "GLOBAL", "USA", "EXUS", "EX-USA", "EUROPE", "EUROPA"
    ]
    is_eq = any(k in cat or k in name or k in t for k in equity_keywords)
    if not is_eq:
        return {"Is_Equity": False}

    # Struttura dati per i paesi specifici
    countries = {
        "Stati Uniti": 0.0,
        "Giappone": 0.0,
        "Regno Unito": 0.0,
        "Francia": 0.0,
        "Germania": 0.0,
        "Svizzera": 0.0,
        "Canada": 0.0,
        "Cina": 0.0,
        "India": 0.0,
        "Taiwan": 0.0,
        "Corea del Sud": 0.0,
        "Altri Paesi": 0.0
    }

    # 3. Mappatura specifica per tipologia di benchmark/ticker/fattore

    # --- WORLD EX-USA (es. EXUS) ---
    if "EXUS" in t or "EX-USA" in name or "EX USA" in name or "EX-USA" in t:
        usa, europa, emergenti, altro = 0.0, 48.0, 0.0, 52.0
        countries.update({
            "Stati Uniti": 0.0, "Giappone": 21.5, "Regno Unito": 13.0,
            "Francia": 10.0, "Svizzera": 9.5, "Germania": 8.0,
            "Canada": 8.0, "Altri Paesi": 30.0
        })

    # --- USA ONLY (S&P 500, Nasdaq, MSCI USA) ---
    elif "S&P" in name or "NASDAQ" in name or ("USA" in name and "EX" not in name) or ("USA" in t and "EX" not in t) or "AZIONI USA" in cat:
        usa, europa, emergenti, altro = 100.0, 0.0, 0.0, 0.0
        countries["Stati Uniti"] = 100.0

    # --- QUALITY FACTOR (es. IWQU, XDEQ) ---
    elif "QUALITY" in name or "IWQU" in t or "QUAL" in name:
        usa, europa, emergenti, altro = 71.0, 18.0, 0.0, 11.0
        countries.update({
            "Stati Uniti": 71.0, "Svizzera": 7.5, "Regno Unito": 5.0,
            "Giappone": 4.0, "Francia": 3.0, "Altri Paesi": 9.5
        })

    # --- MOMENTUM FACTOR (es. IWMO, XMOM) ---
    elif "MOMENTUM" in name or "IWMO" in t or "MOM" in name:
        usa, europa, emergenti, altro = 68.0, 15.0, 0.0, 17.0
        countries.update({
            "Stati Uniti": 68.0, "Giappone": 7.0, "Regno Unito": 4.0,
            "Francia": 3.5, "Svizzera": 3.0, "Germania": 2.5, "Altri Paesi": 12.0
        })

    # --- VALUE FACTOR (es. IWVL, XDEV) ---
    elif "VALUE" in name or "IWVL" in t or "VAL" in name:
        usa, europa, emergenti, altro = 42.0, 24.0, 0.0, 34.0
        countries.update({
            "Stati Uniti": 42.0, "Giappone": 22.0, "Regno Unito": 8.0,
            "Francia": 6.0, "Germania": 5.0, "Altri Paesi": 17.0
        })

    # --- GLOBAL SMALL CAP / VALUE (es. AVWS) ---
    elif "AVWS" in t or ("SMALL CAP" in name and "USA" not in name):
        usa, europa, emergenti, altro = 55.0, 20.0, 5.0, 20.0
        countries.update({
            "Stati Uniti": 55.0, "Giappone": 11.0, "Regno Unito": 7.0,
            "Francia": 4.0, "Germania": 3.5, "Canada": 3.5, "Altri Paesi": 16.0
        })

    # --- EMERGING MARKETS EX-CHINA (es. EMXC) ---
    elif "EMXC" in t or "EX CHINA" in name or "EX-CHINA" in name:
        usa, europa, emergenti, altro = 0.0, 0.0, 100.0, 0.0
        countries.update({
            "India": 26.0, "Taiwan": 24.0, "Corea del Sud": 15.0,
            "Brasile": 6.0, "Altri Paesi": 29.0
        })

    # --- EMERGING MARKETS CORE (es. EIMI, EMAE) ---
    elif "EMERGING" in name or "EMERGENTI" in cat or "EIMI" in t or "EMAE" in t:
        usa, europa, emergenti, altro = 0.0, 0.0, 100.0, 0.0
        countries.update({
            "Cina": 24.0, "India": 19.0, "Taiwan": 18.0,
            "Corea del Sud": 11.0, "Altri Paesi": 28.0
        })

    # --- EUROPE ONLY (es. MEUD, EXSA, Stoxx 600) ---
    elif "EUROPE" in name or "EUROPA" in name or "MEUD" in t or "EXSA" in t or "STOXX" in name:
        usa, europa, emergenti, altro = 0.0, 100.0, 0.0, 0.0
        countries.update({
            "Regno Unito": 22.0, "Francia": 18.0, "Svizzera": 15.0,
            "Germania": 13.0, "Altri Paesi": 32.0
        })

    # --- WORLD CORE STANDARD (es. SWDA, VWCE, IWDA) ---
    elif "WORLD" in t or "WORLD" in name or "SWDA" in t or "VWCE" in t or "IWDA" in t or "GLOBAL" in name or "GLOBALI" in cat:
        if "VWCE" in t or "ALL-WORLD" in name or "FTSE ALL" in name:
            usa, europa, emergenti, altro = 61.5, 16.0, 9.5, 13.0
            countries.update({
                "Stati Uniti": 61.5, "Giappone": 5.8, "Regno Unito": 3.6,
                "Francia": 3.0, "Svizzera": 2.8, "Canada": 3.1,
                "Cina": 2.5, "India": 2.0, "Taiwan": 1.8, "Altri Paesi": 13.9
            })
        else: # MSCI World Standard (SWDA, IWDA)
            usa, europa, emergenti, altro = 68.0, 17.0, 0.0, 15.0
            countries.update({
                "Stati Uniti": 68.0, "Giappone": 6.2, "Regno Unito": 3.8,
                "Francia": 3.2, "Svizzera": 3.0, "Canada": 3.3, "Germania": 2.2, "Altri Paesi": 10.3
            })

    # Fallback generico per azionario non mappato espressamente
    else:
        usa, europa, emergenti, altro = 60.0, 20.0, 10.0, 10.0
        countries.update({
            "Stati Uniti": 60.0, "Giappone": 5.0, "Regno Unito": 4.0,
            "Francia": 3.0, "Germania": 3.0, "Altri Paesi": 25.0
        })

    return {
        "USA": usa,
        "Europa": europa,
        "Emergenti": emergenti,
        "Altro": altro,
        "Countries": countries,
        "Is_Equity": True
    }

# --- NORMALIZED TREND CHART (BASE 100) ---
@st.cache_data(ttl=3600)
def get_historical_normalized_trends(df_assets, period="1y", group_by_category=False):
    series_dict = {}
    
    if group_by_category:
        for cat, group in df_assets.groupby('Categoria'):
            cat_df_list = []
            for _, row in group.iterrows():
                t = str(row['Ticker']).strip()
                if not t or t.upper() in ["MANUAL", "NONE", "NAN", "CASH"] or row['Prezzo_Fisso'] > 0:
                    continue
                try:
                    hist = yf.Ticker(t).history(period=period)
                    if not hist.empty and 'Close' in hist.columns:
                        s = hist['Close'].dropna()
                        if not s.empty and s.iloc[0] > 0:
                            s_norm = (s / s.iloc[0]) * 100
                            s_norm.index = s_norm.index.tz_localize(None)
                            cat_df_list.append(s_norm)
                except Exception:
                    pass
            if cat_df_list:
                cat_combined = pd.concat(cat_df_list, axis=1).mean(axis=1)
                series_dict[cat] = cat_combined
    else:
        for _, row in df_assets.iterrows():
            t = str(row['Ticker']).strip()
            if not t or t.upper() in ["MANUAL", "NONE", "NAN", "CASH"] or row['Prezzo_Fisso'] > 0:
                continue
            
            label = f"{t}"
            
            try:
                hist = yf.Ticker(t).history(period=period)
                if not hist.empty and 'Close' in hist.columns:
                    s = hist['Close'].dropna()
                    if not s.empty and s.iloc[0] > 0:
                        s_norm = (s / s.iloc[0]) * 100
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


# --- 🌍 ANALISI GEOGRAFICA COMPONENTE AZIONARIA (CAP USA <= 50%) ---
st.divider()
st.subheader("🌍 Geographic Breakdown (Solo Azionario)")
st.caption("Ripartizione geografica automatica della componente azionaria (aggiornata mensilmente). Target Max USA = 50%.")

usa_eur, europe_eur, em_eur, other_eur = 0.0, 0.0, 0.0, 0.0
total_equity_eur = 0.0
equity_ticker_geo = {}

for _, row in df.iterrows():
    t = row['Ticker']
    val = float(row['Valore_Attuale'])
    cat = row['Categoria']
    name = row['Nome Asset']
    
    geo_profile = get_etf_geographic_exposure(t, name, cat)
        
    if geo_profile.get("Is_Equity") and val > 0:
        total_equity_eur += val
        usa_eur += val * (geo_profile["USA"] / 100.0)
        europe_eur += val * (geo_profile["Europa"] / 100.0)
        em_eur += val * (geo_profile["Emergenti"] / 100.0)
        other_eur += val * (geo_profile["Altro"] / 100.0)
        
        ticker_lbl = str(t).strip() if pd.notna(t) and str(t).upper() not in ["MANUAL", "NONE", "NAN"] else str(name).strip()
        equity_ticker_geo[ticker_lbl] = {
            "USA": geo_profile["USA"],
            "Europa": geo_profile["Europa"],
            "Emergenti": geo_profile["Emergenti"],
            "Altro": geo_profile["Altro"],
            "Countries": geo_profile.get("Countries", {})
        }

if total_equity_eur > 0:
    pct_usa = (usa_eur / total_equity_eur) * 100.0
    pct_europe = (europe_eur / total_equity_eur) * 100.0
    pct_em = (em_eur / total_equity_eur) * 100.0
    pct_other = (other_eur / total_equity_eur) * 100.0

    # KPI USA vs Cap 50%
    col_g1, col_g2 = st.columns(2)
    col_g1.metric("Valore Azionario Totale", f"€ {total_equity_eur:,.2f}")
    col_g2.metric(
        "Esposizione USA", 
        f"{pct_usa:.1f}%", 
        delta=f"{pct_usa - 50.0:+.1f}% vs limite 50%",
        delta_color="inverse"
    )

    # Allerta Visivo Ribilanciamento USA
    if pct_usa > 50.0:
        eccedenza_pct = pct_usa - 50.0
        eccedenza_eur = total_equity_eur * (eccedenza_pct / 100.0)
        st.warning(
            f"⚠️ **USA sopra il limite massimo (50%)!**\n\n"
            f"Attualmente gli USA rappresentano il **{pct_usa:.1f}%** dell'azionario (€ {usa_eur:,.2f}). "
            f"L'eccedenza è pari a **+{eccedenza_pct:.1f}%** (€ {eccedenza_eur:,.2f}). "
            f"Indirizza i prossimi acquisti azionari su ETF Ex-USA (Europa/Emergenti)."
        )
    else:
        st.success(
            f"✅ **Esposizione USA perfettamente nei limiti.**\n\n"
            f"La quota USA è al **{pct_usa:.1f}%** dell'azionario (sotto il limite massimo del 50%)."
        )

    # Grafico a Torta / Ciambella per le Macro Aree Geografiche
    geo_df = pd.DataFrame({
        "Regione": ["🇺🇸 Stati Uniti (USA)", "🇪🇺 Europa", "🌏 Mercati Emergenti", "🌐 Altro / Resto del Mondo"],
        "Valore_EUR": [usa_eur, europe_eur, em_eur, other_eur],
        "Quota_Pct": [pct_usa, pct_europe, pct_em, pct_other]
    })

    donut_chart = (
        alt.Chart(geo_df)
        .mark_arc(innerRadius=65, stroke="#ffffff", strokeWidth=2)
        .encode(
            theta=alt.Theta(field="Valore_EUR", type="quantitative"),
            color=alt.Color(
                field="Regione", 
                type="nominal",
                scale=alt.Scale(range=["#1f77b4", "#2ca02c", "#ff7f0e", "#7f7f7f"]),
                legend=alt.Legend(title="Macrocategoria", orient="right", labelFontSize=12, titleFontSize=13)
            ),
            tooltip=[
                alt.Tooltip("Regione:N", title="Macrocategoria"),
                alt.Tooltip("Valore_EUR:Q", format=",.2f", title="Valore (€)"),
                alt.Tooltip("Quota_Pct:Q", format=".1f", title="Quota Azionario (%)")
            ]
        )
        .properties(height=320)
    )
    st.altair_chart(donut_chart, use_container_width=True)

    # Tabella Esposizione Geografica Dettagliata (Macrocategorie + Singoli Paesi)
    st.markdown("**Dettaglio Esposizione Geografica e Paesi per Ticker Azionario:**")
    
    rows_structure = [
        ("MACRO: USA", "USA", "🇺🇸 Stati Uniti (USA)"),
        ("MACRO: Europa", "Europa", "🇪🇺 Europa"),
        ("MACRO: Emergenti", "Emergenti", "🌏 Mercati Emergenti"),
        ("MACRO: Altro", "Altro", "🌐 Altro / Resto del Mondo"),
        ("COUNTRY", "Stati Uniti", "  🇺🇸 Stati Uniti"),
        ("COUNTRY", "Giappone", "  🇯🇵 Giappone"),
        ("COUNTRY", "Regno Unito", "  🇬🇧 Regno Unito"),
        ("COUNTRY", "Francia", "  🇫🇷 Francia"),
        ("COUNTRY", "Germania", "  🇩🇪 Germania"),
        ("COUNTRY", "Svizzera", "  🇨🇭 Svizzera"),
        ("COUNTRY", "Canada", "  🇨🇦 Canada"),
        ("COUNTRY", "Cina", "  🇨🇳 Cina"),
        ("COUNTRY", "India", "  🇮🇳 India"),
        ("COUNTRY", "Taiwan", "  🇹🇼 Taiwan"),
        ("COUNTRY", "Corea del Sud", "  🇰🇷 Corea del Sud"),
        ("COUNTRY", "Altri Paesi", "  🌐 Altri Paesi")
    ]

    table_geo_data = {}
    for r_type, key_name, display_label in rows_structure:
        table_geo_data[display_label] = {}
        for ticker_lbl, exp in equity_ticker_geo.items():
            if r_type.startswith("MACRO"):
                val_pct = exp.get(key_name, 0.0)
            else:
                val_pct = exp.get("Countries", {}).get(key_name, 0.0)
            table_geo_data[display_label][ticker_lbl] = f"{val_pct:.1f}%"

    df_geo_table = pd.DataFrame(table_geo_data).T
    st.dataframe(df_geo_table, use_container_width=True)

else:
    st.info("Nessun titolo azionario rilevato nel portafoglio per il calcolo geografico.")


# --- NORMALIZED TREND CHART INGRANDITO E PIÙ LEGGIBILE ---
st.divider()
st.subheader("📊 Performance Comparison (Base 100)")

timeframe_map = {
    "1 mese": "1mo",
    "3 mesi": "3mo",
    "6 mesi": "6mo",
    "1 anno": "1y",
    "3 anni": "3y",
    "5 anni": "5y"
}

col_mode, col_tf = st.columns([1, 1])

with col_mode:
    view_mode = st.radio(
        "Raggruppamento:",
        options=["Per Categoria", "Per Singolo Ticker"],
        horizontal=True
    )

with col_tf:
    selected_tf_label = st.selectbox(
        "Orizzonte temporale:",
        options=list(timeframe_map.keys()),
        index=3
    )

selected_period = timeframe_map[selected_tf_label]
is_cat_view = (view_mode == "Per Categoria")

with st.spinner("Caricamento grafico..."):
    hist_chart_df = get_historical_normalized_trends(df, period=selected_period, group_by_category=is_cat_view)

if not hist_chart_df.empty:
    available_items = list(hist_chart_df.columns)
    
    selected_items = st.multiselect(
        "Filtra elementi nel grafico:",
        options=available_items,
        default=available_items
    )
    
    if selected_items:
        df_chart = hist_chart_df[selected_items].reset_index()
        date_col = df_chart.columns[0]
        df_melted = df_chart.melt(id_vars=[date_col], var_name='Serie', value_name='Valore')

        highlight = alt.selection_point(on='pointerover', fields=['Serie'], empty=True)

        line_chart = (
            alt.Chart(df_melted)
            .mark_line(strokeWidth=3)
            .encode(
                x=alt.X(
                    f'{date_col}:T', 
                    title='Data', 
                    axis=alt.Axis(labelFontSize=12, titleFontSize=14, labelAngle=-30)
                ),
                y=alt.Y(
                    'Valore:Q', 
                    title='Performance (Base 100)', 
                    scale=alt.Scale(zero=False),
                    axis=alt.Axis(labelFontSize=12, titleFontSize=14)
                ),
                color=alt.Color(
                    'Serie:N', 
                    legend=alt.Legend(
                        title="Legenda", 
                        orient="top", 
                        columns=3,
                        labelFontSize=13,
                        titleFontSize=14,
                        symbolSize=100
                    )
                ),
                opacity=alt.condition(highlight, alt.value(1.0), alt.value(0.15)),
                strokeWidth=alt.condition(highlight, alt.value(4.0), alt.value(1.5)),
                tooltip=[
                    alt.Tooltip(f'{date_col}:T', title='Data', format='%d %b %Y'),
                    alt.Tooltip('Serie:N', title='Elemento'),
                    alt.Tooltip('Valore:Q', format='.2f', title='Base 100')
                ]
            )
            .add_params(highlight)
            .properties(height=650)
            .interactive()
        )

        st.altair_chart(line_chart, use_container_width=True)
    else:
        st.warning("Seleziona almeno un elemento per mostrare il grafico.")
else:
    st.info("Dati storici non disponibili.")

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
    3. **Suggerimenti tattici**: dammi 2-3 suggerimenti tattici che possono essere utili, legati ai pesi attuali del mio portafoglio e al bilanciamento geografico azionario, ma senza porre il focus sugli scostamenti attuali che sono già evidenti
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
                "valore_azionario_totale_eur": round(total_equity_eur, 2),
                "esposizione_usa_pct_azionario": round(pct_usa if total_equity_eur > 0 else 0.0, 2),
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
