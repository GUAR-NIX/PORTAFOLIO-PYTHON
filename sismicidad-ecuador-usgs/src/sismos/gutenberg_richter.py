"""
Ley de Gutenberg-Richter:  log10 N(≥M) = a − b·M

* **Mc** (magnitud de completitud): por debajo de Mc el catálogo pierde sismos y la recta se dobla.
  Se usa la máxima curvatura (la clase con más eventos) + 0,2, la corrección que recomiendan
  Woessner y Wiemer (2005) porque MAXC sola subestima Mc. La incertidumbre de Mc sale de un bootstrap.
* **Valor b** por máxima verosimilitud de Aki (1965) con la corrección por clases de Utsu (1966):

      b = log10(e) / ( media(M) − (Mc − ΔM/2) )

  Error de Shi y Bolt (1982):  σ_b = 2,30·b²·sqrt( Σ(Mi − media)² / (n(n−1)) ).
  IC 95 % = b ± 1,96·σ_b, contrastado con un bootstrap de percentiles.
* **Línea base**: mínimos cuadrados sobre log10 N acumulado. Es lo que haría alguien sin estadística
  sísmica; está sesgado porque los puntos acumulados no son independientes y los de magnitud alta
  (pocos eventos) pesan igual que los de magnitud baja.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

LOG10_E = np.log10(np.e)


def a_clases(m, dm: float = 0.1) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    return np.round(np.floor(m / dm + 0.5 + 1e-9) * dm, 6)


def mc_maxc(m, dm: float = 0.1, correccion: float = 0.2) -> float:
    """Máxima curvatura (clase modal de la distribución no acumulada) + corrección."""
    m = a_clases(m, dm)
    clases, conteos = np.unique(m, return_counts=True)
    return float(np.round(clases[np.argmax(conteos)] + correccion, 6))


def mc_bootstrap(m, dm: float = 0.1, correccion: float = 0.2, n_boot: int = 500,
                 semilla: int = 42) -> tuple[float, float]:
    """Media y desviación de Mc remuestreando el catálogo."""
    rng = np.random.default_rng(semilla)
    m = np.asarray(m, dtype=float)
    valores = [mc_maxc(rng.choice(m, len(m)), dm, correccion) for _ in range(n_boot)]
    return float(np.mean(valores)), float(np.std(valores))


@dataclass
class AjusteGR:
    mc: float
    n: int
    b: float
    a: float                 # a anualizado si se da la duración; si no, a del catálogo completo
    sigma_shi_bolt: float
    sigma_aki: float
    ic95_bajo: float
    ic95_alto: float
    ic95_boot_bajo: float | None = None
    ic95_boot_alto: float | None = None
    anios: float | None = None

    def como_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def valor_b_aki(m, mc: float, dm: float = 0.1, anios: float | None = None, n_boot: int = 0,
                semilla: int = 42) -> AjusteGR:
    """Valor b por máxima verosimilitud para los eventos con M ≥ Mc (magnitudes ya en clases de ΔM)."""
    m = a_clases(m, dm)
    m = m[m >= mc - 1e-9]
    n = len(m)
    if n < 2:
        raise ValueError(f"Muy pocos eventos sobre Mc={mc}: {n}")
    media = m.mean()
    b = LOG10_E / (media - (mc - dm / 2))
    sigma_sb = 2.30 * b ** 2 * np.sqrt(((m - media) ** 2).sum() / (n * (n - 1)))
    sigma_aki = b / np.sqrt(n)
    a = np.log10(n / anios if anios else n) + b * mc
    ajuste = AjusteGR(mc=float(mc), n=int(n), b=float(b), a=float(a), sigma_shi_bolt=float(sigma_sb),
                      sigma_aki=float(sigma_aki), ic95_bajo=float(b - 1.96 * sigma_sb),
                      ic95_alto=float(b + 1.96 * sigma_sb), anios=anios)
    if n_boot:
        rng = np.random.default_rng(semilla)
        bs = np.array([LOG10_E / (rng.choice(m, n).mean() - (mc - dm / 2)) for _ in range(n_boot)])
        ajuste.ic95_boot_bajo, ajuste.ic95_boot_alto = map(float, np.percentile(bs, [2.5, 97.5]))
    return ajuste


def valor_b_minimos_cuadrados(m, mc: float, dm: float = 0.1) -> tuple[float, float]:
    """Línea base: recta por mínimos cuadrados a log10 N(≥M) para M ≥ Mc. Devuelve (b, a)."""
    clases, acumulado = distribucion_acumulada(m, dm)
    sel = clases >= mc - 1e-9
    pendiente, intercepto = np.polyfit(clases[sel], np.log10(acumulado[sel]), 1)
    return float(-pendiente), float(intercepto)


def distribucion_acumulada(m, dm: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Clases de magnitud y N(≥M) para cada una (sin clases vacías intermedias)."""
    m = a_clases(m, dm)
    clases = np.round(np.arange(m.min(), m.max() + dm / 2, dm), 6)
    orden = np.sort(m)
    acumulado = len(m) - np.searchsorted(orden, clases - 1e-9)
    return clases, acumulado


def distribucion_no_acumulada(m, dm: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    m = a_clases(m, dm)
    clases = np.round(np.arange(m.min(), m.max() + dm / 2, dm), 6)
    conteos = np.array([(np.abs(m - c) < 1e-6).sum() for c in clases])
    return clases, conteos


def estabilidad_b(m, mcs, dm: float = 0.1) -> list[dict]:
    """b y su error para varios umbrales: si b se estabiliza a partir de cierto Mc, ese Mc es creíble."""
    filas = []
    for mc in mcs:
        try:
            aj = valor_b_aki(m, mc, dm)
            filas.append({"mc": round(float(mc), 1), "b": aj.b, "sigma": aj.sigma_shi_bolt, "n": aj.n})
        except ValueError:
            pass
    return filas


def mc_mbs(m, dm: float = 0.1, ventana: float = 0.5, n_min: int = 50) -> float | None:
    """Mc por estabilidad del valor b (MBS; Cao y Gao, 2002, criterio de Woessner y Wiemer, 2005):
    el menor Mc cuyo b difiere del promedio de b en [Mc, Mc + ventana] en menos de su error σ_b.

    Sirve donde MAXC falla: en un catálogo que mezcla escalas (mb para los sismos chicos, Mw para los
    grandes) la distribución se dobla aunque el catálogo esté completo, y b cambia con el umbral."""
    m = a_clases(m, dm)
    pasos = int(round(ventana / dm))
    candidatos = np.round(np.arange(m.min(), m.max() + dm / 2, dm), 6)
    tabla = {}
    for mc in candidatos:
        if (m >= mc - 1e-9).sum() >= n_min:
            aj = valor_b_aki(m, mc, dm)
            tabla[round(float(mc), 1)] = (aj.b, aj.sigma_shi_bolt)
    for mc, (b, sigma) in tabla.items():
        siguientes = [tabla.get(round(mc + k * dm, 1)) for k in range(pasos + 1)]
        if any(s is None for s in siguientes):
            break
        if abs(np.mean([s[0] for s in siguientes]) - b) <= sigma:
            return mc
    return None


def simular_gr(n: int, b: float, mc: float, dm: float = 0.1, semilla: int = 0) -> np.ndarray:
    """Catálogo sintético de b conocido: M − (Mc − ΔM/2) ~ Exponencial(β = b·ln10), en clases de ΔM."""
    rng = np.random.default_rng(semilla)
    continua = (mc - dm / 2) + rng.exponential(1 / (b * np.log(10)), n)
    return a_clases(continua, dm)
