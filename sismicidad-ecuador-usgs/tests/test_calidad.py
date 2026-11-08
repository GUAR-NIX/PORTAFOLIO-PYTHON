"""Calidad y homogeneización de magnitudes con datos pequeños y con la muestra versionada."""
import pandas as pd
import pytest

from sismos import config
from sismos.calidad import a_mw, asignar_zona, familia_magnitud, limpiar
from conftest import GRABADAS


def crudo(**cambios):
    base = pd.read_csv(GRABADAS / "ecuador_2016-04-16_2016-04-23.csv")
    for k, v in cambios.items():
        base[k] = v
    return base


@pytest.mark.parametrize("tipo, familia", [("mww", "Mw"), ("mwc", "Mw"), ("mb", "mb"), ("ms_20", "Ms"),
                                           ("ml", "Local"), ("md", "Local"), (None, "Desconocida")])
def test_familia_magnitud(tipo, familia):
    assert familia_magnitud(tipo) == familia


def test_conversion_scordilis():
    mag = pd.Series([5.0, 4.0, 7.0, 6.5])
    fam = pd.Series(["mb", "Ms", "Ms", "Mw"])
    mw, fuera = a_mw(mag, fam)
    assert mw.round(3).tolist() == [0.85 * 5 + 1.03, 0.67 * 4 + 2.07, 0.99 * 7 + 0.08, 6.5]
    assert not fuera.any()
    assert a_mw(pd.Series([3.0]), pd.Series(["mb"]))[1].iloc[0]   # mb 3,0 está fuera de rango


def test_limpiar_semana_real():
    df, inf = limpiar(crudo())
    assert inf["filas_crudas"] == len(df) == 67
    assert df["tiempo"].is_monotonic_increasing
    assert df["mw"].max() == 7.8                    # Pedernales conserva su Mww
    assert set(df["familia_mag"]) <= {"Mw", "mb", "Ms", "Local", "Desconocida"}
    mb = df[df["familia_mag"] == "mb"]
    assert ((mb["mw_continua"] - (0.85 * mb["mag_original"] + 1.03)).abs() <= 0.0426).all()


def test_limpiar_quita_duplicados_tipos_y_casi_duplicados():
    base = crudo()
    repetido = base.iloc[[0]]
    casi = base.iloc[[1]].assign(id="otro_id", magType="mb")    # mismo sismo, otra red
    explosion = base.iloc[[2]].assign(id="exp1", type="quarry blast")
    df, inf = limpiar(pd.concat([base, repetido, casi, explosion], ignore_index=True))
    assert inf["duplicados_por_id"] == 1
    assert inf["casi_duplicados"] == 1
    assert inf["tipos_evento"]["quarry blast"] == 1
    assert len(df) == 67


def test_profundidad_fija_se_marca():
    base = crudo()
    base.loc[0, ["depth", "depthError"]] = [10.0, None]
    df, inf = limpiar(base)
    assert inf["profundidad_fija"] >= 1


def test_asignar_zona():
    df = pd.DataFrame({"latitud": [0.0, -33.0, 0.0], "longitud": [-80.0, -72.0, 0.0]})
    zona = asignar_zona(df, config.ZONAS_CINTURON)
    assert zona.tolist()[:2] == ["Ecuador", "Chile centro-sur"] and pd.isna(zona.iloc[2])


def test_muestra_versionada_coherente():
    """La muestra pequeña de data/muestra (para CI) tiene el mismo esquema que el catálogo procesado."""
    muestra = config.MUESTRA / "catalogo_ecuador_muestra.csv"
    if not muestra.exists():
        pytest.skip("falta la muestra (ejecuta el pipeline)")
    m = pd.read_csv(muestra)
    assert {"id", "tiempo", "mw", "profundidad_km", "familia_mag"} <= set(m.columns)
    assert m["mw"].between(2, 9).all()
