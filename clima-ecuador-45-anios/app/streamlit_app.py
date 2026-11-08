"""
Explorador del clima de 22 ciudades del Ecuador (ERA5, 1980–2024).

    streamlit run app/streamlit_app.py

Funciona solo con las tablas versionadas de data/procesados (no necesita descargar nada).
Acepta enlaces del tipo ``?ciudad=Cuenca&variable=precip&desde=1990&hasta=2024``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clima_ecuador import config, graficos, tendencias  # noqa: E402
from clima_ecuador.extremos import NOMBRES  # noqa: E402

st.set_page_config(page_title="Clima del Ecuador 1980–2024", page_icon="🌦️", layout="wide")

VARIABLES = {
    "tmed": ("Temperatura media", "°C", "mean"), "tmax": ("Temperatura máxima", "°C", "mean"),
    "tmin": ("Temperatura mínima", "°C", "mean"), "precip": ("Lluvia", "mm", "sum"),
    "humedad": ("Humedad relativa", "%", "mean"), "viento_max": ("Viento máximo diario", "km/h", "mean"),
    "radiacion": ("Radiación solar", "MJ/m² por día", "mean"),
}
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


@st.cache_data
def cargar():
    mensual = pd.read_parquet(config.MENSUAL)
    mensual = mensual[mensual["punto"].isin(config.CIUDADES)]
    indices = pd.read_parquet(config.ANUAL)
    corr = pd.read_csv(config.REPORTES / "enso_correlaciones_ciudades.csv")
    return mensual, indices, corr


def formato_p(p: float) -> str:
    return "p < 0,001" if p < 0.001 else f"p = {p:.3f}".replace(".", ",")


def anual_de(mensual: pd.DataFrame, ciudad: str, variable: str) -> pd.DataFrame:
    d = mensual[mensual["punto"] == ciudad].assign(anio=lambda x: x["mes"].dt.year)
    agregado = VARIABLES[variable][2]
    g = d.groupby("anio")[variable]
    serie = g.sum(min_count=12) if agregado == "sum" else g.mean().where(g.count() == 12)
    return serie.dropna().rename("valor").reset_index()


def leer_parametros() -> None:
    q = st.query_params
    if "ciudad" in q and q["ciudad"] in config.CIUDADES and "ciudad" not in st.session_state:
        st.session_state["ciudad"] = q["ciudad"]
    if "variable" in q and q["variable"] in VARIABLES and "variable" not in st.session_state:
        st.session_state["variable"] = q["variable"]
    if "desde" in q and "hasta" in q and "periodo" not in st.session_state:
        try:
            st.session_state["periodo"] = (max(int(q["desde"]), config.ANIO_INICIO), min(int(q["hasta"]), config.ANIO_FIN))
        except ValueError:
            pass


mensual, indices, corr = cargar()
leer_parametros()

st.title("🌦️ ¿Cómo ha cambiado el clima del Ecuador desde 1980?")
st.caption("ERA5 (reanálisis de ECMWF, celdas de ~25 km) vía Open-Meteo · 22 ciudades · tendencias con Mann-Kendall "
           "corregido por autocorrelación (Hamed-Rao) y pendiente de Sen")

with st.sidebar:
    st.header("Filtros")
    ciudades = [c for r in config.REGIONES for c, v in config.CIUDADES.items() if v[3] == r]
    ciudad = st.selectbox("Ciudad", ciudades, index=ciudades.index("Quito"), key="ciudad",
                          format_func=lambda c: f"{c} ({config.CIUDADES[c][3]})")
    variable = st.selectbox("Variable", list(VARIABLES), key="variable", format_func=lambda v: VARIABLES[v][0])
    desde, hasta = st.slider("Periodo", config.ANIO_INICIO, config.ANIO_FIN, (config.ANIO_INICIO, config.ANIO_FIN),
                             key="periodo")
    st.caption("La temperatura está corregida por la diferencia de altitud entre la ciudad y la celda de ERA5 "
               "(−6,5 °C/km). La lluvia de ERA5 en la Sierra está muy sobrestimada: mira la validación del README.")

nombre_var, unidad, _ = VARIABLES[variable]
lat, lon, alt_m, region = config.CIUDADES[ciudad]
anual = anual_de(mensual, ciudad, variable)
periodo = anual[anual["anio"].between(desde, hasta)]
ref = anual[anual["anio"].between(*config.PERIODO_REFERENCIA)]["valor"]
normal = float(ref.mean()) if len(ref) else np.nan

if len(periodo) >= 10:
    mk = tendencias.mann_kendall(periodo["valor"].to_numpy(), correccion="hamed_rao", factor_minimo=1)
    pendiente = mk.pendiente * 10
    texto_p = f"{formato_p(mk.p)} ({'significativa' if mk.p < 0.05 else 'no significativa'})"
else:
    mk, pendiente, texto_p = None, np.nan, "se necesitan 10 años"

ultimos = anual[anual["anio"].between(hasta - 9, hasta)]["valor"].mean()
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{ciudad}: normal 1981–2010", f"{normal:,.1f} {unidad}".replace(",", " "))
c2.metric(f"Tendencia {desde}–{hasta} ({unidad}/década)", f"{pendiente:+.2f}", texto_p, delta_color="off")
c3.metric(f"Media {max(hasta - 9, desde)}–{hasta}", f"{ultimos:,.1f} {unidad}".replace(",", " "),
          f"{ultimos - normal:+.2f} vs normal", delta_color="off")
c4.metric("Altitud · región", f"{alt_m:,} m".replace(",", "."), region, delta_color="off")

izq, der = st.columns([2.2, 1])
with izq:
    st.subheader(f"{nombre_var} anual en {ciudad}")
    base = alt.Chart(periodo).mark_line(point=True, strokeWidth=2, color=config.COLOR_REGION[region]).encode(
        x=alt.X("anio:Q", title="Año", axis=alt.Axis(format="d")),
        y=alt.Y("valor:Q", title=f"{nombre_var} ({unidad})", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("anio:Q", title="Año"), alt.Tooltip("valor:Q", title=unidad, format=".2f")])
    st.altair_chart(base, use_container_width=True)
    if mk:
        st.caption(f"Pendiente de Sen: **{pendiente:+.3f} {unidad}/década** (IC 95 %: {mk.ic_bajo * 10:+.3f} a "
                   f"{mk.ic_alto * 10:+.3f}) · cambio en el periodo: {mk.pendiente * (len(periodo) - 1):+.2f} {unidad} · "
                   f"factor de varianza Hamed-Rao: {mk.n_efectivo_factor:.2f}")
with der:
    st.subheader("Ubicación")
    graficos.estilo()
    fig, ax = plt.subplots(figsize=(4, 4.2))
    anillos = graficos.leer_provincias()
    galapagos = region == "Galápagos"
    graficos.mapa_base(ax, anillos, graficos.EXT_GALAPAGOS if galapagos else graficos.EXT_CONTINENTE)
    for c, (la, lo, _, r) in config.CIUDADES.items():
        if (r == "Galápagos") == galapagos:
            ax.scatter(lo, la, s=90 if c == ciudad else 18, color=config.COLOR_REGION[r],
                       edgecolor=config.TEXTO if c == ciudad else "white", linewidth=1.5 if c == ciudad else 0.5, zorder=3)
    ax.annotate(ciudad, (lon, lat), xytext=(6, 4), textcoords="offset points", fontsize=9, fontweight="bold")
    st.pyplot(fig)
    plt.close(fig)

a, b = st.columns(2)
with a:
    st.subheader("Ciclo anual (normal 1981–2010)")
    m = mensual[(mensual["punto"] == ciudad) & mensual["mes"].dt.year.between(*config.PERIODO_REFERENCIA)]
    clim = m.groupby(m["mes"].dt.month)[variable].mean().reset_index()
    clim["nombre_mes"] = [MESES[i - 1] for i in clim["mes"]]
    st.altair_chart(alt.Chart(clim).mark_bar(color=config.COLOR_REGION[region], cornerRadiusTopLeft=3,
                                             cornerRadiusTopRight=3).encode(
        x=alt.X("nombre_mes:N", sort=MESES, title=None), y=alt.Y(f"{variable}:Q", title=f"{nombre_var} ({unidad})"),
        tooltip=[alt.Tooltip("nombre_mes:N", title="Mes"), alt.Tooltip(f"{variable}:Q", format=".1f")]),
        use_container_width=True)
with b:
    st.subheader("Relación con El Niño (ONI)")
    cc = corr[(corr["punto"] == ciudad)].copy()
    cc["serie"] = cc["variable"].map({"precip_pct": "Lluvia", "tmed": "Temperatura media"})
    cc["significativa"] = np.where(cc["p"] < 0.05, "sí", "no")
    st.altair_chart(alt.Chart(cc).mark_bar().encode(
        x=alt.X("rezago:O", title="Meses que el ONI se adelanta"), y=alt.Y("r:Q", title="Correlación"),
        color=alt.Color("serie:N", scale=alt.Scale(range=[config.FRIO, config.CALIDO]), title=None),
        xOffset="serie:N",
        tooltip=["serie", "rezago", alt.Tooltip("r:Q", format=".2f"), alt.Tooltip("p:Q", format=".3f"),
                 "significativa"]), use_container_width=True)
    st.caption("p con tamaño de muestra efectivo (Bretherton 1999): la autocorrelación reduce los datos independientes.")

st.subheader(f"Extremos en {ciudad}: {desde}–{hasta}")
ind = indices[(indices["punto"] == ciudad) & indices["anio"].between(desde, hasta)]
filas = []
for col in ["tx90p", "tn90p", "dias_ola_calor", "r20mm", "rx1day", "cdd"]:
    x = ind.sort_values("anio")[col].to_numpy()
    if len(x) >= 10:
        r = tendencias.mann_kendall(x, correccion="hamed_rao", factor_minimo=1)
        filas.append({"Índice": NOMBRES[col], "Media": round(float(np.mean(x)), 1),
                      "Primeros 10 años": round(float(np.mean(x[:10])), 1),
                      "Últimos 10 años": round(float(np.mean(x[-10:])), 1),
                      "Tendencia por década": round(r.pendiente * 10, 2), "p (Hamed-Rao)": formato_p(r.p)})
st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
st.caption("Umbrales de calor: percentil 90 de cada día del año en 1981–2010 para esta ciudad. "
           "Ola de calor: 3 o más días seguidos sobre ese umbral.")
