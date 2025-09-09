
import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime


st.set_page_config(page_title="Exames Consolidados", layout="wide")

st.title("📈 SF - Dashboard")

# --- Config ---
DEFAULT_CSV_PATH = os.environ.get("CSV_PATH", "app/data/exames_consolidados.csv")
REF_CSV_PATH = os.environ.get("REF_CSV_PATH", "app/data/valores_referencia_lab.csv")

# --- Load main data ---
@st.cache_data(show_spinner=True)
def load_data(csv_path: str):
    df = pd.read_csv(csv_path)
    # Encontrar coluna de data
    date_col = None
    for c in df.columns:
        if c.strip().lower() in ("data", "date"):
            date_col = c
            break
    if date_col is None:
        raise ValueError("Não encontrei a coluna de data ('Data' ou 'date').")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    df = df.sort_values(by=date_col).reset_index(drop=True)
    return df, date_col

# --- Load reference min/max (optional) ---
@st.cache_data(show_spinner=True)
def load_refs(ref_csv_path: str):
    if not os.path.exists(ref_csv_path):
        return {}
    try:
        refs = pd.read_csv(ref_csv_path)
    except Exception:
        return {}
    # Espera colunas: Exame | Mínimo | Máximo
    required = {"Exame", "Mínimo", "Máximo"}
    if not required.issubset(set(refs.columns)):
        return {}
    # Normaliza nomes e cria dicionário
    refs["__key__"] = refs["Exame"].astype(str).str.strip().str.lower()
    ref_map = {
        row["__key__"]: (pd.to_numeric(str(row["Mínimo"]).replace(",", "."), errors="coerce"),
                         pd.to_numeric(str(row["Máximo"]).replace(",", "."), errors="coerce"))
        for _, row in refs.iterrows()
    }
    return ref_map

try:
    df, date_col = load_data(DEFAULT_CSV_PATH)
except Exception as e:
    st.error(f"Erro ao carregar CSV em '{DEFAULT_CSV_PATH}': {e}")
    st.stop()

ref_map = load_refs(REF_CSV_PATH)

# Detectar colunas numéricas plotáveis, exceto data e referências
candidates = []
nn = df.copy()
for c in df.columns:
    if c == date_col:
        continue
    if " - Ref" in c or "(Ref" in c:
        continue
    tmp = pd.to_numeric(df[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    if tmp.notna().sum() > 0:
        nn[c] = tmp
        candidates.append(c)

if not candidates:
    st.error("Não encontrei colunas numéricas para exibir. Verifique o conteúdo do CSV.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Controles")
    feature = st.selectbox("Selecione o exame (feature):", options=sorted(candidates))
    # Datas
    min_d = pd.to_datetime(df[date_col].min())
    max_d = pd.to_datetime(df[date_col].max())
    date_range = st.date_input(
        "Intervalo de datas",
        value=(min_d.date(), max_d.date()),
        min_value=min_d.date(),
        max_value=max_d.date(),
        format="DD/MM/YYYY"
    )
    show_points = st.checkbox("Mostrar pontos", value=True)
    rolling = st.number_input("Média móvel (em nº de amostras)", min_value=0, max_value=30, value=5, step=1)
    show_ref_band = st.checkbox("Mostrar faixa de referência (verde)", value=True,
                                help="Faixa de valores de referência ideais segundo laudos laboratoriais.")

    st.caption("Obs: O app detecta novas colunas numéricas automaticamente quando adicionado ao CSV.")

# Filtro de datas
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    m = (df[date_col] >= start) & (df[date_col] <= end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
    dff = nn.loc[m, [date_col, feature]].copy()
else:
    dff = nn[[date_col, feature]].copy()

# Média móvel
series_to_plot = [feature]
if rolling and rolling > 0:
    dff[f"{feature} (MM {rolling})"] = dff[feature].rolling(rolling, min_periods=1).mean()
    series_to_plot.append(f"{feature} (MM {rolling})")

# Gráfico base
fig = px.line(dff, x=date_col, y=series_to_plot, markers=show_points)
for trace in fig.data:
    if "MM" in trace.name:
        trace.line.color = "gray"
fig.update_layout(
    xaxis_title="Data",
    yaxis_title=feature,
    legend_title_text="Séries",
    hovermode="x unified",
    margin=dict(l=10, r=10, t=40, b=10),
    height=520
)
fig.update_traces(connectgaps=True)

# Faixa de referência (verde) se disponível
ref_key = feature.strip().lower()
if show_ref_band and ref_key in ref_map:
    y0, y1 = ref_map[ref_key]
    if pd.notna(y0) and pd.notna(y1):
        fig.add_hrect(y0=y0, y1=y1, fillcolor="green", opacity=0.12, line_width=0,
                      annotation_text="Faixa de referência", annotation_position="top left")
        # Trace dummy para aparecer na legenda
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines",
            line=dict(color="green", width=10),
            name=f"Ref: {y0:g} – {y1:g}"
        ))

st.plotly_chart(fig, use_container_width=True)

# Tabela
st.subheader("Tabela de valores")
st.dataframe(dff.set_index(date_col), use_container_width=True)

# Info
# st.caption(f"CSV principal: **{DEFAULT_CSV_PATH}** | Referências (opcional): **{REF_CSV_PATH}**")