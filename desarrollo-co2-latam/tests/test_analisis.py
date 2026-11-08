"""Desacople, descomposición de Kaya y curva de Kuznets sobre datos con respuesta conocida."""
import numpy as np
import pandas as pd
import pytest

from desarrollo_co2 import desacople, kaya, kuznets


@pytest.mark.parametrize("pib, co2, esperado", [
    (3.0, -1.0, "Absoluto"),
    (3.0, 1.0, "Relativo"),
    (3.0, 3.0, "Sin desacople"),
    (2.0, 4.0, "Sin desacople"),
    (-1.0, -2.0, "Recesión"),          # bajar emisiones en una recesión no es desacople
    (np.nan, 1.0, "Sin datos"),
])
def test_clasificar(pib, co2, esperado):
    assert desacople.clasificar(pib, co2) == esperado


@pytest.mark.parametrize("pib, co2, esperado", [
    (3.0, -1.0, "Desacople fuerte"),
    (3.0, 1.5, "Desacople débil"),
    (3.0, 2.9, "Acoplamiento expansivo"),   # elasticidad 0,97: la etiqueta OCDE diría "relativo"
    (3.0, 4.5, "Desacople negativo expansivo"),
    (-2.0, 1.0, "Desacople negativo fuerte"),
    (-2.0, -4.0, "Desacople recesivo"),
])
def test_clasificar_tapio(pib, co2, esperado):
    assert desacople.clasificar_tapio(pib, co2) == esperado


def test_tasa_anual():
    assert desacople.tasa_anual(100, 121, 2) == pytest.approx(10.0)
    assert np.isnan(desacople.tasa_anual(0, 10, 5))


def test_extremos_promedian_y_exigen_datos_completos():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=range(2000, 2005))
    assert desacople.extremos(s, 2000, 2004, ventana=3) == (2.0, 4.0)
    s[2003] = np.nan
    assert np.isnan(desacople.extremos(s, 2000, 2004, ventana=3)[1])


def test_tabla_desacople_recupera_tasas_y_categorias(panel_sintetico):
    t = desacople.tabla_desacople(panel_sintetico, 2000, 2010, ventana=3).set_index("iso3")
    assert t.loc["AAA", "categoria"] == "Absoluto"
    assert t.loc["BBB", "categoria"] == "Relativo"
    assert t.loc["CCC", "categoria"] == "Sin desacople"
    # con crecimiento constante, el promedio de 3 años no sesga la tasa más allá de redondeos
    assert t.loc["AAA", "crec_pib_anual"] == pytest.approx(4.0, abs=0.01)
    assert t.loc["BBB", "elasticidad"] == pytest.approx(0.5, abs=0.01)


def test_desacople_movil_cubre_todas_las_ventanas(panel_sintetico):
    m = desacople.desacople_movil(panel_sintetico, ventana_anios=5)
    assert sorted(m["fin"].unique()) == list(range(2005, 2011))
    assert (m.query("iso3 == 'AAA'")["categoria"] == "Absoluto").all()


def test_media_logaritmica():
    assert kaya.media_logaritmica(5, 5) == 5
    assert kaya.media_logaritmica(2, 1) == pytest.approx(1 / np.log(2))


def test_lmdi_sin_residuo(panel_sintetico):
    t = kaya.descomponer(panel_sintetico, "BBB", 2000, 2010).set_index("factor")["mt"]
    assert t.drop("Cambio total").sum() == pytest.approx(t["Cambio total"], rel=1e-12)


def test_lmdi_con_ventana_sin_residuo(panel_sintetico):
    t = kaya.descomponer(panel_sintetico, "CCC", 2000, 2010, ventana=3).set_index("factor")["mt"]
    assert t.drop("Cambio total").sum() == pytest.approx(t["Cambio total"], rel=1e-12)


def test_punto_giro():
    assert kuznets.punto_giro(2.0, -0.1) == pytest.approx(np.exp(10))
    assert np.isnan(kuznets.punto_giro(2.0, 0.1))          # U normal: no hay máximo
    assert kuznets.punto_giro(1.0, -1e-6) == np.inf        # giro absurdo: no desborda


def _panel_cka(b1=8.0, b2=-0.4, paises=12, anios=25, ruido=0.02, semilla=0):
    """Panel con una U invertida conocida: giro en exp(10) ≈ 22.026 USD."""
    rng = np.random.default_rng(semilla)
    filas = []
    for i in range(paises):
        x0 = rng.uniform(7.5, 9.5)
        efecto = rng.normal(0, 0.3)
        for k in range(anios):
            x = x0 + 0.03 * k
            y = efecto + b1 * x + b2 * x ** 2 + rng.normal(0, ruido)
            filas.append({"iso3": f"P{i:02d}", "pais": f"P{i:02d}", "anio": 2000 + k,
                          "pib_pc_ppa": np.exp(x), "co2_pc_t": np.exp(y)})
    return pd.DataFrame(filas)


def test_kuznets_recupera_punto_de_giro_conocido():
    d = kuznets.preparar(_panel_cka())
    m = kuznets.ajustar(d, "fe_pais")
    assert m.params["x2"] == pytest.approx(-0.4, abs=0.02)
    assert kuznets.punto_giro(m.params["x"], m.params["x2"]) == pytest.approx(np.exp(10), rel=0.1)


def test_bootstrap_punto_giro_reproducible():
    d = kuznets.preparar(_panel_cka())
    a = kuznets.bootstrap_punto_giro(d, repeticiones=50, efecto_anio=False, semilla=1)
    b = kuznets.bootstrap_punto_giro(d, repeticiones=50, efecto_anio=False, semilla=1)
    assert a["giro_mediana"] == b["giro_mediana"]
    assert a["pct_u_invertida"] == 100
    assert a["giro_p05"] < np.exp(10) < a["giro_p95"]
