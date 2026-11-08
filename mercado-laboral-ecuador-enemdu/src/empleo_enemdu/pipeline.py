"""Orquestador completo del pipeline de mercado laboral del Ecuador (INEC ENEMDU 2025)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from empleo_enemdu.config import (
    DIR_FIGURAS,
    DIR_MUESTRA,
    DIR_PROCESADOS,
    DIR_RAW,
    DIR_REPORTS,
    DIR_TABLAS,
    RAIZ,
)
from empleo_enemdu.descarga import descargar_todo
from empleo_enemdu.desigualdad import analizar_desigualdad_y_pobreza
from empleo_enemdu.encuesta import DisenoMuestralENEMDU
from empleo_enemdu.graficos import generar_todas_las_figuras
from empleo_enemdu.indicadores import (
    calcular_indicadores_nacionales_y_area,
    contrastes_hipotesis_complejos,
    reconciliar_con_tabulados_inec,
    resumen_ingresos_por_sector,
    resumen_por_provincia,
    resumen_por_rama_actividad,
    resumen_por_subgrupos,
)
from empleo_enemdu.limpieza import (
    cargar_tabulados_oficiales_inec,
    cargar_y_limpiar_microdatos,
    guardar_datos_procesados,
    leer_referencia_oficial_pobreza,
)
from empleo_enemdu.mincer import estimar_modelos_mincer
from empleo_enemdu.oaxaca import brecha_cuantilica_genero, descomposicion_oaxaca_blinder


def _ruta_relativa(ruta: str | Path) -> str:
    """Expresa una ruta respecto a la raíz del proyecto, con separadores POSIX."""
    return Path(ruta).resolve().relative_to(RAIZ.resolve()).as_posix()


def ejecutar_pipeline(
    *,
    sin_descarga: bool = False,
    forzar_descarga: bool = False,
    n_boot_oaxaca: int = 120,
) -> dict[str, Any]:
    """Ejecuta de punta a punta la ingesta, reconciliación, econometría y figuras."""
    t0 = time.perf_counter()
    DIR_REPORTS.mkdir(parents=True, exist_ok=True)
    DIR_TABLAS.mkdir(parents=True, exist_ok=True)
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)

    if not sin_descarga or not (DIR_RAW / "BDDenemdu_personas_2025_anual.csv").exists():
        print("1/8 · Verificando/descargando paquetes oficiales del INEC (ENEMDU 2025)...")
        descargar_todo(DIR_RAW, forzar=forzar_descarga)
    else:
        print("1/8 · Usando microdatos ya presentes en data/raw/...")

    print("2/8 · Cargando y limpiando microdatos (334.786 personas) y tabulados oficiales...")
    df, informe_calidad = cargar_y_limpiar_microdatos(DIR_RAW)
    df_serie, df_oficial_2025 = cargar_tabulados_oficiales_inec(DIR_RAW)
    rutas_procesados = guardar_datos_procesados(
        df,
        df_serie,
        df_oficial_2025,
        dir_procesados=DIR_PROCESADOS,
        dir_muestra=DIR_MUESTRA,
    )

    print("3/8 · Declarando diseño muestral complejo (estrato, upm, fexp) y reconciliando con INEC...")
    diseno = DisenoMuestralENEMDU.desde_dataframe(df)
    df_calc = calcular_indicadores_nacionales_y_area(df, diseno)
    df_reconciliacion = reconciliar_con_tabulados_inec(df_calc, df_oficial_2025)
    contrastes = contrastes_hipotesis_complejos(df, diseno)

    print("4/8 · Calculando radiografía de las 24 provincias, subgrupos demográficos y ramas CIIU...")
    df_prov = resumen_por_provincia(df, diseno)
    df_subgrupos = resumen_por_subgrupos(df)
    df_ramas = resumen_por_rama_actividad(df)
    res_ingresos_sector = resumen_ingresos_por_sector(df)

    print("5/8 · Estimando ecuaciones salariales de Mincer (WLS + errores agrupados por UPM)...")
    res_mincer = estimar_modelos_mincer(df)

    print("6/8 · Ejecutando descomposición de Kitagawa-Oaxaca-Blinder y brechas cuantílicas...")
    res_oaxaca = descomposicion_oaxaca_blinder(df, n_boot=n_boot_oaxaca)
    df_cuantiles = brecha_cuantilica_genero(df)

    print("7/8 · Calculando curvas de Lorenz, Gini, Palma y simulación contrafactual de pobreza...")
    res_desig = analizar_desigualdad_y_pobreza(df, diseno)
    res_desig["referencia_oficial_inec"] = leer_referencia_oficial_pobreza(DIR_RAW)

    print("8/8 · Exportando tablas CSV, 10 figuras editoriales y reports/resultados.json...")
    df_reconciliacion.to_csv(DIR_TABLAS / "reconciliacion_inec_2025.csv", index=False, encoding="utf-8")
    df_prov.to_csv(DIR_TABLAS / "indicadores_provincias_2025.csv", index=False, encoding="utf-8")
    df_subgrupos.to_csv(DIR_TABLAS / "indicadores_subgrupos_2025.csv", index=False, encoding="utf-8")
    df_ramas.to_csv(DIR_TABLAS / "indicadores_ramas_ciiu_2025.csv", index=False, encoding="utf-8")
    df_cuantiles.to_csv(DIR_TABLAS / "brecha_cuantilica_genero_2025.csv", index=False, encoding="utf-8")

    rutas_figuras = generar_todas_las_figuras(
        df=df,
        df_reconciliacion=df_reconciliacion,
        df_serie=df_serie,
        df_prov=df_prov,
        df_subgrupos=df_subgrupos,
        df_ramas=df_ramas,
        res_ingresos_sector=res_ingresos_sector,
        res_mincer=res_mincer,
        res_oaxaca=res_oaxaca,
        df_cuantiles=df_cuantiles,
        res_desig=res_desig,
        dir_figuras=DIR_FIGURAS,
    )

    resultados: dict[str, Any] = {
        "proyecto": "PYTHON_06_empleo_enemdu",
        "fuente": "INEC - Encuesta Nacional de Empleo, Desempleo y Subempleo (ENEMDU Anual 2025 y serie 2018-2025)",
        "tiempo_ejecucion_seg": round(time.perf_counter() - t0, 2),
        "calidad_y_diseno": informe_calidad,
        "reconciliacion_nacional_2025": df_reconciliacion.loc[
            df_reconciliacion["dominio"] == "Total"
        ].to_dict(orient="records"),
        "resumen_reconciliacion": {
            "celdas_evaluadas": int(len(df_reconciliacion)),
            "celdas_reconciliadas_ok": int(df_reconciliacion["reconcilia_ok"].sum()),
            "error_max_indicador_pp": round(float(df_reconciliacion["dif_indicador_pp"].abs().max()), 3),
            "error_max_ee_pp": round(float(df_reconciliacion["dif_ee_pp"].abs().max()), 3),
        },
        "contrastes_hipotesis": contrastes,
        "provincias_2025": df_prov.to_dict(orient="records"),
        "subgrupos_2025": df_subgrupos.to_dict(orient="records"),
        "ramas_ciiu_2025": df_ramas.to_dict(orient="records"),
        "ingresos_por_sector_2025": res_ingresos_sector,
        "mincer": res_mincer,
        "oaxaca_blinder": res_oaxaca,
        "brecha_cuantilica": df_cuantiles.to_dict(orient="records"),
        "desigualdad_y_pobreza": res_desig,
        # Rutas relativas a la raíz del proyecto (sin rutas personales del equipo local)
        "archivos_generados": {
            **{clave: _ruta_relativa(ruta) for clave, ruta in rutas_procesados.items()},
            "figuras": [_ruta_relativa(ruta) for ruta in rutas_figuras],
        },
    }

    ruta_json = DIR_REPORTS / "resultados.json"
    ruta_json.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Pipeline completado en {resultados['tiempo_ejecucion_seg']:.1f} s -> {ruta_json}")
    return resultados


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline completo de PYTHON_06_empleo_enemdu.")
    parser.add_argument("--sin-descarga", action="store_true", help="No verificar descargas en red.")
    parser.add_argument("--forzar-descarga", action="store_true", help="Re-descargar los ZIP del INEC.")
    args = parser.parse_args()
    ejecutar_pipeline(sin_descarga=args.sin_descarga, forzar_descarga=args.forzar_descarga)


if __name__ == "__main__":
    main()
