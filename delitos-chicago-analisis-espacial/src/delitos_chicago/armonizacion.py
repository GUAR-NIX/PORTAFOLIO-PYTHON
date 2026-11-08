"""Armonización de categorías de delito que cambiaron de nombre a lo largo del tiempo.

El portal de Chicago reetiquetó algunos tipos primarios (por ejemplo, `CRIM SEXUAL ASSAULT`
pasó a llamarse `CRIMINAL SEXUAL ASSAULT`). Si se comparan años sin armonizar, el cambio de
etiqueta aparece como un salto falso del delito (+114,6 % en lugar de −0,4 %).

La detección no se hace a mano, sino con los datos: una categoría que deja de aparecer es un
renombre si sus códigos IUCR (el código de delito de Illinois, que no cambia con la etiqueta)
se siguen registrando, después de su último año, bajo otra categoría.
"""
from __future__ import annotations

import pandas as pd

COLUMNAS_TABLA = [
    "tipo_original",
    "tipo_armonizado",
    "primer_anio_original",
    "ultimo_anio_original",
    "registros_original",
    "codigos_iucr",
    "cobertura_iucr_pct",
    "decision",
]


def detectar_renombres(
    conteos: pd.DataFrame,
    anio_ultimo: int,
    min_cobertura: float = 0.8,
) -> pd.DataFrame:
    """Detecta categorías que desaparecen y cuyos códigos IUCR pasan a otra categoría.

    `conteos` tiene columnas `anio`, `tipo_primario`, `codigo_iucr`, `conteo`.
    Una categoría «desaparece» si su último año con registros es anterior a `anio_ultimo`.
    Es renombre si al menos `min_cobertura` de sus registros usan códigos IUCR que, después
    de su último año, aparecen bajo una misma categoría sucesora.
    """
    conteos = conteos.dropna(subset=["tipo_primario"])
    por_tipo = conteos.groupby("tipo_primario").agg(
        primer=("anio", "min"), ultimo=("anio", "max"), total=("conteo", "sum")
    )
    filas = []
    for tipo, info in por_tipo[por_tipo["ultimo"] < anio_ultimo].iterrows():
        propios = conteos[conteos["tipo_primario"] == tipo]
        por_codigo = propios.groupby("codigo_iucr")["conteo"].sum()
        posteriores = conteos[
            (conteos["anio"] > info["ultimo"])
            & conteos["codigo_iucr"].isin(por_codigo.index)
            & (conteos["tipo_primario"] != tipo)
        ]
        sucesor, cobertura, decision = None, 0.0, "sin sucesor: sus códigos IUCR no vuelven a aparecer"
        if not posteriores.empty:
            sucesor = posteriores.groupby("tipo_primario")["conteo"].sum().idxmax()
            codigos_sucesor = set(posteriores.loc[posteriores["tipo_primario"] == sucesor, "codigo_iucr"])
            cobertura = float(por_codigo[por_codigo.index.isin(codigos_sucesor)].sum() / por_codigo.sum())
            decision = (
                "renombre: se armoniza"
                if cobertura >= min_cobertura
                else "no se armoniza: cobertura IUCR insuficiente"
            )
        filas.append({
            "tipo_original": tipo,
            "tipo_armonizado": sucesor if cobertura >= min_cobertura else tipo,
            "primer_anio_original": int(info["primer"]),
            "ultimo_anio_original": int(info["ultimo"]),
            "registros_original": int(info["total"]),
            "codigos_iucr": len(por_codigo),
            "cobertura_iucr_pct": round(cobertura * 100, 1),
            "decision": decision,
        })
    return pd.DataFrame(filas, columns=COLUMNAS_TABLA).sort_values("registros_original", ascending=False)


def mapa_renombres(tabla: pd.DataFrame) -> dict[str, str]:
    """Diccionario {tipo_original: tipo_armonizado} solo con los renombres aceptados."""
    aceptados = tabla[tabla["tipo_original"] != tabla["tipo_armonizado"]]
    return dict(zip(aceptados["tipo_original"], aceptados["tipo_armonizado"]))


def armonizar_tipos(serie: pd.Series, mapa: dict[str, str]) -> pd.Series:
    """Aplica el mapa de renombres a una serie de tipos primarios."""
    return serie.map(lambda t: mapa.get(t, t))


def expresion_sql(mapa: dict[str, str], columna: str = "tipo_primario") -> str:
    """Expresión SQL (DuckDB) que devuelve la categoría armonizada."""
    if not mapa:
        return columna
    casos = " ".join(
        f"WHEN '{o.replace(chr(39), chr(39) * 2)}' THEN '{d.replace(chr(39), chr(39) * 2)}'" for o, d in mapa.items()
    )
    return f"CASE {columna} {casos} ELSE {columna} END"


def comparar_antes_despues(
    conteos: pd.DataFrame, mapa: dict[str, str], anio_ini: int, anio_fin: int
) -> pd.DataFrame:
    """Muestra, para cada renombre, los conteos por etiqueta original y sumados en dos años."""
    filas = []
    por_anio_tipo = conteos.groupby(["anio", "tipo_primario"])["conteo"].sum()
    for original, destino in mapa.items():
        for etiqueta in (original, destino):
            ini = int(por_anio_tipo.get((anio_ini, etiqueta), 0))
            fin = int(por_anio_tipo.get((anio_fin, etiqueta), 0))
            filas.append({"categoria": etiqueta, "grupo": destino, f"conteo_{anio_ini}": ini, f"conteo_{anio_fin}": fin})
        ini = sum(f[f"conteo_{anio_ini}"] for f in filas[-2:])
        fin = sum(f[f"conteo_{anio_fin}"] for f in filas[-2:])
        filas.append({"categoria": f"{destino} (armonizada)", "grupo": destino, f"conteo_{anio_ini}": ini, f"conteo_{anio_fin}": fin})
    tabla = pd.DataFrame(filas)
    if tabla.empty:
        return tabla
    ini_col, fin_col = f"conteo_{anio_ini}", f"conteo_{anio_fin}"
    tabla["cambio_pct"] = ((tabla[fin_col] - tabla[ini_col]) / tabla[ini_col].where(tabla[ini_col] > 0) * 100).round(1)
    return tabla
