"""App: curva de supervivencia (Kaplan-Meier) de las solicitudes del 311 por tipo de queja y borough.

Lee solo archivos versionados de reports/tablas/ (curvas precalculadas sobre los 7,5 M de solicitudes),
así que funciona sin descargar los datos.

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from nyc311.etiquetas import BOROUGHS_ES, tipo_es  # noqa: E402

DIR_TABLAS = RAIZ / "reports" / "tablas"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
LUGARES = ["Toda la ciudad", "BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
ETIQ_LUGAR = {"Toda la ciudad": "Toda la ciudad", **BOROUGHS_ES}


@st.cache_data
def cargar() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    curvas = pd.read_parquet(DIR_TABLAS / "curvas_km.parquet")
    curvas = curvas.loc[curvas["dimension"].eq("tipo_borough")]
    resumen = pd.read_csv(DIR_TABLAS / "resumen_app.csv")
    res = json.loads((RAIZ / "reports" / "resultados.json").read_text(encoding="utf-8"))
    return curvas, resumen, res


def formato_duracion(dias: float) -> str:
    if not pd.notna(dias) or dias == float("inf"):
        return "no alcanzada"
    if dias < 1 / 24:
        return f"{dias * 1440:.0f} min"
    if dias < 1:
        return f"{dias * 24:.1f} h".replace(".", ",")
    return f"{dias:.1f} días".replace(".", ",")


def main() -> None:
    st.set_page_config(page_title="311 NYC · tiempos de resolución", layout="wide")
    curvas, resumen, res = cargar()
    st.title("¿Cuánto tarda Nueva York en resolver una solicitud del 311?")
    st.caption(
        f"Kaplan-Meier sobre {res['global']['n']:,} solicitudes creadas entre oct-2024 y sep-2026 "
        f"(corte {res['fuente']['fecha_corte'][:10]}). Las abiertas al corte se tratan como **censuradas**. "
        "Fuente: NYC Open Data, 311 Service Requests.".replace(",", ".")
    )

    tipos = ["Todos los tipos"] + (
        resumen.loc[resumen["tipo_queja"].ne("Todos los tipos") & resumen["borough"].eq("Toda la ciudad")]
        .sort_values("n", ascending=False)["tipo_queja"].tolist()
    )
    col1, col2 = st.columns([1, 2])
    tipo = col1.selectbox("Tipo de queja", tipos, format_func=lambda t: t if t == "Todos los tipos" else f"{tipo_es(t)} ({t})")
    lugares = col2.multiselect("Borough (puedes comparar varios)", LUGARES, default=["Toda la ciudad", "BRONX"],
                               format_func=ETIQ_LUGAR.get)
    if not lugares:
        st.info("Elige al menos un borough.")
        return

    sel = curvas.loc[curvas["grupo"].eq(tipo) & curvas["borough"].isin(lugares)].copy()
    sel = sel.loc[sel["tiempo"] > 0]
    sel["lugar"] = sel["borough"].map(ETIQ_LUGAR)
    for c in ["supervivencia", "ic_inferior", "ic_superior"]:
        sel[c] = 100 * sel[c]
    sel["horas"] = sel["tiempo"] * 24
    dominio = [ETIQ_LUGAR[l] for l in LUGARES if l in lugares]
    color = alt.Color("lugar:N", title="Borough", scale=alt.Scale(domain=dominio, range=SERIES[: len(dominio)]))
    x = alt.X("horas:Q", scale=alt.Scale(type="log", domain=[1 / 60, 24 * 400]), title="horas desde que se creó (escala log)")
    banda = alt.Chart(sel).mark_area(opacity=0.18, interpolate="step-after").encode(
        x=x, y="ic_inferior:Q", y2="ic_superior:Q", color=color
    )
    linea = alt.Chart(sel).mark_line(strokeWidth=2, interpolate="step-after").encode(
        x=x,
        y=alt.Y("supervivencia:Q", title="% de solicitudes aún abiertas", scale=alt.Scale(domain=[0, 100])),
        color=color,
        tooltip=[alt.Tooltip("lugar:N", title="Borough"), alt.Tooltip("horas:Q", format=",.1f", title="Horas"),
                 alt.Tooltip("supervivencia:Q", format=".1f", title="% abiertas")],
    )
    regla = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(strokeDash=[3, 3], color="#8f8d87").encode(y="y:Q")
    st.altair_chart((banda + linea + regla).properties(height=420), use_container_width=True)

    tabla = resumen.loc[resumen["tipo_queja"].eq(tipo) & resumen["borough"].isin(lugares)].copy()
    tabla["Borough"] = tabla["borough"].map(ETIQ_LUGAR)
    tabla["Mediana (IC 95 %)"] = [
        f"{formato_duracion(m)} ({formato_duracion(lo)} – {formato_duracion(hi)})"
        for m, lo, hi in zip(tabla["mediana_km_dias"], tabla["mediana_ic_inf"], tabla["mediana_ic_sup"])
    ]
    tabla["Promedio ingenuo de cerradas"] = tabla["promedio_ingenuo_cerradas_dias"].map(formato_duracion)
    vista = tabla[["Borough", "n", "Mediana (IC 95 %)", "pct_cerradas_1d", "pct_cerradas_7d", "pct_cerradas_30d",
                   "pct_censuradas", "Promedio ingenuo de cerradas"]].rename(
        columns={"n": "Solicitudes", "pct_cerradas_1d": "% cerradas en 1 día", "pct_cerradas_7d": "% en 7 días",
                 "pct_cerradas_30d": "% en 30 días", "pct_censuradas": "% abiertas al corte"})
    st.dataframe(vista.round(1), hide_index=True, use_container_width=True)
    st.caption(
        "Las diferencias entre boroughs **no** controlan por descriptor, canal ni horario y no son causales: "
        "ver el modelo de Cox estratificado y el análisis O/E del README."
    )


main()
