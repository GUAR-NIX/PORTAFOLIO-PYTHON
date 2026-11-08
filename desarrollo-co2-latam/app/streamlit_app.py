"""
App para comparar países: crecimiento vs emisiones en América Latina.

    streamlit run app/streamlit_app.py

Lee solo el panel versionado (data/procesados/panel_latam.csv): funciona sin descargar nada.
"""
import sys
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from desarrollo_co2 import config, desacople, graficos  # noqa: E402
from desarrollo_co2.graficos import num  # noqa: E402

st.set_page_config(page_title="Desarrollo y CO2 en América Latina", page_icon="🌎", layout="wide")

INDICADORES = {
    "CO2 por persona (t)": "co2_pc_t",
    "CO2 por USD de PIB (kg, PPA 2021)": "intensidad_co2_kg_usd",
    "PIB per cápita (USD PPA 2021)": "pib_pc_ppa",
    "Energía primaria por persona (MWh)": "energia_pc_mwh",
    "CO2 por kWh de energía (kg)": "carbono_energia_kg_kwh",
    "CO2 de consumo por persona (t)": "co2_consumo_pc_t",
    "Energía renovable (% del consumo final)": "renovable_pct_consumo",
    "Pobreza extrema (%)": "pobreza_extrema_pct",
    "Población urbana (%)": "urbana_pct",
}
MEDIDAS_CO2 = {"Territorial (producción)": "co2_mt", "Basado en consumo": "co2_consumo_mt"}


@st.cache_data
def cargar() -> pd.DataFrame:
    return pd.read_csv(config.PANEL)


panel = cargar()
nombres = dict(zip(panel["iso3"], panel["pais"]))
iso_por_nombre = {v: k for k, v in nombres.items()}
con_pib = sorted(panel.dropna(subset=["pib_ppa"])["pais"].unique())

# --- Controles -------------------------------------------------------------
st.sidebar.header("Filtros")
# valores iniciales desde la URL (enlaces para compartir), p. ej. ?pais=Brasil&desde=2012&hasta=2024&medida=consumo
qp = st.query_params
pais_inicial = qp.get("pais", "Ecuador") if qp.get("pais") in con_pib else "Ecuador"
try:
    periodo_inicial = (max(1990, int(qp.get("desde", config.PERIODO_DESACOPLE[0]))),
                       min(2024, int(qp.get("hasta", config.PERIODO_DESACOPLE[1]))))
except ValueError:
    periodo_inicial = config.PERIODO_DESACOPLE
pais = st.sidebar.selectbox("País", con_pib, index=con_pib.index(pais_inicial), key="pais")
comparar = st.sidebar.multiselect("Comparar con", sorted(nombres.values()),
                                  default=[config.NOMBRE_REGION, "Colombia", "Perú"], key="comparar")
periodo = st.sidebar.slider("Periodo", 1990, 2024, periodo_inicial, key="periodo")
medida = st.sidebar.radio("Medida de CO2", list(MEDIDAS_CO2), index=int(qp.get("medida") == "consumo"), key="medida")
st.sidebar.caption("Los extremos del periodo son promedios de 3 años (si el periodo es corto, de 1 año).")

col_co2 = MEDIDAS_CO2[medida]
ini, fin = periodo
ventana = config.VENTANA_EXTREMOS if fin - ini >= 8 else 1
if col_co2 == "co2_consumo_mt" and fin > 2023:
    fin = 2023
    st.sidebar.info("El CO2 de consumo llega hasta 2023: el periodo termina en 2023.")
iso = iso_por_nombre[pais]

# --- Encabezado y KPIs -----------------------------------------------------
st.title("🌎 ¿Crecer sin emitir más? Desarrollo y CO2 en América Latina")
st.caption("Banco Mundial (PIB PPA, población) + Our World in Data / Global Carbon Project (CO2). "
           "Desacople = el PIB crece más rápido que las emisiones.")

tabla = desacople.tabla_desacople(panel, ini, fin, col_co2=col_co2, ventana=ventana)
fila = tabla.set_index("iso3").loc[iso]
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"{pais}: PIB real", f"{num(fila['crec_pib_anual'], 1)} % anual")
k2.metric(f"{pais}: CO2", f"{num(fila['crec_co2_anual'], 1)} % anual")
k3.metric(f"{pais}: elasticidad CO2/PIB", num(fila["elasticidad"], 2))
k4.metric(f"{pais}: clasificación", str(fila["categoria"]), fila["tapio"], delta_color="off")

# --- Índices del país ------------------------------------------------------
izq, der = st.columns(2)
with izq:
    st.subheader(f"{pais}: PIB y CO2 (índice {ini} = 100)")
    g = panel[(panel["iso3"] == iso) & panel["anio"].between(ini, fin)].set_index("anio")
    series = {"PIB real": "pib_ppa", "CO2": col_co2, "Población": "poblacion_bm"}
    ind = pd.DataFrame({etq: 100 * g[c] / g[c].iloc[0] for etq, c in series.items()}).reset_index()
    largo = ind.melt("anio", var_name="serie", value_name="indice")
    escala = alt.Scale(domain=list(series), range=[config.COLORES[0], config.COLORES[1], config.GRIS])
    lineas = alt.Chart(largo).mark_line(strokeWidth=2).encode(
        x=alt.X("anio:Q", title=None, axis=alt.Axis(format="d")),
        y=alt.Y("indice:Q", title="Índice", scale=alt.Scale(zero=False)),
        color=alt.Color("serie:N", scale=escala, legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.StrokeDash("serie:N", legend=None,
                                  scale=alt.Scale(domain=list(series), range=[[1, 0], [1, 0], [5, 4]])),
        tooltip=[alt.Tooltip("anio:Q", title="Año"), alt.Tooltip("serie:N", title="Serie"),
                 alt.Tooltip("indice:Q", title="Índice", format=".0f")])
    # una sola capa: en Streamlit 1.66 los gráficos Altair compuestos (capas) no se dibujan
    st.altair_chart(lineas.properties(height=360), width="stretch")

with der:
    st.subheader("Comparar un indicador")
    nombre_ind = st.selectbox("Indicador", list(INDICADORES), key="indicador")
    col = INDICADORES[nombre_ind]
    sel = [pais, *[c for c in comparar if c != pais]]
    d = panel[panel["pais"].isin(sel) & panel["anio"].between(*periodo)].dropna(subset=[col])
    # el color sigue al país dentro de la selección (el país elegido siempre es el primero)
    escala = alt.Scale(domain=sel, range=[config.COLORES[i % len(config.COLORES)] for i in range(len(sel))])
    graf = alt.Chart(d).mark_line(strokeWidth=2).encode(
        x=alt.X("anio:Q", title=None, axis=alt.Axis(format="d")),
        y=alt.Y(f"{col}:Q", title=nombre_ind),
        color=alt.Color("pais:N", scale=escala, legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("pais:N", title="País"), alt.Tooltip("anio:Q", title="Año"),
                 alt.Tooltip(f"{col}:Q", title=nombre_ind, format=",.2f")])
    st.altair_chart(graf.properties(height=360), width="stretch")

# --- Mapa de desacople de todos los países ---------------------------------
# Misma figura del informe (matplotlib), recalculada con el periodo y la medida elegidos.
st.subheader(f"Desacople de todos los países, {ini}–{fin} ({medida.lower()})")
figura = graficos.desacople_dispersion(tabla, (ini, fin), nombre=None)
figura.axes[0].set_title("")  # el subtítulo de Streamlit ya dice el periodo
st.pyplot(figura, width="stretch")
plt.close(figura)

conteo = desacople.conteo_categorias(tabla)
st.markdown(" · ".join(f"**{c}**: {n}" for c, n in conteo.items() if n))

with st.expander("Tabla completa"):
    vista = tabla[["pais", "crec_pib_anual", "crec_co2_anual", "elasticidad", "cambio_intensidad_pct",
                   "categoria", "tapio"]].rename(columns={
        "pais": "País", "crec_pib_anual": "PIB % anual", "crec_co2_anual": "CO2 % anual",
        "elasticidad": "Elasticidad", "cambio_intensidad_pct": "Cambio intensidad %",
        "categoria": "Clasificación", "tapio": "Tapio"})
    st.dataframe(vista.round(2), hide_index=True, width="stretch")

st.caption("Cuba y Venezuela no tienen PIB en el Banco Mundial y quedan fuera de la clasificación. "
           "Código y metodología: README del proyecto.")
