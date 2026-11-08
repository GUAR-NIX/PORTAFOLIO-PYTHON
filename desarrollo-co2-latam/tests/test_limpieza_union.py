"""Lectura de las fuentes, cobertura y unión por ISO3."""
import json

import numpy as np
import pandas as pd
import pytest

from desarrollo_co2 import config, descarga, limpieza, union


def _registro(iso3, anio, codigo, valor, nombre="X"):
    """Misma forma que devuelve la API v2 del Banco Mundial."""
    return {"indicator": {"id": codigo, "value": "..."}, "country": {"id": iso3[:2], "value": nombre},
            "countryiso3code": iso3, "date": str(anio), "value": valor, "unit": "", "obs_status": "", "decimal": 0}


def test_leer_bm_json_convierte_tipos_y_conserva_nulos(tmp_path):
    ruta = tmp_path / "bm.json"
    ruta.write_text(json.dumps([_registro("ECU", 2020, "SP.POP.TOTL", 17_588_595),
                                _registro("VEN", 2020, "SP.POP.TOTL", None, "Venezuela, RB")]), encoding="utf-8")
    df = limpieza.leer_bm_json(ruta)
    assert df["anio"].dtype.kind == "i"
    assert df.loc[df["iso3"] == "ECU", "valor"].item() == 17_588_595
    assert np.isnan(df.loc[df["iso3"] == "VEN", "valor"].item())   # el nulo no se pierde ni se imputa


def test_bm_a_ancho_renombra_y_crea_columnas_vacias():
    largo = pd.DataFrame({"iso3": ["ECU", "ECU"], "anio": [2020, 2021],
                          "indicador": ["SP.POP.TOTL", "SP.POP.TOTL"], "valor": [1.0, 2.0]})
    ancho = limpieza.bm_a_ancho(largo)
    assert list(ancho.columns) == ["iso3", "anio", *config.INDICADORES_BM.values()]
    assert ancho["poblacion_bm"].tolist() == [1.0, 2.0]
    assert ancho["pib_ppa"].isna().all()


def test_bm_a_ancho_rechaza_duplicados():
    largo = pd.DataFrame({"iso3": ["ECU", "ECU"], "anio": [2020, 2020],
                          "indicador": ["SP.POP.TOTL"] * 2, "valor": [1.0, 2.0]})
    with pytest.raises(ValueError, match="repetidas"):
        limpieza.bm_a_ancho(largo)


def test_leer_owid_descarta_agregados_sin_iso(tmp_path):
    cols = ["iso_code", "year", *config.COLUMNAS_OWID]
    filas = [["ECU", 2020] + [1.0] * len(config.COLUMNAS_OWID),
             [None, 2020] + [9.0] * len(config.COLUMNAS_OWID),        # "World": sin código ISO
             ["ECU", 1950] + [1.0] * len(config.COLUMNAS_OWID)]       # fuera del rango de años
    ruta = tmp_path / "owid.csv"
    pd.DataFrame(filas, columns=cols).to_csv(ruta, index=False)
    df = limpieza.leer_owid(ruta)
    assert len(df) == 1 and df["iso3"].item() == "ECU" and "co2_mt" in df


@pytest.mark.parametrize("anios, esperado", [
    ([1990, 1991, 1992, 1995], "1990–1992, 1995"),
    ([2001], "2001"),
    ([], ""),
    ([2003, 2001, 2002, 2002], "2001–2003"),
])
def test_rangos_compactos(anios, esperado):
    assert limpieza.rangos_compactos(anios) == esperado


def test_cobertura_lista_anios_faltantes():
    panel = pd.DataFrame({"iso3": ["ECU"] * 5, "anio": range(2000, 2005), "v": [1, None, None, 4, 5]})
    cob = limpieza.cobertura(panel, ["v"], anio_inicio=2000, anio_fin=2004).iloc[0]
    assert cob["pct_completo"] == 60.0
    assert cob["anios_faltantes"] == "2001–2002"


def test_unir_por_iso3_y_detectar_filas_huerfanas():
    bm = pd.DataFrame({"iso3": ["ECU", "VEN"], "anio": [2020, 2020], "pib_ppa": [1.0, np.nan]})
    owid = pd.DataFrame({"iso3": ["ECU", "VEN", "ECU"], "anio": [2020, 2020, 2021], "co2_mt": [40.0, 90.0, 38.0]})
    p = union.unir(bm, owid)
    assert len(p) == 3
    assert p.loc[(p["iso3"] == "ECU") & (p["anio"] == 2021), "origen"].item() == "solo_owid"
    assert p.loc[p["iso3"] == "VEN", "pais"].iloc[0] == "Venezuela"   # nombre en español desde el ISO3


def test_unir_falla_si_una_fuente_tiene_filas_repetidas():
    bm = pd.DataFrame({"iso3": ["ECU", "ECU"], "anio": [2020, 2020], "pib_ppa": [1.0, 2.0]})
    owid = pd.DataFrame({"iso3": ["ECU"], "anio": [2020], "co2_mt": [40.0]})
    with pytest.raises(pd.errors.MergeError):
        union.unir(bm, owid)


def test_agregado_regional_no_suma_con_huecos(panel_sintetico):
    p = panel_sintetico.copy()
    p.loc[(p["iso3"] == "CCC") & (p["anio"] == 2005), "co2_mt"] = np.nan
    reg = union.agregado_regional(p, ["AAA", "BBB", "CCC"]).set_index("anio")
    assert np.isnan(reg.loc[2005, "co2_mt"])                       # falta un miembro: no hay total
    esperado = p[p["anio"] == 2004]["co2_mt"].sum()
    assert reg.loc[2004, "co2_mt"] == pytest.approx(esperado)


def test_miembros_region_exige_serie_completa(panel_sintetico):
    p = panel_sintetico.copy()
    p.loc[(p["iso3"] == "AAA") & (p["anio"] == 2003), "pib_ppa"] = np.nan
    assert union.miembros_region(p, 2000, 2010) == ["BBB", "CCC"]


def test_derivadas_unidades(panel_sintetico):
    d = union.agregar_derivadas(panel_sintetico.assign(pib_pc_ppa=np.nan, co2_consumo_mt=np.nan,
                                                       co2_petroleo_mt=np.nan)).iloc[0]
    assert d["co2_pc_t"] == pytest.approx(50e6 / 1e7)              # 5 t por persona
    assert d["intensidad_co2_kg_usd"] == pytest.approx(50e9 / 1e11)  # 0,5 kg por USD
    assert d["pib_pc_ppa"] == pytest.approx(1e11 / 1e7)


def test_url_indicador_varios_paises():
    url, params = descarga.url_indicador("SP.POP.TOTL", ["ECU", "COL"], 1990, 2024)
    assert url.endswith("/country/ECU;COL/indicator/SP.POP.TOTL")
    assert params["date"] == "1990:2024" and params["format"] == "json"


def test_completar_combustibles_solo_rellena_ceros_logicos():
    df = pd.DataFrame({
        "co2_mt": [10.0, 10.0],
        "co2_petroleo_mt": [9.0, 5.0], "co2_gas_mt": [np.nan, np.nan], "co2_carbon_mt": [np.nan, np.nan],
        "co2_cemento_mt": [1.0, 1.0], "co2_quema_mt": [0.0, np.nan],
    })
    r = limpieza.completar_combustibles(df)
    assert r.loc[0, "co2_gas_mt"] == 0          # 9 + 1 = 10: el vacío es un cero
    assert np.isnan(r.loc[1, "co2_gas_mt"])     # 5 + 1 ≠ 10: falta información, no se inventa
