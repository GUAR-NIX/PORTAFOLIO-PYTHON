"""Aplicación interactiva Streamlit para el análisis espacial y temporal de delitos en Chicago.

Permite explorar patrones temporales, mapas de calor y coropletas por área comunitaria,
efectividad de arrestos por distrito e inferencia de pronósticos de demanda delictiva.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import folium
from folium.plugins import HeatMap
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "data"
PROCESADOS = DATOS / "procesados" / "delitos_parquet"
MUESTRA = DATOS / "muestra" / "muestra_delitos.parquet"
RAW = DATOS / "raw"
REPORTES = RAIZ / "reports"
FIGURAS = REPORTES / "figures"
COLUMNAS = "id_delito, fecha, arresto, domestico, distrito, area_comunitaria, CAST(anio AS INTEGER) AS anio, latitud, longitud"

st.set_page_config(
    page_title="Chicago Crime Analytics | Portafolio de Datos",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def expresion_tipo_armonizado() -> str:
    """CASE de SQL con los renombres detectados por el pipeline (reports/armonizacion_categorias.csv)."""
    ruta = REPORTES / "armonizacion_categorias.csv"
    if not ruta.exists():
        return "tipo_primario"
    tabla = pd.read_csv(ruta)
    tabla = tabla[tabla["tipo_original"] != tabla["tipo_armonizado"]]
    if tabla.empty:
        return "tipo_primario"
    casos = " ".join(
        "WHEN '{}' THEN '{}'".format(o.replace("'", "''"), d.replace("'", "''"))
        for o, d in zip(tabla["tipo_original"], tabla["tipo_armonizado"])
    )
    return f"CASE tipo_primario {casos} ELSE tipo_primario END"


@st.cache_data(show_spinner=False)
def cargar_datos_base() -> pd.DataFrame:
    """Carga solo las columnas necesarias del Parquet (o de la muestra versionada) con tipos armonizados.

    DELITOS_FUENTE=muestra fuerza la muestra (útil para pruebas y equipos con poca memoria).
    """
    usar_muestra = os.environ.get("DELITOS_FUENTE") == "muestra"
    if not usar_muestra and PROCESADOS.exists() and any(PROCESADOS.glob("**/*.parquet")):
        origen = f"read_parquet('{(PROCESADOS / '**' / '*.parquet').as_posix()}', hive_partitioning=true)"
    elif MUESTRA.exists():
        origen = f"read_parquet('{MUESTRA.as_posix()}')"
    else:
        st.error("No se encontraron datos en Parquet ni muestra.")
        return pd.DataFrame()
    consulta = f"SELECT {COLUMNAS}, {expresion_tipo_armonizado()} AS tipo_primario FROM {origen}"
    df = duckdb.connect().execute(consulta).df()
    df["tipo_primario"] = df["tipo_primario"].astype("category")
    return df


@st.cache_data(show_spinner=False)
def cargar_geo() -> gpd.GeoDataFrame | None:
    """Carga el GeoJSON oficial de áreas comunitarias."""
    ruta = RAW / "community_areas.geojson"
    if not ruta.exists():
        return None
    try:
        gdf = gpd.read_file(ruta)
        gdf["area_comunitaria"] = pd.to_numeric(gdf["area_numbe"], errors="coerce").astype("Int64")
        gdf["nombre_area"] = gdf["community"].str.title()
        return gdf
    except Exception:
        return None


def main() -> None:
    st.title("Delitos en Chicago: análisis espacial y temporal")
    st.markdown(
        "Explorador de los registros del Chicago Data Portal (categorías armonizadas). "
        "El año en curso es parcial: compáralo con cuidado."
    )

    df_todo = cargar_datos_base()
    if df_todo.empty:
        st.warning("Ejecuta primero el pipeline de ingesta para visualizar los datos.")
        return

    cargar_geo()

    # ── Barra lateral con filtros ──────────────────────────────────────────────
    st.sidebar.header("Filtros")

    anios_disp = sorted(df_todo["anio"].dropna().unique().astype(int))
    min_anio, max_anio = int(min(anios_disp)), int(max(anios_disp))

    rango_anios = st.sidebar.slider(
        "Rango de años",
        min_value=min_anio,
        max_value=max_anio,
        value=(max(min_anio, max_anio - 5), max_anio),
    )

    tipos_disp = sorted(df_todo["tipo_primario"].dropna().unique().tolist())
    tipos_seleccionados = st.sidebar.multiselect(
        "Tipo de delito",
        options=tipos_disp,
        default=tipos_disp[:5] if len(tipos_disp) > 5 else tipos_disp,
    )

    filtro_domestico = st.sidebar.radio(
        "Violencia doméstica",
        options=["Todos", "Solo violencia doméstica", "Sin violencia doméstica"],
    )

    # Aplicar filtros
    df_filtrado = df_todo[
        (df_todo["anio"] >= rango_anios[0]) & (df_todo["anio"] <= rango_anios[1])
    ]
    if tipos_seleccionados:
        df_filtrado = df_filtrado[df_filtrado["tipo_primario"].isin(tipos_seleccionados)]
    if filtro_domestico == "Solo violencia doméstica":
        df_filtrado = df_filtrado[df_filtrado["domestico"] == True]
    elif filtro_domestico == "Sin violencia doméstica":
        df_filtrado = df_filtrado[df_filtrado["domestico"] == False]

    # ── KPIs Superiores ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    total_casos = len(df_filtrado)
    tasa_arresto = (df_filtrado["arresto"].sum() / total_casos * 100) if total_casos else 0.0
    pct_dom = (df_filtrado["domestico"].sum() / total_casos * 100) if total_casos else 0.0

    c1.metric("Total Delitos Filtrados", f"{total_casos:,}")
    c2.metric("Tasa de Arresto Efectiva", f"{tasa_arresto:.1f}%")
    c3.metric("Violencia Doméstica", f"{pct_dom:.1f}%")
    area_top = df_filtrado["area_comunitaria"].value_counts().index[0] if total_casos else "N/A"
    c4.metric("Área Comunitaria Top", f"Área #{int(area_top)}" if area_top != "N/A" else "N/A")

    st.markdown("---")

    # ── Pestañas de análisis ───────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "Tendencias y estacionalidad",
        "Análisis espacial",
        "Arrestos y distritos",
        "Pronóstico (backtesting)",
    ])

    with tab1:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.subheader("Evolución Anual del Volumen Delictivo")
            serie_anual = df_filtrado.groupby(["anio", "tipo_primario"], observed=True).size().reset_index(name="delitos")
            fig_anual = px.bar(
                serie_anual,
                x="anio",
                y="delitos",
                color="tipo_primario",
                title="Delitos por Año y Tipo",
                barmode="stack",
            )
            fig_anual.update_layout(xaxis_title="Año", yaxis_title="Total Delitos", height=420)
            st.plotly_chart(fig_anual, use_container_width=True)

        with col_t2:
            st.subheader("Mapa de Calor: Hora del Día × Día de Semana")
            df_calor = df_filtrado.copy()
            df_calor["hora"] = pd.to_datetime(df_calor["fecha"]).dt.hour
            df_calor["dia_semana"] = pd.to_datetime(df_calor["fecha"]).dt.dayofweek
            matriz = df_calor.groupby(["dia_semana", "hora"]).size().unstack(fill_value=0).reindex(index=range(7), fill_value=0)
            matriz.index = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            fig_calor = px.imshow(
                matriz,
                labels=dict(x="Hora del Día", y="Día", color="Delitos"),
                color_continuous_scale="YlOrRd",
                title="Concentración de Incidentes",
            )
            fig_calor.update_layout(height=420)
            st.plotly_chart(fig_calor, use_container_width=True)

    with tab2:
        st.subheader("Distribución Geográfica y Hotspots")
        c_map1, c_map2 = st.columns([2, 1])

        with c_map1:
            mapa_html_ruta = REPORTES / "mapa_chicago_coropleta.html"
            if mapa_html_ruta.exists():
                st.components.v1.html(mapa_html_ruta.read_text(encoding="utf-8"), height=520)
            else:
                st.info("Generando mapa de calor de puntos representativos...")
                puntos = (
                    df_filtrado[df_filtrado["latitud"].notna() & df_filtrado["longitud"].notna()]
                    .sample(min(3000, len(df_filtrado)), random_state=42)[["latitud", "longitud"]]
                    .values.tolist()
                )
                m = folium.Map(location=[41.8781, -87.6298], zoom_start=11, tiles=None)
                # Fondo de Esri: sin clave y sin bloqueos por Referer (OpenStreetMap y CARTO los bloquean)
                folium.TileLayer(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                    attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
                    max_native_zoom=16, max_zoom=19,
                ).add_to(m)
                HeatMap(puntos, radius=10, blur=12).add_to(m)
                st.components.v1.html(m._repr_html_(), height=520)

        with c_map2:
            st.write("##### Top Áreas Comunitarias")
            top_areas = df_filtrado["area_comunitaria"].value_counts().head(10).reset_index()
            top_areas.columns = ["Área", "Delitos"]
            st.dataframe(top_areas, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Efectividad Policial y Tasas de Arresto")
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            tasas_tipo = (
                df_filtrado.groupby("tipo_primario", observed=True)
                .agg(delitos=("id_delito", "count"), arrestos=("arresto", "sum"))
                .reset_index()
            )
            tasas_tipo["tasa_arresto_pct"] = (tasas_tipo["arrestos"] / tasas_tipo["delitos"] * 100).round(1)
            tasas_tipo = tasas_tipo.sort_values("tasa_arresto_pct", ascending=True)

            fig_p1 = px.bar(
                tasas_tipo,
                x="tasa_arresto_pct",
                y="tipo_primario",
                orientation="h",
                title="Tasa de Arresto por Tipo de Delito (%)",
                color="tasa_arresto_pct",
                color_continuous_scale="Viridis",
            )
            fig_p1.update_layout(xaxis_title="Tasa de Arresto (%)", height=450)
            st.plotly_chart(fig_p1, use_container_width=True)

        with col_p2:
            st.write("##### Distribución por Distrito Policial")
            dist_stats = (
                df_filtrado[df_filtrado["distrito"].notna()]
                .groupby("distrito")
                .agg(
                    total=("id_delito", "count"),
                    arresto_pct=("arresto", lambda x: round(x.sum() / len(x) * 100, 1)),
                    domestico_pct=("domestico", lambda x: round(x.sum() / len(x) * 100, 1)),
                )
                .reset_index()
                .sort_values("total", ascending=False)
            )
            st.dataframe(dist_stats, use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("Modelado Predictivo de Demanda Mensual")
        reporte_pron = REPORTES / "evaluacion_pronostico.json"
        if reporte_pron.exists():
            metricas_dict = json.loads(reporte_pron.read_text(encoding="utf-8"))
            st.write(f"##### Backtesting de origen móvil · mejor modelo: {metricas_dict['ganador']}")
            st.table(pd.DataFrame.from_dict(metricas_dict["metricas"], orient="index"))

            fig_pred = FIGURAS / "10_pronostico_vs_real.png"
            if fig_pred.exists():
                st.image(str(fig_pred), caption="Pronóstico del mejor modelo frente a lo real, con intervalo del 90 %")
        else:
            st.info("Ejecuta el pipeline completo para generar los resultados del modelo de pronóstico.")


if __name__ == "__main__":
    main()
