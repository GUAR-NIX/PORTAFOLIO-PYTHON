"""
App Streamlit: mapa de sismos con filtros (región, años, magnitud) y Gutenberg-Richter de lo filtrado.

    streamlit run app/streamlit_app.py

Usa los catálogos procesados de data/procesados/ (versionados): no consulta la API.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sismos import config  # noqa: E402
from sismos import gutenberg_richter as gr  # noqa: E402

st.set_page_config(page_title="Sismos del Ecuador y el Cinturón de Fuego", page_icon="🌋", layout="wide")

ECUADOR_LOCAL = "Ecuador ampliado (M≥2,5 desde 1970)"
CINTURON = "Cinturón de Fuego completo (M≥5 desde 1973)"


@st.cache_data
def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    columnas = ["id", "tiempo", "anio", "latitud", "longitud", "profundidad_km", "mw", "tipo_mag", "lugar"]
    ecuador = pd.read_parquet(config.CATALOGO_ECUADOR, columns=columnas)
    mundo = pd.read_parquet(config.CATALOGO_CINTURON, columns=columnas + ["zona"])
    return ecuador, mundo[mundo["zona"].notna()]


def color_profundidad(prof: pd.Series) -> list[list[int]]:
    """Rampa naranja → morado oscuro (0 → 300 km), igual que las figuras del informe."""
    paradas = np.array([[242, 166, 94], [194, 65, 12], [122, 31, 107], [31, 17, 71]], dtype=float)
    x = (prof.fillna(0).clip(0, 300) / 300 * (len(paradas) - 1)).to_numpy()
    i = np.minimum(x.astype(int), len(paradas) - 2)
    f = (x - i)[:, None]
    rgb = paradas[i] * (1 - f) + paradas[i + 1] * f
    return [[int(r), int(g), int(b), 190] for r, g, b in rgb]


def coma(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


ecuador, mundo = cargar()

st.title("🌋 Sismos del Ecuador y del Cinturón de Fuego")
st.caption("Catálogo del USGS (dominio público). Magnitudes homogeneizadas a Mw. "
           "**La estadística sísmica estima frecuencias medias; no predice terremotos.**")

with st.sidebar:
    st.header("Filtros")
    opciones = [ECUADOR_LOCAL, CINTURON] + sorted(mundo["zona"].unique())
    pedida = st.query_params.get("region")          # enlace directo: ?region=Japón
    region = st.selectbox("Región", opciones, key="region",
                          index=opciones.index(pedida) if pedida in opciones else 0)
    base = ecuador if region == ECUADOR_LOCAL else (mundo if region == CINTURON else mundo[mundo["zona"] == region])
    a0, a1 = int(base["anio"].min()), int(base["anio"].max())
    anios = st.slider("Años", a0, a1, (a0, a1), key="anios")
    m_min_datos = float(base["mw"].min())
    magnitudes = st.slider("Magnitud (Mw)", float(np.floor(m_min_datos * 2) / 2), 9.0,
                           (float(np.floor(m_min_datos * 2) / 2), 9.0), step=0.1, key="magnitud")

datos = base[base["anio"].between(*anios) & base["mw"].between(*magnitudes)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sismos", f"{len(datos):,}".replace(",", "."))
c2.metric("Magnitud máxima", f"{datos['mw'].max():.1f}".replace(".", ",") if len(datos) else "—")
c3.metric("M≥7", int((datos["mw"] >= 7).sum()))
mc = gr.mc_maxc(datos["mw"]) if len(datos) >= 50 else None
if mc is not None and (datos["mw"] >= mc).sum() >= 50:
    aj = gr.valor_b_aki(datos["mw"], mc)
    c4.metric(f"Valor b (Mc={mc:.1f})".replace(".", ","), f"{aj.b:.2f}".replace(".", ","),
              help="Máxima verosimilitud de Aki; Mc por máxima curvatura + 0,2")
    st.caption(f"Valor b con IC 95 % (Shi-Bolt): {coma(aj.b)} [{coma(aj.ic95_bajo)}–{coma(aj.ic95_alto)}] con "
               f"{aj.n} sismos sobre Mc. Mc por máxima curvatura puede quedarse corto: ver el informe.")
else:
    c4.metric("Valor b", "—", help="Hacen falta al menos 50 sismos sobre Mc")

st.subheader("Mapa de epicentros (color = profundidad, tamaño = magnitud)")
mapa = datos.assign(color=color_profundidad(datos["profundidad_km"]),
                    radio=(4 ** (datos["mw"] - 2.5)).clip(1, 4 ** 6) * 40,
                    fecha=datos["tiempo"].astype(str).str[:16])
if region == CINTURON:
    # El Pacífico cruza ±180°: las longitudes este pasan a negativas (140°E → −220°) para que el
    # cinturón quede continuo en una sola copia del mapa
    mapa["longitud"] = np.where(mapa["longitud"] > 0, mapa["longitud"] - 360, mapa["longitud"])
    vista = pdk.ViewState(latitude=10, longitude=-160, zoom=1)
else:
    vista = pdk.ViewState(latitude=float(datos["latitud"].mean() if len(datos) else 0),
                          longitude=float(datos["longitud"].mean() if len(datos) else -78), zoom=4.5)
capa = pdk.Layer("ScatterplotLayer", data=mapa[["longitud", "latitud", "color", "radio", "mw", "profundidad_km",
                                                "fecha", "lugar"]],
                 get_position="[longitud, latitud]", get_fill_color="color", get_radius="radio",
                 radius_min_pixels=1.5, radius_max_pixels=30, pickable=True, opacity=0.8)
st.pydeck_chart(pdk.Deck(layers=[capa], initial_view_state=vista, map_style=pdk.map_styles.CARTO_LIGHT,
                         tooltip={"text": "M{mw} · {profundidad_km} km\n{fecha}\n{lugar}"}), key="mapa")

izq, der = st.columns(2)
with izq:
    st.subheader("Sismos por año")
    por_anio = datos.groupby("anio").size().rename("sismos").reset_index()
    st.altair_chart(alt.Chart(por_anio).mark_bar(color="#2a78d6").encode(
        x=alt.X("anio:O", title="año"), y=alt.Y("sismos:Q", title="sismos"),
        tooltip=["anio", "sismos"]), width="stretch")
with der:
    st.subheader("Gutenberg-Richter de la selección")
    if len(datos) >= 10:
        clases, acum = gr.distribucion_acumulada(datos["mw"])
        fmd = pd.DataFrame({"Mw": clases, "N(≥M)": acum})
        st.altair_chart(alt.Chart(fmd).mark_circle(size=45, color="#52514e").encode(
            x=alt.X("Mw:Q", scale=alt.Scale(zero=False)),
            y=alt.Y("N(≥M):Q", scale=alt.Scale(type="log")), tooltip=["Mw", "N(≥M)"]), width="stretch")
        st.caption("Recta en escala log = ley de Gutenberg-Richter. La curva se aplana a la izquierda de Mc "
                   "(sismos pequeños que el catálogo no registra).")
    else:
        st.info("Muy pocos sismos para la distribución.")

st.subheader("Sismos más fuertes de la selección")
st.dataframe(datos.nlargest(10, "mw")[["tiempo", "mw", "tipo_mag", "profundidad_km", "lugar"]]
             .rename(columns={"tiempo": "fecha (UTC)", "mw": "Mw", "tipo_mag": "escala original",
                              "profundidad_km": "profundidad (km)", "lugar": "lugar (USGS)"}),
             hide_index=True, width="stretch")
