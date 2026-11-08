"""Análisis espacial de delitos en Chicago.

- Tasas **anuales** por 100 mil habitantes por área comunitaria (población del censo 2020, CMAP).
- Persistencia del ranking de tasas año a año.
- Hotspots estadísticos con **Getis-Ord Gi*** (esda/libpysal) sobre una grilla de 1 km,
  con corrección de comparaciones múltiples (FDR) y estabilidad año a año (índice de Jaccard).
- Mapas estáticos y mapas interactivos livianos en Folium.
"""
from __future__ import annotations

from pathlib import Path

import esda
import folium
from folium.plugins import HeatMap
import geopandas as gpd
import libpysal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
import pandas as pd
from scipy import stats
from shapely.geometry import box
from statsmodels.stats.multitest import multipletests

from delitos_chicago.config import FIGURAS, RAW, REFERENCIA, REPORTES

# Mapa base de Esri (gris claro): no pide clave y funciona aunque el HTML se abra como archivo local
# (OpenStreetMap y CARTO bloquean las teselas cuando la página no envía un Referer).
TESELAS_ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
ATRIBUCION_ESRI = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors y la comunidad de usuarios GIS"


def mapa_base(ubicacion: list[float], zoom: int) -> folium.Map:
    """Mapa Folium con fondo gris claro de Esri (zoom nativo hasta 16)."""
    mapa = folium.Map(location=ubicacion, zoom_start=zoom, tiles=None)
    folium.TileLayer(TESELAS_ESRI, attr=ATRIBUCION_ESRI, name="Esri gris claro",
                     max_native_zoom=16, max_zoom=19).add_to(mapa)
    return mapa

# Las coordenadas X/Y del portal están en NAD83 / Illinois East (pies topográficos de EE. UU., EPSG:3435)
CRS_PIES = "EPSG:3435"
METROS_POR_PIE = 1200 / 3937


def cargar_poblacion(ruta: Path = REFERENCIA / "poblacion_areas_cmap_2020.csv") -> pd.Series:
    """Población del censo 2020 por área comunitaria (CMAP), indexada por número de área."""
    tabla = pd.read_csv(ruta)
    return tabla.set_index("area_comunitaria")["poblacion_2020"]


def cargar_geojson_areas(ruta_geojson: Path = RAW / "community_areas.geojson") -> gpd.GeoDataFrame:
    """Carga los polígonos de las 77 áreas comunitarias con número y nombre."""
    if not ruta_geojson.exists():
        raise FileNotFoundError(f"GeoJSON no encontrado: {ruta_geojson}")
    gdf = gpd.read_file(ruta_geojson)
    gdf["area_comunitaria"] = pd.to_numeric(gdf["area_numbe"], errors="coerce").astype(int)
    gdf["nombre_area"] = gdf["community"].str.title()
    return gdf[["area_comunitaria", "nombre_area", "geometry"]]


# ── Tasas anuales y rankings por área comunitaria ─────────────────────────

def tasas_anuales_area(df: pd.DataFrame, poblacion: pd.Series, anios: list[int] | None = None) -> pd.DataFrame:
    """Delitos y tasa anual por 100 mil habitantes por área y año.

    La población es la del censo 2020 para todos los años: la tasa es comparable entre áreas,
    pero en años lejanos a 2020 es solo aproximada.
    """
    sub = df[df["area_comunitaria"].isin(poblacion.index)]
    if anios is not None:
        sub = sub[sub["anio"].isin(anios)]
    tabla = (
        sub.groupby(["anio", "area_comunitaria"]).agg(delitos=("arresto", "size"), arrestos=("arresto", "sum")).reset_index()
    )
    tabla["anio"] = tabla["anio"].astype(int)
    tabla["area_comunitaria"] = tabla["area_comunitaria"].astype(int)
    tabla["poblacion_2020"] = tabla["area_comunitaria"].map(poblacion)
    tabla["tasa_100k"] = (tabla["delitos"] / tabla["poblacion_2020"] * 100_000).round(1)
    tabla["rank_tasa"] = tabla.groupby("anio")["tasa_100k"].rank(ascending=False, method="min").astype(int)
    tabla["rank_volumen"] = tabla.groupby("anio")["delitos"].rank(ascending=False, method="min").astype(int)
    return tabla.sort_values(["anio", "rank_tasa"]).reset_index(drop=True)


def resumen_areas(tasas: pd.DataFrame, nombres: pd.Series) -> pd.DataFrame:
    """Promedios anuales por área en la ventana de `tasas`, con estabilidad del ranking de tasa."""
    res = tasas.groupby("area_comunitaria").agg(
        poblacion_2020=("poblacion_2020", "first"),
        delitos_promedio_anual=("delitos", "mean"),
        tasa_anual_100k=("tasa_100k", "mean"),
        arrestos=("arrestos", "sum"),
        delitos=("delitos", "sum"),
        rank_tasa_promedio=("rank_tasa", "mean"),
        rank_tasa_desv=("rank_tasa", "std"),
        rank_tasa_mejor=("rank_tasa", "min"),
        rank_tasa_peor=("rank_tasa", "max"),
        anios=("anio", "nunique"),
    ).reset_index()
    res["nombre_area"] = res["area_comunitaria"].map(nombres)
    res["tasa_arresto_pct"] = (res["arrestos"] / res["delitos"] * 100).round(1)
    res["delitos_promedio_anual"] = res["delitos_promedio_anual"].round(0).astype(int)
    res["tasa_anual_100k"] = res["tasa_anual_100k"].round(0).astype(int)
    res["rank_tasa_promedio"] = res["rank_tasa_promedio"].round(1)
    res["rank_tasa_desv"] = res["rank_tasa_desv"].fillna(0).round(1)
    res["puesto_tasa"] = res["tasa_anual_100k"].rank(ascending=False, method="min").astype(int)
    res["puesto_volumen"] = res["delitos_promedio_anual"].rank(ascending=False, method="min").astype(int)
    columnas = ["area_comunitaria", "nombre_area", "poblacion_2020", "delitos_promedio_anual", "tasa_anual_100k",
                "puesto_tasa", "puesto_volumen", "rank_tasa_promedio", "rank_tasa_desv", "rank_tasa_mejor",
                "rank_tasa_peor", "tasa_arresto_pct", "anios"]
    return res[columnas].sort_values("puesto_tasa").reset_index(drop=True)


# ── Hotspots Getis-Ord Gi* sobre grilla ────────────────────────────────────

def conteos_grilla(df: pd.DataFrame, anios: list[int], tam_celda_m: float = 1000.0) -> pd.DataFrame:
    """Cuenta delitos por celda cuadrada (en metros) y año a partir de las coordenadas X/Y del portal.

    El área de estudio son las celdas con al menos un delito en la ventana; los años sin delitos
    en una celda del área cuentan como 0.
    """
    sub = df[df["anio"].isin(anios) & df["coord_x"].gt(0) & df["coord_y"].gt(0)]
    lado_pies = tam_celda_m / METROS_POR_PIE
    celdas = pd.DataFrame({
        "cx": np.floor(sub["coord_x"].to_numpy() / lado_pies).astype(int),
        "cy": np.floor(sub["coord_y"].to_numpy() / lado_pies).astype(int),
        "anio": sub["anio"].astype(int).to_numpy(),
    })
    return (
        celdas.groupby(["cx", "cy", "anio"]).size()
        .unstack("anio", fill_value=0)
        .reindex(columns=anios, fill_value=0)
        .stack()
        .rename("delitos")
        .reset_index()
    )


def pesos_reina(celdas: pd.DataFrame) -> libpysal.weights.W:
    """Pesos binarios de contigüidad tipo reina (8 vecinos) entre celdas de la grilla."""
    puntos = celdas[["cx", "cy"]].to_numpy(dtype=float)
    return libpysal.weights.DistanceBand(puntos, threshold=1.5, binary=True, silence_warnings=True)


def gi_estrella(valores: np.ndarray, w: libpysal.weights.W) -> np.ndarray:
    """Puntaje z de Getis-Ord Gi* (la celda cuenta como su propia vecina; pesos binarios)."""
    return esda.G_Local(np.asarray(valores, dtype=float), w, transform="B", permutations=0, star=True).Zs


def hotspots_gi(conteos: pd.DataFrame, alfa: float = 0.05) -> pd.DataFrame:
    """Gi* por año con p bilateral y corrección FDR de Benjamini-Hochberg dentro de cada año.

    hotspot = z > 0 y significativo tras FDR; coldspot = z < 0 y significativo.
    """
    celdas = conteos[["cx", "cy"]].drop_duplicates().sort_values(["cx", "cy"]).reset_index(drop=True)
    w = pesos_reina(celdas)
    islas = set(w.islands)
    if islas:
        celdas = celdas.drop(index=list(islas)).reset_index(drop=True)
        w = pesos_reina(celdas)
    resultados = []
    for anio, grupo in conteos.groupby("anio"):
        g = celdas.merge(grupo, on=["cx", "cy"], how="left").fillna({"delitos": 0})
        z = gi_estrella(g["delitos"].to_numpy(), w)
        p = 2 * stats.norm.sf(np.abs(z))
        rechaza = multipletests(p, alpha=alfa, method="fdr_bh")[0]
        g["anio"] = int(anio)
        g["z_gi"] = z.round(3)
        g["p_valor"] = p
        g["hotspot"] = rechaza & (z > 0)
        g["coldspot"] = rechaza & (z < 0)
        resultados.append(g)
    return pd.concat(resultados, ignore_index=True)


def jaccard(a: set, b: set) -> float:
    """Índice de Jaccard |A ∩ B| / |A ∪ B| (1 si ambos conjuntos están vacíos)."""
    union = a | b
    return 1.0 if not union else len(a & b) / len(union)


def estabilidad_hotspots(gi: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Solapamiento de hotspots entre años: Jaccard consecutivo, frente al primer año y persistencia."""
    anios = sorted(gi["anio"].unique())
    conjuntos = {
        a: set(map(tuple, gi.loc[(gi["anio"] == a) & gi["hotspot"], ["cx", "cy"]].to_numpy())) for a in anios
    }
    total_celdas = gi[["cx", "cy"]].drop_duplicates().shape[0]
    filas = []
    for i, a in enumerate(anios):
        sub = gi[gi["anio"] == a]
        filas.append({
            "anio": int(a),
            "celdas_hotspot": len(conjuntos[a]),
            "pct_celdas": round(len(conjuntos[a]) / total_celdas * 100, 1),
            "pct_delitos_en_hotspots": round(float(sub.loc[sub["hotspot"], "delitos"].sum() / sub["delitos"].sum() * 100), 1),
            "celdas_coldspot": int(sub["coldspot"].sum()),
            "jaccard_vs_anio_anterior": round(jaccard(conjuntos[anios[i - 1]], conjuntos[a]), 3) if i else None,
            f"jaccard_vs_{anios[0]}": round(jaccard(conjuntos[anios[0]], conjuntos[a]), 3),
        })
    tabla = pd.DataFrame(filas)
    persistentes = set.intersection(*conjuntos.values())
    alguna_vez = set.union(*conjuntos.values())
    ultimo = gi[gi["anio"] == anios[-1]].set_index(["cx", "cy"])["delitos"]
    resumen = {
        "anios": [int(a) for a in anios],
        "celdas_area_estudio": int(total_celdas),
        "celdas_hotspot_todos_los_anios": len(persistentes),
        "celdas_hotspot_alguna_vez": len(alguna_vez),
        "pct_persistentes_sobre_alguna_vez": round(len(persistentes) / len(alguna_vez) * 100, 1) if alguna_vez else 0.0,
        "pct_hotspots_primer_anio_que_siguen_ultimo": round(
            len(conjuntos[anios[0]] & conjuntos[anios[-1]]) / len(conjuntos[anios[0]]) * 100, 1
        ) if conjuntos[anios[0]] else 0.0,
        "jaccard_consecutivo_promedio": round(float(tabla["jaccard_vs_anio_anterior"].dropna().mean()), 3),
        "jaccard_primer_vs_ultimo": round(jaccard(conjuntos[anios[0]], conjuntos[anios[-1]]), 3),
        "pct_delitos_ultimo_anio_en_persistentes": round(
            float(ultimo[ultimo.index.isin(list(persistentes))].sum() / ultimo.sum() * 100), 1
        ),
        "pct_celdas_persistentes": round(len(persistentes) / total_celdas * 100, 1),
    }
    return tabla, resumen


def areas_de_hotspots_persistentes(gi: pd.DataFrame, gdf_areas: gpd.GeoDataFrame, tam_celda_m: float) -> pd.DataFrame:
    """Área comunitaria donde cae el centro de cada celda que fue hotspot todos los años."""
    anios = gi["anio"].nunique()
    pers = gi.groupby(["cx", "cy"])["hotspot"].sum()
    pers = pers[pers == anios].reset_index()[["cx", "cy"]]
    centros = grilla_a_geodf(pers, tam_celda_m)
    centros["geometry"] = centros.centroid
    unidas = gpd.sjoin(centros, gdf_areas.to_crs(CRS_PIES), how="inner", predicate="within")
    unidas["area_comunitaria"] = unidas["area_comunitaria"].astype(int)
    return (
        unidas.groupby(["area_comunitaria", "nombre_area"]).size().rename("celdas_persistentes")
        .reset_index().sort_values("celdas_persistentes", ascending=False).reset_index(drop=True)
    )


def grilla_a_geodf(tabla: pd.DataFrame, tam_celda_m: float = 1000.0) -> gpd.GeoDataFrame:
    """Polígonos de las celdas (en EPSG:3435) para graficar."""
    lado = tam_celda_m / METROS_POR_PIE
    geometria = [box(x * lado, y * lado, (x + 1) * lado, (y + 1) * lado) for x, y in zip(tabla["cx"], tabla["cy"])]
    return gpd.GeoDataFrame(tabla.copy(), geometry=geometria, crs=CRS_PIES)


# ── Figuras ────────────────────────────────────────────────────────────────

def graficar_coropleta_tasa(gdf_areas: gpd.GeoDataFrame, resumen: pd.DataFrame, titulo: str,
                            ruta_png: Path = FIGURAS / "06_mapa_coropleta_tasa.png") -> Path:
    """Coropleta de la tasa anual promedio por 100 mil habitantes."""
    gdf = gdf_areas.merge(resumen[["area_comunitaria", "tasa_anual_100k"]], on="area_comunitaria", how="left")
    fig, ax = plt.subplots(figsize=(9, 11))
    gdf.plot(column="tasa_anual_100k", cmap="YlOrRd", linewidth=0.5, edgecolor="#424242", legend=True, ax=ax,
             legend_kwds={"label": "Delitos por año por 100 mil habitantes (promedio)", "orientation": "horizontal",
                          "shrink": 0.7, "pad": 0.02})
    ax.set_title(titulo, fontsize=13)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return ruta_png


def graficar_ranking_areas(resumen: pd.DataFrame, top_n: int, titulo: str,
                           ruta_png: Path = FIGURAS / "07_ranking_hotspots_areas.png") -> Path:
    """Compara el top por tasa anual con el top por volumen: no son las mismas áreas."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
    top_t = resumen.nsmallest(top_n, "puesto_tasa")
    ax1.barh(top_t["nombre_area"][::-1], top_t["tasa_anual_100k"][::-1], color="#C62828")
    ax1.set_xlabel("Delitos por año por 100 mil habitantes")
    ax1.set_title(f"Top {top_n} por tasa anual")
    top_v = resumen.nsmallest(top_n, "puesto_volumen")
    ax2.barh(top_v["nombre_area"][::-1], top_v["delitos_promedio_anual"][::-1], color="#1565C0")
    ax2.set_xlabel("Delitos por año (promedio)")
    ax2.set_title(f"Top {top_n} por volumen")
    fig.suptitle(titulo)
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150)
    plt.close(fig)
    return ruta_png


def graficar_hotspots_por_anio(gi: pd.DataFrame, gdf_areas: gpd.GeoDataFrame, tabla_estab: pd.DataFrame,
                               tam_celda_m: float, ruta_png: Path = FIGURAS / "12_hotspots_gi_por_anio.png") -> Path:
    """Mapas pequeños con los hotspots y coldspots Gi* de cada año."""
    anios = sorted(gi["anio"].unique())
    contorno = gdf_areas.to_crs(CRS_PIES)
    columnas = 4
    filas = int(np.ceil(len(anios) / columnas))
    fig, axes = plt.subplots(filas, columnas, figsize=(4 * columnas, 5 * filas))
    cmap = ListedColormap(["#1565C0", "#EEEEEE", "#C62828"])
    for ax, anio in zip(axes.flat, anios):
        sub = gi[gi["anio"] == anio].copy()
        sub["clase"] = np.select([sub["coldspot"], sub["hotspot"]], [0, 2], default=1)
        grilla_a_geodf(sub, tam_celda_m).plot(column="clase", cmap=cmap, vmin=0, vmax=2, ax=ax, linewidth=0)
        contorno.boundary.plot(ax=ax, color="#616161", linewidth=0.3)
        fila = tabla_estab.set_index("anio").loc[anio]
        jac = "" if pd.isna(fila["jaccard_vs_anio_anterior"]) else f" · Jaccard vs año ant. {fila['jaccard_vs_anio_anterior']:.2f}"
        ax.set_title(f"{anio}: {int(fila['celdas_hotspot'])} celdas{jac}", fontsize=9)
        ax.axis("off")
    for ax in list(axes.flat)[len(anios):]:
        ax.axis("off")
    fig.suptitle(f"Getis-Ord Gi* sobre grilla de {tam_celda_m / 1000:g} km (rojo: hotspot, azul: coldspot; FDR 5 %)")
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=130)
    plt.close(fig)
    return ruta_png


def graficar_persistencia(gi: pd.DataFrame, gdf_areas: gpd.GeoDataFrame, tam_celda_m: float,
                          ruta_png: Path = FIGURAS / "13_persistencia_hotspots.png") -> Path:
    """Número de años en que cada celda fue hotspot Gi*."""
    anios = gi["anio"].nunique()
    pers = gi.groupby(["cx", "cy"])["hotspot"].sum().reset_index(name="anios_hotspot")
    contorno = gdf_areas.to_crs(CRS_PIES)
    fig, ax = plt.subplots(figsize=(8, 10))
    grilla_a_geodf(pers, tam_celda_m).plot(column="anios_hotspot", cmap="Reds", vmin=0, vmax=anios, legend=True, ax=ax,
                                           linewidth=0, legend_kwds={"label": f"Años como hotspot (de {anios})", "shrink": 0.6})
    contorno.boundary.plot(ax=ax, color="#424242", linewidth=0.3)
    ax.set_title(f"Persistencia de hotspots Gi* {gi['anio'].min()}–{gi['anio'].max()}")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150)
    plt.close(fig)
    return ruta_png


# ── Mapas interactivos ─────────────────────────────────────────────────────

def generar_mapa_coropleta_html(gdf_areas: gpd.GeoDataFrame, resumen: pd.DataFrame, titulo: str,
                                ruta_html: Path = REPORTES / "mapa_chicago_coropleta.html") -> Path:
    """Coropleta interactiva de la tasa anual. Geometrías simplificadas (~20 m) para que el HTML pese poco."""
    gdf = gdf_areas.merge(resumen, on=["area_comunitaria", "nombre_area"], how="left")
    gdf["geometry"] = gdf.to_crs(CRS_PIES).simplify(65).to_crs(gdf.crs)
    gdf = gdf[["area_comunitaria", "nombre_area", "tasa_anual_100k", "delitos_promedio_anual", "puesto_tasa", "geometry"]]
    escala = folium.LinearColormap(["#FFF7BC", "#FD8D3C", "#BD0026"], vmin=float(gdf["tasa_anual_100k"].min()),
                                   vmax=float(gdf["tasa_anual_100k"].max()), caption=titulo)
    mapa = mapa_base([41.8381, -87.6798], 10)
    folium.GeoJson(
        gdf.to_json(),
        style_function=lambda f: {"fillColor": escala(f["properties"]["tasa_anual_100k"]), "color": "#424242",
                                  "weight": 0.5, "fillOpacity": 0.75},
        tooltip=folium.GeoJsonTooltip(
            fields=["nombre_area", "tasa_anual_100k", "delitos_promedio_anual", "puesto_tasa"],
            aliases=["Área:", "Tasa anual por 100 mil:", "Delitos por año:", "Puesto por tasa:"],
        ),
    ).add_to(mapa)
    escala.add_to(mapa)
    mapa.save(str(ruta_html))
    return ruta_html


def generar_mapa_calor_puntos_html(df: pd.DataFrame, n_muestra: int = 12000,
                                   ruta_html: Path = REPORTES / "mapa_calor_hotspots.html") -> Path:
    """Mapa de calor (Folium HeatMap) sobre una muestra aleatoria de puntos georreferenciados."""
    geo = df[df["latitud"].between(41.64, 42.03) & df["longitud"].between(-87.94, -87.52)]
    muestra = geo.sample(min(n_muestra, len(geo)), random_state=42)
    mapa = mapa_base([41.8381, -87.6798], 10)
    HeatMap(muestra[["latitud", "longitud"]].round(4).to_numpy().tolist(), radius=12, blur=15, max_zoom=13).add_to(mapa)
    mapa.save(str(ruta_html))
    return ruta_html
