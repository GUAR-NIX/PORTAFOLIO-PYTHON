import numpy as np
import pymannkendall as pmk
import pytest

from clima_ecuador import tendencias


def serie_ar1(n=45, phi=0.6, pendiente=0.0, semilla=1):
    rng = np.random.default_rng(semilla)
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = phi * e[i - 1] + rng.normal()
    return pendiente * np.arange(n) + e


def test_sen_recupera_pendiente_exacta():
    x = 3 + 0.25 * np.arange(30)
    r = tendencias.mann_kendall(x, correccion="ninguna")
    assert r.pendiente == pytest.approx(0.25)
    assert r.tendencia == "sube"
    assert r.ic_bajo <= 0.25 <= r.ic_alto


def test_serie_constante_sin_tendencia():
    r = tendencias.mann_kendall(np.ones(20), correccion="ninguna")
    assert r.s == 0 and r.tendencia == "sin tendencia"


def test_s_cuenta_pares():
    # 1,2,3 -> 3 pares crecientes; 3,2,1 -> −3
    assert tendencias.estadistico_s(np.array([1, 2, 3])) == 3
    assert tendencias.estadistico_s(np.array([3, 2, 1])) == -3


@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_coincide_con_pymannkendall_original(semilla):
    x = serie_ar1(pendiente=0.03, semilla=semilla)
    propio = tendencias.mann_kendall(x, correccion="ninguna")
    ref = pmk.original_test(x)
    assert propio.s == pytest.approx(ref.s)
    assert propio.var_s == pytest.approx(ref.var_s)
    assert propio.p == pytest.approx(ref.p, rel=1e-6)
    assert propio.pendiente == pytest.approx(ref.slope)


@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_coincide_con_pymannkendall_hamed_rao(semilla):
    x = serie_ar1(pendiente=0.03, semilla=semilla)
    propio = tendencias.mann_kendall(x, correccion="hamed_rao")
    ref = pmk.hamed_rao_modification_test(x)
    assert propio.p == pytest.approx(ref.p, rel=1e-4)


@pytest.mark.parametrize("semilla", [1, 2])
def test_coincide_con_pymannkendall_yue_wang(semilla):
    x = serie_ar1(pendiente=0.03, semilla=semilla)
    propio = tendencias.mann_kendall(x, correccion="yue_wang")
    ref = pmk.yue_wang_modification_test(x)
    assert propio.p == pytest.approx(ref.p, rel=1e-4)


def test_autocorrelacion_reduce_falsos_positivos():
    """Ruido rojo sin tendencia: el test original rechaza mucho más que el 5 %; Hamed-Rao, menos."""
    rechazos_original = rechazos_hr = 0
    for s in range(200):
        x = serie_ar1(n=45, phi=0.7, semilla=100 + s)
        rechazos_original += tendencias.mann_kendall(x, correccion="ninguna").p < 0.05
        rechazos_hr += tendencias.mann_kendall(x, correccion="hamed_rao").p < 0.05
    assert rechazos_original / 200 > 0.15
    assert rechazos_hr < rechazos_original


def test_benjamini_hochberg():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    ajustado = tendencias.benjamini_hochberg(p)
    assert ajustado == pytest.approx([0.04, 0.0533333, 0.0533333, 0.20], rel=1e-4)
    assert np.all(ajustado >= p)


def test_pettitt_encuentra_el_salto():
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 0.3, 20), rng.normal(2, 0.3, 25)])
    k, p = tendencias.pettitt(x)
    assert k == 19 and p < 0.01


def test_tabla_tendencias(diario_sintetico):
    d = diario_sintetico.assign(anio=diario_sintetico["fecha"].dt.year)
    anual = d.groupby(["punto", "anio"]).agg(tmed=("tmed", "mean"), precip=("precip", "sum")).reset_index()
    t = tendencias.tabla_tendencias(anual, ["tmed", "precip"]).set_index("variable")
    assert t.loc["tmed", "pendiente_decada"] == pytest.approx(0.3, abs=0.06)
    assert t.loc["tmed", "tendencia"] == "sube"
    assert {"p_original", "p_hamed_rao", "p_yue_wang", "p_fdr"} <= set(t.columns)


def test_piso_del_factor_hace_el_test_conservador():
    """Con autocorrelación negativa (oscilación) el factor de Hamed-Rao baja de 1; con piso 1 el p no baja."""
    rng = np.random.default_rng(11)
    x = np.tile([1.0, -1.0, 0.8, -0.9], 12) + rng.normal(0, 0.2, 48) + 0.01 * np.arange(48)
    libre = tendencias.mann_kendall(x, correccion="hamed_rao")
    conservador = tendencias.mann_kendall(x, correccion="hamed_rao", factor_minimo=1)
    original = tendencias.mann_kendall(x, correccion="ninguna")
    assert libre.n_efectivo_factor < 1
    assert conservador.p == pytest.approx(original.p)
    assert libre.p < conservador.p


def test_pettitt_sin_tendencia_no_confunde_tendencia_con_salto():
    rng = np.random.default_rng(2)
    rampa = 0.05 * np.arange(45) + rng.normal(0, 0.2, 45)
    assert tendencias.pettitt(rampa)[1] < 0.05                 # con tendencia "encuentra" un cambio
    assert tendencias.pettitt_sin_tendencia(rampa)[1] > 0.05   # sin tendencia, no hay salto
