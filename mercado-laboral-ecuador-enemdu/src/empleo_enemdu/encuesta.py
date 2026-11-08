"""Inferencia estadística en muestras complejas estratificadas y por conglomerados (ENEMDU).

Implementa el estimador de razón para subpoblaciones (dominios) mediante linealización
de Taylor respetando estratos (`estrato`), unidades primarias de muestreo (`upm`) y
factores de expansión (`fexp`), además del cálculo del efecto de diseño (DEFF), tamaño
de muestra efectivo y pruebas de hipótesis de diferencias entre dominios que comparten UPM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class EstimacionCompleja:
    """Resultado de una estimación de media o proporción bajo diseño muestral complejo."""

    indicador: str
    dominio: str
    estimacion: float
    error_estandar: float
    error_estandar_mas: float
    limite_inferior: float
    limite_superior: float
    coeficiente_variacion: float
    deff: float
    deft: float
    n_muestral: int
    n_efectivo: float
    poblacion_expandida: float
    n_upm: int
    n_estratos: int
    grados_libertad: int

    def a_dict(self, *, en_porcentaje: bool = False) -> dict[str, Any]:
        """Convierte la estimación a diccionario (opcionalmente escalando proporciones a %)."""
        d = asdict(self)
        if en_porcentaje:
            for k in (
                "estimacion",
                "error_estandar",
                "error_estandar_mas",
                "limite_inferior",
                "limite_superior",
            ):
                d[k] = round(d[k] * 100.0, 4)
        return d


@dataclass
class DisenoMuestralENEMDU:
    """Estructura precalculada del diseño muestral bietápico estratificado de la ENEMDU."""

    pos_upm: np.ndarray
    pos_estrato_de_upm: np.ndarray
    a_h_por_upm: np.ndarray
    a_h_por_estrato: np.ndarray
    n_upm: int
    n_estratos: int
    fexp: np.ndarray

    @classmethod
    def desde_dataframe(
        cls,
        df: pd.DataFrame,
        *,
        col_estrato: str = "estrato",
        col_upm: str = "upm",
        col_fexp: str = "fexp",
    ) -> "DisenoMuestralENEMDU":
        """Construye la estructura de estratos y UPM sobre la muestra completa."""
        estrato = df[col_estrato].to_numpy()
        upm = df[col_upm].to_numpy()
        fexp = df[col_fexp].to_numpy(dtype=np.float64)

        pares = (
            pd.DataFrame({"estrato": estrato, "upm": upm})
            .drop_duplicates()
            .sort_values(["estrato", "upm"])
            .reset_index(drop=True)
        )
        estratos_unicos, pos_estrato_de_upm, a_h_por_estrato = np.unique(
            pares["estrato"].to_numpy(),
            return_inverse=True,
            return_counts=True,
        )
        a_h_por_upm = a_h_por_estrato[pos_estrato_de_upm].astype(np.float64)

        codigos = pd.MultiIndex.from_arrays([estrato, upm])
        indice_unico = pd.MultiIndex.from_frame(pares)
        pos_upm = indice_unico.get_indexer(codigos)

        return cls(
            pos_upm=pos_upm,
            pos_estrato_de_upm=pos_estrato_de_upm,
            a_h_por_upm=a_h_por_upm,
            a_h_por_estrato=a_h_por_estrato.astype(np.float64),
            n_upm=len(pares),
            n_estratos=len(estratos_unicos),
            fexp=fexp,
        )

    def varianza_totales_linealizados(
        self,
        z_i: np.ndarray,
        *,
        upm_solitaria: str = "certainty",
    ) -> float:
        """Calcula la varianza por linealización de Taylor a partir de los residuos z_i."""
        # Suma de z_i en cada UPM (incluyendo UPMs con suma 0 fuera del dominio)
        z_ha = np.bincount(self.pos_upm, weights=z_i, minlength=self.n_upm)

        # Media de z_ha dentro de cada estrato h
        suma_estrato = np.bincount(
            self.pos_estrato_de_upm, weights=z_ha, minlength=self.n_estratos
        )
        media_estrato = suma_estrato / np.maximum(self.a_h_por_estrato, 1.0)
        z_centrado = z_ha - media_estrato[self.pos_estrato_de_upm]

        factor = np.where(
            self.a_h_por_upm > 1.0,
            self.a_h_por_upm / np.maximum(self.a_h_por_upm - 1.0, 1.0),
            0.0,
        )
        var_total = float(np.sum(factor * (z_centrado ** 2)))

        if upm_solitaria == "adjust":
            solitarias = self.a_h_por_upm == 1.0
            if np.any(solitarias):
                media_global = float(np.mean(z_ha))
                var_total += float(np.sum((z_ha[solitarias] - media_global) ** 2))
        return max(var_total, 0.0)


def estimar_razon_dominio(
    diseno: DisenoMuestralENEMDU,
    y: np.ndarray | pd.Series,
    mascara_dominio: np.ndarray | pd.Series,
    *,
    indicador: str = "indicador",
    dominio: str = "Nacional",
    nivel_confianza: float = 0.95,
    upm_solitaria: str = "certainty",
) -> EstimacionCompleja:
    """Estima la media/proporción de `y` en `mascara_dominio` con linealización de Taylor."""
    y_arr = np.asarray(y, dtype=np.float64)
    dom_arr = np.asarray(mascara_dominio, dtype=bool) & np.isfinite(y_arr)
    w = diseno.fexp

    n_muestral = int(np.sum(dom_arr))
    if n_muestral == 0:
        raise ValueError(f"El dominio '{dominio}' para '{indicador}' no tiene observaciones válidas.")

    v_i = np.where(dom_arr, w, 0.0)
    u_i = np.where(dom_arr, w * y_arr, 0.0)

    x_gorro = float(np.sum(v_i))
    y_gorro = float(np.sum(u_i))
    r_gorro = y_gorro / x_gorro

    # Residuo linealizado de Taylor: z_i = w_i * d_i * (y_i - R_gorro) / X_gorro
    z_i = np.where(dom_arr, w * (y_arr - r_gorro) / x_gorro, 0.0)
    var_compleja = diseno.varianza_totales_linealizados(z_i, upm_solitaria=upm_solitaria)
    ee_complejo = float(np.sqrt(var_compleja))

    # Varianza bajo Muestreo Aleatorio Simple (MAS) ponderado en el dominio
    residuos_dom = y_arr[dom_arr] - r_gorro
    pesos_dom = w[dom_arr]
    s2_mas = float(np.sum(pesos_dom * (residuos_dom ** 2)) / max(x_gorro, 1e-12))
    if n_muestral > 1:
        s2_mas *= n_muestral / (n_muestral - 1.0)
    var_mas = s2_mas / max(n_muestral, 1)
    ee_mas = float(np.sqrt(max(var_mas, 0.0)))

    deff = float(var_compleja / var_mas) if var_mas > 1e-15 else 1.0
    deft = float(np.sqrt(max(deff, 0.0)))
    n_efectivo = float(n_muestral / deff) if deff > 1e-12 else float(n_muestral)

    gl = max(diseno.n_upm - diseno.n_estratos, 1)
    alfa = 1.0 - nivel_confianza
    t_crit = float(stats.t.ppf(1.0 - alfa / 2.0, df=gl))
    lim_inf = r_gorro - t_crit * ee_complejo
    lim_sup = r_gorro + t_crit * ee_complejo
    cv = float((ee_complejo / abs(r_gorro)) * 100.0) if abs(r_gorro) > 1e-12 else 0.0

    return EstimacionCompleja(
        indicador=indicador,
        dominio=dominio,
        estimacion=r_gorro,
        error_estandar=ee_complejo,
        error_estandar_mas=ee_mas,
        limite_inferior=lim_inf,
        limite_superior=lim_sup,
        coeficiente_variacion=cv,
        deff=deff,
        deft=deft,
        n_muestral=n_muestral,
        n_efectivo=n_efectivo,
        poblacion_expandida=x_gorro,
        n_upm=diseno.n_upm,
        n_estratos=diseno.n_estratos,
        grados_libertad=gl,
    )


def prueba_diferencia_dominios(
    diseno: DisenoMuestralENEMDU,
    y: np.ndarray | pd.Series,
    mascara_a: np.ndarray | pd.Series,
    mascara_b: np.ndarray | pd.Series,
    *,
    nombre_a: str = "Grupo A",
    nombre_b: str = "Grupo B",
) -> dict[str, float | str]:
    """Prueba t de diseño complejo para R_A - R_B capturando la covarianza intra-UPM."""
    y_arr = np.asarray(y, dtype=np.float64)
    dom_a = np.asarray(mascara_a, dtype=bool) & np.isfinite(y_arr)
    dom_b = np.asarray(mascara_b, dtype=bool) & np.isfinite(y_arr)
    w = diseno.fexp

    xa = float(np.sum(np.where(dom_a, w, 0.0)))
    xb = float(np.sum(np.where(dom_b, w, 0.0)))
    ra = float(np.sum(np.where(dom_a, w * y_arr, 0.0))) / xa
    rb = float(np.sum(np.where(dom_b, w * y_arr, 0.0))) / xb

    za = np.where(dom_a, w * (y_arr - ra) / xa, 0.0)
    zb = np.where(dom_b, w * (y_arr - rb) / xb, 0.0)
    z_diff = za - zb

    var_diff = diseno.varianza_totales_linealizados(z_diff)
    var_a = diseno.varianza_totales_linealizados(za)
    var_b = diseno.varianza_totales_linealizados(zb)
    ee_diff = float(np.sqrt(var_diff))
    ee_indep = float(np.sqrt(var_a + var_b))

    diff = ra - rb
    gl = max(diseno.n_upm - diseno.n_estratos, 1)
    t_stat = diff / ee_diff if ee_diff > 1e-15 else 0.0
    p_valor = float(2.0 * stats.t.sf(abs(t_stat), df=gl))
    t_crit = float(stats.t.ppf(0.975, df=gl))

    return {
        "grupo_a": nombre_a,
        "grupo_b": nombre_b,
        "estimacion_a": ra,
        "estimacion_b": rb,
        "diferencia": diff,
        "error_estandar_complejo": ee_diff,
        "error_estandar_independiente": ee_indep,
        "estadistico_t": t_stat,
        "p_valor": p_valor,
        "ic95_inferior": diff - t_crit * ee_diff,
        "ic95_superior": diff + t_crit * ee_diff,
    }


def cuantil_ponderado(
    valores: np.ndarray | pd.Series,
    pesos: np.ndarray | pd.Series,
    cuantiles: list[float] | np.ndarray,
) -> np.ndarray:
    """Calcula cuantiles ponderados exactos para una variable continua."""
    x = np.asarray(valores, dtype=np.float64)
    w = np.asarray(pesos, dtype=np.float64)
    valido = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x = x[valido]
    w = w[valido]
    orden = np.argsort(x, kind="mergesort")
    x = x[orden]
    w = w[orden]
    acum = np.cumsum(w)
    p = (acum - 0.5 * w) / acum[-1]
    return np.interp(np.asarray(cuantiles, dtype=np.float64), p, x)
