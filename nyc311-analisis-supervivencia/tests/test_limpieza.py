"""Limpieza, validación y construcción de la duración con censura."""

from __future__ import annotations

import pandas as pd
import pytest

from nyc311.limpieza import (
    agrupar_top,
    construir_duracion,
    limpiar,
    normalizar_borough,
    normalizar_zip,
    validar_tabla,
)

CORTE = "2026-10-26T01:36:17"


def fila(clave, creada, cerrada, estado="Closed", agencia="NYPD", tipo="Illegal Parking", zip_="10027",
         borough="MANHATTAN", canal="PHONE"):
    return {"unique_key": clave, "created_date": creada, "closed_date": cerrada, "agency": agencia,
            "complaint_type": tipo, "descriptor": "Blocked Hydrant", "status": estado, "incident_zip": zip_,
            "borough": borough, "open_data_channel_type": canal}


@pytest.fixture()
def crudo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            fila("1", "2025-01-01T10:00:00.000", "2025-01-01T12:00:00.000"),                    # normal: 2 h
            fila("1", "2025-01-01T10:00:00.000", "2025-01-01T12:00:00.000"),                    # duplicado
            fila("2", "2025-01-02T10:00:00.000", "2025-01-01T10:00:00.000"),                    # cierre antes de apertura
            fila("3", "2025-01-03T00:00:00.000", None),                                         # Closed sin fecha
            fila("4", "2026-10-01T00:00:00.000", None, estado="In Progress", agencia="HPD"),     # abierta: censurada
            fila("5", "2025-02-01T00:00:00.000", "2025-02-11T00:00:00.000", estado="Open"),     # reabierta: censurada
            fila("6", "2026-10-20T00:00:00.000", "2026-11-30T00:00:00.000"),                    # cierre tras el corte
            fila("7", "2025-03-01T08:00:00.000", "2025-03-01T08:00:00.000", borough="Unspecified",
                 zip_="10027-1234", canal="UNKNOWN"),                                           # instantánea
            fila("8", "fecha rota", None),                                                      # creación ilegible
            fila("9", "2025-04-01T00:00:00.000", "2025-04-08T00:00:00.000", zip_="90210", borough=" queens "),
        ]
    )


def test_reglas_de_limpieza_y_conteos(crudo: pd.DataFrame) -> None:
    df, inf = limpiar(crudo, CORTE)
    assert inf["filas_crudas"] == 10
    assert inf["duplicados_unique_key"] == 1
    assert inf["sin_fecha_creacion_valida"] == 1
    assert inf["cierre_antes_de_apertura"] == 1
    assert inf["cerradas_sin_fecha_cierre"] == 1
    assert inf["cierre_posterior_al_corte"] == 1
    assert inf["fecha_cierre_con_estado_abierto"] == 1
    assert sorted(df["unique_key"]) == [1, 4, 5, 6, 7, 9]
    assert inf["filas_limpias"] == 6 and inf["filas_descartadas"] == 4
    assert validar_tabla(df) == []


def test_duracion_y_censura_por_caso(crudo: pd.DataFrame) -> None:
    df = limpiar(crudo, CORTE)[0].set_index("unique_key")
    corte = pd.Timestamp(CORTE)
    assert df.loc[1, "evento"] == 1 and df.loc[1, "duracion_dias"] == pytest.approx(2 / 24)
    # Abierta al corte: censurada con la duración hasta el corte
    assert df.loc[4, "evento"] == 0
    assert df.loc[4, "duracion_dias"] == pytest.approx((corte - pd.Timestamp("2026-10-01")).total_seconds() / 86400)
    # Tiene fecha de cierre pero el estado dice abierta: manda el estado
    assert df.loc[5, "evento"] == 0 and pd.isna(df.loc[5, "cerrada"])
    # Cierre posterior al corte: todavía abierta en la fecha de corte
    assert df.loc[6, "evento"] == 0
    assert df.loc[6, "duracion_dias"] == pytest.approx((corte - pd.Timestamp("2026-10-20")).total_seconds() / 86400)
    # Cierre instantáneo: evento con duración 0, marcado
    assert df.loc[7, "evento"] == 1 and df.loc[7, "duracion_dias"] == 0 and df.loc[7, "cierre_instantaneo"] == 1


def test_categorias_normalizadas(crudo: pd.DataFrame) -> None:
    df = limpiar(crudo, CORTE)[0].set_index("unique_key")
    assert df.loc[7, "borough"] == "SIN DATO"
    assert df.loc[9, "borough"] == "QUEENS"
    assert df.loc[7, "zip"] == "10027"          # ZIP+4 recortado
    assert pd.isna(df.loc[9, "zip"])            # ZIP de California: fuera de NYC
    assert df.loc[7, "canal"] == "Otro/desconocido"
    assert df.loc[1, "canal"] == "Teléfono"


def test_construir_duracion_directa() -> None:
    creada = pd.Series(pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:00", "2025-01-01 00:00"]))
    cerrada = pd.Series(pd.to_datetime(["2025-01-03 12:00", None, "2025-01-10 00:00"]))
    estado = pd.Series(["Closed", "Open", "Closed"])
    r = construir_duracion(creada, cerrada, estado, pd.Timestamp("2025-01-05"))
    assert r["evento"].tolist() == [1, 0, 0]
    assert r["duracion_dias"].tolist() == pytest.approx([2.5, 4.0, 4.0])


def test_normalizadores() -> None:
    z = normalizar_zip(pd.Series(["10001", "11697", "11698", "1000", "N/A", None, "11201-0001", "09999"]))
    assert z.isna().tolist() == [False, False, True, True, True, True, False, True]
    assert z.iloc[6] == "11201"
    b = normalizar_borough(pd.Series(["Bronx", "STATEN  ISLAND", "Unspecified", None]))
    assert b.tolist() == ["BRONX", "STATEN ISLAND", "SIN DATO", "SIN DATO"]


def test_agrupar_top() -> None:
    s = pd.Series(list("aaabbc"))
    assert agrupar_top(s, 2).tolist() == ["a", "a", "a", "b", "b", "Otros"]


def test_validar_tabla_detecta_problemas(crudo: pd.DataFrame) -> None:
    df = limpiar(crudo, CORTE)[0]
    roto = df.copy()
    roto.loc[0, "duracion_dias"] = -1.0
    roto = pd.concat([roto, roto.iloc[[1]]])
    problemas = validar_tabla(roto)
    assert "duraciones negativas" in problemas and "unique_key duplicado" in problemas


def test_ruta_arrow_da_lo_mismo_que_la_ruta_de_texto(crudo: pd.DataFrame, tmp_path) -> None:
    """`cargar_crudo` convierte fechas e id en Arrow para ahorrar RAM: el resultado debe ser idéntico."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from nyc311.limpieza import cargar_crudo

    tabla = pa.Table.from_pandas(crudo.astype("string"), preserve_index=False)
    for col in ["agency", "complaint_type", "status", "borough", "incident_zip", "open_data_channel_type"]:
        tabla = tabla.set_column(tabla.column_names.index(col), col, tabla.column(col).dictionary_encode())
    ruta = tmp_path / "crudo.parquet"
    pq.write_table(tabla, ruta)
    desde_arrow, inf_arrow = limpiar(cargar_crudo(ruta), CORTE)
    desde_texto, inf_texto = limpiar(crudo, CORTE)
    assert inf_arrow == inf_texto
    columnas = ["unique_key", "estado", "agencia", "borough", "zip", "canal", "duracion_dias", "evento"]
    pd.testing.assert_frame_equal(
        desde_arrow[columnas].astype({c: "string" for c in ["estado", "agencia", "borough", "zip", "canal"]}),
        desde_texto[columnas].astype({c: "string" for c in ["estado", "agencia", "borough", "zip", "canal"]}),
    )
