"""Validación de la serie publicada por el INEC con microdatos de un año anterior (ENEMDU 2024).

La serie 2018–2025 de `serie_historica_2018_2025.csv` proviene del tabulado oficial del INEC;
no es un cálculo propio. Este módulo descarga los microdatos de otro año, aplica exactamente la
misma limpieza y el mismo motor de diseño muestral que para 2025, y compara las 80 celdas
(10 indicadores × 8 dominios) contra el valor publicado en la serie para ese año.

Uso:
    python -m empleo_enemdu.validacion_anual --anio 2024
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from empleo_enemdu.config import (
    DIR_PROCESADOS,
    DIR_RAW,
    DIR_REPORTS,
    DIR_TABLAS,
    URLS_MICRODATOS_VALIDACION,
)
from empleo_enemdu.descarga import descargar_archivo, extraer_zip
from empleo_enemdu.encuesta import DisenoMuestralENEMDU
from empleo_enemdu.indicadores import calcular_indicadores_nacionales_y_area
from empleo_enemdu.limpieza import cargar_y_limpiar_microdatos

TOLERANCIA_PP = 0.1  # La serie del INEC se publica redondeada a un decimal


def validar_anio_contra_serie(
    anio: int = 2024,
    *,
    dir_raw: Path = DIR_RAW,
    ruta_serie: Path = DIR_PROCESADOS / "serie_historica_2018_2025.csv",
    certificados: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calcula los indicadores del año con microdatos propios y los cruza con la serie del INEC."""
    url = URLS_MICRODATOS_VALIDACION[anio]
    dir_anio = dir_raw / str(anio)
    ruta_zip = dir_anio / url.rsplit("/", 1)[-1]
    info = descargar_archivo(url, ruta_zip, certificados=certificados)
    if not (dir_anio / f"BDDenemdu_personas_{anio}_anual.csv").exists():
        extraer_zip(ruta_zip, dir_anio)

    df, calidad = cargar_y_limpiar_microdatos(dir_anio, anio=anio)
    diseno = DisenoMuestralENEMDU.desde_dataframe(df)
    df_calc = calcular_indicadores_nacionales_y_area(df, diseno)

    serie = pd.read_csv(ruta_serie)
    oficial = serie.loc[serie["anio"].eq(anio), ["indicador", "dominio", "valor_pct"]]
    cruce = df_calc[["indicador", "dominio", "estimacion_pct", "ee_complejo_pct", "n_muestral"]].merge(
        oficial.rename(columns={"valor_pct": "serie_inec_pct"}),
        on=["indicador", "dominio"],
        how="inner",
    )
    cruce.insert(0, "anio", anio)
    cruce["dif_pp"] = (cruce["estimacion_pct"].round(1) - cruce["serie_inec_pct"]).round(2)
    cruce["coincide"] = cruce["dif_pp"].abs() <= TOLERANCIA_PP + 1e-9

    resumen = {
        "anio": anio,
        "url_microdatos": url,
        "sha256_zip": info["sha256"],
        "bytes_zip": info["bytes"],
        "personas": calidad["filas_totales_personas"],
        "upm": calidad["upm_unicas"],
        "estratos": calidad["estratos_unicos"],
        "celdas_comparadas": int(len(cruce)),
        "celdas_coinciden": int(cruce["coincide"].sum()),
        "dif_max_abs_pp": round(float(cruce["dif_pp"].abs().max()), 2),
        "tolerancia_pp": TOLERANCIA_PP,
        "nacional": {
            fila["indicador"]: {
                "calculado_pct": round(fila["estimacion_pct"], 2),
                "serie_inec_pct": fila["serie_inec_pct"],
            }
            for fila in cruce.loc[cruce["dominio"].eq("Total")].to_dict(orient="records")
        },
    }
    return cruce, resumen


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida la serie del INEC con microdatos de otro año.")
    parser.add_argument("--anio", type=int, default=2024, choices=sorted(URLS_MICRODATOS_VALIDACION))
    parser.add_argument(
        "--certificados",
        default=None,
        help="Solo si el certificado del INEC no se valida con el sistema: usa el paquete certifi o un .pem. "
        "Nunca desactiva la verificación.",
    )
    args = parser.parse_args()

    cruce, resumen = validar_anio_contra_serie(args.anio, certificados=args.certificados)
    DIR_TABLAS.mkdir(parents=True, exist_ok=True)
    cruce.to_csv(DIR_TABLAS / f"validacion_microdatos_{args.anio}.csv", index=False, encoding="utf-8")
    ruta_json = DIR_REPORTS / f"validacion_microdatos_{args.anio}.json"
    ruta_json.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{args.anio}: {resumen['celdas_coinciden']}/{resumen['celdas_comparadas']} celdas coinciden "
        f"con la serie del INEC (dif. máx. {resumen['dif_max_abs_pp']} pp) -> {ruta_json.name}"
    )


if __name__ == "__main__":
    main()
