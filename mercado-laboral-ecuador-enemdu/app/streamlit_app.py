"""Tablero interactivo del mercado laboral del Ecuador (INEC ENEMDU 2025).

    streamlit run app/streamlit_app.py

Lee los resultados y tablas procesadas en `reports/` y `data/procesados/`: funciona sin red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from empleo_enemdu.config import DIR_PROCESADOS, DIR_REPORTS, DIR_TABLAS, PALETA, SBU_USD_2025  # noqa: E402

st.set_page_config(
    page_title="Mercado Laboral del Ecuador · ENEMDU 2025",
    page_icon="🇪🇨",
    layout="wide",
)


@st.cache_data
def cargar_datos_app() -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    resultados = json.loads((DIR_REPORTS / "resultados.json").read_text(encoding="utf-8"))
    df_prov = pd.read_csv(DIR_TABLAS / "indicadores_provincias_2025.csv")
    df_sub = pd.read_csv(DIR_TABLAS / "indicadores_subgrupos_2025.csv")
    df_ramas = pd.read_csv(DIR_TABLAS / "indicadores_ramas_ciiu_2025.csv")
    df_cuant = pd.read_csv(DIR_TABLAS / "brecha_cuantilica_genero_2025.csv")
    df_serie = pd.read_csv(DIR_PROCESADOS / "serie_historica_2018_2025.csv")
    return resultados, df_prov, df_sub, df_ramas, df_cuant, df_serie


resultados, df_prov, df_sub, df_ramas, df_cuant, df_serie = cargar_datos_app()

# --- Barra lateral ---
st.sidebar.header("Filtros de exploración")
provincias_lista = ["Nacional (Total)"] + sorted(df_prov["provincia"].unique().tolist())
qp = st.query_params
prov_inicial = qp.get("provincia", "Nacional (Total)")
if prov_inicial not in provincias_lista:
    prov_inicial = "Nacional (Total)"

provincia_sel = st.sidebar.selectbox(
    "Territorio (Provincia / Nacional)",
    provincias_lista,
    index=provincias_lista.index(prov_inicial),
    key="provincia_sel",
)

dimension_sel = st.sidebar.selectbox(
    "Desagregación demográfica",
    [
        "Autoidentificación étnica",
        "Nivel de instrucción",
        "Grupo de edad",
        "Sexo",
        "Área",
    ],
    key="dimension_sel",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Calculadora salarial Mincer")
esc_sim = st.sidebar.slider("Años de escolaridad", 0, 22, 12, key="esc_sim")
exp_sim = st.sidebar.slider("Años de experiencia laboral", 0, 45, 10, key="exp_sim")
sexo_sim = st.sidebar.radio("Sexo", ["Hombre", "Mujer"], horizontal=True, key="sexo_sim")
sector_sim = st.sidebar.radio("Sector", ["Formal (con IESS)", "Informal"], horizontal=True, key="sector_sim")
area_sim = st.sidebar.radio("Área", ["Urbana", "Rural"], horizontal=True, key="area_sim")

# --- Encabezado y KPIs ---
st.title("🇪🇨 Mercado Laboral del Ecuador con Encuesta Ponderada (INEC ENEMDU 2025)")
st.caption(
    "334.786 personas encuestadas · 18,86 millones expandidos · Inferencia con diseño muestral complejo "
    "(`estrato`, `upm`, `fexp`), ecuación salarial de Mincer y descomposición de Kitagawa-Oaxaca-Blinder."
)

if provincia_sel == "Nacional (Total)":
    rec_nac = {r["indicador"]: r for r in resultados["reconciliacion_nacional_2025"]}
    t_adec = rec_nac["Empleo Adecuado/Pleno"]["estimacion_pct"]
    ee_adec = rec_nac["Empleo Adecuado/Pleno"]["ee_complejo_pct"]
    t_sub = rec_nac["Subempleo"]["estimacion_pct"]
    t_inf = rec_nac["Sector informal"]["estimacion_pct"]
    ee_inf = rec_nac["Sector informal"]["ee_complejo_pct"]
    t_des = rec_nac["Desempleo"]["estimacion_pct"]
    ing_med = resultados["desigualdad_y_pobreza"]["ingreso_laboral_ocupados"]["p50_usd"]
else:
    fila_p = df_prov.loc[df_prov["provincia"] == provincia_sel].iloc[0]
    t_adec = float(fila_p["empleo_adecuado_pct"])
    ee_adec = float(fila_p["empleo_adecuado_ee_pct"])
    t_sub = float(fila_p["subempleo_pct"])
    t_inf = float(fila_p["informalidad_pct"])
    ee_inf = float(fila_p["informalidad_ee_pct"])
    t_des = float(fila_p["desempleo_pct"])
    ing_med = float(fila_p["ingreso_laboral_mediano_usd"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(f"{provincia_sel}: Empleo adecuado", f"{t_adec:.1f} %", f"±{1.96 * ee_adec:.1f} pp (IC 95%)", delta_color="off")
c2.metric("Sector informal (ocupados)", f"{t_inf:.1f} %", f"±{1.96 * ee_inf:.1f} pp (IC 95%)", delta_color="off")
c3.metric("Subempleo (PEA)", f"{t_sub:.1f} %")
c4.metric("Desempleo (PEA)", f"{t_des:.1f} %")
c5.metric("Ingreso laboral mediano", f"{ing_med:.0f} USD/mes", f"SBU = {SBU_USD_2025:.0f} USD", delta_color="off")

# --- Fila 1: Serie histórica y comparativa provincial ---
col_izq, col_der = st.columns(2)

with col_izq:
    st.subheader("Evolución histórica 2018–2025 (% de la PEA / ocupados)")
    dom_hist = "Total" if provincia_sel == "Nacional (Total)" else provincia_sel
    sub_hist = df_serie.loc[
        (df_serie["dominio"] == dom_hist)
        & df_serie["indicador"].isin(
            ["Empleo Adecuado/Pleno", "Sector informal", "Subempleo", "Otro Empleo no pleno", "Desempleo"]
        )
    ].copy()
    graf_hist = (
        alt.Chart(sub_hist)
        .mark_line(point=True, strokeWidth=2.4)
        .encode(
            x=alt.X("anio:Q", title="Año", axis=alt.Axis(format="d")),
            y=alt.Y("valor_pct:Q", title="Porcentaje (%)"),
            color=alt.Color("indicador:N", legend=alt.Legend(orient="top", title=None)),
            tooltip=[
                alt.Tooltip("anio:Q", title="Año"),
                alt.Tooltip("indicador:N", title="Indicador"),
                alt.Tooltip("valor_pct:Q", title="Tasa (%)", format=".1f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(graf_hist, width="stretch")

with col_der:
    st.subheader(f"Brechas por {dimension_sel.lower()} (2025)")
    sub_dim = df_sub.loc[df_sub["dimension"] == dimension_sel].copy()
    largo_dim = sub_dim.melt(
        id_vars=["categoria", "ingreso_mediano_usd"],
        value_vars=["empleo_adecuado_pct", "informalidad_pct", "subempleo_pct"],
        var_name="metrica",
        value_name="porcentaje",
    )
    mapa_metricas = {
        "empleo_adecuado_pct": "Empleo adecuado (%)",
        "informalidad_pct": "Sector informal (%)",
        "subempleo_pct": "Subempleo (%)",
    }
    largo_dim["metrica"] = largo_dim["metrica"].map(mapa_metricas)
    graf_dim = (
        alt.Chart(largo_dim)
        .mark_bar()
        .encode(
            x=alt.X("porcentaje:Q", title="Porcentaje (%)"),
            y=alt.Y("categoria:N", sort="-x", title=None),
            color=alt.Color("metrica:N", legend=alt.Legend(orient="top", title=None)),
            xOffset="metrica:N",
            tooltip=[
                alt.Tooltip("categoria:N", title="Grupo"),
                alt.Tooltip("metrica:N", title="Métrica"),
                alt.Tooltip("porcentaje:Q", title="Valor (%)", format=".1f"),
                alt.Tooltip("ingreso_mediano_usd:Q", title="Ingreso mediano (USD)", format=".0f"),
            ],
        )
        .properties(height=340)
    )
    st.altair_chart(graf_dim, width="stretch")

# --- Fila 2: Calculadora Mincer y Brecha Cuantílica ---
col_m1, col_m2 = st.columns(2)

with col_m1:
    st.subheader("Simulación salarial (Ecuación de Mincer WLS + Formalidad)")
    coefs_m2 = resultados["mincer"]["modelos"]["m2_formalidad"]["coeficientes"]
    # Predicción del salario por hora sobre la media muestral ajustada
    log_base = 0.52  # intercepto efectivo aproximado en log(USD/hora)
    log_pred = (
        log_base
        + coefs_m2["escolaridad"]["beta"] * esc_sim
        + coefs_m2["experiencia"]["beta"] * exp_sim
        + coefs_m2["experiencia_cuad"]["beta"] * ((exp_sim ** 2) / 100.0)
        + (coefs_m2["mujer"]["beta"] if sexo_sim == "Mujer" else 0.0)
        + (coefs_m2["rural"]["beta"] if area_sim == "Rural" else 0.0)
        + (coefs_m2["informal"]["beta"] if sector_sim == "Informal" else coefs_m2["afiliado_seguro"]["beta"])
    )
    sal_hora_est = float(np.exp(log_pred))
    sal_mes_est = sal_hora_est * 40.0 * 4.3333

    m_a, m_b = st.columns(2)
    m_a.metric("Salario estimado por hora", f"{sal_hora_est:.2f} USD/h")
    m_b.metric("Ingreso mensual estimado (40 h/sem)", f"{sal_mes_est:.0f} USD/mes")

    df_dip = pd.DataFrame(resultados["mincer"]["efecto_diploma"]).iloc[1:]
    graf_dip = (
        alt.Chart(df_dip)
        .mark_bar(color=PALETA["primario"])
        .encode(
            x=alt.X("premio_salarial_pct:Q", title="Premio salarial por hora vs. sin instrucción (%)"),
            y=alt.Y("nivel:N", sort=None, title=None),
            tooltip=[
                alt.Tooltip("nivel:N", title="Nivel"),
                alt.Tooltip("premio_salarial_pct:Q", title="Premio (%)", format=".1f"),
            ],
        )
        .properties(height=230)
    )
    st.altair_chart(graf_dip, width="stretch")

with col_m2:
    st.subheader("Brecha salarial de género por cuantiles (P10 a P90)")
    graf_cuant = (
        alt.Chart(df_cuant)
        .mark_line(point=True, strokeWidth=2.3)
        .encode(
            x=alt.X("percentil:Q", title="Percentil de la distribución salarial"),
            y=alt.Y("brecha_hora_pct:Q", title="Brecha salarial por hora Hombre − Mujer (%)"),
            color=alt.Color("sector:N", legend=alt.Legend(orient="top", title=None)),
            tooltip=[
                alt.Tooltip("sector:N", title="Sector"),
                alt.Tooltip("percentil:Q", title="Percentil"),
                alt.Tooltip("brecha_hora_pct:Q", title="Brecha hora (%)", format=".1f"),
                alt.Tooltip("brecha_mensual_pct:Q", title="Brecha mensual (%)", format=".1f"),
            ],
        )
        .properties(height=310)
    )
    st.altair_chart(graf_cuant, width="stretch")

with st.expander("Tabla provincial completa (24 provincias · diseño muestral complejo)"):
    st.dataframe(df_prov, hide_index=True, width="stretch")
