"""
streamlit_app.py -- Modelo de afluencia EFE/Fesur 2027.

Versión metodológica mensual-elástica:
- La oferta se edita por servicio, mes y tipo de día.
- La demanda de cada mes se calcula de forma independiente.
- El calendario 2027 incorpora feriados nacionales y reglas operacionales por servicio.
- No se reparte un total anual fijo: el total anual resulta de sumar los 12 meses.
- El cambio de oferta en un mes afecta ese mes y el total anual, no redistribuye el resto del año.
"""
import os
import html
import base64
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

import pipeline_afluencia as P
import oferta as O
import od_biotren_hibrido as OD
import od_laja_talcahuano as OL
import od_tren_araucania as TAOD
import backtesting as BT
import incertidumbre as INC

st.set_page_config(page_title="Afluencia EFE/Fesur 2027", layout="wide", page_icon="🚆")

PAL = {"BIOTREN": "#1f6feb", "CORTO_LAJA": "#0e9f6e", "TREN_ARAUCANIA": "#d97706", "LLANQUIHUE_PM": "#9333ea"}
CONF = {"BIOTREN": "ALTA", "CORTO_LAJA": "ALTA", "TREN_ARAUCANIA": "MEDIA", "LLANQUIHUE_PM": "BAJA"}
CONF_C = {"ALTA": "#0e9f6e", "MEDIA": "#d97706", "BAJA": "#dc2626"}
DATA = os.path.join(os.path.dirname(__file__), "data")
ASSETS = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILENAME = "efe_trenes_chile_logo.png"


def _read_logo_data_uri():
    logo_path = os.path.join(ASSETS, LOGO_FILENAME)
    try:
        with open(logo_path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    except Exception:
        return ""


LOGO_DATA_URI = _read_logo_data_uri()

REFERENCIAS_CIERRE_2026 = os.path.join(DATA, "referencias_cierre_2026")
REF_SERVICIO_TO_MODELO = {
    "Biotren": "BIOTREN",
    "Laja Talcahuano": "CORTO_LAJA",
    "Tren Araucanía": "TREN_ARAUCANIA",
}
REF_TIPO_LABEL = {
    "historico_observado": "Histórico observado",
    "cierre_2026_estimado": "Cierre 2026 estimado",
    "proyeccion_2027_modelo": "Proyección 2027 modelo",
}
REF_TIPO_COLOR = {
    "Histórico observado": "#1f6feb",
    "Cierre 2026 estimado": "#d97706",
    "Proyección 2027 modelo": "#dc2626",
}

st.markdown("""
<style>
  :root {
    --efe-blue: #003A70;
    --efe-blue-2: #0057A8;
    --efe-blue-3: #0A4D8F;
    --efe-blue-soft: #EAF3FA;
    --efe-blue-soft-2: #F3F8FC;
    --efe-red: #D71920;
    --efe-red-soft: #FFF3F3;
    --efe-gray-900: #0B1F3A;
    --efe-gray-700: #34445C;
    --efe-gray-600: #66758A;
    --efe-gray-300: #D9E1E8;
    --efe-gray-200: #E8EEF4;
    --efe-gray-100: #F6F8FB;
    --efe-white: #FFFFFF;
    --efe-shadow: 0 10px 28px rgba(0, 58, 112, .075);
    --efe-shadow-soft: 0 4px 16px rgba(0, 58, 112, .055);
    --efe-radius-lg: 22px;
    --efe-radius-md: 16px;
    --efe-radius-sm: 12px;
  }

  html, body, [class*="css"] {
    font-family: "Univia Pro", "Inter", "Segoe UI", Arial, sans-serif !important;
    color: var(--efe-gray-900);
  }

  .stApp {
    background:
      radial-gradient(circle at 10% 0%, rgba(0, 58, 112, .055), transparent 26rem),
      linear-gradient(180deg, #FFFFFF 0%, #F7FAFD 42%, #FFFFFF 100%);
  }

  .block-container {
    max-width: 1520px;
    padding-top: 2.35rem;
    padding-left: 1.55rem;
    padding-right: 1.55rem;
    padding-bottom: 2.5rem;
  }

  h1, h2, h3, h4, h5 {
    color: var(--efe-blue) !important;
    letter-spacing: -.025em;
    font-weight: 820 !important;
  }

  h3 { margin-top: .4rem !important; }

  .efe-app-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1.2rem;
    margin: .45rem 0 1.25rem;
  }

  .efe-logo-wrap {
    display: flex;
    align-items: center;
    gap: 1rem;
    min-width: 240px;
  }

  .efe-logo-image {
    display: block;
    width: min(100%, 360px);
    max-height: 118px;
    height: auto;
    object-fit: contain;
  }

  .efe-pill {
    display: inline-flex;
    align-items: center;
    gap: .55rem;
    background: linear-gradient(180deg, #FFFFFF 0%, #F5F8FC 100%);
    border: 1px solid var(--efe-gray-300);
    color: var(--efe-blue);
    border-radius: 14px;
    padding: .72rem 1.05rem;
    font-weight: 800;
    box-shadow: var(--efe-shadow-soft);
    white-space: nowrap;
  }

  .efe-title-block { margin: .12rem 0 1.05rem; }
  .efe-page-title {
    color: var(--efe-blue);
    font-size: clamp(2rem, 3.2vw, 3.05rem);
    line-height: 1.03;
    font-weight: 900;
    margin: 0;
    letter-spacing: -.055em;
  }
  .efe-page-subtitle {
    color: #7A89A0;
    font-size: clamp(1.0rem, 1.2vw, 1.18rem);
    font-weight: 720;
    margin-top: .25rem;
  }

  .efe-service-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin: .2rem 0 .95rem;
  }

  .efe-service-title {
    color: var(--efe-blue);
    font-size: clamp(1.8rem, 2.6vw, 2.65rem);
    line-height: 1.05;
    font-weight: 900;
    margin: 0;
    letter-spacing: -.05em;
  }

  .efe-service-subtitle {
    color: #7A89A0;
    font-size: 1rem;
    font-weight: 720;
    margin-top: .25rem;
  }

  .hero {
    background: transparent;
    color: var(--efe-blue);
    padding: 0;
    border-radius: 0;
    margin-bottom: .6rem;
    box-shadow: none;
  }
  .hero h1 { color: var(--efe-blue) !important; margin: 0; font-size: 2.25rem; }
  .hero p { color: #7A89A0; margin: .2rem 0 0; font-weight: 700; }

  .efe-card, .efe-metric-card, .efe-panel, .efe-table-card, .efe-alert-list, .efe-section {
    background: rgba(255,255,255,.94);
    border: 1px solid var(--efe-gray-200);
    border-radius: var(--efe-radius-md);
    box-shadow: var(--efe-shadow-soft);
  }

  .efe-panel, .efe-table-card, .efe-alert-list, .efe-section {
    padding: 1.0rem 1.1rem;
    margin: .4rem 0 .85rem;
  }

  .efe-section-title {
    color: var(--efe-blue);
    font-size: 1.05rem;
    font-weight: 900;
    margin-bottom: .08rem;
  }
  .efe-section-note {
    color: var(--efe-gray-600);
    font-size: .88rem;
    font-weight: 650;
    margin-top: .05rem;
  }

  .efe-metric-card {
    min-height: 112px;
    padding: 1.0rem .95rem;
    display: flex;
    gap: .82rem;
    align-items: flex-start;
    margin-bottom: .72rem;
  }
  .efe-icon-circle {
    flex: 0 0 auto;
    width: 46px;
    height: 46px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--efe-blue);
    background: linear-gradient(180deg, #F7FAFD 0%, #EAF3FA 100%);
    border: 1px solid #DCE8F3;
    font-size: 1.35rem;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.7);
  }
  .efe-metric-label {
    color: var(--efe-blue);
    font-size: .76rem;
    font-weight: 900;
    line-height: 1.25;
  }
  .efe-metric-value {
    color: var(--efe-blue);
    font-size: 1.35rem;
    font-weight: 900;
    line-height: 1.1;
    margin-top: .38rem;
    letter-spacing: -.025em;
  }
  .efe-metric-detail {
    color: var(--efe-gray-700);
    font-size: .82rem;
    font-weight: 720;
    margin-top: .22rem;
  }
  .efe-metric-delta {
    color: #0066CC;
    font-size: .78rem;
    font-weight: 830;
    margin-top: .45rem;
  }
  .efe-metric-note {
    color: var(--efe-gray-600);
    font-size: .76rem;
    font-weight: 650;
    margin-top: .35rem;
  }

  .efe-alert-row {
    display:flex;
    align-items:center;
    gap:.9rem;
    border: 1px solid var(--efe-gray-200);
    border-radius: 12px;
    padding: .72rem .85rem;
    margin: .52rem 0;
    background: #FFFFFF;
    color: var(--efe-blue);
    font-weight: 700;
  }
  .efe-alert-icon {
    width: 34px;
    height: 34px;
    border: 2px solid var(--efe-red);
    border-radius: 50%;
    color: var(--efe-red);
    display:flex;
    align-items:center;
    justify-content:center;
    font-weight: 900;
    flex: 0 0 auto;
  }

  .efe-chip {
    display:inline-block;
    padding:.32rem .65rem;
    border-radius:999px;
    background: var(--efe-blue-soft);
    color: var(--efe-blue);
    border:1px solid #D6E7F6;
    font-size:.76rem;
    font-weight:850;
    margin:.18rem .25rem .18rem 0;
  }

  .badge, .bt-chip {
    display:inline-block;
    border-radius:999px;
    padding: .28rem .7rem;
    background: var(--efe-blue-soft) !important;
    color: var(--efe-blue) !important;
    border:1px solid #D6E7F6;
    font-size:.76rem;
    font-weight:850;
  }

  div[data-testid="stMetric"] {
    background: rgba(255,255,255,.94);
    border: 1px solid var(--efe-gray-200);
    border-radius: var(--efe-radius-md);
    padding: .9rem 1rem;
    box-shadow: var(--efe-shadow-soft);
  }
  div[data-testid="stMetricLabel"] p { color: var(--efe-blue); font-weight: 850; }
  div[data-testid="stMetricValue"] { color: var(--efe-blue); font-weight: 900; }
  div[data-testid="stMetricDelta"] { color: #0066CC; font-weight: 800; }

  div[data-testid="stDataFrame"], div[data-testid="stTable"] {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--efe-gray-200);
    box-shadow: none;
  }

  div[data-testid="stExpander"] {
    border: 1px solid var(--efe-gray-200) !important;
    border-radius: 14px !important;
    background: #FFFFFF !important;
    box-shadow: var(--efe-shadow-soft);
    margin: .5rem 0;
  }

  button[data-baseweb="tab"] {
    font-weight: 850;
    color: var(--efe-blue);
    border-radius: 999px;
  }

  .stPlotlyChart {
    background: rgba(255,255,255,.94);
    border: 1px solid var(--efe-gray-200);
    border-radius: var(--efe-radius-md);
    padding: .25rem;
    box-shadow: var(--efe-shadow-soft);
  }

  code { white-space: pre-wrap; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def cargar():
    diario = pd.read_csv(os.path.join(DATA, "afluencia_diaria_consolidada.csv"), parse_dates=["fecha"])
    params = O.aplicar_oferta_actual(pd.read_csv(os.path.join(DATA, "oferta_params.csv")))
    mdf = P.mensualizar(diario)
    hist = O.analisis_mensual_historico(mdf)
    hist_anual = O.resumen_historico_anual(mdf)
    return diario, params, mdf, hist, hist_anual


try:
    diario, params, mdf, hist, hist_anual = cargar()
except Exception as e:
    st.error(f"No se pudieron cargar los datos en /data: {e}")
    st.stop()

_logo_html = f'<img class="efe-logo-image" src="{LOGO_DATA_URI}" alt="EFE Trenes de Chile" />' if LOGO_DATA_URI else ''
st.markdown(
    (
        '<div class="efe-app-top">'
        '<div class="efe-logo-wrap">' + _logo_html + '</div>'
        '<div class="efe-pill">▣ Proyección 2027</div>'
        '</div>'
        '<div class="efe-title-block">'
        '<div class="efe-page-title">Modelo de afluencia 2027 — EFE Sur</div>'
        '<div class="efe-page-subtitle">Proyección operacional, ocupación, oferta y referencias históricas para la toma de decisiones.</div>'
        '</div>'
    ),
    unsafe_allow_html=True,
)



@st.cache_data
def cargar_referencias_cierre_2026():
    mensual_path = os.path.join(REFERENCIAS_CIERRE_2026, "afluencia_historica_cierre_2026_long.csv")
    anual_path = os.path.join(REFERENCIAS_CIERRE_2026, "afluencia_historica_cierre_2026_resumen_anual.csv")
    mensual = pd.read_csv(mensual_path)
    anual = pd.read_csv(anual_path)
    mensual["servicio_modelo"] = mensual["servicio"].map(REF_SERVICIO_TO_MODELO)
    anual["servicio_modelo"] = anual["servicio"].map(REF_SERVICIO_TO_MODELO)
    mensual["tipo_dato_label"] = mensual["tipo_dato"].map(REF_TIPO_LABEL)
    anual["tipo_dato_label"] = anual["tipo_dato"].map(REF_TIPO_LABEL)
    mensual["periodo"] = mensual["anio"].astype(int).astype(str) + "-" + mensual["mes_num"].astype(int).astype(str).str.zfill(2)
    return mensual, anual


def construir_referencia_anual_visual(serv):
    _, anual = cargar_referencias_cierre_2026()
    proy = pd.DataFrame([
        {
            "servicio": next(k for k, v in REF_SERVICIO_TO_MODELO.items() if v == servicio),
            "servicio_modelo": servicio,
            "anio": 2027,
            "tipo_dato": "proyeccion_2027_modelo",
            "tipo_dato_label": REF_TIPO_LABEL["proyeccion_2027_modelo"],
            "afluencia_anual": float(serv[servicio].sum()),
        }
        for servicio in REF_SERVICIO_TO_MODELO.values()
    ])
    base = anual.copy()
    base = base[base["servicio_modelo"].isin(REF_SERVICIO_TO_MODELO.values())]
    return pd.concat([base, proy], ignore_index=True, sort=False)


def construir_referencia_mensual_visual(serv):
    mensual, _ = cargar_referencias_cierre_2026()
    proy_rows = []
    for servicio in REF_SERVICIO_TO_MODELO.values():
        nombre_ref = next(k for k, v in REF_SERVICIO_TO_MODELO.items() if v == servicio)
        for periodo, valor in serv[servicio].astype(float).items():
            proy_rows.append({
                "servicio": nombre_ref,
                "servicio_modelo": servicio,
                "anio": 2027,
                "mes_num": int(str(periodo)[5:7]),
                "mes": str(periodo)[5:7],
                "periodo": periodo,
                "afluencia": float(valor),
                "tipo_dato": "proyeccion_2027_modelo",
                "tipo_dato_label": REF_TIPO_LABEL["proyeccion_2027_modelo"],
                "fuente": "Modelo operacional 2027 vigente",
            })
    base = mensual[mensual["servicio_modelo"].isin(REF_SERVICIO_TO_MODELO.values())].copy()
    return pd.concat([base, pd.DataFrame(proy_rows)], ignore_index=True, sort=False)

def fmt(n):
    return f"{int(round(float(n))):,}".replace(",", ".")


def fmt_mm(n):
    return f"$ {float(n) / 1_000_000:,.0f} MM".replace(",", ".")


def fmt_pct(delta):
    if pd.isna(delta):
        return "s/i"
    return f"{delta:+.1f}%".replace(".", ",")


def fmt_share(x):
    if pd.isna(x):
        return "s/i"
    return f"{float(x) * 100:.4f}%".replace(".", ",")


@st.cache_data(show_spinner=False)
def calcular_od_biotren_tarjeta_mes_cached(periodo, valor):
    serie = pd.Series([float(valor)], index=[periodo])
    return OD.distribuir_proyeccion_biotren_por_tipo_tarjeta(serie)


@st.cache_data(show_spinner=False)
def calcular_resultado_biotren_tarjeta_anual_cached(serie_dict):
    serie = pd.Series(serie_dict, dtype=float)
    return OD.distribuir_proyeccion_biotren_por_tipo_tarjeta(serie)


@st.cache_data(show_spinner=False)
def calcular_resultado_laja_anual_cached(serie_dict):
    serie = pd.Series(serie_dict, dtype=float)
    return OL.calcular_resultado_laja_anual(serie)


@st.cache_data(show_spinner=False)
def calcular_od_laja_mes_cached(periodo, valor):
    return OL.distribuir_laja_talcahuano_mes(periodo, float(valor))


@st.cache_data(show_spinner=False)
def calcular_resultado_tren_araucania_anual_cached(serie_dict):
    serie = pd.Series(serie_dict, dtype=float)
    return TAOD.calcular_resultado_anual(serie)


@st.cache_data(show_spinner=False)
def calcular_od_tren_araucania_mes_cached(periodo, valor):
    return TAOD.distribuir_mes(periodo, float(valor))


@st.cache_data(show_spinner=False)
def calcular_resumen_anual_ingresos_subsidio_biotren_cached(serie_dict):
    resultado = calcular_resultado_biotren_tarjeta_anual_cached(serie_dict)
    return resultado["ingresos_subsidio_biotren"]


def _rol_tarjetario(tipo_tarjeta):
    if tipo_tarjeta in {"monedero", "media_superior", "adulto_mayor"}:
        return "Tarifa directa"
    return "Sin ingreso directo"


def _grupo_subsidio_tarjeta(tipo_tarjeta):
    if tipo_tarjeta == "media_superior":
        return "Subsidio estudiante"
    if tipo_tarjeta == "adulto_mayor":
        return "Fuera de subsidio"
    return "Grupo normal"


def render_indicadores_ejecutivos_biotren_2027(serv):
    serie = serv["BIOTREN"].astype(float).copy()
    ingresos_subsidio = calcular_resumen_anual_ingresos_subsidio_biotren_cached(serie.to_dict())
    anual = ingresos_subsidio["resumen_anual"]
    pasajeros = float(anual["viajes_biotren"])
    ingreso_medio = float(anual["ingreso_total_biotren"]) / pasajeros if pasajeros > 0 else 0.0
    servicios_comerciales = float(O.servicios_comerciales_biotren_mensuales(2027).sum())
    pasajeros_por_servicio = pasajeros / servicios_comerciales if servicios_comerciales > 0 else 0.0
    diag_recal = serv.attrs.get("recalibracion_2027", {}).get("diagnostico_biotren", {})
    referencia_pre_ajuste = float(diag_recal.get("total_pre_ajuste_ocupacion", pasajeros))
    diferencia_pre_ajuste = pasajeros - referencia_pre_ajuste

    st.markdown("## Biotren: afluencia, distribución e ingresos 2027")
    st.markdown(
        """
<div class="bt-panel">
  <h4>Resumen ejecutivo</h4>
  <p class="bt-note">El escenario ajustado considera una validación operacional por ocupación promedio general, oferta vigente y tendencia histórica mensual. Sobre esa base se calculan la venta de pasajes, el subsidio normal y el subsidio estudiante; la distribución OD/tipo de tarjeta se aplica como capa posterior.</p>
  <span class="bt-chip">Afluencia 2027</span><span class="bt-chip">Ingresos tarifarios</span><span class="bt-chip">Subsidios Biotren</span><span class="bt-chip">OD y tipo de tarjeta</span>
</div>
""",
        unsafe_allow_html=True,
    )

    fila_1 = st.columns(4)
    fila_1[0].metric("Pasajeros 2027", fmt(pasajeros))
    fila_1[1].metric("Venta de pasajes", fmt_mm(anual["ingreso_venta"]))
    fila_1[2].metric("Subsidio total", fmt_mm(anual["subsidio_total"]))
    fila_1[3].metric("Ingreso total Biotren", fmt_mm(anual["ingreso_total_biotren"]))

    fila_2 = st.columns(4)
    fila_2[0].metric("Subsidio normal", fmt_mm(anual["subsidio_normal"]))
    fila_2[1].metric("Subsidio estudiante", fmt_mm(anual["subsidio_estudiante"]))
    fila_2[2].metric("Tasa descuento", f"{float(anual['tasa_descuento_normal']) * 100:.1f}%".replace(".", ","))
    fila_2[3].metric("Pax/servicio comercial", f"{pasajeros_por_servicio:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."), f"Δ {fmt(diferencia_pre_ajuste)} vs ref.")

    st.caption("Indicadores específicos de Biotren: la venta de pasajes proviene de tarifas directas; el subsidio normal usa la tasa de descuento parametrizada; la matriz estudiante sin subsidio proviene del presupuesto base; la venta media_superior considera diagonal; el ingreso teórico estudiante sin subsidio excluye diagonal; el subsidio estudiante corresponde a la diferencia agregada entre ambos; el ingreso total corresponde a venta de pasajes + subsidio normal + subsidio estudiante. El cálculo financiero no modifica la afluencia proyectada.")


def render_participacion_redistribucion_biotren(serv):
    st.markdown("### Detalle histórico de participación mensual")
    mensual_recal = pd.DataFrame(serv.attrs.get("recalibracion_2027", {}).get("mensual", []))
    if mensual_recal.empty or "proyeccion_vigente_pre_redistribucion" not in mensual_recal.columns:
        vigente = serv["BIOTREN"].astype(float)
    else:
        vigente = mensual_recal[mensual_recal["servicio"].eq("BIOTREN")].set_index("mes")["proyeccion_vigente_pre_redistribucion"].astype(float)
    diag = O.diagnostico_redistribucion_biotren_2027(vigente, serv["BIOTREN"].astype(float))
    total = float(serv["BIOTREN"].astype(float).sum())
    servicios = float(O.servicios_comerciales_biotren_mensuales(2027).sum())
    pps = total / servicios if servicios else 0.0
    mayores = diag.sort_values("diferencia_afluencia", ascending=False).head(2)
    menores = diag.sort_values("diferencia_afluencia", ascending=True).head(2)
    c = st.columns(4)
    c[0].metric("Total anual Biotren", fmt(total))
    c[1].metric("Pax/servicio comercial", f"{pps:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c[2].metric("Mayor aumento", ", ".join(mayores["mes"].astype(int).astype(str)))
    c[3].metric("Validación suma", fmt(diag["afluencia_2027_redistribuida"].sum()))

    chart = pd.DataFrame({
        "Mes": diag["mes"],
        "2024": diag["participacion_2024"],
        "2025": diag["participacion_2025"],
        "Cierre 2026": diag["participacion_cierre_2026"],
        "2027 vigente": diag["participacion_2027_vigente"],
        "2027 redistribuido": diag["participacion_2027_redistribuida"],
    })
    fig = go.Figure()
    for col in ["2024", "2025", "Cierre 2026", "2027 vigente", "2027 redistribuido"]:
        fig.add_trace(go.Scatter(x=chart["Mes"], y=chart[col] * 100, mode="lines+markers", name=col))
    fig.update_layout(yaxis_title="Participación mensual (%)", xaxis_title="Mes", height=360, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")

    tabla = diag[[
        "mes", "participacion_ponderada_reciente", "participacion_2027_vigente",
        "participacion_2027_redistribuida", "afluencia_2027_vigente",
        "afluencia_2027_redistribuida", "diferencia_afluencia",
        "pasajeros_por_servicio_redistribuido", "observacion_metodologica",
    ]].rename(columns={
        "mes": "Mes",
        "participacion_ponderada_reciente": "Participación histórica reciente",
        "participacion_2027_vigente": "Participación 2027 vigente",
        "participacion_2027_redistribuida": "Participación 2027 redistribuida",
        "afluencia_2027_vigente": "Afluencia 2027 vigente",
        "afluencia_2027_redistribuida": "Afluencia 2027 redistribuida",
        "diferencia_afluencia": "Diferencia",
        "pasajeros_por_servicio_redistribuido": "Pasajeros por servicio redistribuido",
        "observacion_metodologica": "Observación metodológica",
    })
    st.dataframe(tabla.style.format({
        "Participación histórica reciente": "{:.4%}",
        "Participación 2027 vigente": "{:.4%}",
        "Participación 2027 redistribuida": "{:.4%}",
        "Afluencia 2027 vigente": "{:,.0f}",
        "Afluencia 2027 redistribuida": "{:,.0f}",
        "Diferencia": "{:+,.0f}",
        "Pasajeros por servicio redistribuido": "{:,.1f}",
    }), width="stretch", hide_index=True)
    with st.expander("Detalle técnico de diagnóstico mensual", expanded=False):
        st.write("Meses con mayor disminución: " + ", ".join(menores["mes"].astype(int).astype(str)))
        st.dataframe(diag.style.format({c: "{:.4%}" for c in diag.columns if "participacion" in c}), width="stretch", hide_index=True)


@st.cache_data(show_spinner=False)
def calcular_distribucion_biotren_linea_mod_cached(serie_dict):
    serie = pd.Series(serie_dict, dtype=float)
    return OD.distribuir_proyeccion_biotren_por_linea_mod(serie)


def _matriz_tarjeta(df, tipo_tarjeta, valor):
    tmp = df[df["tipo_tarjeta"].eq(tipo_tarjeta)]
    estaciones = list(dict.fromkeys(pd.concat([tmp["origen"], tmp["destino"]]).astype(str)))
    M = tmp.pivot_table(index="origen", columns="destino", values=valor, aggfunc="sum", fill_value=0.0)
    return M.reindex(index=estaciones, columns=estaciones, fill_value=0.0)



def render_incertidumbre_biotren(serv):
    st.markdown("### 9. Diagnósticos de incertidumbre")
    try:
        bt = BT.ejecutar_backtesting(params, mdf)
        bandas = INC.calcular_bandas_incertidumbre(serv.astype(float), bt.metricas_servicio)
    except Exception as e:
        st.warning(f"No fue posible calcular las bandas diagnósticas de Biotren: {e}")
        return

    fila = bandas.anual[bandas.anual["servicio"].eq("BIOTREN")].copy()
    if fila.empty:
        st.warning("No hay métricas de incertidumbre disponibles para Biotren.")
        return

    cols = {
        "total_banda_baja": "Banda baja",
        "total_base": "Base vigente",
        "total_banda_alta": "Banda alta",
        "total_ajustado_sesgo": "Ajuste por sesgo",
        "WMAPE_usado": "WMAPE usado (%)",
        "sesgo_usado": "Sesgo usado (%)",
        "advertencia_metodologica": "Advertencia metodológica",
    }
    st.dataframe(
        fila[list(cols)].rename(columns=cols).style.format({
            "Banda baja": "{:,.0f}",
            "Base vigente": "{:,.0f}",
            "Banda alta": "{:,.0f}",
            "Ajuste por sesgo": "{:,.0f}",
            "WMAPE usado (%)": "{:.2f}",
            "Sesgo usado (%)": "{:+.2f}",
        }),
        width="stretch",
        hide_index=True,
    )
    st.caption("Las bandas derivan del backtesting retrospectivo diagnóstico. No son intervalos estadísticos formales y no reemplazan la base operacional vigente de Biotren.")

def hist_valor(servicio, anio, meses=None):
    h = hist[hist.servicio == servicio].copy()
    h = h[h.anio.astype(int) == int(anio)]
    if meses is not None:
        h = h[h.mes.astype(int).isin([int(m) for m in meses])]
    if h.empty:
        return None
    return float(h["afluencia_mensual_normalizada"].sum())


def hist_resumen(servicio, anio):
    h = hist_anual[(hist_anual.servicio == servicio) & (hist_anual.anio.astype(int) == int(anio))].copy()
    if h.empty:
        return None
    r = h.iloc[0]
    return {
        "total": float(r["afluencia_observada_normalizada"]),
        "meses": int(r["meses_observados"]),
        "primer_mes": int(r["primer_mes"]),
        "ultimo_mes": int(r["ultimo_mes"]),
    }


def var_pct(valor, base):
    if base is None or base == 0 or pd.isna(base):
        return None
    return (float(valor) / float(base) - 1.0) * 100.0


def resumen_validacion_servicio(s, serv, uni, detalle):
    total = float(serv[s].sum())
    viajes = float(detalle[detalle.servicio == s]["viajes_operados_plan"].sum())
    pax_viaje = total / viajes if viajes > 0 else 0.0
    meses = serv[s].astype(float)
    rows = [
        {"Indicador": "Proyección anual 2027", "Valor": fmt(total)},
        {"Indicador": "Viajes operados proyectados", "Valor": fmt(viajes)},
        {"Indicador": "Pasajeros por viaje proyectado", "Valor": fmt(pax_viaje)},
        {"Indicador": "Mes de mayor afluencia", "Valor": f"{meses.idxmax()} ({fmt(meses.max())})"},
        {"Indicador": "Mes de menor afluencia", "Valor": f"{meses.idxmin()} ({fmt(meses.min())})"},
    ]
    for y in [2024, 2025]:
        hs = hist_resumen(s, y)
        if hs is not None:
            if hs["meses"] >= 12:
                rows.append({"Indicador": f"Comparación anual con {y}", "Valor": f"{fmt(hs['total'])} histórico; variación {fmt_pct(var_pct(total, hs['total']))}"})
            else:
                rows.append({"Indicador": f"Histórico {y} observado", "Valor": f"{fmt(hs['total'])} entre meses {hs['primer_mes']:02d}-{hs['ultimo_mes']:02d}; no comparable como año completo"})
    h26 = hist_valor(s, 2026)
    if h26 is not None:
        meses_obs = sorted(hist[(hist.servicio == s) & (hist.anio.astype(int) == 2026)]["mes"].astype(int).unique().tolist())
        if meses_obs:
            proy_mismos = float(serv.loc[[f"2027-{m:02d}" for m in meses_obs], s].sum())
            rows.append({"Indicador": f"Comparación con 2026 observado ({min(meses_obs):02d}-{max(meses_obs):02d})", "Valor": f"{fmt(h26)} histórico parcial; 2027 mismos meses {fmt(proy_mismos)}; variación {fmt_pct(var_pct(proy_mismos, h26))}"})
    return pd.DataFrame(rows)


def render_justificacion_servicio(s, serv, uni, detalle):
    total = float(serv[s].sum())
    det_s = detalle[detalle.servicio == s].copy()
    viajes = float(det_s["viajes_operados_plan"].sum())
    pax_viaje = total / viajes if viajes > 0 else 0.0
    h2024 = hist_valor(s, 2024)
    h2025 = hist_valor(s, 2025)

    with st.expander("Justificación metodológica del resultado proyectado", expanded=True):
        st.markdown("""
El resultado proyectado 2027 corresponde al escenario operacional vigente y se construye con base histórica normalizada, calendario operacional, oferta de servicios, tratamiento de feriados y ajustes específicos por servicio. La proyección principal es mensual por servicio; en Biotren, las capas de línea, OD, tipo de tarjeta, ingresos y subsidios distribuyen e interpretan la demanda ya proyectada, sin recalcular la afluencia total.
""")

        resumen_servicios = []
        for servicio in O.SERVICIOS:
            pasajeros_servicio = float(serv[servicio].sum())
            if servicio == "BIOTREN":
                financiero = "Venta, subsidio normal y subsidio estudiante implementados"
                base = "Base histórica, calendario operacional, oferta L1/L2 y distribución posterior MOD/OD"
                ajuste = "Ajuste operacional vigente y distribución posterior de demanda"
                observacion = "Las capas OD/tarjeta/financieras no modifican la afluencia proyectada."
            elif servicio == "CORTO_LAJA":
                financiero = "Sin cálculo tarifario implementado"
                base = "Base histórica y recuperación de demanda"
                ajuste = "Confiabilidad operacional, oferta y supresión acotada"
                observacion = "El resultado se interpreta como recuperación operacional parcial."
            elif servicio == "TREN_ARAUCANIA":
                financiero = "Sin cálculo tarifario implementado"
                base = "Tramos operacionales y calendario 2027"
                ajuste = "Oferta efectiva por tramo y tratamiento de componente escolar"
                observacion = "La demanda se calcula por tipo de servicio, no con proporción fija agregada."
            else:
                financiero = "Sin cálculo tarifario implementado"
                base = "Referencia laboral, comportamiento observado y calendario"
                ajuste = "Moderación del efecto novedad y calibración laboral marzo-diciembre"
                observacion = "El resultado conserva variación mensual por estacionalidad y calendario."
            resumen_servicios.append({
                "Servicio": O.NOMBRE.get(servicio, servicio),
                "Pasajeros 2027": pasajeros_servicio,
                "Base metodológica": base,
                "Ajuste principal": ajuste,
                "Cálculo financiero implementado": financiero,
                "Observación": observacion,
            })
        st.dataframe(
            pd.DataFrame(resumen_servicios),
            width="stretch",
            hide_index=True,
            column_config={"Pasajeros 2027": st.column_config.NumberColumn("Pasajeros 2027", format="%d")},
        )

        st.markdown("#### Lectura del servicio seleccionado")
        st.dataframe(resumen_validacion_servicio(s, serv, uni, detalle), width="stretch", hide_index=True)

        if s == "BIOTREN":
            serie_biotren = serv["BIOTREN"].astype(float).copy()
            try:
                dist_linea = calcular_distribucion_biotren_linea_mod_cached(serie_biotren.to_dict())
                linea_anual = dist_linea.groupby("linea_od", as_index=False).agg(Pasajeros=("viajes_proyectados", "sum"))
                linea_anual["Participación"] = linea_anual["Pasajeros"] / linea_anual["Pasajeros"].sum()
                linea_anual = linea_anual.set_index("linea_od").reindex(["L1", "L2", "L1-L2"]).reset_index().rename(columns={"linea_od": "Línea"})
            except Exception:
                linea_anual = pd.DataFrame(columns=["Línea", "Pasajeros", "Participación"])
            try:
                ingresos_subsidio = calcular_resumen_anual_ingresos_subsidio_biotren_cached(serie_biotren.to_dict())
                anual = ingresos_subsidio["resumen_anual"]
                cobertura = ingresos_subsidio.get("cobertura_estudiante", {})
            except Exception:
                anual = {}
                cobertura = {}

            st.markdown("##### Biotren: proyección, distribución e ingresos")
            st.markdown(f"""
- **Proyección de afluencia:** el modelo estima **{fmt(total)} pasajeros** para Biotren en 2027 desde el escenario operacional vigente.
- **Distribución por línea:** la demanda se distribuye posteriormente entre L1, L2 y L1-L2 con matrices MOD históricas atribuibles.
- **Tipo de tarjeta e ingresos:** la distribución OD por tipo de tarjeta permite estimar venta de pasajes y subsidios sin alterar la demanda mensual.
- **Alcance financiero:** los ingresos y subsidios calculados corresponden sólo a Biotren, no al total del sistema EFE Sur.
""")
            if not linea_anual.empty:
                st.dataframe(
                    linea_anual,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Pasajeros": st.column_config.NumberColumn("Pasajeros", format="%d"),
                        "Participación": st.column_config.NumberColumn("Participación", format="%.2%%"),
                    },
                )

            financiero = pd.DataFrame([
                {
                    "Concepto": "Venta de pasajes",
                    "Grupo considerado": "monedero, media_superior, adulto_mayor",
                    "Base de cálculo": "Tarifas directas por tipo de tarjeta",
                    "Monto anual 2027": anual.get("ingreso_venta", 0.0),
                    "Observación metodológica": "Otros tipos mantienen ingreso directo cero.",
                },
                {
                    "Concepto": "Subsidio normal",
                    "Grupo considerado": "Todas excepto media_superior y adulto_mayor",
                    "Base de cálculo": "Monto_normal_base / (1 - tasa_descuento_normal) - Monto_normal_base",
                    "Monto anual 2027": anual.get("subsidio_normal", 0.0),
                    "Observación metodológica": "Tasa de descuento normal vigente y diagonal en cero.",
                },
                {
                    "Concepto": "Subsidio estudiante",
                    "Grupo considerado": "media_superior",
                    "Base de cálculo": "Ingreso teórico sin subsidio sin diagonal - venta media_superior con diagonal",
                    "Monto anual 2027": anual.get("subsidio_estudiante", 0.0),
                    "Observación metodológica": "No se usa brecha OD max(0, tarifa_sin_subsidio - tarifa_pagada) como fórmula final.",
                },
                {
                    "Concepto": "Subsidio total",
                    "Grupo considerado": "normal + media_superior",
                    "Base de cálculo": "Subsidio normal + subsidio estudiante",
                    "Monto anual 2027": anual.get("subsidio_total", 0.0),
                    "Observación metodológica": "adulto_mayor no integra subsidio normal ni estudiante.",
                },
                {
                    "Concepto": "Ingreso total Biotren",
                    "Grupo considerado": "Biotren",
                    "Base de cálculo": "Venta_pasajes + Subsidio_normal + Subsidio_estudiante",
                    "Monto anual 2027": anual.get("ingreso_total_biotren", 0.0),
                    "Observación metodológica": "Ingreso financiero estimado sólo para Biotren.",
                },
            ])
            st.dataframe(
                financiero,
                width="stretch",
                hide_index=True,
                column_config={"Monto anual 2027": st.column_config.NumberColumn("Monto anual 2027", format="$ %d")},
            )

            with st.expander("Detalle técnico de ingresos y subsidios Biotren", expanded=False):
                st.markdown("""
**Venta de pasajes.** `monedero` usa tarifa normal; `media_superior` usa tarifa estudiante pagada; `adulto_mayor` usa tarifa adulto mayor. `estudiante_basica`, `discapacitado`, `funcionario_normal`, `funcionario_especial` y `convenio_colectivo` no generan venta directa.

**Subsidio normal.** `Subsidio_normal = Monto_normal_base / (1 - tasa_descuento_normal) - Monto_normal_base`, con tarifa normal, grupo normal igual a todas las tarjetas excepto `media_superior` y `adulto_mayor`, y diagonal en cero.

**Subsidio estudiante.** `Subsidio_estudiante = Ingreso_teorico_estudiante_sin_subsidio_sin_diagonal - Venta_media_superior_con_diagonal`. `media_superior` es el único grupo estudiante considerado; la venta real estimada considera diagonal; el ingreso teórico sin subsidio excluye diagonal; esta diferencia de tratamiento es intencional. No se usa como fórmula final `max(0, tarifa_sin_subsidio - tarifa_pagada)` por par OD.

**Ingreso total.** `Ingreso_total_Biotren = Venta_pasajes + Subsidio_normal + Subsidio_estudiante`.
""")

            st.markdown("##### Limitaciones y advertencias")
            st.info("Las capas OD, línea y tipo de tarjeta distribuyen la demanda proyectada de Biotren; no recalculan la afluencia total.")
            st.warning("Los ingresos y subsidios están implementados sólo para Biotren; los otros servicios no tienen cálculo tarifario en el modelo.")
            if cobertura.get("sin_cobertura_modelo"):
                st.warning("Matriz estudiante BT sin subsidio con cobertura parcial; estaciones del modelo sin cobertura: " + ", ".join(cobertura.get("sin_cobertura_modelo", [])))
            if cobertura.get("estaciones_sin_tarifas"):
                st.warning("Estaciones en matriz sin tarifas disponibles hacia/desde otras estaciones: " + ", ".join(cobertura.get("estaciones_sin_tarifas", [])))
            st.info("La diagonal tiene tratamiento diferenciado en subsidio estudiante: venta media_superior con diagonal e ingreso teórico sin subsidio sin diagonal.")
        elif s == "CORTO_LAJA":
            st.markdown(f"""
**Resultado proyectado.** La proyección anual de Laja-Talcahuano alcanza **{fmt(total)} pasajeros**. El resultado combina base histórica, calendario operacional, oferta vigente y recuperación parcial de demanda asociada a confiabilidad operacional.

**Alcance financiero.** El modelo no implementa actualmente cálculo tarifario, ingresos ni subsidios para este servicio. La lectura financiera se limita a Biotren.

**Consistencia histórica.** El resultado queda {fmt_pct(var_pct(total, h2024)) if h2024 else 's/i'} respecto de 2024 y {fmt_pct(var_pct(total, h2025)) if h2025 else 's/i'} respecto de 2025, considerando la información histórica disponible.
""")
        elif s == "TREN_ARAUCANIA":
            tramos = {col: float(uni[col].sum()) for col in ["TA_TEMUCO_VICTORIA", "TA_TEMUCO_PITRUFQUEN", "TA_CLARET"] if col in uni.columns}
            st.markdown(f"""
**Resultado proyectado.** La proyección anual de Tren Araucanía alcanza **{fmt(total)} pasajeros**. El cálculo considera tramos operacionales y oferta efectiva por tipo de servicio.

**Tramos operacionales.** Temuco-Victoria proyecta **{fmt(tramos.get('TA_TEMUCO_VICTORIA', 0))}**, Temuco-Pitrufquén **{fmt(tramos.get('TA_TEMUCO_PITRUFQUEN', 0))}** y Claret **{fmt(tramos.get('TA_CLARET', 0))}** pasajeros. El componente Claret se trata como escolar cuando corresponde.

**Alcance financiero.** El modelo no implementa actualmente cálculo tarifario, ingresos ni subsidios para este servicio.
""")
        elif s == "LLANQUIHUE_PM":
            ene_feb = float(serv.loc[["2027-01", "2027-02"], s].sum())
            st.markdown(f"""
**Resultado proyectado.** La proyección anual de Llanquihue-Puerto Montt alcanza **{fmt(total)} pasajeros**, con **{fmt(ene_feb)}** pasajeros en enero-febrero. La proyección combina referencia laboral, comportamiento observado, calendario y moderación del efecto novedad.

**Perfil mensual.** Marzo-diciembre se calibra con una referencia laboral, sin forzar un valor idéntico en todos los meses. Enero y febrero incorporan menor efecto de novedad del servicio.

**Alcance financiero.** El modelo no implementa actualmente cálculo tarifario, ingresos ni subsidios para este servicio.
""")

        st.markdown("#### Componentes que explican el resultado mensual")
        tabla_comp = tabla_detalle_mes(detalle, s)
        if not tabla_comp.empty:
            vista_comp = tabla_comp[["periodo", "viajes_operados_plan", "demanda_proyectada", "var_oferta_operada_pct", "var_demanda_pct", "elasticidad_media"]].rename(columns={
                "periodo": "Periodo",
                "viajes_operados_plan": "Viajes operados",
                "demanda_proyectada": "Demanda proyectada",
                "var_oferta_operada_pct": "Variación oferta",
                "var_demanda_pct": "Variación demanda",
                "elasticidad_media": "Elasticidad media",
            })
            st.dataframe(
                vista_comp,
                width="stretch",
                hide_index=True,
                column_config={
                    "Viajes operados": st.column_config.NumberColumn("Viajes operados", format="%d"),
                    "Demanda proyectada": st.column_config.NumberColumn("Demanda proyectada", format="%d"),
                    "Variación oferta": st.column_config.NumberColumn("Variación oferta", format="%.2f"),
                    "Variación demanda": st.column_config.NumberColumn("Variación demanda", format="%.2f"),
                    "Elasticidad media": st.column_config.NumberColumn("Elasticidad media", format="%.2f"),
                },
            )
        st.caption("La elasticidad menor que 1 implica rendimiento marginal decreciente: un aumento de oferta eleva la demanda, pero no en la misma proporción que los servicios adicionales.")

def editor_oferta(unit, label, base_df=None):
    if base_df is None:
        sub = params[params.unit == unit].pivot(index="mes", columns="dt", values="servicios_dia")[O.DTYPES]
    else:
        sub = base_df[base_df.unit == unit].pivot(index="mes", columns="dt", values="servicios_dia")[O.DTYPES]
    sub.index.name = "Mes"
    st.caption(f"**{label}** — servicios por día. Cada modificación impacta directamente el mes editado.")
    cfg = {dt: st.column_config.NumberColumn(O.DTNOMBRE[dt], min_value=0.0, step=1.0, format="%.1f") for dt in O.DTYPES}
    ed = st.data_editor(sub, width="stretch", key=f"of_{unit}", column_config=cfg)
    plan = ed.reset_index().melt(id_vars="Mes", var_name="dt", value_name="servicios_dia").rename(columns={"Mes": "mes"})
    plan["unit"] = unit
    plan["mes"] = plan["mes"].astype(int)
    plan["servicios_dia"] = pd.to_numeric(plan["servicios_dia"], errors="coerce")
    return plan[["unit", "mes", "dt", "servicios_dia"]]


def editor_tren_araucania():
    st.info("La oferta se edita por tipo de servicio. Claret se considera servicio escolar y sólo opera entre marzo y diciembre; enero y febrero se fuerzan a cero.")
    base_tramos = O.oferta_tren_araucania_tramos_df(mensual=True)
    cols = st.columns(3)
    planes = []
    for i, unit in enumerate(O.TA_TRAMOS):
        with cols[i]:
            planes.append(editor_oferta(unit, O.TA_TRAMO_NOMBRE[unit], base_df=base_tramos))
    plan_tramos = pd.concat(planes, ignore_index=True)
    plan_tramos.loc[(plan_tramos.unit == "TA_CLARET") & (plan_tramos.mes.isin([1, 2])), "servicios_dia"] = 0.0
    with st.expander("Distribución histórica usada por tipo de servicio"):
        dist = O.perfil_distribucion_tren_araucania_por_tramo()
        piv = dist.pivot(index="mes", columns="unit", values="participacion_demanda_historica")
        piv = piv.rename(columns=O.TA_TRAMO_NOMBRE)
        st.dataframe((piv * 100).round(1), width="stretch")
        st.caption("Participación mensual ponderada con TA-Dist.xlsx. Claret queda en 0% para enero y febrero. La respuesta ante cambios de oferta se calcula tramo por tramo, no como redistribución estática 13/87.")
    return plan_tramos, plan_tramos


def _referencia_servicio_disponible(s):
    return s in set(REF_SERVICIO_TO_MODELO.values())


def _referencia_servicio_mensual(s, serv):
    if not _referencia_servicio_disponible(s):
        return pd.DataFrame()
    mensual = construir_referencia_mensual_visual(serv)
    return mensual[mensual["servicio_modelo"].eq(s)].copy().sort_values(["anio", "mes_num"])


def _referencia_servicio_anual(s, serv):
    if not _referencia_servicio_disponible(s):
        return pd.DataFrame()
    anual = construir_referencia_anual_visual(serv)
    return anual[anual["servicio_modelo"].eq(s)].copy().sort_values("anio")


def grafico_historico_y_proyeccion(s, serv):
    fig = go.Figure()
    ref = _referencia_servicio_mensual(s, serv)
    if not ref.empty:
        for tipo in ["Histórico observado", "Cierre 2026 estimado", "Proyección 2027 modelo"]:
            d = ref[ref["tipo_dato_label"].eq(tipo)].copy()
            if d.empty:
                continue
            fig.add_trace(go.Scatter(
                x=d["periodo"].astype(str),
                y=d["afluencia"].astype(float),
                name=tipo,
                mode="lines+markers" if tipo != "Histórico observado" else "lines",
                line=dict(
                    color=REF_TIPO_COLOR[tipo],
                    width=3 if tipo != "Histórico observado" else 2,
                    dash="dash" if tipo == "Proyección 2027 modelo" else "solid",
                ),
                marker=dict(size=7),
            ))
    else:
        st.info("La referencia histórica normalizada de cierre 2026 está disponible sólo para Biotren, Laja-Talcahuano y Tren Araucanía; no se extrapola histórico para este servicio.")
        fig.add_trace(go.Scatter(
            x=list(serv.index),
            y=serv[s].astype(float),
            name="Proyección 2027 modelo",
            mode="lines+markers",
            line=dict(color=REF_TIPO_COLOR["Proyección 2027 modelo"], width=3, dash="dash"),
        ))
    fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.15, x=0),
                      hovermode="x unified", font=dict(family="Segoe UI", color="#0f2740"))
    fig.update_xaxes(showgrid=False, title="Periodo")
    fig.update_yaxes(gridcolor="#eef2f7", title="pasajeros/mes")
    st.plotly_chart(fig, width="stretch")


def tabla_referencia_anual_servicio(s, serv):
    anual = _referencia_servicio_anual(s, serv)
    if anual.empty:
        return pd.DataFrame()
    tabla = anual[["anio", "tipo_dato_label", "afluencia_anual"]].rename(columns={
        "anio": "año",
        "tipo_dato_label": "tipo de dato",
        "afluencia_anual": "total anual",
    })
    tabla["observación metodológica"] = tabla["tipo de dato"].map({
        "Histórico observado": "Registro histórico observado normalizado desde el CSV de referencia.",
        "Cierre 2026 estimado": "Estimación de cierre anual 2026; no corresponde a observado definitivo.",
        "Proyección 2027 modelo": "Resultado vigente del motor operacional 2027; no recalibrado por el cierre 2026.",
    })
    return tabla


def tabla_historica_servicio(s):
    h = hist[hist.servicio == s].copy()
    if h.empty:
        return pd.DataFrame()
    h["mes"] = h["mes"].map(lambda x: f"{int(x):02d}")
    piv = h.pivot_table(index="mes", columns="anio", values="afluencia_mensual_normalizada", aggfunc="first")
    return piv.round(0).astype("Int64")


def tabla_detalle_mes(detalle, s):
    d = detalle[detalle.servicio == s].copy()
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(["periodo", "mes"]).agg(
        servicios_dia_base=("servicios_dia", "sum"),
        servicios_dia_plan=("servicios_dia_plan", "sum"),
        viajes_operados_base=("viajes_operados_base", "sum"),
        viajes_operados_plan=("viajes_operados_plan", "sum"),
        demanda_base=("demanda_base_mensual", "sum"),
        demanda_proyectada=("afl", "sum"),
        elasticidad_media=("elasticidad", "mean"),
        factor_estacionalidad_medio=("factor_estacionalidad", "mean"),
    ).reset_index().sort_values("mes")
    g["impacto_mes_vs_base"] = g["demanda_proyectada"] - g["demanda_base"]
    g["var_oferta_operada_pct"] = (g["viajes_operados_plan"] / g["viajes_operados_base"].replace(0, pd.NA) - 1) * 100
    g["var_demanda_pct"] = (g["demanda_proyectada"] / g["demanda_base"].replace(0, pd.NA) - 1) * 100
    cols = ["periodo", "servicios_dia_base", "servicios_dia_plan", "viajes_operados_base", "viajes_operados_plan",
            "demanda_base", "demanda_proyectada", "impacto_mes_vs_base", "var_oferta_operada_pct", "var_demanda_pct", "elasticidad_media"]
    return g[cols].round({"servicios_dia_base": 1, "servicios_dia_plan": 1, "viajes_operados_base": 0,
                          "viajes_operados_plan": 0, "demanda_base": 0, "demanda_proyectada": 0,
                          "impacto_mes_vs_base": 0, "var_oferta_operada_pct": 1,
                          "var_demanda_pct": 1, "elasticidad_media": 2})





def tabla_calendario_servicio(s):
    cal = O.calendario_operacional_resumen(2027).copy()
    if s == "BIOTREN":
        units = ["BIOTREN_L1", "BIOTREN_L2"]
    elif s == "TREN_ARAUCANIA":
        units = O.TA_TRAMOS
    else:
        units = O.UNIDADES_DE[s]
    cal = cal[cal["unit"].isin(units)].copy()
    cal["mes"] = cal["mes"].map(lambda x: f"{int(x):02d}")
    return cal.sort_values(["unit", "mes", "dt"])


def tabla_feriados_2027():
    f = O.feriados_chile(2027).copy()
    if f.empty:
        return f
    f["fecha"] = f["fecha"].dt.strftime("%Y-%m-%d")
    return f.rename(columns={"dt_calendario": "tipo_dia_calendario"})


def render_ecuacion_servicio(s):
    """Muestra la ecuación específica usada por el motor para el servicio seleccionado."""
    e = O.ELASTICIDAD_OFERTA_SERVICIO.get(s, 0.45)
    fn = O.AJUSTE_NIVEL_SERVICIO.get(s, 1.0)
    fe = O.FUERZA_ESTACIONALIDAD.get(s, 0.5)
    st.markdown("#### Ecuación específica de proyección")

    if s == "BIOTREN":
        latex = r"""
        D_{\mathrm{BT},m} =
        \sum_{u \in \{L1,L2\}}\sum_{d \in \{LV,Sab,Dom\}}
        \left[
        S_{1,u,m,d}\,N^{op}_{u,m,d}\,(1-\tau_{u,m,d}-c_u)\,q_{u,m,d}\,FN\,F_{est,\mathrm{BT},m}
        \left(\frac{V_{1,u,m,d}}{V_{0,u,m,d}}\right)^{EPS}
        \right]
        """
        st.latex(latex.replace("FN", f"{fn:.3f}").replace("EPS", f"{e:.2f}"))
        st.caption(f"Biotren usa días operacionales sin feriados nacionales, elasticidad de oferta {e:.2f}, factor de nivel {fn:.3f} y fuerza estacional {fe:.2f}. La suma operacional se realiza sobre L1 y L2; Laja-Talcahuano se mantiene separado para evitar doble conteo. El perfil mensual incorpora un tratamiento estacional del bloque marzo-abril para mantener una trayectoria mensual coherente con la evidencia histórica disponible.")

    elif s == "CORTO_LAJA":
        latex = r"""
        D_{\mathrm{LT},m} =
        \sum_{d \in \{LV,Sab,Dom\}}
        \left[
        S_{1,\mathrm{LT},m,d}\,N^{op}_{\mathrm{LT},m,d}\,(1-\tau^*_{\mathrm{LT},m,d}-c)\,q_{\mathrm{LT},m,d}\,FN\,F_{est,\mathrm{LT},m}
        \left(\frac{V_{1,\mathrm{LT},m,d}}{V_{0,\mathrm{LT},m,d}}\right)^{EPS}
        \right]
        """
        st.latex(latex.replace("FN", f"{fn:.3f}").replace("EPS", f"{e:.2f}"))
        st.latex(r"\tau^*_{\mathrm{LT},m,d}=\min(\tau_{\mathrm{LT},m,d},0.01)")
        st.caption(f"Laja-Talcahuano opera feriados con oferta de fin de semana e incorpora recuperación de confiabilidad: supresión base acotada a 1%, mayor peso del patrón histórico de mejor desempeño y factor de recuperación {fn:.3f}. Esto permite representar una recuperación operacional parcial sin asumir el máximo histórico como meta directa.")

    elif s == "TREN_ARAUCANIA":
        st.latex(r"""
        D_{\mathrm{TA},m}=\sum_{r\in\{VT,PT,CL\}}D_{r,m}
        """)
        st.latex(r"""
        D_{r,m}=D^{base}_{\mathrm{TA},m}\cdot\alpha_{r,m}^{hist}\cdot
        \left(\frac{V_{1,r,m}}{V_{0,r,m}}\right)^{\varepsilon_r}
        """)
        st.latex(r"""
        V_{r,m}=\sum_{d\in\{LV,Sab,Dom\}}S_{r,m,d}\cdot N^{op}_{r,m,d}\cdot(1-\tau_{\mathrm{TA},m,d}-c)
        """)
        st.latex(r"\alpha_{CL,m}=0\quad\text{para }m\in\{enero,febrero\}")
        st.caption("Tren Araucanía no opera feriados nacionales en el escenario base y usa distribución mensual observada por tipo de servicio. La oferta se edita por tramo y cada tramo tiene elasticidad diferenciada: Victoria-Temuco 0,46; Pitrufquén-Temuco 0,28; Claret 0,12. Así, un aumento en Victoria-Temuco genera mayor efecto que un aumento equivalente en Pitrufquén o Claret.")

    elif s == "LLANQUIHUE_PM":
        latex = r"""
        D_{\mathrm{LLPM},m} =
        \sum_{d \in \{LV,Sab,Dom\}}
        \left[
        S_{1,\mathrm{LLPM},m,d}\,N^{op}_{\mathrm{LLPM},m,d}\,(1-\tau_{\mathrm{LLPM},m,d}-c)\,q_{\mathrm{LLPM},m,d}\,FN\,F_{est,\mathrm{LLPM},m}
        \left(\frac{V_{1,\mathrm{LLPM},m,d}}{V_{0,\mathrm{LLPM},m,d}}\right)^{EPS}
        \right]
        """
        st.latex(latex.replace("FN", f"{fn:.3f}").replace("EPS", f"{e:.2f}"))
        st.caption(f"Llanquihue-Puerto Montt no opera feriados nacionales en el escenario base y conserva una señal estival en enero-febrero. Se aplica elasticidad de oferta {e:.2f}; los días sábado y domingo quedan en cero salvo modificación explícita de oferta.")

def render_metodologia():
    st.markdown("### Marco metodológico del modelo")
    st.markdown("""
<div class="method">
<b>Propósito.</b> El modelo estima la afluencia mensual 2027 por servicio y permite analizar escenarios de oferta por mes y tipo de día.
<br><br>
<b>Escenario operacional vigente.</b> Biotren: 12.673.199; Tren Araucanía: 840.777; Llanquihue-Puerto Montt: 412.132; Laja-Talcahuano: 540.842; total sistema: 14.889.050 pasajeros.
<br><br>
<b>Separación metodológica.</b> La proyección base mensual, el backtesting histórico diagnóstico y las bandas de incertidumbre se mantienen como componentes diferenciados.
</div>
""", unsafe_allow_html=True)

    with st.expander("1. Secuencia metodológica", expanded=True):
        st.markdown("""
1. El modelo construye una proyección mensual por servicio.
2. La proyección considera calendario operacional, oferta, feriados, productividad, estacionalidad y supuestos específicos.
3. Cada servicio se trata de forma independiente según sus reglas operacionales.
4. Sólo Biotren incorpora módulos posteriores de distribución por línea OD, distribución OD por tipo de tarjeta, ingresos tarifarios preliminares y base referencial de subsidio.
5. El backtesting histórico es retrospectivo diagnóstico no holdout.
6. Las bandas de incertidumbre derivan del backtesting diagnóstico, no reemplazan el escenario base y se calculan sobre la base 2027 vigente.
""")

    with st.expander("2. Tratamiento por servicio", expanded=False):
        st.markdown("""
- **Biotren:** proyecta **12.673.199 pasajeros**. La proyección incorpora ajuste base progresivo hacia un nivel intermedio cercano a 12,8 millones, afectación operacional de Línea 2 en fines de semana de enero-febrero y ajuste residual en meses laborales. El resultado queda cercano al objetivo operacional de 12,7 millones.
- **Tren Araucanía:** proyecta **840.777 pasajeros**. Victoria-Temuco opera con 11 servicios lunes-viernes durante 2027. La metodología separa Temuco-Victoria, Temuco-Pitrufquén y Claret; Claret es un componente escolar específico de marzo-diciembre. El perfil mensual combina patrón histórico, calendario, control técnico de marzo, refuerzo de mayo por coherencia marzo-mayo 2026 e incremento marginal del resto de meses preservando el perfil 2025.
- **Llanquihue-Puerto Montt:** proyecta **412.132 pasajeros**. Marzo-diciembre se calibra con un promedio laboral referencial cercano a 1.500 pasajeros por día laboral; el promedio del bloque es aproximadamente 1.499,85. Enero y febrero incorporan reducción por menor efecto de novedad.
- **Laja-Talcahuano:** proyecta **540.842 pasajeros**. No recibe ajuste operacional específico nuevo; mantiene su patrón histórico, oferta operacional, calendario y regla de feriados como operación de fin de semana.
""")
        st.info("Tren Araucanía, Llanquihue-Puerto Montt y Laja-Talcahuano no utilizan MOD Biotren, categorías L1/L2/L1-L2, tipo de tarjeta, ingresos ni base referencial de subsidio Biotren.")

    with st.expander("3. Calendario operacional, oferta y feriados", expanded=False):
        st.info("Para Biotren, Tren Araucanía y Llanquihue-Puerto Montt, los feriados nacionales tienen oferta efectiva cero. Para Laja-Talcahuano, los feriados operan con oferta de fin de semana; si el feriado cae lunes-viernes se imputa como domingo operacional.")
        st.markdown("La oferta de escenario se aplica por mes y tipo de día. Una modificación de oferta afecta el mes editado y el total anual por agregación de meses.")
        st.dataframe(tabla_feriados_2027(), width="stretch", height=240)
        st.markdown("**Resumen de días operacionales por unidad, mes y tipo de día**")
        st.dataframe(O.calendario_operacional_resumen(2027), width="stretch", height=280)

    with st.expander("4. Biotren: distribución por línea OD basada en MOD", expanded=False):
        st.markdown("""
La demanda total mensual de Biotren proviene del modelo temporal. La MOD histórica atribuible no genera ese total; sólo distribuye la demanda ya proyectada.

- **Categorías estándar:** `L1`, `L2` y `L1-L2`.
- **Concepción:** estación común/intercambio; `Concepción → Concepción` queda como control `No clasificado` y no recibe proyección estándar.
- **Criterio vigente:** el supuesto fijo 80/20 no corresponde a la metodología vigente; fue reemplazado por participaciones mensuales basadas en MOD histórica atribuible.
- **Validación:** la suma mensual `L1 + L2 + L1-L2` conserva el total mensual de Biotren.
""")

    with st.expander("5. Biotren: tipo de tarjeta, ingresos y subsidio", expanded=False):
        st.markdown("""
La distribución OD por tipo de tarjeta se recalcula sobre el total mensual vigente de Biotren.

**Tipos con ingreso tarifario directo:** `monedero`, `media_superior` y `adulto_mayor`.

**Tipos con tarifa cero:** `estudiante_basica`, `discapacitado`, `funcionario_normal`, `funcionario_especial` y `convenio_colectivo`.

Los ingresos son preliminares y no incorporan subsidios, evasión, ajustes contables ni reglas comerciales adicionales. La base de subsidio es referencial y no calcula montos monetarios.
""")

    with st.expander("6. Backtesting e incertidumbre", expanded=False):
        st.markdown("""
El backtesting histórico compara observado vs estimado en periodos conocidos. Es una validación retrospectiva diagnóstica no holdout y no reemplaza la proyección operacional 2027.

Las bandas de incertidumbre derivan de métricas históricas de error, especialmente WMAPE. No son intervalos estadísticos formales ni intervalos de confianza. El ajuste por sesgo es una sensibilidad diagnóstica. Las bandas se calculan sobre la base vigente: Biotren 12.673.199; Tren Araucanía 840.777; Llanquihue-Puerto Montt 412.132; Laja-Talcahuano 540.842.
""")

    with st.expander("7. Validaciones y limitaciones", expanded=False):
        st.markdown("""
**Validaciones:** conservación de totales mensuales, suma de participaciones MOD por línea, `No clasificado` sin proyección estándar, consistencia por tipo de tarjeta, ingresos sólo en tipos con tarifa aplicable, feriados por servicio, backtesting diagnóstico, bandas de incertidumbre sin valores negativos y ausencia de binarios versionados.

**Limitaciones:** elasticidades agregadas, OD dependiente de datos históricos disponibles, ingresos preliminares, ausencia de cálculo monetario de subsidios, capacidad, ocupación, tiempos de viaje y confiabilidad diaria detallada.
""")

    st.markdown("#### Bibliografía")
    st.markdown("""
- Transportation Research Board. *TCRP Report 95, Chapter 9: Transit Scheduling and Frequency*. Washington, D.C., 2004. https://trb.org/publications/tcrp/tcrp_rpt_95c9.pdf
- Balcombe, R. et al. *The Demand for Public Transport: A Practical Guide*. TRL Report TRL593, 2004. https://www.trl.co.uk/uploads/trl/documents/TRL593%20-%20The%20Demand%20for%20Public%20Transport.pdf
- Paulley, N. et al. *The demand for public transport: The effects of fares, quality of service, income and car ownership*. Transport Policy, 13(4), 295-306, 2006. https://eprints.whiterose.ac.uk/id/eprint/2034/1/ITS23_The_demand_for_public_transport_UPLOADABLE.pdf
- Berrebi, S., Joshi, S. & Watkins, K. *On Ridership and Frequency*. Transportation Research Part A, 2021. https://doi.org/10.48550/arXiv.2002.02493
- Feriados de Chile. *Feriados de Chile — Año 2027*. Fuente basada en Biblioteca del Congreso Nacional. https://www.feriados.cl/2027.htm
""")

def render_validacion_historica():
    st.markdown("### Validación histórica — backtesting")
    st.info("El backtesting compara observado vs estimado en periodos históricos conocidos. Es una validación retrospectiva diagnóstica, no un holdout estricto ni una garantía predictiva; no recalibra ni altera el escenario vigente 2027.")
    try:
        bt = BT.ejecutar_backtesting(params, mdf)
    except Exception as e:
        st.warning(f"No fue posible ejecutar el backtesting histórico: {e}")
        return

    anios_bt = sorted(bt.observado_estimado["anio"].dropna().astype(int).unique().tolist())
    meses_bt = int(len(bt.observado_estimado))
    with st.expander("Alcance metodológico del backtesting", expanded=True):
        st.markdown(f"""
- **Tipo:** `{BT.BACKTESTING_TIPO}`; corresponde a una revisión retrospectiva diagnóstica, no a una validación holdout fuera de muestra.
- **Periodos evaluados:** años {", ".join(map(str, anios_bt))}; se incluyen sólo meses con observación histórica disponible ({meses_bt} filas servicio-mes).
- **Observado:** afluencia mensual normalizada `pax_norm`, con columna de cobertura para advertir meses incompletos.
- **Estimado:** motor mensual-elástico y parámetros vigentes cargados por la aplicación; pueden incorporar información posterior al periodo evaluado.
- **Interpretación:** WMAPE es la métrica agregada principal; MAPE se muestra como referencia y puede ser inestable en servicios o meses de baja afluencia.
""")

    total = bt.resumen_total_sistema.iloc[0]
    k = st.columns(5)
    k[0].metric("MAE sistema", fmt(total["MAE"]))
    k[1].metric("RMSE sistema", fmt(total["RMSE"]))
    k[2].metric("MAPE sistema", f"{total['MAPE']:.1f}%")
    k[3].metric("WMAPE sistema", f"{total['WMAPE']:.1f}%")
    k[4].metric("Sesgo sistema", f"{total['sesgo']:+.1f}%")

    st.markdown("#### Métricas por servicio")
    ms = bt.metricas_servicio.copy()
    ms["servicio"] = ms["servicio"].map(lambda x: O.NOMBRE.get(x, x))
    st.dataframe(ms, width="stretch", hide_index=True)

    st.markdown("#### Tabla observado vs estimado por mes")
    comp = bt.observado_estimado.copy()
    comp["servicio"] = comp["servicio"].map(lambda x: O.NOMBRE.get(x, x))
    st.dataframe(comp[["servicio", "periodo", "observado", "estimado", "error", "error_abs", "error_pct", "cobertura"]], width="stretch", height=360)

    st.markdown("#### Errores mensuales agregados del sistema")
    err = comp.groupby("periodo", as_index=False).agg(observado=("observado", "sum"), estimado=("estimado", "sum"))
    err["error"] = err["estimado"] - err["observado"]
    err["error_abs"] = err["error"].abs()
    err["error_pct"] = err["error"] / err["observado"].replace(0, pd.NA)
    st.dataframe(err, width="stretch", height=260)

    st.markdown("#### Advertencias metodológicas")
    for warning in bt.advertencias:
        st.warning(warning)



def render_evolucion_historica_cierre_proyeccion(serv):
    st.markdown("#### Evolución histórica, cierre 2026 y proyección 2027")
    st.info(
        "Los CSV normalizados de cierre 2026 se usan exclusivamente como referencia visual. "
        "El cierre 2026 se rotula como estimado y no recalibra ni modifica la proyección operacional 2027 vigente."
    )
    anual = construir_referencia_anual_visual(serv)
    mensual = construir_referencia_mensual_visual(serv)

    servicios = list(REF_SERVICIO_TO_MODELO.values())
    servicio_sel = st.selectbox(
        "Servicio",
        servicios,
        format_func=lambda x: O.NOMBRE.get(x, x),
        key="ref_cierre_2026_servicio",
    )

    anual_s = anual[anual["servicio_modelo"].eq(servicio_sel)].copy().sort_values("anio")
    mensual_s = mensual[mensual["servicio_modelo"].eq(servicio_sel)].copy()

    fig = go.Figure()
    for tipo in ["Histórico observado", "Cierre 2026 estimado", "Proyección 2027 modelo"]:
        d = anual_s[anual_s["tipo_dato_label"].eq(tipo)].sort_values("anio")
        if d.empty:
            continue
        modo = "lines+markers" if tipo == "Histórico observado" else "markers"
        fig.add_trace(go.Scatter(
            x=d["anio"].astype(int),
            y=d["afluencia_anual"].astype(float),
            name=tipo,
            mode=modo,
            marker=dict(size=11),
            line=dict(color=REF_TIPO_COLOR[tipo], width=3, dash="dash" if tipo != "Histórico observado" else "solid"),
        ))
    fig.update_layout(height=360, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12, x=0),
                      hovermode="x unified", font=dict(family="Segoe UI", color="#0f2740"))
    fig.update_xaxes(dtick=1, showgrid=False, title="Año")
    fig.update_yaxes(gridcolor="#eef2f7", title="pasajeros/año")
    st.plotly_chart(fig, width="stretch")

    mensual_cmp = mensual_s[mensual_s["anio"].isin([2026, 2027])].copy().sort_values(["anio", "mes_num"])
    fig_m = go.Figure()
    for tipo in ["Cierre 2026 estimado", "Proyección 2027 modelo"]:
        d = mensual_cmp[mensual_cmp["tipo_dato_label"].eq(tipo)]
        if d.empty:
            continue
        fig_m.add_trace(go.Scatter(
            x=d["mes_num"].astype(int),
            y=d["afluencia"].astype(float),
            name=tipo,
            mode="lines+markers",
            line=dict(color=REF_TIPO_COLOR[tipo], width=3, dash="dash" if tipo == "Proyección 2027 modelo" else "solid"),
        ))
    fig_m.update_layout(height=320, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.12, x=0),
                        hovermode="x unified", font=dict(family="Segoe UI", color="#0f2740"))
    fig_m.update_xaxes(dtick=1, range=[0.7, 12.3], showgrid=False, title="Mes")
    fig_m.update_yaxes(gridcolor="#eef2f7", title="pasajeros/mes")
    st.plotly_chart(fig_m, width="stretch")

    tabla = anual_s[["anio", "tipo_dato_label", "afluencia_anual"]].rename(columns={
        "anio": "año",
        "tipo_dato_label": "tipo de dato",
        "afluencia_anual": "afluencia",
    })
    tabla["observación metodológica"] = tabla["tipo de dato"].map({
        "Histórico observado": "Registro histórico observado normalizado desde el CSV de referencia.",
        "Cierre 2026 estimado": "Estimación de cierre anual 2026; no corresponde a observado definitivo.",
        "Proyección 2027 modelo": "Resultado vigente del motor operacional 2027; no recalibrado por el cierre 2026.",
    })
    st.dataframe(tabla.style.format({"afluencia": "{:,.0f}"}), width="stretch", hide_index=True, height=300)


def _resumen_kpi_servicio(s, serv, detalle):
    serie = serv[s].astype(float).copy()
    total = float(serie.sum())
    cierre_2026 = _cierre_2026_servicio(s, serv)
    if s == "BIOTREN":
        resumen_ocup = O.resumen_ocupacion_biotren(serie, 2027)
        servicios_total = float(resumen_ocup["servicios_comerciales_anuales"])
        pax_servicio = float(resumen_ocup["pax_servicio_comercial_anual"])
        detalle_indicador = "pax/servicio comercial"
    else:
        viajes_m = _servicios_mensuales_desde_detalle(detalle, s, serie.index)
        servicios_total = float(viajes_m.sum())
        pax_servicio = total / servicios_total if servicios_total > 0 else 0.0
        detalle_indicador = "pax/servicio"
    return {
        "nombre": O.NOMBRE[s],
        "total": total,
        "total_compacto": fmt_compacto_efe(total),
        "total_detalle": fmt_num_efe(total, 0),
        "pax_servicio": pax_servicio,
        "pax_servicio_detalle": f"{fmt_num_efe(pax_servicio, 1)} {detalle_indicador}",
        "servicios_total": servicios_total,
        "servicios_compacto": fmt_compacto_efe(servicios_total),
        "servicios_detalle": fmt_num_efe(servicios_total, 0),
        "delta": fmt_delta_vs(total, cierre_2026),
    }


def render_resumen():
    uni, serv, detalle = O.proyectar_mensual_elastico(params, mdf, return_detalle=True)
    efe_service_header(
        "Resumen 2027 recalibrado",
        "Vista consolidada de afluencia proyectada por servicio, con indicadores consistentes respecto de cada sección específica.",
        "Proyección 2027",
    )
    st.info("El total anual es la suma de los meses proyectados. El escenario 2027 recalibrado conserva trazabilidad contra el escenario anterior y aplica supuestos operacionales específicos por servicio.")

    cards = []
    for s in O.SERVICIOS:
        kpi = _resumen_kpi_servicio(s, serv, detalle)
        cards.append({
            "titulo": kpi["nombre"],
            "valor": kpi["total_compacto"],
            "detalle": kpi["total_detalle"],
            "delta": kpi["delta"],
            "nota": kpi["pax_servicio_detalle"],
            "icono": "👥",
        })
    render_metric_grid(cards, cols_per_row=4)

    st.markdown("#### Comparación contra escenario anterior")
    escenario_anterior = {"BIOTREN": 12991160.0, "CORTO_LAJA": 540842.0, "TREN_ARAUCANIA": 950258.0, "LLANQUIHUE_PM": 420853.0}
    motivos = {
        "BIOTREN": "Baja progresiva, afectación L2 fines de semana y ajuste residual laboral",
        "TREN_ARAUCANIA": "Victoria-Temuco 11 servicios L-V y suavizamiento de marzo",
        "LLANQUIHUE_PM": "Promedio laboral marzo-diciembre y menor efecto novedad estival",
        "CORTO_LAJA": "Sin ajuste específico nuevo",
    }
    comp = pd.DataFrame([{
        "servicio": O.NOMBRE[k],
        "total anterior": escenario_anterior[k],
        "total recalibrado": float(serv[k].sum()),
        "diferencia": float(serv[k].sum()) - escenario_anterior[k],
        "diferencia %": (float(serv[k].sum()) / escenario_anterior[k] - 1.0) * 100.0,
        "motivo principal": motivos[k],
    } for k in O.SERVICIOS])
    st.dataframe(comp.style.format({"total anterior":"{:,.0f}", "total recalibrado":"{:,.0f}", "diferencia":"{:,.0f}", "diferencia %":"{:+.2f}%"}), width="stretch", hide_index=True)

    diag_detalle = detalle.groupby(["servicio", "mes"], as_index=False)["afl"].sum()
    if not diag_detalle.empty:
        bt = serv["BIOTREN"].astype(float)
        st.caption(f"Biotren queda a {fmt(abs(bt.sum() - 12_700_000))} pasajeros del objetivo de 12,7 millones. Los indicadores mostrados en esta pestaña son consistentes con los reportados en la sección específica de cada servicio.")

    fig = go.Figure()
    for s in O.SERVICIOS:
        fig.add_trace(go.Scatter(x=list(serv.index), y=serv[s].astype(float), name=O.NOMBRE[s],
                                 mode="lines+markers", line=dict(color=PAL[s], width=3)))
    fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1, x=0),
                      hovermode="x unified", font=dict(family="Segoe UI", color="#0f2740"))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eef2f7", title="pax/mes")
    st.plotly_chart(fig, width="stretch")

    render_evolucion_historica_cierre_proyeccion(serv)

    st.markdown("#### Proyección mensual 2027")
    st.dataframe(serv, width="stretch")

    st.markdown("#### Calendario operacional 2027 aplicado")
    st.dataframe(O.calendario_operacional_resumen(2027), width="stretch", height=260)

    st.markdown("#### Comportamiento histórico anual observado")
    st.dataframe(hist_anual, width="stretch")

    tramos_ta = uni[[c for c in uni.columns if str(c).startswith("TA_")]].copy()
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("⬇ Resumen por servicio", serv.to_csv().encode(), "proyeccion_2027_resumen_mensual_elastico.csv")
    c2.download_button("⬇ Detalle por unidad", uni.to_csv().encode(), "proyeccion_2027_unidades_mensual_elastico.csv")
    c3.download_button("⬇ Tren Araucanía por tramo", tramos_ta.to_csv().encode(), "proyeccion_2027_tren_araucania_tramos.csv")
    c4.download_button("⬇ Detalle de cálculo", detalle.to_csv(index=False).encode(), "detalle_calculo_mensual_elastico.csv")



def _serie_biotren_vigente_pre_redistribucion(serv):
    mensual_recal = pd.DataFrame(serv.attrs.get("recalibracion_2027", {}).get("mensual", []))
    if mensual_recal.empty or "proyeccion_vigente_pre_redistribucion" not in mensual_recal.columns:
        return serv["BIOTREN"].astype(float)
    vigente = mensual_recal[mensual_recal["servicio"].eq("BIOTREN")].set_index("mes")["proyeccion_vigente_pre_redistribucion"].astype(float)
    vigente.index = [f"2027-{int(m):02d}" for m in vigente.index]
    return vigente.reindex(serv.index).astype(float)


def _tabla_financiera_biotren(anual_sub, venta_por_tipo):
    return pd.DataFrame([
        {
            "Concepto": "Venta de pasajes",
            "Grupo considerado": "Biotren",
            "Base de cálculo": "monedero normal + media_superior estudiante pagada + adulto_mayor",
            "Monto anual": anual_sub.get("ingreso_venta", sum(venta_por_tipo.values())),
            "Observación": "Corresponde sólo a Biotren; otros tipos de tarjeta mantienen ingreso directo cero.",
        },
        {
            "Concepto": "Subsidio normal",
            "Grupo considerado": "Todas las tarjetas excepto media_superior y adulto_mayor",
            "Base de cálculo": "Monto normal base / (1 - tasa_descuento_normal) - monto normal base",
            "Monto anual": anual_sub.get("subsidio_normal", 0.0),
            "Observación": "Usa tasa parametrizada; no modifica la afluencia mensual.",
        },
        {
            "Concepto": "Subsidio estudiante",
            "Grupo considerado": "media_superior",
            "Base de cálculo": "Ingreso teórico estudiante sin subsidio sin diagonal - venta media_superior con diagonal",
            "Monto anual": anual_sub.get("subsidio_estudiante", 0.0),
            "Observación": "Fórmula oficial agregada; la brecha OD se mantiene sólo como diagnóstico.",
        },
        {
            "Concepto": "Subsidio total",
            "Grupo considerado": "Biotren",
            "Base de cálculo": "Subsidio normal + subsidio estudiante",
            "Monto anual": anual_sub.get("subsidio_total", 0.0),
            "Observación": "No corresponde al total del sistema EFE Sur.",
        },
        {
            "Concepto": "Ingreso total Biotren",
            "Grupo considerado": "Biotren",
            "Base de cálculo": "Venta de pasajes + subsidio normal + subsidio estudiante",
            "Monto anual": anual_sub.get("ingreso_total_biotren", 0.0),
            "Observación": "Resultado financiero anual exclusivo de Biotren.",
        },
    ])



def render_ocupacion_mensual_biotren(serie):
    resumen = O.resumen_ocupacion_biotren(serie, 2027)
    diag = resumen["diagnostico_mensual"].copy()
    bandas_color = {
        "Baja utilización": "#64748b",
        "Operación estable": "#1f6feb",
        "Alta utilización": "#0e9f6e",
        "Tensión operacional": "#dc2626",
    }

    st.markdown("### 4. Ocupación mensual y bandas de funcionamiento")
    st.caption("El indicador principal usa servicios comerciales programados; la capacidad equivalente se muestra sólo como diagnóstico técnico.")
    c = st.columns(6)
    c[0].metric("Pax/servicio comercial", f"{resumen['pax_servicio_comercial_anual']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c[1].metric("Pax/capacidad equivalente", f"{resumen['pax_capacidad_equivalente_anual']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c[2].metric("Mayor ocupación", f"Mes {resumen['mes_mayor_pax_servicio_comercial']}")
    c[3].metric("Menor ocupación", f"Mes {resumen['mes_menor_pax_servicio_comercial']}")
    c[4].metric("Meses baja utilización", int(resumen["meses_por_banda"].get("Baja utilización", 0)))
    alta_tension = int(resumen["meses_por_banda"].get("Alta utilización", 0) + resumen["meses_por_banda"].get("Tensión operacional", 0))
    c[5].metric("Meses alta/tensión", alta_tension)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=diag["mes"],
        y=diag["pax_servicio_comercial"],
        mode="lines+markers",
        name="Pax/servicio comercial",
        marker=dict(color=[bandas_color[b] for b in diag["banda_funcionamiento"]], size=9),
        line=dict(color="#1f6feb", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=diag["mes"],
        y=diag["pax_capacidad_equivalente"],
        mode="lines+markers",
        name="Pax/capacidad equivalente (diagnóstico)",
        marker=dict(color="#94a3b8", size=7),
        line=dict(color="#94a3b8", width=2, dash="dot"),
    ))
    fig.add_hline(y=300, line_dash="dash", line_color="#dc2626", annotation_text="Referencia 300", annotation_position="top left")
    fig.update_layout(height=360, xaxis_title="Mes", yaxis_title="Pasajeros por servicio", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

    visible = diag[["mes", "afluencia_biotren", "servicios_comerciales", "pax_servicio_comercial", "banda_funcionamiento"]].rename(columns={
        "mes": "Mes",
        "afluencia_biotren": "Afluencia 2027",
        "servicios_comerciales": "Servicios comerciales",
        "pax_servicio_comercial": "Pax/servicio comercial",
        "banda_funcionamiento": "Banda",
    })
    st.dataframe(
        visible,
        width="stretch",
        hide_index=True,
        height=260,
        column_config={
            "Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"),
            "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d"),
            "Pax/servicio comercial": st.column_config.NumberColumn("Pax/servicio comercial", format="%.1f"),
        },
    )

    with st.expander("Diagnóstico técnico de capacidad equivalente", expanded=False):
        st.markdown("La ocupación principal se calcula sobre servicios comerciales programados. Los servicios acoplados de L2 se incorporan sólo en el diagnóstico de capacidad equivalente, dado que aumentan la capacidad disponible sin crear una frecuencia adicional.")
        tecnico = diag.rename(columns={
            "mes": "Mes",
            "afluencia_biotren": "Afluencia 2027",
            "servicios_comerciales": "Servicios comerciales",
            "servicios_equivalentes_capacidad": "Servicios equivalentes capacidad",
            "servicios_acoplados_l2_lv": "Acoplados L2 L-V",
            "servicios_acoplados_mensuales": "Acoplados mensuales equivalentes",
            "pax_servicio_comercial": "Pax/servicio comercial",
            "pax_capacidad_equivalente": "Pax/capacidad equivalente",
            "diferencia_pax_comercial_vs_capacidad": "Diferencia pax comercial-capacidad",
            "participacion_mensual_afluencia": "Participación mensual",
            "banda_funcionamiento": "Banda",
            "observacion_metodologica": "Observación metodológica",
        })
        st.dataframe(tecnico, width="stretch", hide_index=True, height=330)
        st.markdown("Nota metodológica: las bandas son diagnósticas, no recalibran demanda ni modifican la oferta corregida de L2.")


def _efe_section_title(titulo, nota=None):
    st.markdown(f'<div class="efe-section"><h4>{titulo}</h4>', unsafe_allow_html=True)
    if nota:
        st.markdown(f'<p class="efe-note">{nota}</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def _efe_card(titulo, valor, nota="", estilo="primary"):
    clase = {
        "primary": "efe-card-primary",
        "secondary": "efe-card-secondary",
        "diagnostic": "efe-card-diagnostic",
    }.get(estilo, "efe-card-primary")
    st.markdown(
        f"""
<div class="efe-card {clase}">
  <div class="efe-kpi-title">{titulo}</div>
  <div class="efe-kpi-value">{valor}</div>
  <div class="efe-kpi-note">{nota}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_biotren_header():
    st.markdown(
        """
<div class="efe-header">
  <div class="efe-header-kicker">Biotren · Escenario 2027</div>
  <div class="efe-header-title">Biotren 2027: afluencia, ocupación e ingresos</div>
  <div class="efe-header-subtitle">Escenario de gestión operacional-comercial con oferta corregida, capacidad efectiva, integración TP, plan de evasión y validación mensual de ocupación.</div>
  <span class="efe-brand">EFE Sur · Gerencia de Pasajeros</span>
</div>
""",
        unsafe_allow_html=True,
    )


def render_biotren_kpis(pasajeros, servicios_anuales, resumen_ocup, anual_sub):
    _efe_section_title("1. Indicadores ejecutivos")
    servicios_equiv = float(resumen_ocup["servicios_equivalentes_capacidad_anuales"])
    pax_servicio = float(resumen_ocup["pax_servicio_comercial_anual"])
    pax_capacidad = float(resumen_ocup["pax_capacidad_equivalente_anual"])
    cards = [
        ("Pasajeros 2027", fmt(pasajeros), "Demanda anual Biotren", "primary"),
        ("Servicios comerciales", fmt(servicios_anuales), "Frecuencia programada", "primary"),
        ("Pax/servicio comercial", f"{pax_servicio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), "Indicador principal", "primary"),
        ("Servicios equivalentes", fmt(servicios_equiv), "Diagnóstico de capacidad", "diagnostic"),
        ("Venta de pasajes", fmt_mm(anual_sub.get("ingreso_venta", 0.0)), "Sólo Biotren", "secondary"),
        ("Subsidio total", fmt_mm(anual_sub.get("subsidio_total", 0.0)), "Normal + estudiante", "secondary"),
        ("Ingreso total", fmt_mm(anual_sub.get("ingreso_total_biotren", 0.0)), "Venta + subsidios", "secondary"),
        ("Subsidio normal", fmt_mm(anual_sub.get("subsidio_normal", 0.0)), "Tasa parametrizada", "secondary"),
        ("Subsidio estudiante", fmt_mm(anual_sub.get("subsidio_estudiante", 0.0)), "Brecha agregada", "secondary"),
    ]
    for i in range(0, len(cards), 3):
        cols = st.columns(3)
        for col, card in zip(cols, cards[i:i + 3]):
            with col:
                _efe_card(*card)
    st.caption(
        "La ocupación principal se calcula sobre servicios comerciales programados. "
        f"Los servicios acoplados de L2 se incorporan sólo como capacidad equivalente diagnóstica; "
        f"Pax/capacidad equivalente: {pax_capacidad:,.2f}.".replace(",", "X").replace(".", ",").replace("X", ".")
    )


def render_biotren_fundamento_gestion():
    _efe_section_title("2. Fundamento del escenario de gestión Biotren 2027")
    factores = pd.DataFrame([
        {"Factor": "Oferta L1/L2", "Aplicación 2027": "L1 47 L-V; L2 110 L-V; fines de semana según periodo", "Rol metodológico": "Base operacional"},
        {"Factor": "Acoplados L2", "Aplicación 2027": "3 servicios L2 L-V desde mayo", "Rol metodológico": "Capacidad efectiva"},
        {"Factor": "Integración buses TP", "Aplicación 2027": "Principalmente Concepción; extensible operacionalmente a estaciones", "Rol metodológico": "Captura de demanda alimentadora"},
        {"Factor": "Plan evasión", "Aplicación 2027": "1% del cierre 2026", "Rol metodológico": "Recuperación de viajes registrados"},
        {"Factor": "Bandas de funcionamiento", "Aplicación 2027": "Diagnóstico mensual", "Rol metodológico": "Validación de eficiencia"},
    ])
    st.dataframe(factores, width="stretch", hide_index=True, height=210)
    st.caption("Estos factores fundamentan el escenario de gestión consolidado y no se suman nuevamente sobre la demanda anual proyectada.")
    with st.expander("Detalle metodológico del escenario Biotren", expanded=False):
        st.markdown("""
El escenario Biotren 2027 se formula como un escenario de gestión operacional-comercial. La demanda anual proyectada se sustenta en la oferta operacional programada, la capacidad efectiva disponible, la integración con buses del transporte público, el plan de evasión y la validación mensual de ocupación.

La oferta operacional distingue entre frecuencia comercial y capacidad efectiva. La Línea 1 considera 47 servicios de lunes a viernes, 8 servicios los sábados y sin operación dominical. La Línea 2 considera 110 servicios de lunes a viernes durante todo el año. En fines de semana, la Línea 2 opera con 14 servicios sábado y 14 domingo en enero-febrero, y con 53 servicios sábado y 32 domingo desde marzo. Desde mayo a diciembre, tres servicios L2 de lunes a viernes en punta mañana operan acoplados dentro de los 110 servicios comerciales. Estos servicios no se contabilizan como frecuencia adicional, sino como capacidad efectiva.

La integración con buses del transporte público se considera como una medida de captura de demanda alimentadora, concentrada principalmente en estación Concepción por su rol de nodo estructurante de la red Biotren. Operacionalmente, la integración puede extenderse al resto de estaciones, permitiendo mejorar la accesibilidad y continuidad de viaje del sistema. Dado que en esta etapa no se dispone de una matriz observada de transbordos bus-tren por estación, la integración TP se utiliza como fundamento del escenario de gestión y no como redistribución OD específica.

El plan de evasión se incorpora como recuperación de viajes registrados equivalente a 1% del cierre 2026 de Biotren. Este componente representa una mejora en la captura de validaciones y trazabilidad de la demanda efectiva, sin interpretarse necesariamente como demanda física completamente nueva. Su efecto fundamenta el escenario de gestión consolidado y no debe sumarse nuevamente si la afluencia anual ya fue calibrada al escenario consolidado.

La coherencia del escenario se valida mediante indicadores de ocupación mensual. El indicador principal corresponde a pasajeros por servicio comercial; como diagnóstico técnico se calcula también pasajeros por capacidad equivalente, incorporando el efecto de los servicios acoplados. Adicionalmente, los meses se clasifican en bandas de baja utilización, operación estable, alta utilización y tensión operacional. Estas bandas permiten evaluar la distribución mensual de la carga, sin modificar por sí mismas la demanda proyectada.

Una vez consolidada la demanda total de Biotren, el modelo distribuye la afluencia por línea, tipo de tarjeta y matriz OD. Sobre esa distribución se estiman ingresos por venta de pasajes, subsidio normal y subsidio estudiante; estos cálculos financieros no modifican la afluencia.
""")


def render_biotren_ocupacion_mensual(serie):
    resumen = O.resumen_ocupacion_biotren(serie, 2027)
    diag = resumen["diagnostico_mensual"].copy()
    bandas_color = {"Baja utilización": "#5F6B7A", "Operación estable": "#0057A8", "Alta utilización": "#007A5E", "Tensión operacional": "#D71920"}
    _efe_section_title("3. Ocupación mensual y bandas de funcionamiento", "El indicador principal usa servicios comerciales programados; la capacidad equivalente se muestra sólo como diagnóstico técnico.")
    cols = st.columns(7)
    metrics = [
        ("Pax/servicio comercial", f"{resumen['pax_servicio_comercial_anual']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        ("Pax/capacidad equivalente", f"{resumen['pax_capacidad_equivalente_anual']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        ("Mes mayor", f"Mes {resumen['mes_mayor_pax_servicio_comercial']}"),
        ("Mes menor", f"Mes {resumen['mes_menor_pax_servicio_comercial']}"),
        ("Baja utilización", int(resumen["meses_por_banda"].get("Baja utilización", 0))),
        ("Alta utilización", int(resumen["meses_por_banda"].get("Alta utilización", 0))),
        ("Tensión", int(resumen["meses_por_banda"].get("Tensión operacional", 0))),
    ]
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, value)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=diag["mes"],
        y=diag["pax_servicio_comercial"],
        mode="lines+markers",
        name="Pax/servicio comercial",
        marker=dict(color=[bandas_color[b] for b in diag["banda_funcionamiento"]], size=9),
        line=dict(color="#003A70", width=3),
    ))
    fig.add_trace(go.Scatter(
        x=diag["mes"],
        y=diag["pax_capacidad_equivalente"],
        mode="lines+markers",
        name="Pax/capacidad equivalente (diagnóstico)",
        marker=dict(color="#91B7D8", size=7),
        line=dict(color="#91B7D8", width=2, dash="dot"),
    ))
    fig.add_hline(y=300, line_dash="dash", line_color="#D71920", annotation_text="Referencia 300", annotation_position="top left")
    fig.update_layout(height=360, xaxis_title="Mes", yaxis_title="Pasajeros por servicio", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h"), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    visible = diag[["mes", "afluencia_biotren", "servicios_comerciales", "pax_servicio_comercial", "banda_funcionamiento"]].rename(columns={"mes": "Mes", "afluencia_biotren": "Afluencia 2027", "servicios_comerciales": "Servicios comerciales", "pax_servicio_comercial": "Pax/servicio comercial", "banda_funcionamiento": "Banda"})
    st.dataframe(visible, width="stretch", hide_index=True, height=250, column_config={"Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"), "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d"), "Pax/servicio comercial": st.column_config.NumberColumn("Pax/servicio comercial", format="%.1f")})
    return resumen, diag


def render_biotren_evolucion_redistribucion(serie, vigente, diag, servicios_mensuales, serv_completo):
    _efe_section_title("4. Evolución mensual y redistribución 2027")
    ref = construir_referencia_mensual_visual(serv_completo)
    ref_b = ref[(ref["servicio_modelo"].eq("BIOTREN")) & (ref["anio"].isin([2026, 2027]))].copy().sort_values(["anio", "mes_num"])
    fig = go.Figure()
    for label, color, dash in [("Cierre 2026 estimado", "#5F6B7A", "solid"), ("Proyección 2027 modelo", "#003A70", "dash")]:
        d = ref_b[ref_b["tipo_dato_label"].eq(label)]
        if not d.empty:
            fig.add_trace(go.Scatter(x=d["mes_num"].astype(int), y=d["afluencia"].astype(float), name=label, mode="lines+markers", line=dict(color=color, width=3, dash=dash)))
    fig.update_layout(height=330, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="white", paper_bgcolor="white", legend=dict(orientation="h", y=1.12, x=0), hovermode="x unified")
    fig.update_xaxes(dtick=1, range=[0.7, 12.3], showgrid=False, title="Mes")
    fig.update_yaxes(gridcolor="#D9E1E8", title="Pasajeros/mes")
    st.plotly_chart(fig, width="stretch")
    total = float(serie.sum())
    tabla = pd.DataFrame({
        "Mes": diag["mes"],
        "Afluencia 2027": serie.values,
        "Participación anual": serie.values / total if total else 0.0,
        "Variación vs referencia": serie.values - vigente.values,
        "Servicios comerciales": servicios_mensuales.values,
    })
    st.dataframe(tabla, width="stretch", hide_index=True, height=250, column_config={"Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"), "Participación anual": st.column_config.NumberColumn("Participación anual", format="%.2%%"), "Variación vs referencia": st.column_config.NumberColumn("Variación vs referencia", format="%+d"), "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d")})
    with st.expander("Detalle de redistribución mensual", expanded=False):
        st.markdown("""
- Participación mensual = afluencia mensual / afluencia anual.
- Pesos del patrón reciente: 2024 = 25%, 2025 = 35%, cierre 2026 = 40%.
- Participación objetivo = 80% patrón histórico ponderado + 20% participación de servicios comerciales 2027.
- El redondeo se ajusta para que la suma mensual conserve exactamente el total anual Biotren.
""")
        st.dataframe(diag, width="stretch", hide_index=True, height=320)


def render_biotren_distribucion_linea(serie):
    _efe_section_title("5. Distribución por línea")
    dist_linea = calcular_distribucion_biotren_linea_mod_cached(serie.to_dict())
    anual_linea = dist_linea.groupby("linea_od", as_index=False).agg(viajes=("viajes_proyectados", "sum"))
    total = float(anual_linea["viajes"].sum())
    anual_linea["participacion"] = anual_linea["viajes"] / total if total else 0.0
    anual_linea = anual_linea.set_index("linea_od").reindex(["L1", "L2", "L1-L2"]).fillna(0.0).reset_index()
    fig = go.Figure(go.Bar(x=anual_linea["linea_od"], y=anual_linea["viajes"], text=[fmt(v) for v in anual_linea["viajes"]], textposition="outside"))
    fig.update_layout(height=310, yaxis_title="Pasajeros", xaxis_title="Línea", showlegend=False, margin=dict(l=10, r=10, t=20, b=10), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    tabla = anual_linea.rename(columns={"linea_od": "Línea", "viajes": "Pasajeros 2027", "participacion": "Participación"})
    st.dataframe(tabla, width="stretch", hide_index=True, column_config={"Pasajeros 2027": st.column_config.NumberColumn("Pasajeros 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.1%%")})
    return dist_linea


def render_biotren_distribucion_tarjeta(resumen_anual_tipo):
    _efe_section_title("6. Distribución por tipo de tarjeta")
    resumen_tipo = resumen_anual_tipo.groupby(["tipo_tarjeta", "nombre_visual", "tipo_pasajero_tarifa"], as_index=False).agg(viajes=("viajes_proyectados", "sum"), venta_pasajes=("ingresos_tarifarios_proyectados", "sum"))
    total_viajes = float(resumen_tipo["viajes"].sum())
    resumen_tipo["participacion"] = resumen_tipo["viajes"] / total_viajes if total_viajes else 0.0
    resumen_tipo["rol_tarifario"] = resumen_tipo["tipo_tarjeta"].map(_rol_tarjetario)
    resumen_tipo["grupo_subsidio"] = resumen_tipo["tipo_tarjeta"].map(_grupo_subsidio_tarjeta)
    resumen_tipo = resumen_tipo.sort_values("viajes", ascending=False)
    fig_tarjetas = go.Figure(go.Bar(x=resumen_tipo["nombre_visual"], y=resumen_tipo["viajes"], text=[fmt(v) for v in resumen_tipo["viajes"]], textposition="outside"))
    fig_tarjetas.update_layout(title="Viajes anuales por tipo de tarjeta", height=360, yaxis_title="Viajes", xaxis_title="Tipo de tarjeta", showlegend=False, margin=dict(l=10, r=10, t=45, b=90), plot_bgcolor="white", paper_bgcolor="white")
    fig_tarjetas.update_xaxes(tickangle=-25)
    st.plotly_chart(fig_tarjetas, width="stretch")
    tabla_tarjetas = resumen_tipo.rename(columns={"tipo_tarjeta": "Tipo de tarjeta", "nombre_visual": "Nombre", "tipo_pasajero_tarifa": "Tarifa aplicada", "viajes": "Viajes 2027", "participacion": "Participación", "rol_tarifario": "Rol tarifario", "grupo_subsidio": "Grupo subsidio"})
    st.dataframe(
        tabla_tarjetas[["Tipo de tarjeta", "Nombre", "Rol tarifario", "Grupo subsidio", "Tarifa aplicada", "Viajes 2027", "Participación"]],
        width="stretch",
        hide_index=True,
        height=300,
        column_config={"Viajes 2027": st.column_config.NumberColumn("Viajes 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.2%%")},
    )
    return resumen_tipo


def render_biotren_finanzas(anual_sub, venta_por_tipo):
    _efe_section_title("7. Resultados financieros Biotren")
    tabla_financiera = _tabla_financiera_biotren(anual_sub, venta_por_tipo)
    st.dataframe(
        tabla_financiera,
        width="stretch",
        hide_index=True,
        column_config={"Monto anual": st.column_config.NumberColumn("Monto anual", format="$ %d")},
    )


def render_biotren_advertencias(cobertura):
    _efe_section_title("8. Advertencias y cobertura")
    advertencias = [
        "La capacidad equivalente es diagnóstica y no representa frecuencia comercial adicional.",
        "La integración TP no redistribuye OD por falta de matriz observada de transbordos bus-tren.",
        "El plan evasión representa recuperación de viajes registrados y no se suma nuevamente sobre la demanda anual.",
        "Las bandas mensuales son diagnósticas y no recalibran demanda.",
    ]
    if cobertura.get("sin_cobertura_modelo"):
        advertencias.append("Concepción Centro sin cobertura en matriz estudiante sin subsidio: " + ", ".join(cobertura.get("sin_cobertura_modelo", [])))
    if cobertura.get("estaciones_sin_tarifas"):
        advertencias.append("Estaciones sin tarifas disponibles en matriz estudiante sin subsidio: " + ", ".join(cobertura.get("estaciones_sin_tarifas", [])))
    for adv in advertencias:
        st.markdown(f'<div class="efe-warning">{adv}</div>', unsafe_allow_html=True)


def render_biotren_expanders_tecnicos(serie, dist_linea, resumen_tipo, cobertura, diag_ocup, serv):
    with st.expander("Detalle OD mensual por tipo de tarjeta", expanded=False):
        periodos = list(serie.index)
        periodo = st.selectbox("Mes proyectado", periodos, format_func=lambda x: f"{str(x)[5:7]} - 2027", key="od_biotren_periodo_compacto")
        tipo_tarjeta = st.selectbox("Tipo de tarjeta", OD.TIPOS_TARJETA_ESPERADOS, key="od_biotren_tipo_tarjeta_compacto")
        resultado_mes = calcular_od_biotren_tarjeta_mes_cached(periodo, float(serie.loc[periodo]))
        viajes_long = resultado_mes["viajes_tipo_tarjeta_long"]
        resumen_mes = resultado_mes["resumen_tipo_tarjeta"].copy()
        M = _matriz_tarjeta(viajes_long, tipo_tarjeta, "viajes_proyectados")
        R = _matriz_tarjeta(viajes_long, tipo_tarjeta, "ingresos_tarifarios_proyectados")
        st.caption("Detalle técnico en memoria: distribuye el total mensual seleccionado por tipo de tarjeta y par OD.")
        t1, t2, t3 = st.tabs(["Matriz OD viajes", "Matriz OD ingresos", "Resumen mensual"])
        with t1:
            st.dataframe(M.round(0).astype(int).copy(deep=True), width="stretch", height=420)
        with t2:
            st.dataframe(R.round(0).astype(int).copy(deep=True), width="stretch", height=420)
        with t3:
            st.dataframe(resumen_mes, width="stretch", height=260)
    with st.expander("Diagnóstico técnico de capacidad equivalente", expanded=False):
        st.markdown("La ocupación principal se calcula sobre servicios comerciales programados. Los servicios acoplados de L2 se incorporan sólo en el diagnóstico de capacidad equivalente, dado que aumentan la capacidad disponible sin crear una frecuencia adicional.")
        tecnico = diag_ocup.rename(columns={"mes": "Mes", "afluencia_biotren": "Afluencia 2027", "servicios_comerciales": "Servicios comerciales", "servicios_equivalentes_capacidad": "Servicios equivalentes capacidad", "servicios_acoplados_l2_lv": "Acoplados L2 L-V", "servicios_acoplados_mensuales": "Acoplados mensuales equivalentes", "pax_servicio_comercial": "Pax/servicio comercial", "pax_capacidad_equivalente": "Pax/capacidad equivalente", "diferencia_pax_comercial_vs_capacidad": "Diferencia pax comercial-capacidad", "participacion_mensual_afluencia": "Participación mensual", "banda_funcionamiento": "Banda", "observacion_metodologica": "Observación metodológica"})
        st.dataframe(tecnico, width="stretch", hide_index=True, height=330)
    with st.expander("Detalle de conservación por línea", expanded=False):
        mensual_linea = dist_linea.pivot_table(index="periodo", columns="linea_od", values="viajes_proyectados", aggfunc="sum", fill_value=0.0).reindex(columns=["L1", "L2", "L1-L2"], fill_value=0.0)
        mensual_linea["Total líneas"] = mensual_linea.sum(axis=1)
        mensual_linea["Total Biotren"] = serie.reindex(mensual_linea.index).astype(float)
        mensual_linea["Diferencia"] = mensual_linea["Total líneas"] - mensual_linea["Total Biotren"]
        st.dataframe(mensual_linea.reset_index().rename(columns={"periodo": "Periodo"}), width="stretch", hide_index=True, height=280)
    with st.expander("Justificación metodológica", expanded=False):
        st.markdown("""
- La redistribución mensual usa participación anual reciente y conserva el total anual Biotren.
- La validación operacional se expresa como pasajeros por servicio comercial = pasajeros anuales / servicios comerciales anuales.
- Los servicios acoplados L2 son capacidad efectiva; no aumentan frecuencia comercial.
- Integración TP y plan evasión fundamentan el escenario consolidado; no se suman nuevamente sobre la demanda anual.
- Subsidio normal: `Monto_normal_base / (1 - tasa_descuento_normal) - Monto_normal_base`.
- Subsidio estudiante: `Ingreso_teorico_estudiante_sin_subsidio_sin_diagonal - Venta_media_superior_con_diagonal`.
""")
        st.write(f"Matriz estudiante sin subsidio: {fmt(cobertura.get('estaciones_matriz', 0))} estaciones.")
    with st.expander("Ecuaciones y controles internos", expanded=False):
        render_incertidumbre_biotren(serv)



def render_laja_talcahuano_ejecutivo(serv, uni, detalle):
    s = "CORTO_LAJA"
    nombre = O.NOMBRE[s]
    serie = serv[s].astype(float).copy()
    total = float(serie.sum())
    viajes_m = _servicios_mensuales_desde_detalle(detalle, s, serie.index)
    viajes_total = float(viajes_m.sum())
    pax_servicio = total / viajes_total if viajes_total > 0 else 0.0
    ocupacion = OL.ocupacion_laja_talcahuano_mensual(serie, viajes_m)
    capacidad_total = float(ocupacion["capacidad_pax"].sum())
    ocupacion_anual = total / capacidad_total if capacidad_total else 0.0
    resultado = calcular_resultado_laja_anual_cached(serie.to_dict())
    resumen_anual = resultado["resumen_anual"]
    resumen_tipo = resultado["resumen_anual_tipo_pasajero"].copy()
    resumen_mensual = resultado["resumen_mensual"].copy()
    control = resultado["control_conservacion"].copy()
    cierre_2026 = _cierre_2026_servicio(s, serv)
    _, mes_labels = _month_labels_from_index(serie.index)
    peak_period = str(serie.idxmax())
    peak_label = MESES_CORTOS.get(int(peak_period[5:7]), peak_period) if len(peak_period) >= 7 else peak_period

    efe_service_header(
        f"{nombre} 2027: afluencia, ocupación e ingresos",
        "Distribución OD y venta de pasajes mediante MOD 2024 por tipo de pasajero y matriz tarifaria 2026 EFESUR. No aplica subsidio por pasajero transportado.",
        "Proyección 2027",
    )

    cards = [
        {"titulo": "Pasajeros 2027", "valor": fmt_compacto_efe(total), "detalle": fmt_num_efe(total, 0), "delta": fmt_delta_vs(total, cierre_2026), "nota": "Total anual proyectado", "icono": "👥"},
        {"titulo": "Servicios comerciales", "valor": fmt_compacto_efe(viajes_total), "detalle": fmt_num_efe(viajes_total, 0), "delta": "Oferta operacional 2027", "nota": "Total anual de servicios", "icono": "🚆"},
        {"titulo": "Pax/servicio", "valor": fmt_num_efe(pax_servicio, 1), "detalle": f"{fmt_num_efe(pax_servicio, 2)} pax/servicio", "delta": "Indicador operacional", "nota": "Promedio anual", "icono": "●"},
        {"titulo": "Ocupación capacidad", "valor": f"{fmt_num_efe(ocupacion_anual * 100, 1)}%", "detalle": "578 pax/tren", "delta": "Capacidad referencial", "nota": "Afluencia/capacidad anual", "icono": "%"},
        {"titulo": "Venta de pasajes", "valor": fmt_clp_compacto(resumen_anual.get("ingreso_venta", 0.0)), "detalle": fmt_clp_detalle(resumen_anual.get("ingreso_venta", 0.0)), "delta": "Sin subsidio", "nota": "Sólo ingreso tarifario", "icono": "▰"},
        {"titulo": "Tarifa media", "valor": fmt_clp_compacto(resumen_anual.get("tarifa_media", 0.0)), "detalle": fmt_clp_detalle(resumen_anual.get("tarifa_media", 0.0)), "delta": "Ingreso/viaje", "nota": "Promedio ponderado", "icono": "$"},
        {"titulo": "Mes peak", "valor": peak_label, "detalle": fmt_num_efe(serie.max(), 0), "delta": "Demanda mensual máxima", "nota": "Pasajeros en mes peak", "icono": "▴"},
    ]
    render_metric_grid(cards, cols_per_row=5)

    c1, c2 = st.columns([1.05, 1.0])
    with c1:
        efe_section("Evolución mensual y ocupación", "Histórico/cierre disponible y proyección mensual 2027.")
        st.plotly_chart(fig_evolucion_servicio(s, serv), width="stretch")
    with c2:
        efe_section("Ocupación mensual sobre capacidad", "Capacidad referencial: 578 pasajeros por tren.")
        st.plotly_chart(fig_ocupacion_pct(mes_labels, ocupacion["ocupacion_pct"].astype(float).values * 100.0, 100.0), width="stretch")

    tabla_mensual = pd.DataFrame({
        "Mes": mes_labels,
        "Afluencia 2027": serie.values,
        "Servicios comerciales": viajes_m.values,
        "Capacidad pax": ocupacion["capacidad_pax"].values,
        "Pax/servicio": ocupacion["pax_servicio"].values,
        "Ocupación": ocupacion["ocupacion_pct"].values,
    })
    c3, c4, c5 = st.columns([1.0, 1.0, 1.05])
    with c3:
        efe_section("Participación mensual 2027", "Control mensual de demanda, oferta y ocupación.")
        st.dataframe(tabla_mensual, width="stretch", hide_index=True, height=315, column_config={
            "Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"),
            "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d"),
            "Capacidad pax": st.column_config.NumberColumn("Capacidad pax", format="%d"),
            "Pax/servicio": st.column_config.NumberColumn("Pax/servicio", format="%.1f"),
            "Ocupación": st.column_config.NumberColumn("Ocupación", format="%.1%%"),
        })
    with c4:
        efe_section("Distribución por tipo de pasajero", "MOD histórica 2024 escalada al total mensual proyectado.")
        top_tipo = resumen_tipo.sort_values("viajes", ascending=False).copy()
        fig_tipo = go.Figure(go.Pie(labels=top_tipo["nombre_visual"], values=top_tipo["viajes"], hole=.60, marker=dict(colors=EFE_COLORS), textinfo="percent", sort=False))
        fig_tipo.update_layout(height=240, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, paper_bgcolor="white", annotations=[dict(text=f"{fmt_compacto_efe(total)}<br>Pax 2027", x=.5, y=.5, showarrow=False, font=dict(color=EFE_BLUE, size=15))])
        st.plotly_chart(fig_tipo, width="stretch")
        st.dataframe(top_tipo[["nombre_visual", "viajes", "participacion"]].rename(columns={"nombre_visual": "Tipo de pasajero", "viajes": "Pax 2027", "participacion": "Participación"}), width="stretch", hide_index=True, height=150, column_config={"Pax 2027": st.column_config.NumberColumn("Pax 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.1%%")})
    with c5:
        efe_section("Principales pares OD", "Top OD anual por viajes proyectados.")
        od_top = resultado["viajes_od_tipo_long"].groupby(["origen", "destino"], as_index=False).agg(viajes=("viajes_proyectados", "sum"), ingreso=("ingreso_tarifario_proyectado", "sum"))
        od_top = od_top.sort_values("viajes", ascending=False).head(12)
        od_top["OD"] = od_top["origen"] + " → " + od_top["destino"]
        st.dataframe(od_top[["OD", "viajes", "ingreso"]], width="stretch", hide_index=True, height=390, column_config={"viajes": st.column_config.NumberColumn("Pax 2027", format="%d"), "ingreso": st.column_config.NumberColumn("Venta", format="$ %d")})

    c6, c7 = st.columns([1.0, 1.0])
    with c6:
        efe_section("Resultados financieros Laja-Talcahuano", "Sólo venta de pasajes; no aplica subsidio por pasajero transportado.")
        fin = pd.DataFrame([
            {"Concepto": "Venta de pasajes", "Monto anual": resumen_anual.get("ingreso_venta", 0.0)},
            {"Concepto": "Subsidio por pasajero", "Monto anual": 0.0},
            {"Concepto": "Ingreso total reportado", "Monto anual": resumen_anual.get("ingreso_venta", 0.0)},
        ])
        st.dataframe(fin, width="stretch", hide_index=True, height=190, column_config={"Monto anual": st.column_config.NumberColumn("Monto anual", format="$ %d")})
        st.caption("La matriz tarifaria se usa sólo para venta de pasajes. No se calcula subsidio normal, estudiante ni total.")
    with c7:
        efe_section("Advertencias y cobertura", "Controles metodológicos y límites de interpretación.")
        alertas = _advertencias_servicio(s) + [
            "MOD 2024 por tipo de pasajero usada como estructura de distribución; no modifica el total mensual proyectado.",
            "Conservación mensual: la suma OD por tipo coincide con la afluencia mensual proyectada.",
            "Ida y vuelta: la tarifa comercial se imputa con factor 0,5 porque la MOD representa viajes transportados, no boletos comerciales.",
        ]
        if int(control.get("od_sin_tarifa", pd.Series([0])).sum()) > 0:
            alertas.append("Existen pares OD sin tarifa en la matriz 2026; revisar cobertura tarifaria.")
        render_alertas(alertas)

    with st.expander("Detalle OD mensual por tipo de pasajero", expanded=False):
        periodos = list(serie.index)
        periodo = st.selectbox("Mes proyectado", periodos, format_func=lambda x: f"{str(x)[5:7]} - 2027", key="od_laja_periodo")
        tipos = list(OL.TIPOS_PASAJERO_LAJA)
        tipo = st.selectbox("Tipo de pasajero", tipos, key="od_laja_tipo")
        res_mes = calcular_od_laja_mes_cached(periodo, float(serie.loc[periodo]))
        viajes_long = res_mes["viajes_od_tipo_long"]
        M = OL.matriz_od(viajes_long, tipo_pasajero=tipo, valor_col="viajes_proyectados")
        R = OL.matriz_od(viajes_long, tipo_pasajero=tipo, valor_col="ingreso_tarifario_proyectado")
        t1, t2, t3 = st.tabs(["Matriz OD viajes", "Matriz OD ingresos", "Resumen mensual"])
        with t1:
            st.dataframe(M.round(0).astype(int), width="stretch", height=420)
        with t2:
            st.dataframe(R.round(0).astype(int), width="stretch", height=420)
        with t3:
            st.dataframe(res_mes["resumen_tipo_pasajero"], width="stretch", height=260)
    with st.expander("Validación de conservación y cobertura", expanded=False):
        st.markdown("La redistribución conserva el total mensual proyectado y aplica tarifas 2026 EFESUR por tipo de pasajero y OD. No calcula subsidios.")
        st.dataframe(control, width="stretch", hide_index=True, height=260)
        st.dataframe(resumen_mensual, width="stretch", hide_index=True, height=260)
    with st.expander("Metodología matricial aplicada", expanded=False):
        st.markdown("""
- Se utiliza la MOD 2024 mensual por tipo de pasajero como estructura histórica de distribución.
- Para cada mes, se calcula la participación de cada tipo de pasajero sobre el total observado.
- Dentro de cada tipo, se calcula la participación de cada par OD.
- La afluencia mensual 2027 proyectada se distribuye como: total mensual × participación tipo × participación OD condicionada al tipo.
- La suma resultante por mes, tipo y OD se ajusta proporcionalmente para conservar exactamente el total mensual proyectado.
- La matriz tarifaria 2026 EFESUR se aplica a cada OD/tipo para estimar venta de pasajes.
- Para ida y vuelta, la tarifa comercial se divide por 2 para obtener la tarifa imputable por viaje transportado.
- No se calcula subsidio por pasajero transportado para este servicio.
""")

def render_biotren_ejecutivo(serv, uni, detalle):
    serie = serv["BIOTREN"].astype(float).copy()
    vigente = _serie_biotren_vigente_pre_redistribucion(serv)
    servicios_mensuales = O.servicios_comerciales_biotren_mensuales(2027)
    servicios_anuales = float(servicios_mensuales.sum())
    diag = O.diagnostico_redistribucion_biotren_2027(vigente, serie)
    resultado_anual = calcular_resultado_biotren_tarjeta_anual_cached(serie.to_dict())
    resumen_anual_tipo = resultado_anual["resumen_tipo_tarjeta"].copy()
    ingresos_subsidio = resultado_anual.get("ingresos_subsidio_biotren", {})
    anual_sub = ingresos_subsidio.get("resumen_anual", {})
    cobertura = ingresos_subsidio.get("cobertura_estudiante", {})
    pasajeros = float(anual_sub.get("viajes_biotren", serie.sum()))
    render_biotren_header()
    resumen_ocup = O.resumen_ocupacion_biotren(serie, 2027)
    render_biotren_kpis(pasajeros, servicios_anuales, resumen_ocup, anual_sub)
    render_biotren_fundamento_gestion()
    _, diag_ocup = render_biotren_ocupacion_mensual(serie)
    render_biotren_evolucion_redistribucion(serie, vigente, diag, servicios_mensuales, serv)
    dist_linea = render_biotren_distribucion_linea(serie)
    resumen_tipo = render_biotren_distribucion_tarjeta(resumen_anual_tipo)
    venta_por_tipo = resumen_tipo.set_index("tipo_tarjeta")["venta_pasajes"].to_dict()
    render_biotren_finanzas(anual_sub, venta_por_tipo)
    render_biotren_advertencias(cobertura)
    render_biotren_expanders_tecnicos(serie, dist_linea, resumen_tipo, cobertura, diag_ocup, serv)

# -----------------------------------------------------------------------------
# Vista ejecutiva EFE: componentes visuales reutilizables para todos los servicios
# -----------------------------------------------------------------------------

EFE_BLUE = "#003A70"
EFE_BLUE_2 = "#0057A8"
EFE_RED = "#D71920"
EFE_GRID = "#D9E1E8"
EFE_TEXT = "#0B1F3A"
EFE_MUTED = "#66758A"
EFE_COLORS = ["#003A70", "#3D7EDB", "#8FB7E8", "#DCE8F5", "#B8C7D8", "#E8EEF4"]
MESES_CORTOS = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}


def _h(x):
    return html.escape(str(x))


def fmt_num_efe(n, dec=0):
    try:
        val = float(n)
    except Exception:
        return "s/i"
    if dec == 0:
        return f"{val:,.0f}".replace(",", ".")
    return f"{val:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_m_efe(n, sufijo="M"):
    try:
        val = float(n) / 1_000_000
    except Exception:
        return "s/i"
    return f"{val:,.1f}{sufijo}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_clp_m_efe(n):
    try:
        val = float(n) / 1_000_000
    except Exception:
        return "$ s/i"
    return f"$ {val:,.0f}M".replace(",", ".")


def fmt_compacto_efe(n):
    try:
        val = float(n)
    except Exception:
        return "s/i"
    if abs(val) >= 1_000_000:
        return f"{val / 1_000_000:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(val) >= 1_000:
        return f"{val / 1_000:,.1f} mil".replace(",", "X").replace(".", ",").replace("X", ".")
    if float(val).is_integer():
        return f"{val:,.0f}".replace(",", ".")
    return f"{val:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_clp_detalle(n):
    try:
        val = float(n)
    except Exception:
        return "$ s/i"
    return f"$ {val:,.0f}".replace(",", ".")


def fmt_clp_compacto(n):
    try:
        val = float(n)
    except Exception:
        return "$ s/i"
    if abs(val) >= 1_000_000_000:
        return f"$ {val / 1_000_000:,.0f}M".replace(",", ".")
    if abs(val) >= 1_000_000:
        return f"$ {val / 1_000_000:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")
    return fmt_clp_detalle(val)


def fmt_delta_vs(valor, base, etiqueta="vs 2026"):
    if base is None or pd.isna(base) or float(base) == 0:
        return "Referencia no disponible"
    return f"{(float(valor) / float(base) - 1.0) * 100:+.1f}% {etiqueta}".replace(".", ",")


def _month_labels_from_index(index):
    labels = []
    nums = []
    for i, p in enumerate(index, start=1):
        try:
            n = int(str(p)[5:7])
        except Exception:
            n = i
        nums.append(n)
        labels.append(MESES_CORTOS.get(n, str(p)))
    return nums, labels


def efe_service_header(titulo, subtitulo, etiqueta="Proyección 2027"):
    html = (
        '<div class="efe-service-top">'
        '<div class="efe-title-block">'
        f'<div class="efe-service-title">{_h(titulo)}</div>'
        f'<div class="efe-service-subtitle">{_h(subtitulo)}</div>'
        '</div>'
        f'<div class="efe-pill">▣ {_h(etiqueta)}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def efe_section(titulo, nota=None):
    nota_html = f'<div class="efe-section-note">{_h(nota)}</div>' if nota else ""
    st.markdown(f'<div class="efe-section-title">{_h(titulo)}</div>{nota_html}', unsafe_allow_html=True)


def efe_metric_card(titulo, valor, delta=None, icono="●", nota=None, detalle=None):
    detalle_html = f'<div class="efe-metric-detail">{_h(detalle)}</div>' if detalle else ""
    delta_html = f'<div class="efe-metric-delta">{_h(delta)}</div>' if delta else ""
    nota_html = f'<div class="efe-metric-note">{_h(nota)}</div>' if nota else ""
    html = (
        '<div class="efe-metric-card">'
        f'<div class="efe-icon-circle">{_h(icono)}</div>'
        '<div>'
        f'<div class="efe-metric-label">{_h(titulo)}</div>'
        f'<div class="efe-metric-value">{_h(valor)}</div>'
        f'{detalle_html}{delta_html}{nota_html}'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_metric_grid(cards, cols_per_row=5):
    for i in range(0, len(cards), cols_per_row):
        row_cards = cards[i:i + cols_per_row]
        cols = st.columns(len(row_cards))
        for col, card in zip(cols, row_cards):
            with col:
                efe_metric_card(**card)


def apply_efe_plot_layout(fig, height=350, ytitle=None, xtitle=None, legend=True):
    fig.update_layout(
        height=height,
        margin=dict(l=14, r=14, t=24, b=18),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Univia Pro, Inter, Segoe UI, Arial", color=EFE_TEXT, size=12),
        hovermode="x unified",
        showlegend=legend,
        legend=dict(orientation="h", y=1.13, x=0, font=dict(size=12)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title=xtitle)
    fig.update_yaxes(gridcolor=EFE_GRID, zeroline=False, title=ytitle)
    return fig


def _linea_referencia_mensual(s, serv, anios=(2025, 2026, 2027)):
    ref = _referencia_servicio_mensual(s, serv)
    if ref.empty:
        return pd.DataFrame()
    ref = ref[ref["anio"].astype(int).isin([int(a) for a in anios])].copy()
    ref["mes_label"] = ref["mes_num"].astype(int).map(MESES_CORTOS)
    return ref.sort_values(["anio", "mes_num"])


def fig_evolucion_servicio(s, serv):
    ref = _linea_referencia_mensual(s, serv)
    fig = go.Figure()
    if not ref.empty:
        estilos = {
            2025: ("#3D7EDB", "dash", 2, "2025 (pax)"),
            2026: (EFE_BLUE, "solid", 3, "2026 (pax)"),
            2027: (EFE_RED, "solid", 3, "2027 (pax)"),
        }
        for anio, (color, dash, width, label) in estilos.items():
            d = ref[ref["anio"].astype(int).eq(anio)]
            if not d.empty:
                fig.add_trace(go.Scatter(
                    x=d["mes_label"], y=d["afluencia"].astype(float),
                    name=label, mode="lines+markers", line=dict(color=color, width=width, dash=dash),
                    marker=dict(size=7),
                ))
    else:
        _, labels = _month_labels_from_index(serv.index)
        fig.add_trace(go.Scatter(x=labels, y=serv[s].astype(float), name="2027 (pax)", mode="lines+markers", line=dict(color=EFE_RED, width=3)))
    return apply_efe_plot_layout(fig, height=330, ytitle="Pasajeros", xtitle=None)


def fig_pax_servicio(labels, pax_servicio, referencia=None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=pax_servicio, name="Pax/servicio", mode="lines+markers", line=dict(color=EFE_BLUE, width=3), marker=dict(size=7)))
    if referencia is not None and referencia > 0:
        fig.add_hline(y=float(referencia), line_dash="dash", line_color=EFE_RED, annotation_text=f"Referencia {fmt_num_efe(referencia, 0)}", annotation_position="top left")
    return apply_efe_plot_layout(fig, height=330, ytitle="Pax/servicio", xtitle=None)


def fig_ocupacion_pct(labels, ocupacion_pct, referencia=100.0):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=ocupacion_pct, name="Ocupación (%)", mode="lines+markers", line=dict(color=EFE_BLUE, width=3), marker=dict(size=7)))
    if referencia is not None and referencia > 0:
        fig.add_hline(y=float(referencia), line_dash="dash", line_color=EFE_RED, annotation_text=f"Referencia {fmt_num_efe(referencia, 0)}%", annotation_position="top left")
    return apply_efe_plot_layout(fig, height=330, ytitle="Ocupación (%)", xtitle=None)


def _servicios_mensuales_desde_detalle(detalle, s, index):
    d = tabla_detalle_mes(detalle, s)
    if d.empty or "viajes_operados_plan" not in d.columns:
        return pd.Series(0.0, index=index)
    return d.set_index("periodo")["viajes_operados_plan"].astype(float).reindex(index).fillna(0.0)


def _cierre_2026_servicio(s, serv):
    ref = _referencia_servicio_anual(s, serv)
    if ref.empty:
        return None
    d = ref[ref["tipo_dato_label"].eq("Cierre 2026 estimado")]
    if d.empty:
        return None
    return float(d.iloc[-1]["afluencia_anual"])


def _advertencias_servicio(s):
    if s == "BIOTREN":
        return [
            "La capacidad equivalente es diagnóstica y no frecuencia comercial adicional.",
            "La integración TP no redistribuye OD por falta de matriz observada de transbordos bus-tren.",
            "El plan evasión representa recuperación de viajes registrados y no se suma nuevamente sobre la demanda anual.",
        ]
    if s == "CORTO_LAJA":
        return [
            "Oferta base: 8 servicios todos los días; enero-febrero fin de semana considera 10 servicios cuando aplica.",
            "El escenario incorpora recuperación parcial de confiabilidad operacional.",
            "El modelo no implementa cálculo tarifario ni subsidios para este servicio.",
        ]
    if s == "TREN_ARAUCANIA":
        return [
            "La MOD distribuye la afluencia proyectada por mes, tipo de pasajero y par OD; no recalibra la demanda total.",
            "Normal paga tarifa normal; Delegación paga 70% de tarifa normal; Adulto Mayor paga tarifa adulto mayor; Estudiante y Claret pagan tarifa estudiante.",
            "Discapacitado, Estudiante Básica, Funcionario y Sindicato se modelan sin ingreso tarifario directo.",
            "El subsidio normal usa tasa de descuento 12,7% y considera Normal, Discapacitado, Funcionario, Sindicato y Delegación sobre tarifa normal completa.",
            "El subsidio estudiante considera Estudiante, Claret y Estudiante Básica; usa la diferencia entre la matriz estudiante sin subsidio y la matriz estudiante con subsidio, independiente de la venta directa.",
        ]
    if s == "LLANQUIHUE_PM":
        return [
            "Enero-febrero incorporan moderación del efecto novedad del servicio.",
            "Marzo-diciembre se calibran con referencia laboral sin forzar valores idénticos por mes.",
            "El modelo no implementa cálculo tarifario ni subsidios para este servicio.",
        ]
    return ["Proyección sujeta a actualización de supuestos operacionales y de oferta."]


def render_alertas(alertas):
    rows = "".join(
        f'<div class="efe-alert-row"><div class="efe-alert-icon">!</div><div>{_h(a)}</div></div>'
        for a in alertas
    )
    st.markdown(f'<div class="efe-alert-list">{rows}</div>', unsafe_allow_html=True)


def _componentes_por_unidad(detalle, s):
    d = detalle[detalle.servicio.eq(s)].copy()
    if d.empty or "unit" not in d.columns:
        return pd.DataFrame()
    out = d.groupby("unit", as_index=False).agg(pasajeros=("afl", "sum"), servicios=("viajes_operados_plan", "sum"))
    labels = {
        "BIOTREN_L1": "L1 Talcahuano/Hualqui",
        "BIOTREN_L2": "L2 Coronel/Concepción",
        "CORTO_LAJA": "Laja-Talcahuano",
        "TREN_ARAUCANIA": "Tren Araucanía",
        "LLANQUIHUE_PM": "Llanquihue-Puerto Montt",
    }
    labels.update(getattr(O, "TA_TRAMO_NOMBRE", {}))
    out["componente"] = out["unit"].map(labels).fillna(out["unit"])
    total = float(out["pasajeros"].sum())
    out["participacion"] = out["pasajeros"] / total if total else 0.0
    return out.sort_values("pasajeros", ascending=False)


def render_componentes_servicio(detalle, s):
    comp = _componentes_por_unidad(detalle, s)
    if comp.empty:
        st.info("No hay componentes operacionales desagregados disponibles para este servicio.")
        return
    fig = go.Figure(go.Pie(
        labels=comp["componente"], values=comp["pasajeros"], hole=.58,
        marker=dict(colors=EFE_COLORS), textinfo="percent", sort=False,
    ))
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), showlegend=True, legend=dict(orientation="v", x=1.02, y=.5), paper_bgcolor="white", font=dict(color=EFE_TEXT))
    st.plotly_chart(fig, width="stretch")
    tabla = comp[["componente", "pasajeros", "participacion"]].rename(columns={"componente": "Componente", "pasajeros": "Pax 2027", "participacion": "Participación"})
    st.dataframe(tabla, width="stretch", hide_index=True, height=190, column_config={"Pax 2027": st.column_config.NumberColumn("Pax 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.1%%")})


def render_servicio_generico_ejecutivo(s, serv, uni, detalle):
    nombre = O.NOMBRE[s]
    serie = serv[s].astype(float).copy()
    total = float(serie.sum())
    viajes_m = _servicios_mensuales_desde_detalle(detalle, s, serie.index)
    viajes_total = float(viajes_m.sum())
    pax_servicio = total / viajes_total if viajes_total > 0 else 0.0
    _, mes_labels = _month_labels_from_index(serie.index)
    pax_servicio_m = (serie / viajes_m.replace(0, pd.NA)).astype(float).fillna(0.0)
    cierre_2026 = _cierre_2026_servicio(s, serv)
    peak_period = str(serie.idxmax())
    min_period = str(serie.idxmin())
    peak_label = MESES_CORTOS.get(int(peak_period[5:7]), peak_period) if len(peak_period) >= 7 else peak_period
    min_label = MESES_CORTOS.get(int(min_period[5:7]), min_period) if len(min_period) >= 7 else min_period

    efe_service_header(
        f"{nombre} 2027: afluencia y operación",
        "Proyección 2027 y referencias históricas para control operacional, oferta y toma de decisiones.",
        "Proyección 2027",
    )

    cards = [
        {"titulo": "Pasajeros 2027", "valor": fmt_compacto_efe(total), "detalle": fmt_num_efe(total, 0), "delta": fmt_delta_vs(total, cierre_2026), "nota": "Total anual proyectado", "icono": "👥"},
        {"titulo": "Servicios comerciales", "valor": fmt_compacto_efe(viajes_total), "detalle": fmt_num_efe(viajes_total, 0), "delta": "Oferta operacional 2027", "nota": "Total anual de servicios", "icono": "🚆"},
        {"titulo": "Pax/servicio", "valor": fmt_num_efe(pax_servicio, 1), "detalle": f"{fmt_num_efe(pax_servicio, 2)} pax/servicio", "delta": "Indicador operacional", "nota": "Promedio anual", "icono": "●"},
        {"titulo": "Mes peak", "valor": peak_label, "detalle": fmt_num_efe(serie.max(), 0), "delta": "Demanda mensual máxima", "nota": "Pasajeros en mes peak", "icono": "▴"},
        {"titulo": "Mes menor", "valor": min_label, "detalle": fmt_num_efe(serie.min(), 0), "delta": "Demanda mensual mínima", "nota": "Pasajeros en mes menor", "icono": "▾"},
    ]
    resultado_ta = None
    if s == "TREN_ARAUCANIA":
        resultado_ta = calcular_resultado_tren_araucania_anual_cached(serie.to_dict())
        anual_ta = resultado_ta["resumen_anual"]
        cards.extend([
            {"titulo": "Venta de pasajes", "valor": fmt_clp_compacto(anual_ta.get("ingreso_venta", 0)), "detalle": fmt_clp_detalle(anual_ta.get("ingreso_venta", 0)), "delta": "Ingreso tarifario", "nota": "Normal, Adulto Mayor, Estudiante, Claret y Delegación", "icono": "▰"},
            {"titulo": "Subsidio total", "valor": fmt_clp_compacto(anual_ta.get("subsidio_total", 0)), "detalle": fmt_clp_detalle(anual_ta.get("subsidio_total", 0)), "delta": "Normal + estudiante", "nota": "Tasa normal 12,7%", "icono": "▣"},
            {"titulo": "Ingreso total", "valor": fmt_clp_compacto(anual_ta.get("ingreso_total_tren_araucania", 0)), "detalle": fmt_clp_detalle(anual_ta.get("ingreso_total_tren_araucania", 0)), "delta": "Venta + subsidio", "nota": f"Tarifa media total: {fmt_num_efe(anual_ta.get('tarifa_media_total', 0), 0)}", "icono": "▥"},
        ])

    render_metric_grid(cards, cols_per_row=5)

    c1, c2 = st.columns([1.05, 1.0])
    with c1:
        efe_section("Evolución mensual y ocupación", "Histórico/cierre disponible y proyección mensual 2027.")
        st.plotly_chart(fig_evolucion_servicio(s, serv), width="stretch")
    with c2:
        efe_section("Pax/servicio mensual", "Indicador mensual sobre servicios comerciales proyectados.")
        ref = pax_servicio if pax_servicio > 0 else None
        st.plotly_chart(fig_pax_servicio(mes_labels, pax_servicio_m.values, ref), width="stretch")

    tabla = pd.DataFrame({
        "Mes": mes_labels,
        "Afluencia 2027": serie.values,
        "Servicios comerciales": viajes_m.values,
        "Pax/servicio": pax_servicio_m.values,
        "Participación mensual": serie.values / total if total else 0.0,
    })
    c3, c4 = st.columns([1.0, 1.15])
    with c3:
        efe_section("Participación mensual 2027", "Control mensual de demanda, oferta y carga relativa.")
        st.dataframe(tabla, width="stretch", hide_index=True, height=325, column_config={
            "Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"),
            "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d"),
            "Pax/servicio": st.column_config.NumberColumn("Pax/servicio", format="%.1f"),
            "Participación mensual": st.column_config.NumberColumn("Participación mensual", format="%.1%%"),
        })
    with c4:
        efe_section("Distribución operacional", "Composición por unidad, tramo o servicio modelado.")
        render_componentes_servicio(detalle, s)

    c5, c6 = st.columns([1.0, 1.0])
    with c5:
        efe_section("Componentes que explican el resultado", "Detalle mensual del cálculo oferta-demanda.")
        detalle_mes = tabla_detalle_mes(detalle, s)
        if not detalle_mes.empty:
            vista = detalle_mes[["periodo", "viajes_operados_plan", "demanda_proyectada", "var_oferta_operada_pct", "var_demanda_pct", "elasticidad_media"]].rename(columns={
                "periodo": "Periodo",
                "viajes_operados_plan": "Servicios",
                "demanda_proyectada": "Demanda",
                "var_oferta_operada_pct": "Var. oferta",
                "var_demanda_pct": "Var. demanda",
                "elasticidad_media": "Elasticidad",
            })
            st.dataframe(vista, width="stretch", hide_index=True, height=285, column_config={
                "Servicios": st.column_config.NumberColumn("Servicios", format="%d"),
                "Demanda": st.column_config.NumberColumn("Demanda", format="%d"),
                "Var. oferta": st.column_config.NumberColumn("Var. oferta", format="%.1f%%"),
                "Var. demanda": st.column_config.NumberColumn("Var. demanda", format="%.1f%%"),
                "Elasticidad": st.column_config.NumberColumn("Elasticidad", format="%.2f"),
            })
        else:
            st.info("No hay detalle mensual disponible.")
    with c6:
        efe_section("Advertencias y cobertura", "Alcance metodológico del servicio.")
        render_alertas(_advertencias_servicio(s))

    if s == "TREN_ARAUCANIA" and resultado_ta is not None:
        anual_ta = resultado_ta["resumen_anual"]
        resumen_tipo_ta = resultado_ta["resumen_tipo_pasajero"].copy()
        resumen_mensual_ta = resultado_ta["resumen_mensual"].copy()
        cta1, cta2 = st.columns([1.0, 1.0])
        with cta1:
            efe_section("Resultados financieros Tren Araucanía", "Venta de pasajes y subsidios calculados sobre distribución OD/tipo de pasajero.")
            tabla_fin = pd.DataFrame([
                {"Concepto": "Venta de pasajes", "Monto anual": anual_ta.get("ingreso_venta", 0)},
                {"Concepto": "Base normal subsidio", "Monto anual": anual_ta.get("monto_base_subsidio_normal", 0)},
                {"Concepto": "Base estudiante sin subsidio", "Monto anual": anual_ta.get("ingreso_teorico_estudiante_sin_subsidio", 0)},
                {"Concepto": "Base estudiante con subsidio", "Monto anual": anual_ta.get("venta_base_estudiante_subsidio", 0)},
                {"Concepto": "Subsidio normal", "Monto anual": anual_ta.get("subsidio_normal", 0)},
                {"Concepto": "Subsidio estudiante", "Monto anual": anual_ta.get("subsidio_estudiante", 0)},
                {"Concepto": "Subsidio total", "Monto anual": anual_ta.get("subsidio_total", 0)},
                {"Concepto": "Ingreso total", "Monto anual": anual_ta.get("ingreso_total_tren_araucania", 0)},
            ])
            st.dataframe(tabla_fin, width="stretch", hide_index=True, height=225, column_config={"Monto anual": st.column_config.NumberColumn("Monto anual", format="$ %d")})
        with cta2:
            efe_section("Distribución por tipo de pasajero", "Viajes, venta y subsidio por tipo.")
            vista_tipo = resumen_tipo_ta[["tipo_pasajero_visual", "viajes", "ingreso_venta", "monto_base_subsidio_normal", "ingreso_teorico_estudiante_sin_subsidio", "venta_base_estudiante_subsidio", "subsidio_total", "participacion"]].rename(columns={
                "tipo_pasajero_visual": "Tipo pasajero",
                "viajes": "Viajes",
                "ingreso_venta": "Venta",
                "monto_base_subsidio_normal": "Base normal",
                "ingreso_teorico_estudiante_sin_subsidio": "Base estudiante sin subsidio",
                "venta_base_estudiante_subsidio": "Base estudiante con subsidio",
                "subsidio_total": "Subsidio",
                "participacion": "Participación",
            })
            st.dataframe(vista_tipo, width="stretch", hide_index=True, height=225, column_config={
                "Viajes": st.column_config.NumberColumn("Viajes", format="%d"),
                "Venta": st.column_config.NumberColumn("Venta", format="$ %d"),
                "Base normal": st.column_config.NumberColumn("Base normal", format="$ %d"),
                "Base estudiante sin subsidio": st.column_config.NumberColumn("Base estudiante sin subsidio", format="$ %d"),
                "Base estudiante con subsidio": st.column_config.NumberColumn("Base estudiante con subsidio", format="$ %d"),
                "Subsidio": st.column_config.NumberColumn("Subsidio", format="$ %d"),
                "Participación": st.column_config.NumberColumn("Participación", format="%.1%%"),
            })
        with st.expander("Detalle OD mensual Tren Araucanía", expanded=False):
            periodos = list(serie.index)
            periodo = st.selectbox("Mes proyectado", periodos, format_func=lambda x: f"{str(x)[5:7]} - 2027", key="od_ta_periodo")
            tipos = [t for t in TAOD.TIPOS_PASAJERO_ESPERADOS if t in set(resumen_tipo_ta["tipo_pasajero"])]
            tipo = st.selectbox("Tipo de pasajero", tipos, key="od_ta_tipo")
            res_mes = calcular_od_tren_araucania_mes_cached(periodo, float(serie.loc[periodo]))
            viajes_long = res_mes["viajes_long"]
            t1, t2, t3 = st.tabs(["Matriz OD viajes", "Matriz OD venta", "Resumen mensual"])
            with t1:
                st.dataframe(TAOD.matriz_tipo(viajes_long, tipo, "viajes_proyectados").round(0).astype(int), width="stretch", height=390)
            with t2:
                st.dataframe(TAOD.matriz_tipo(viajes_long, tipo, "ingreso_venta").round(0).astype(int), width="stretch", height=390)
            with t3:
                st.dataframe(pd.DataFrame([res_mes["resumen_mes"]]), width="stretch", hide_index=True)
        with st.expander("Control financiero mensual Tren Araucanía", expanded=False):
            st.dataframe(resumen_mensual_ta, width="stretch", hide_index=True, height=300, column_config={
                "viajes_tren_araucania": st.column_config.NumberColumn("Viajes", format="%d"),
                "ingreso_venta": st.column_config.NumberColumn("Venta", format="$ %d"),
                "monto_base_subsidio_normal": st.column_config.NumberColumn("Base normal subsidio", format="$ %d"),
                "viajes_base_subsidio_normal": st.column_config.NumberColumn("Viajes base normal", format="%d"),
                "ingreso_teorico_estudiante_sin_subsidio": st.column_config.NumberColumn("Base estudiante sin subsidio", format="$ %d"),
                "venta_base_estudiante_subsidio": st.column_config.NumberColumn("Base estudiante con subsidio", format="$ %d"),
                "viajes_base_subsidio_estudiante": st.column_config.NumberColumn("Viajes base estudiante", format="%d"),
                "subsidio_normal": st.column_config.NumberColumn("Subsidio normal", format="$ %d"),
                "subsidio_estudiante": st.column_config.NumberColumn("Subsidio estudiante", format="$ %d"),
                "subsidio_total": st.column_config.NumberColumn("Subsidio total", format="$ %d"),
                "ingreso_total_tren_araucania": st.column_config.NumberColumn("Ingreso total", format="$ %d"),
            })

    with st.expander("Justificación metodológica", expanded=False):
        render_justificacion_servicio(s, serv, uni, detalle)
    with st.expander("Ecuación específica de proyección", expanded=False):
        render_ecuacion_servicio(s)
    with st.expander("Calendario operacional aplicado", expanded=False):
        st.dataframe(tabla_calendario_servicio(s), width="stretch")
    st.download_button(f"⬇ Descargar proyección {nombre} (CSV)", pd.DataFrame({"periodo": serie.index, "pasajeros": serie.values}).to_csv(index=False).encode(), f"proyeccion_2027_{s}.csv", key=f"dl_{s}_ejecutivo")


def render_biotren_ejecutivo(serv, uni, detalle):
    serie = serv["BIOTREN"].astype(float).copy()
    vigente = _serie_biotren_vigente_pre_redistribucion(serv)
    servicios_mensuales = O.servicios_comerciales_biotren_mensuales(2027).astype(float)
    diag_redistrib = O.diagnostico_redistribucion_biotren_2027(vigente, serie)
    resultado_anual = calcular_resultado_biotren_tarjeta_anual_cached(serie.to_dict())
    resumen_anual_tipo = resultado_anual["resumen_tipo_tarjeta"].copy()
    ingresos_subsidio = resultado_anual.get("ingresos_subsidio_biotren", {})
    anual_sub = ingresos_subsidio.get("resumen_anual", {})
    cobertura = ingresos_subsidio.get("cobertura_estudiante", {})
    resumen_ocup = O.resumen_ocupacion_biotren(serie, 2027)
    diag_ocup = resumen_ocup["diagnostico_mensual"].copy()
    pasajeros = float(anual_sub.get("viajes_biotren", serie.sum()))
    servicios_anuales = float(resumen_ocup["servicios_comerciales_anuales"])
    servicios_equiv = float(resumen_ocup["servicios_equivalentes_capacidad_anuales"])
    pax_servicio = float(resumen_ocup["pax_servicio_comercial_anual"])
    pax_capacidad = float(resumen_ocup["pax_capacidad_equivalente_anual"])
    cierre_2026 = _cierre_2026_servicio("BIOTREN", serv)
    _, mes_labels = _month_labels_from_index(serie.index)

    efe_service_header(
        "Biotren 2027: afluencia, ocupación e ingresos",
        "Proyección 2027 y referencias históricas para la toma de decisiones.",
        "Proyección 2027",
    )

    tasa_ocup_eq = float(resumen_ocup.get("tasa_ocupacion_equivalente_anual", 0.0))
    cards = [
        {"titulo": "Pasajeros 2027", "valor": fmt_compacto_efe(pasajeros), "detalle": fmt_num_efe(pasajeros, 0), "delta": fmt_delta_vs(pasajeros, cierre_2026), "nota": "Total anual Biotren", "icono": "👥"},
        {"titulo": "Servicios comerciales", "valor": fmt_compacto_efe(servicios_anuales), "detalle": fmt_num_efe(servicios_anuales, 0), "delta": "Frecuencia programada", "nota": "Servicios comerciales anuales", "icono": "🚆"},
        {"titulo": "Pax/servicio", "valor": fmt_num_efe(pax_servicio, 1), "detalle": f"{fmt_num_efe(pax_servicio, 2)} pax/servicio comercial", "delta": "Indicador principal", "nota": "Consistente con Resumen", "icono": "●"},
        {"titulo": "Ocupación capacidad", "valor": f"{fmt_num_efe(tasa_ocup_eq * 100, 1)}%", "detalle": "605 pax/tren; acoplados duplican capacidad", "delta": "Capacidad equivalente", "nota": "Tasa anual referencial", "icono": "%"},
        {"titulo": "Servicios equivalentes", "valor": fmt_compacto_efe(servicios_equiv), "detalle": fmt_num_efe(servicios_equiv, 0), "delta": "Capacidad diagnóstica", "nota": f"Pax/capacidad eq.: {fmt_num_efe(pax_capacidad, 2)}", "icono": "▣"},
        {"titulo": "Venta de pasajes", "valor": fmt_clp_compacto(anual_sub.get("ingreso_venta", 0)), "detalle": fmt_clp_detalle(anual_sub.get("ingreso_venta", 0)), "delta": "Sólo Biotren", "nota": "Valor anual proyectado", "icono": "▰"},
        {"titulo": "Subsidio total", "valor": fmt_clp_compacto(anual_sub.get("subsidio_total", 0)), "detalle": fmt_clp_detalle(anual_sub.get("subsidio_total", 0)), "delta": "Normal + estudiante", "nota": "Valor anual proyectado", "icono": "▣"},
        {"titulo": "Ingreso total", "valor": fmt_clp_compacto(anual_sub.get("ingreso_total_biotren", 0)), "detalle": fmt_clp_detalle(anual_sub.get("ingreso_total_biotren", 0)), "delta": "Venta + subsidios", "nota": "Valor anual proyectado", "icono": "▥"},
        {"titulo": "Subsidio normal", "valor": fmt_clp_compacto(anual_sub.get("subsidio_normal", 0)), "detalle": fmt_clp_detalle(anual_sub.get("subsidio_normal", 0)), "delta": "Tasa 18,9%", "nota": "Grupo normal", "icono": "◈"},
        {"titulo": "Subsidio estudiante", "valor": fmt_clp_compacto(anual_sub.get("subsidio_estudiante", 0)), "detalle": fmt_clp_detalle(anual_sub.get("subsidio_estudiante", 0)), "delta": "Media superior", "nota": "Brecha tarifaria", "icono": "▰"},
    ]
    render_metric_grid(cards, cols_per_row=5)

    c1, c2 = st.columns([1.04, 1.0])
    with c1:
        efe_section("Evolución mensual y ocupación", "Comparación mensual disponible y ocupación relativa 2027.")
        try:
            from plotly.subplots import make_subplots
            ref = _linea_referencia_mensual("BIOTREN", serv, anios=(2025, 2026, 2027))
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            estilos = {
                2026: (EFE_BLUE, "solid", 3, "2026 (pax)"),
                2027: (EFE_RED, "solid", 3, "2027 (pax)"),
                2025: ("#3D7EDB", "dash", 2, "2025 (pax)"),
            }
            if not ref.empty:
                for anio, (color, dash, width, label) in estilos.items():
                    d = ref[ref["anio"].astype(int).eq(anio)]
                    if not d.empty:
                        fig.add_trace(go.Scatter(x=d["mes_label"], y=d["afluencia"].astype(float), mode="lines+markers", name=label, line=dict(color=color, dash=dash, width=width), marker=dict(size=6)), secondary_y=False)
            ocup_rel = diag_ocup["tasa_ocupacion_equivalente_pct"].astype(float) * 100.0
            fig.add_trace(go.Scatter(x=mes_labels, y=ocup_rel, name="Ocupación 2027 (%)", mode="lines", fill="tozeroy", line=dict(color="#DCE8F5", width=1), fillcolor="rgba(0,58,112,.10)"), secondary_y=True)
            fig.update_yaxes(title_text="Pasajeros", secondary_y=False, gridcolor=EFE_GRID)
            fig.update_yaxes(title_text="Ocupación capacidad (%)", secondary_y=True, range=[0, max(100, float(ocup_rel.max()) * 1.20)], showgrid=False)
            fig.update_layout(height=330, margin=dict(l=14, r=14, t=24, b=18), plot_bgcolor="white", paper_bgcolor="white", font=dict(family="Univia Pro, Inter, Segoe UI, Arial", color=EFE_TEXT, size=12), hovermode="x unified", legend=dict(orientation="h", y=1.15, x=0))
            fig.update_xaxes(showgrid=False, zeroline=False)
            st.plotly_chart(fig, width="stretch")
        except Exception:
            st.plotly_chart(fig_evolucion_servicio("BIOTREN", serv), width="stretch")
    with c2:
        efe_section("Pax/servicio mensual", "Servicios comerciales; línea roja de referencia 300 pax/servicio.")
        st.plotly_chart(fig_pax_servicio(mes_labels, diag_ocup["pax_servicio_comercial"].astype(float).values, 300), width="stretch")

    total = float(serie.sum())
    tabla_mensual = pd.DataFrame({
        "Mes": mes_labels,
        "Afluencia 2027": serie.values,
        "Servicios comerciales": servicios_mensuales.reindex(serie.index).values,
        "Pax/servicio": diag_ocup["pax_servicio_comercial"].values,
        "Participación mensual": serie.values / total if total else 0.0,
    })
    dist_linea = calcular_distribucion_biotren_linea_mod_cached(serie.to_dict())
    anual_linea = dist_linea.groupby("linea_od", as_index=False).agg(viajes=("viajes_proyectados", "sum"))
    anual_linea = anual_linea.set_index("linea_od").reindex(["L2", "L1", "L1-L2"]).fillna(0.0).reset_index()
    mapa_linea = {"L2": "L2 Concepción/Coronel", "L1": "L1 Talcahuano/Hualqui", "L1-L2": "Interlínea L1-L2"}
    anual_linea["linea"] = anual_linea["linea_od"].map(mapa_linea).fillna(anual_linea["linea_od"])
    anual_linea["participacion"] = anual_linea["viajes"] / float(anual_linea["viajes"].sum()) if float(anual_linea["viajes"].sum()) else 0.0

    resumen_tipo = resumen_anual_tipo.groupby(["tipo_tarjeta", "nombre_visual", "tipo_pasajero_tarifa"], as_index=False).agg(viajes=("viajes_proyectados", "sum"), venta_pasajes=("ingresos_tarifarios_proyectados", "sum"))
    resumen_tipo = resumen_tipo.sort_values("viajes", ascending=False)
    resumen_tipo["participacion"] = resumen_tipo["viajes"] / float(resumen_tipo["viajes"].sum()) if float(resumen_tipo["viajes"].sum()) else 0.0
    resumen_tipo["rol_tarifario"] = resumen_tipo["tipo_tarjeta"].map(_rol_tarjetario)
    resumen_tipo["grupo_subsidio"] = resumen_tipo["tipo_tarjeta"].map(_grupo_subsidio_tarjeta)

    c3, c4, c5 = st.columns([1.0, 1.0, 1.05])
    with c3:
        efe_section("Participación mensual y redistribución 2027", "Control mensual de afluencia, oferta y carga.")
        st.dataframe(tabla_mensual, width="stretch", hide_index=True, height=315, column_config={
            "Afluencia 2027": st.column_config.NumberColumn("Afluencia 2027", format="%d"),
            "Servicios comerciales": st.column_config.NumberColumn("Servicios comerciales", format="%d"),
            "Pax/servicio": st.column_config.NumberColumn("Pax/servicio", format="%.1f"),
            "Participación mensual": st.column_config.NumberColumn("Participación mensual", format="%.1%%"),
        })
    with c4:
        efe_section("Distribución por línea", "Distribución MOD posterior al total Biotren.")
        fig_linea = go.Figure(go.Pie(labels=anual_linea["linea"], values=anual_linea["viajes"], hole=.60, marker=dict(colors=EFE_COLORS), textinfo="percent", sort=False))
        fig_linea.update_layout(height=240, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, paper_bgcolor="white", annotations=[dict(text=f"{fmt_m_efe(pasajeros)}<br>Pax 2027", x=.5, y=.5, showarrow=False, font=dict(color=EFE_BLUE, size=15))])
        st.plotly_chart(fig_linea, width="stretch")
        st.dataframe(anual_linea[["linea", "viajes", "participacion"]].rename(columns={"linea": "Línea", "viajes": "Pax 2027", "participacion": "Participación"}), width="stretch", hide_index=True, height=150, column_config={"Pax 2027": st.column_config.NumberColumn("Pax 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.1%%")})
    with c5:
        efe_section("Distribución por tipo de tarjeta", "Viajes e ingresos tarifarios proyectados.")
        top_tipo = resumen_tipo.head(5).copy()
        fig_tipo = go.Figure(go.Pie(labels=top_tipo["nombre_visual"], values=top_tipo["viajes"], hole=.60, marker=dict(colors=EFE_COLORS), textinfo="percent", sort=False))
        fig_tipo.update_layout(height=240, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, paper_bgcolor="white", annotations=[dict(text=f"{fmt_m_efe(pasajeros)}<br>Pax 2027", x=.5, y=.5, showarrow=False, font=dict(color=EFE_BLUE, size=15))])
        st.plotly_chart(fig_tipo, width="stretch")
        st.dataframe(resumen_tipo[["nombre_visual", "viajes", "participacion"]].rename(columns={"nombre_visual": "Tipo de tarjeta", "viajes": "Pax 2027", "participacion": "Participación"}).head(7), width="stretch", hide_index=True, height=150, column_config={"Pax 2027": st.column_config.NumberColumn("Pax 2027", format="%d"), "Participación": st.column_config.NumberColumn("Participación", format="%.1%%")})

    venta_por_tipo = resumen_tipo.set_index("tipo_tarjeta")["venta_pasajes"].to_dict()
    tabla_fin = _tabla_financiera_biotren(anual_sub, venta_por_tipo)
    c6, c7 = st.columns([1.0, 1.0])
    with c6:
        efe_section("Resultados financieros Biotren", "Millones de CLP; cálculo tarifario implementado sólo para Biotren.")
        vista_fin = tabla_fin[["Concepto", "Monto anual"]].copy()
        vista_fin["Monto anual"] = vista_fin["Monto anual"].astype(float)
        st.dataframe(vista_fin, width="stretch", hide_index=True, height=275, column_config={"Monto anual": st.column_config.NumberColumn("Monto anual", format="$ %d")})
    with c7:
        efe_section("Advertencias y cobertura", "Controles metodológicos y límites de interpretación.")
        advertencias = _advertencias_servicio("BIOTREN")
        if cobertura.get("sin_cobertura_modelo"):
            advertencias.append("Concepción Centro sin cobertura en matriz estudiante sin subsidio: " + ", ".join(cobertura.get("sin_cobertura_modelo", [])))
        if cobertura.get("estaciones_sin_tarifas"):
            advertencias.append("Estaciones sin tarifas disponibles en matriz estudiante sin subsidio: " + ", ".join(cobertura.get("estaciones_sin_tarifas", [])))
        render_alertas(advertencias)

    with st.expander("Detalle OD mensual por tipo de tarjeta", expanded=False):
        periodos = list(serie.index)
        periodo = st.selectbox("Mes proyectado", periodos, format_func=lambda x: f"{str(x)[5:7]} - 2027", key="od_biotren_periodo_ejecutivo")
        tipo_tarjeta = st.selectbox("Tipo de tarjeta", OD.TIPOS_TARJETA_ESPERADOS, key="od_biotren_tipo_tarjeta_ejecutivo")
        resultado_mes = calcular_od_biotren_tarjeta_mes_cached(periodo, float(serie.loc[periodo]))
        viajes_long = resultado_mes["viajes_tipo_tarjeta_long"]
        resumen_mes = resultado_mes["resumen_tipo_tarjeta"].copy()
        M = _matriz_tarjeta(viajes_long, tipo_tarjeta, "viajes_proyectados")
        R = _matriz_tarjeta(viajes_long, tipo_tarjeta, "ingresos_tarifarios_proyectados")
        t1, t2, t3 = st.tabs(["Matriz OD viajes", "Matriz OD ingresos", "Resumen mensual"])
        with t1:
            st.dataframe(M.round(0).astype(int).copy(deep=True), width="stretch", height=420)
        with t2:
            st.dataframe(R.round(0).astype(int).copy(deep=True), width="stretch", height=420)
        with t3:
            st.dataframe(resumen_mes, width="stretch", height=260)
    with st.expander("Justificación metodológica", expanded=False):
        st.markdown("""
- El escenario Biotren 2027 se formula como un escenario de gestión operacional-comercial.
- La frecuencia comercial distingue servicios comerciales de capacidad efectiva.
- L2 mantiene 110 servicios L-V; los 3 acoplados desde mayo son capacidad equivalente y no frecuencia adicional.
- Integración TP y plan evasión fundamentan el escenario consolidado; no se suman nuevamente sobre la demanda anual.
- Las bandas mensuales son diagnósticas y no recalibran la demanda.
""")
        render_biotren_fundamento_gestion()
    with st.expander("Diagnóstico técnico de capacidad equivalente", expanded=False):
        tecnico = diag_ocup.rename(columns={"mes": "Mes", "afluencia_biotren": "Afluencia 2027", "servicios_comerciales": "Servicios comerciales", "servicios_equivalentes_capacidad": "Servicios equivalentes capacidad", "pax_servicio_comercial": "Pax/servicio comercial", "pax_capacidad_equivalente": "Pax/capacidad equivalente", "banda_funcionamiento": "Banda"})
        st.dataframe(tecnico, width="stretch", hide_index=True, height=330)
    with st.expander("Detalle de redistribución mensual", expanded=False):
        st.dataframe(diag_redistrib, width="stretch", hide_index=True, height=320)
    with st.expander("Ecuaciones y controles internos", expanded=False):
        render_incertidumbre_biotren(serv)


def render_servicio(s):
    cf = CONF[s]
    st.markdown(f"<span class='badge'>Confianza {cf}</span>", unsafe_allow_html=True)

    with st.expander("Parámetros de oferta 2027", expanded=False):
        ce = {}
        plan_tramos = None
        if s == "BIOTREN":
            st.info("Biotren se edita por línea. L1 considera 47 servicios L-V durante 2027; L2 mantiene 110 servicios L-V todo el año. Desde mayo, 3 servicios L2 L-V operan acoplados dentro de esos 110 y se registran sólo como capacidad efectiva.")
            c1, c2 = st.columns(2)
            with c1:
                plan_l1 = editor_oferta("BIOTREN_L1", "Línea 1")
            with c2:
                plan_l2 = editor_oferta("BIOTREN_L2", "Línea 2")
            plan = pd.concat([plan_l1, plan_l2], ignore_index=True)
        elif s == "TREN_ARAUCANIA":
            plan_tramos, plan = editor_tren_araucania()
        else:
            plan = editor_oferta(O.UNIDADES_DE[s][0], O.NOMBRE[s])

        st.markdown("**Contingencia adicional sobre supresión histórica**")
        unidades_ce = O.UNIDADES_DE[s]
        cc = st.columns(len(unidades_ce))
        for i, u in enumerate(unidades_ce):
            ce[u] = cc[i].number_input(f"{u} (+% supresión)", 0.0, 30.0, 0.0, 1.0, key=f"ce_{u}") / 100.0

    uni, serv, detalle = O.proyectar_mensual_elastico(params, mdf, plan=plan, contingencia_extra=ce, return_detalle=True)

    if s == "BIOTREN":
        render_biotren_ejecutivo(serv, uni, detalle)
    elif s == "CORTO_LAJA":
        render_laja_talcahuano_ejecutivo(serv, uni, detalle)
    else:
        render_servicio_generico_ejecutivo(s, serv, uni, detalle)

tabs = st.tabs(["📘 Metodología", "📊 Resumen", "🧪 Validación histórica"] + [O.NOMBRE[s] for s in O.SERVICIOS])
with tabs[0]:
    render_metodologia()
with tabs[1]:
    render_resumen()
with tabs[2]:
    render_validacion_historica()
for i, s in enumerate(O.SERVICIOS):
    with tabs[i + 3]:
        render_servicio(s)
