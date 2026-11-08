import numpy as np
import pandas as pd
import pytest

from clima_ecuador import agregacion, calidad, config, descarga


def horario_sintetico(dias=3):
    horas = pd.date_range("2001-01-01", periods=24 * (dias + 1), freq="h")
    temp = 10 + 5 * np.sin(2 * np.pi * (horas.hour.to_numpy() - 10) / 24)     # UTC
    return pd.DataFrame({"punto": "Quito", "hora_utc": horas, "temp": temp.astype("float32"),
                         "punto_rocio": (temp - 3).astype("float32"), "precip": 0.5, "radiacion": 100.0,
                         "viento_u": 3.0, "viento_v": 4.0, "rafagas": 10.0})


def celdas(altitud=2850, altitud_celda=3150, region="Sierra"):
    return pd.DataFrame({"punto": ["Quito"], "region": [region], "altitud": [altitud],
                         "altitud_celda": [altitud_celda]})


def test_humedad_relativa_magnus():
    assert agregacion.humedad_relativa(np.array([20.0]), np.array([20.0]))[0] == pytest.approx(100)
    assert agregacion.humedad_relativa(np.array([25.0]), np.array([15.0]))[0] == pytest.approx(53.9, abs=0.5)


def test_correccion_por_altitud_y_viento():
    h = agregacion.variables_derivadas(horario_sintetico(), celdas())
    # la ciudad está 300 m más abajo que la celda -> +1,95 °C
    assert (h["temp"] - h["temp_celda"]).iloc[0] == pytest.approx(1.95, abs=1e-4)
    assert h["viento"].iloc[0] == pytest.approx(5 * 3.6)
    assert (h["hora_local"] - h["hora_utc"]).iloc[0] == pd.Timedelta(hours=-5)


def test_galapagos_usa_utc_menos_6():
    h = agregacion.variables_derivadas(horario_sintetico(), celdas(region="Galápagos"))
    assert (h["hora_local"] - h["hora_utc"]).iloc[0] == pd.Timedelta(hours=-6)


def test_diario_en_hora_local_con_24_horas():
    h = agregacion.variables_derivadas(horario_sintetico(dias=3), celdas())
    d = agregacion.a_diario(h, 2000, 2002)
    # el primer día local (31-12-2000) está incompleto: empieza a las 19:00 locales -> se descarta
    assert d["fecha"].min() == pd.Timestamp("2001-01-01")
    fila = d.iloc[0]
    assert fila["precip"] == pytest.approx(12.0)                          # 24 × 0,5 mm
    assert fila["radiacion"] == pytest.approx(100 * 24 * 3600 / 1e6, abs=0.01)
    assert fila["tmin"] <= fila["tmed"] <= fila["tmax"]
    assert fila["tmax"] - fila["tmin"] == pytest.approx(10, abs=0.2)


def test_lluvia_diaria_suma_de_01_a_24_horas():
    """La lluvia de la hora t es la de la hora que termina en t: la de las 00:00 pertenece al día anterior."""
    h = agregacion.variables_derivadas(horario_sintetico(dias=3), celdas())
    h["precip"] = 0.0
    medianoche = h["hora_local"] == pd.Timestamp("2001-01-02 00:00")
    h.loc[medianoche, "precip"] = 7.0
    d = agregacion.a_diario(h, 2000, 2002).set_index("fecha")
    assert d.loc["2001-01-01", "precip"] == pytest.approx(7.0)
    assert d.loc["2001-01-02", "precip"] == pytest.approx(0.0)


def test_mensual_exige_90_por_ciento_de_dias(diario_sintetico):
    f = diario_sintetico["fecha"]
    d = diario_sintetico[~((f.dt.year == 1990) & (f.dt.month == 5) & (f.dt.day <= 5))]
    m = agregacion.a_mensual(d)
    indexado = m.set_index("mes")
    assert np.isnan(indexado.loc["1990-05-01", "tmed"])      # 26 de 31 días
    assert not np.isnan(indexado.loc["1990-06-01", "tmed"])
    a = agregacion.a_anual(m)
    assert 1990 not in a["anio"].tolist() and len(a) == 39


def test_controles_detectan_problemas():
    h = agregacion.variables_derivadas(horario_sintetico(dias=5), celdas())
    roto = h.drop(index=[10, 11]).copy()
    roto.loc[20, "temp"] = 80
    assert calidad.huecos_tiempo(roto)["saltos"].sum() == 1
    assert calidad.fuera_de_rango(roto).set_index("variable").loc["temp", "fuera"] == 1
    pegado = h.copy()
    pegado.loc[:30, "temp"] = 12.0
    assert calidad.valores_pegados(pegado)["rachas_pegadas"].sum() == 1


def test_bloques_cubren_el_periodo():
    b = descarga.bloques(1980, 2024)
    assert b[0]["nombre"] == "year_1980" and b[41]["nombre"] == "year_2021"
    trozos = b[42:]
    assert trozos[0]["inicio"] <= pd.Timestamp("2022-01-01")
    fin = trozos[-1]["inicio"] + pd.Timedelta(hours=config.HORAS_POR_TROZO)
    assert fin >= pd.Timestamp("2025-01-01 07:00")
    assert descarga.indice_malla(-0.25, -78.5) == (359, 406)
