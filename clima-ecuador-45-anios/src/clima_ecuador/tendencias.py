"""
Tendencias no paramétricas: Mann-Kendall, pendiente de Sen y corrección por autocorrelación.

* **Mann-Kendall** (Mann 1945, Kendall 1975): ¿la serie sube o baja de forma monótona? No supone normalidad ni
  linealidad y es robusto a valores extremos (El Niño 1997-98, por ejemplo).
* **Pendiente de Sen** (Sen 1968): mediana de todas las pendientes entre pares; intervalo de confianza de Gilbert (1987).
* **Autocorrelación**: si un año cálido tiende a seguir a otro cálido, la varianza de S está subestimada y el test
  declara "significativo" de más. Dos correcciones de la varianza:
  - **Hamed y Rao (1998)**: tamaño efectivo con la autocorrelación de los rangos de la serie sin tendencia,
    solo los rezagos significativos. Es la que se reporta.
  - **Yue y Wang (2004)**: con la autocorrelación de la serie sin tendencia, todos los rezagos.
* **Benjamini-Hochberg**: con 22 ciudades × varias variables se corrige la tasa de falsos descubrimientos.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class ResultadoMK:
    n: int
    s: float
    var_s: float
    z: float
    p: float
    tendencia: str          # "sube", "baja" o "sin tendencia"
    pendiente: float        # Sen, unidades por paso de tiempo
    intercepto: float
    ic_bajo: float
    ic_alto: float
    n_efectivo_factor: float = 1.0


def _var_s(x: np.ndarray) -> float:
    """Varianza de S con corrección por empates."""
    n = len(x)
    _, conteos = np.unique(x, return_counts=True)
    empates = conteos[conteos > 1]
    return (n * (n - 1) * (2 * n + 5) - np.sum(empates * (empates - 1) * (2 * empates + 5))) / 18


def estadistico_s(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    dif = x[None, :] - x[:, None]                  # dif[i, j] = x[j] − x[i]
    return float(np.sign(dif[np.triu_indices(len(x), 1)]).sum())


def _z(s: float, var_s: float) -> float:
    if var_s <= 0:
        return 0.0
    if s > 0:
        return (s - 1) / np.sqrt(var_s)
    if s < 0:
        return (s + 1) / np.sqrt(var_s)
    return 0.0


def pendiente_sen(x: np.ndarray, t: np.ndarray | None = None, var_s: float | None = None,
                  alfa: float = 0.05) -> tuple[float, float, float, float]:
    """Pendiente de Sen, intercepto (Conover) e intervalo de confianza (Gilbert 1987)."""
    x = np.asarray(x, dtype=float)
    t = np.arange(len(x), dtype=float) if t is None else np.asarray(t, dtype=float)
    i, j = np.triu_indices(len(x), 1)
    pendientes = (x[j] - x[i]) / (t[j] - t[i])
    pendiente = float(np.median(pendientes))
    intercepto = float(np.median(x) - pendiente * np.median(t))
    var_s = _var_s(x) if var_s is None else var_s
    c = stats.norm.ppf(1 - alfa / 2) * np.sqrt(var_s)
    orden = np.sort(pendientes)
    m1 = int(np.floor((len(orden) - c) / 2))
    m2 = int(np.ceil((len(orden) + c) / 2))
    bajo = orden[max(m1 - 1, 0)] if len(orden) else np.nan
    alto = orden[min(m2 - 1, len(orden) - 1)] if len(orden) else np.nan
    return pendiente, intercepto, float(bajo), float(alto)


def _acf(x: np.ndarray, nlags: int) -> np.ndarray:
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    denominador = np.sum(x ** 2)
    return np.array([np.sum(x[: n - k] * x[k:]) / denominador for k in range(nlags + 1)])


def _resultado(x, s, var_s, factor, alfa) -> ResultadoMK:
    z = _z(s, var_s)
    p = float(2 * (1 - stats.norm.cdf(abs(z))))
    pendiente, intercepto, bajo, alto = pendiente_sen(x, var_s=var_s, alfa=alfa)
    tendencia = "sin tendencia" if p >= alfa else ("sube" if z > 0 else "baja")
    return ResultadoMK(len(x), s, float(var_s), float(z), p, tendencia, pendiente, intercepto, bajo, alto, float(factor))


def mann_kendall(x, alfa: float = 0.05, correccion: str = "hamed_rao",
                 factor_minimo: float | None = None) -> ResultadoMK:
    """Test de Mann-Kendall. ``correccion``: "ninguna", "hamed_rao" o "yue_wang". Ignora los NaN.

    ``factor_minimo=1`` hace la corrección solo conservadora: con autocorrelación negativa en algún rezago
    (el ciclo de 3–7 años de El Niño en Galápagos, por ejemplo) el factor baja de 1 y el test se volvería
    *más* permisivo que el original.
    """
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 4:
        raise ValueError("Mann-Kendall necesita al menos 4 valores")
    s = estadistico_s(x)
    var_s = _var_s(x)
    factor = 1.0
    if correccion in ("hamed_rao", "yue_wang"):
        pendiente, *_ = pendiente_sen(x)
        sin_tendencia = x - pendiente * np.arange(1, n + 1)
        if correccion == "hamed_rao":
            rangos = stats.rankdata(sin_tendencia)
            acf = _acf(rangos, n - 1)
            limite = stats.norm.ppf(1 - alfa / 2) / np.sqrt(n)
            k = np.arange(1, n)
            significativos = np.abs(acf[1:]) > limite
            suma = np.sum(((n - k) * (n - k - 1) * (n - k - 2) * acf[1:])[significativos])
            factor = 1 + 2 / (n * (n - 1) * (n - 2)) * suma
        else:
            acf = _acf(sin_tendencia, n - 1)
            k = np.arange(1, n)
            factor = 1 + 2 * np.sum((1 - k / n) * acf[1:])
        factor = max(factor, 1e-6 if factor_minimo is None else factor_minimo)
        var_s = var_s * factor
    elif correccion != "ninguna":
        raise ValueError(f"Corrección desconocida: {correccion}")
    return _resultado(x, s, var_s, factor, alfa)


def benjamini_hochberg(p: np.ndarray | pd.Series) -> np.ndarray:
    """Valores p ajustados por la tasa de falsos descubrimientos (BH 1995)."""
    p = np.asarray(p, dtype=float)
    n = len(p)
    orden = np.argsort(p)
    ajustado = p[orden] * n / np.arange(1, n + 1)
    ajustado = np.minimum.accumulate(ajustado[::-1])[::-1]
    salida = np.empty(n)
    salida[orden] = np.minimum(ajustado, 1)
    return salida


def pettitt_sin_tendencia(x) -> tuple[int, float]:
    """Pettitt sobre los residuos de la recta de Sen: ¿hay un salto *además* de la tendencia?

    Una serie con tendencia lineal siempre "cambia" a mitad de camino; quitando la tendencia, un p bajo apunta a
    un escalón real (por ejemplo, un cambio en las observaciones que asimila el reanálisis).
    """
    x = np.asarray(x, dtype=float)
    pendiente, intercepto, *_ = pendiente_sen(x)
    return pettitt(x - (intercepto + pendiente * np.arange(len(x))))


def pettitt(x) -> tuple[int, float]:
    """Test de Pettitt (1979) de un punto de cambio: posición (índice del último valor antes) y p aproximado."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    signos = np.sign(x[None, :] - x[:, None])          # signos[i, j] = sign(x[j] − x[i])
    u = np.array([-signos[: k + 1, k + 1:].sum() for k in range(n - 1)])
    k = int(np.argmax(np.abs(u)))
    estadistico = np.abs(u[k])
    p = float(min(1.0, 2 * np.exp(-6 * estadistico ** 2 / (n ** 3 + n ** 2))))
    return k, p


def tabla_tendencias(anual: pd.DataFrame, variables: list[str], grupo: str = "punto", tiempo: str = "anio",
                     por: float = 10.0, alfa: float = 0.05, factor_minimo: float | None = 1.0) -> pd.DataFrame:
    """Tendencia de cada serie anual: pendiente de Sen por década, p original y corregido, FDR y cambio total.

    El p que decide la significancia es el de Hamed-Rao con ``factor_minimo`` (por defecto 1: solo conservador).
    """
    filas = []
    for clave, datos in anual.groupby(grupo):
        for var in variables:
            x = datos.sort_values(tiempo)[var].dropna().to_numpy()
            if len(x) < 10:
                continue
            original = mann_kendall(x, alfa, "ninguna")
            hr = mann_kendall(x, alfa, "hamed_rao", factor_minimo)
            hr_libre = mann_kendall(x, alfa, "hamed_rao")
            yw = mann_kendall(x, alfa, "yue_wang")
            filas.append({grupo: clave, "variable": var, "n": len(x),
                          "pendiente_decada": hr.pendiente * por, "ic_bajo_decada": hr.ic_bajo * por,
                          "ic_alto_decada": hr.ic_alto * por, "cambio_total": hr.pendiente * (len(x) - 1),
                          "z": original.z, "p_original": original.p, "p_hamed_rao": hr.p, "p_hr_sin_piso": hr_libre.p,
                          "p_yue_wang": yw.p, "factor_hr": hr_libre.n_efectivo_factor, "media": float(np.mean(x))})
    t = pd.DataFrame(filas)
    if len(t):
        t["p_fdr"] = np.nan
        for var, idx in t.groupby("variable").groups.items():
            t.loc[idx, "p_fdr"] = benjamini_hochberg(t.loc[idx, "p_hamed_rao"])
        t["significativa"] = t["p_hamed_rao"] < alfa
        t["significativa_fdr"] = t["p_fdr"] < alfa
        t["tendencia"] = np.where(~t["significativa"], "sin tendencia",
                                  np.where(t["pendiente_decada"] > 0, "sube", "baja"))
    return t


def como_dict(r: ResultadoMK) -> dict:
    return asdict(r)
