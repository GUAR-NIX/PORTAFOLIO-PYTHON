"""Estimadores con datos simulados de parámetros conocidos (Gutenberg-Richter, Omori, retorno, declustering)."""
import numpy as np
import pandas as pd
import pytest

from sismos import gutenberg_richter as gr
from sismos import omori, retorno
from sismos.desagrupar import gardner_knopoff, ventana_gk


@pytest.mark.parametrize("b_real", [0.8, 1.0, 1.3])
def test_valor_b_aki_recupera_b_simulado(b_real):
    m = gr.simular_gr(20_000, b_real, mc=4.0, semilla=1)
    aj = gr.valor_b_aki(m, 4.0, n_boot=200)
    assert abs(aj.b - b_real) < 0.04
    assert aj.ic95_bajo < b_real < aj.ic95_alto
    assert aj.ic95_boot_bajo < b_real < aj.ic95_boot_alto


def test_cobertura_del_ic95_de_shi_bolt():
    """En 200 catálogos simulados de 300 eventos, el IC 95 % debe contener al b real ~95 % de las veces."""
    aciertos = 0
    for semilla in range(200):
        aj = gr.valor_b_aki(gr.simular_gr(300, 1.0, 3.0, semilla=semilla), 3.0)
        aciertos += aj.ic95_bajo <= 1.0 <= aj.ic95_alto
    assert 0.90 <= aciertos / 200 <= 0.99


def test_mc_maxc_subestima_y_mbs_acierta_con_rampa_de_deteccion():
    """Catálogo completo desde 4,0 con detección que cae en rampa hasta 3,0: MAXC + 0,2 se queda corto
    (problema conocido de MAXC) y la estabilidad de b (MBS) encuentra el Mc real."""
    rng = np.random.default_rng(3)
    m = gr.simular_gr(30_000, 1.0, 3.0, semilla=3)
    detectado = rng.uniform(size=len(m)) < np.clip((m - 3.0) / 1.0, 0, 1)   # rampa de detección 3→4
    assert 3.5 <= gr.mc_maxc(m[detectado]) < 4.0
    assert 3.9 <= gr.mc_mbs(m[detectado]) <= 4.1
    assert abs(gr.valor_b_aki(m[detectado], 4.2).b - 1.0) < 0.06


def test_mc_mbs_en_catalogo_completo_es_bajo():
    m = gr.simular_gr(5_000, 1.0, 3.0, semilla=5)
    assert gr.mc_mbs(m) <= 3.3


def test_minimos_cuadrados_linea_base_existe_y_es_razonable():
    m = gr.simular_gr(20_000, 1.0, 3.0, semilla=2)
    b, a = gr.valor_b_minimos_cuadrados(m, 3.0)
    assert 0.8 < b < 1.2


def test_distribucion_acumulada():
    clases, acum = gr.distribucion_acumulada([4.0, 4.0, 4.1, 4.3])
    assert list(np.round(clases, 1)) == [4.0, 4.1, 4.2, 4.3]
    assert list(acum) == [4, 2, 1, 1]


def test_valor_b_falla_con_muy_pocos_eventos():
    with pytest.raises(ValueError):
        gr.valor_b_aki([5.0], 5.0)


def test_omori_utsu_recupera_parametros_simulados():
    t = omori.simular_omori(k=50, c=0.05, p=1.1, s=0, t=365, semilla=7)
    aj = omori.ajustar_omori_utsu(t, 0, 365)
    assert abs(aj["p"] - 1.1) < 2.5 * aj["se_p"] + 0.02
    assert 0.01 < aj["c"] < 0.2
    expo = omori.ajustar_exponencial(t, 0, 365)
    assert expo["aic"] > aj["aic"] + 10       # la línea base exponencial pierde con claridad


def test_omori_p1_es_caso_particular():
    t = omori.simular_omori(k=30, c=0.1, p=1.0, s=0, t=200, semilla=8)
    libre = omori.ajustar_omori_utsu(t, 0, 200)
    fijo = omori.ajustar_omori_utsu(t, 0, 200, p_fijo=1.0)
    assert fijo["p"] == 1.0
    assert fijo["log_verosimilitud"] <= libre["log_verosimilitud"] + 1e-6


def test_acumulado_omori_coincide_con_conteo_esperado():
    k, c, p = 20, 0.1, 1.0
    assert omori.acumulado_omori([10], k, c, p)[0] == pytest.approx(k * np.log(10.1 / 0.1))


def test_retorno_y_probabilidad():
    # 10 sismos por año con M≥5 y b=1 → 0,1 por año con M≥7 → 10 años
    assert retorno.tasa_anual(7, 10, 1.0, 5) == pytest.approx(0.1)
    assert retorno.probabilidad(0.1, 10) == pytest.approx(1 - np.exp(-1))
    e = retorno.tasa_empirica(16, 56)
    assert e["tasa_ic95"][0] < 16 / 56 < e["tasa_ic95"][1]
    filas = retorno.retorno_con_incertidumbre(gr.simular_gr(2000, 1.0, 5.0, semilla=1), 5.0, 100,
                                              objetivos=(7.0,), n_boot=200)
    assert filas[0]["periodo_ic95"][0] < 5 < filas[0]["periodo_ic95"][1]   # 2000/100·10^-2 = 0,2 por año → 5 años


def test_gardner_knopoff_quita_replicas_y_deja_independientes():
    t0 = pd.Timestamp("2016-04-16", tz="UTC")
    df = pd.DataFrame({
        "tiempo": [t0, t0 + pd.Timedelta(days=1), t0 + pd.Timedelta(days=30), t0 + pd.Timedelta(days=2000),
                   t0 + pd.Timedelta(days=2)],
        "latitud": [0.0, 0.2, -0.3, 0.0, -10.0],
        "longitud": [-80.0, -80.1, -80.2, -80.0, -80.0],
        "mw": [7.8, 5.0, 6.0, 5.5, 5.0],
    })
    principal = gardner_knopoff(df)
    assert principal.tolist() == [True, False, False, True, True]
    distancia, dias = ventana_gk([7.8, 5.0])
    assert distancia[0] > distancia[1] and dias[0] > dias[1]
