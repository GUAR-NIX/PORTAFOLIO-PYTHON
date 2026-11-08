"""Por qué el promedio de las solicitudes cerradas está sesgado: experimento de «corte retrospectivo».

Tomamos una cohorte antigua (creada en octubre–diciembre de 2024), de la que hoy conocemos el desenlace
casi completo (≈ 2 años de seguimiento). Luego **fingimos** que la descarga se hizo poco después
(`corte_ficticio`), cuando muchas solicitudes seguían abiertas, y comparamos con la «verdad»:

* Promedio y mediana **ingenuos**: solo las cerradas antes del corte ficticio (descarta las lentas).
* Promedio que **trata las abiertas como cerradas al corte** (las acorta artificialmente).
* **Kaplan-Meier** con las abiertas como censuradas al corte ficticio.

Si KM recupera la mediana y el % cerrado a 30 días de la verdad y los ingenuos no, queda demostrado
con datos reales, no con una simulación.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyc311.limpieza import SEGUNDOS_DIA
from nyc311.supervivencia import evaluar, kaplan_meier, mediana_con_ic

COHORTE_DESDE = "2024-10-01"
COHORTE_HASTA = "2025-01-01"  # exclusivo
CORTE_FICTICIO = "2025-01-15"
HORIZONTE_DIAS = 30.0


def recensurar(df: pd.DataFrame, corte: pd.Timestamp | str) -> pd.DataFrame:
    """Reconstruye duración y evento como se habrían visto si la descarga se hubiera hecho en `corte`.

    Solo usa `creada` y `cerrada` (los cierres posteriores al corte ficticio pasan a censura).
    """
    corte = pd.Timestamp(corte)
    sub = df.loc[df["creada"] < corte]
    evento = sub["cerrada"].notna() & (sub["cerrada"] <= corte)
    fin = sub["cerrada"].where(evento, corte)
    return pd.DataFrame(
        {
            "duracion_dias": (fin - sub["creada"]).dt.total_seconds().to_numpy() / SEGUNDOS_DIA,
            "evento": evento.astype("int8").to_numpy(),
        },
        index=sub.index,
    )


def _medidas(duracion: np.ndarray, evento: np.ndarray) -> dict[str, float]:
    tabla = kaplan_meier(duracion, evento)
    med, lo, hi = mediana_con_ic(tabla)
    cerradas = duracion[evento == 1]
    return {
        "n": int(duracion.size),
        "pct_abiertas": 100 * float(1 - evento.mean()),
        "promedio_ingenuo": float(cerradas.mean()),
        "mediana_ingenua": float(np.median(cerradas)),
        "promedio_abiertas_al_corte": float(duracion.mean()),
        "pct_cerradas_30d_ingenuo": 100 * float(((evento == 1) & (duracion <= HORIZONTE_DIAS)).mean()),
        "mediana_km": med,
        "mediana_km_ic_inf": lo,
        "mediana_km_ic_sup": hi,
        "pct_cerradas_30d_km": 100 * (1 - float(evaluar(tabla, HORIZONTE_DIAS)[0])),
    }


def experimento_corte_retrospectivo(
    df: pd.DataFrame, grupo: str | None = "agencia", min_n: int = 2_000
) -> pd.DataFrame:
    """Compara, para la cohorte y por grupo, las medidas ingenuas y KM al corte ficticio con la verdad actual.

    La «verdad» es KM con todo el seguimiento disponible (fecha de corte real), donde casi no queda censura.
    """
    cohorte = df.loc[(df["creada"] >= COHORTE_DESDE) & (df["creada"] < COHORTE_HASTA)]
    ficticio = recensurar(cohorte, CORTE_FICTICIO)
    grupos = [("Todas", cohorte.index)]
    if grupo:
        grupos += [(str(k), idx) for k, idx in cohorte.groupby(grupo, observed=True).groups.items() if len(idx) >= min_n]

    filas = []
    for nombre, idx in grupos:
        verdad = _medidas(cohorte.loc[idx, "duracion_dias"].to_numpy(), cohorte.loc[idx, "evento"].to_numpy())
        visto = _medidas(ficticio.loc[idx, "duracion_dias"].to_numpy(), ficticio.loc[idx, "evento"].to_numpy())
        filas.append(
            {
                "grupo": nombre,
                "n": visto["n"],
                "pct_abiertas_corte_ficticio": visto["pct_abiertas"],
                "pct_abiertas_hoy": verdad["pct_abiertas"],
                "promedio_ingenuo_ficticio": visto["promedio_ingenuo"],
                "mediana_ingenua_ficticio": visto["mediana_ingenua"],
                "promedio_abiertas_al_corte_ficticio": visto["promedio_abiertas_al_corte"],
                "mediana_km_ficticio": visto["mediana_km"],
                "mediana_km_ficticio_ic_inf": visto["mediana_km_ic_inf"],
                "mediana_km_ficticio_ic_sup": visto["mediana_km_ic_sup"],
                "mediana_verdad": verdad["mediana_km"],
                "promedio_verdad_cerradas": verdad["promedio_ingenuo"],
                "pct_cerradas_30d_ingenuo_ficticio": visto["pct_cerradas_30d_ingenuo"],
                "pct_cerradas_30d_km_ficticio": visto["pct_cerradas_30d_km"],
                "pct_cerradas_30d_verdad": verdad["pct_cerradas_30d_km"],
            }
        )
    return pd.DataFrame(filas)
