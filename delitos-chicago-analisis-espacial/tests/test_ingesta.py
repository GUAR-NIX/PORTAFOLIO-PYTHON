"""Pruebas de la ingesta con DuckDB sobre CSV pequeños con los problemas reales del portal."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from delitos_chicago import ingesta
from delitos_chicago.ingesta import BBOX_CHICAGO, auditar_y_limpiar

ENCABEZADO = "ID,Case Number,Date,Block,IUCR,Primary Type,Description,Location Description,Arrest,Domestic,Beat,District,Ward,Community Area,FBI Code,X Coordinate,Y Coordinate,Year,Latitude,Longitude"


def _fila(id_: int, fecha: str, tipo: str, lat: str, lon: str, anio: int) -> str:
    return f"{id_},JA{id_},{fecha},001XX N STATE ST,0820,{tipo},X,STREET,false,true,111,1,42,32,06,1176000,1900000,{anio},{lat},{lon}"


def test_auditar_y_limpiar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "crimes_2019.csv").write_text("\n".join([
        ENCABEZADO,
        _fila(1, "01/15/2019 10:30:00 PM", "theft ", "41.88", "-87.63", 2019),
        _fila(2, "02/01/2019 01:00:00 AM", "BATTERY", "", "", 2019),  # sin coordenadas
        _fila(3, "03/01/2019 12:00:00 AM", "THEFT", "0.0", "0.0", 2019),  # fuera de Chicago
    ]) + "\n", encoding="utf-8")
    (raw / "crimes_2020.csv").write_text("\n".join([
        ENCABEZADO,
        _fila(4, "2020-05-01T08:15:00.000", "ASSAULT", "41.80", "-87.70", 2020),
        _fila(1, "01/15/2019 10:30:00 PM", "THEFT", "41.88", "-87.63", 2019),  # id repetido entre archivos
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(ingesta, "REPORTES", tmp_path / "reports")

    calidad = auditar_y_limpiar(carpeta_raw=raw, destino=tmp_path / "procesados")
    assert calidad["total_registros_brutos"] == 5
    assert calidad["duplicados_id"] == 1
    assert calidad["total_registros_limpios"] == 4
    assert calidad["sin_coordenadas"] == 1
    assert calidad["coordenadas_fuera_chicago"] == 1
    assert calidad["fechas_invalidas"] == 0  # ambos formatos de fecha del portal se interpretan
    assert (tmp_path / "reports" / "calidad.json").exists()

    patron = (tmp_path / "procesados" / "delitos_parquet" / "**" / "*.parquet").as_posix()
    df = duckdb.sql(f"SELECT * FROM read_parquet('{patron}', hive_partitioning=true) ORDER BY id_delito").df()
    assert df["id_delito"].tolist() == [1, 2, 3, 4]
    assert df.loc[0, "tipo_primario"] == "THEFT"  # se normalizan mayúsculas y espacios
    assert df.loc[0, "fecha"].hour == 22
    assert sorted(df["anio"].unique()) == [2019, 2020]


def test_bbox_limites() -> None:
    assert BBOX_CHICAGO["lat_min"] < BBOX_CHICAGO["lat_max"]
    assert BBOX_CHICAGO["lon_min"] < BBOX_CHICAGO["lon_max"]
