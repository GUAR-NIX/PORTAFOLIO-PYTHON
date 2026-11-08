# Guía paso a paso · Tiempos del 311 con análisis de supervivencia

Esta guía explica cómo correr el proyecto de punta a punta y cómo defenderlo en una entrevista para analista de datos.

## 1. Preparar el entorno (5 min)

```bash
python -m venv .venv
.venv\Scripts\activate             # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
pip install -e .                   # instala el paquete src/nyc311
pytest -q                          # las pruebas no necesitan red ni los datos completos
```

`lifelines` 0.30 se instala sin problemas en Python 3.14. El Kaplan-Meier y el log-rank del proyecto están
implementados en numpy y validados contra lifelines, así que funcionarían incluso sin esa librería.

## 2. Descargar los datos (~15 min)

```bash
python descargar_datos.py
```

* Pide a la API Socrata de NYC Open Data solo 10 columnas, un mes por tarea, en páginas de 50.000 filas
  ordenadas por `unique_key` (sin `$order`, `$offset` puede repetir o saltar filas).
* Cada página se guarda en `data/raw/paginas/AAAA-MM/`. Si se corta la luz, vuelve a ejecutar el mismo comando:
  se saltan las páginas existentes y los meses con `_completo.json`.
* La primera vez se crea `data/raw/manifiesto_descarga.json` con la **fecha de corte** (`{{fecha_corte}}`), que no
  cambia al reanudar.
* Resultado: `data/raw/nyc311_crudo.parquet` ({{filas_crudas}} filas).

## 3. Correr el análisis (~5 min)

```bash
python -m nyc311.pipeline          # limpieza → KM → sesgo → Cox → equidad → evolución → figuras
python -m nyc311.cifras_readme     # README y esta guía, con las cifras de reports/
```

Qué mirar en `reports/`:

| Archivo | Contenido |
| --- | --- |
| `resultados.json` | Calidad, cifras globales, sesgo, Cox, equidad y evolución |
| `tablas/km_*.csv` | Mediana KM con IC, % cerradas a 1/7/30 días, RMST y promedio ingenuo por grupo |
| `tablas/sesgo_corte_retrospectivo.csv` | El experimento que demuestra el sesgo del promedio |
| `tablas/cox_*.csv`, `supuesto_ph_*.csv` | Hazard ratios, prueba de Schoenfeld y HR por ventana |
| `tablas/equidad_*.csv` | O/E por borough y por ZIP |
| `tablas/curvas_km.parquet`, `resumen_app.csv` | Curvas precalculadas para figuras y app |

## 4. Notebooks y app

```bash
python scripts/crear_notebooks.py
jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
streamlit run app/streamlit_app.py
```

1. `01_ingesta_y_calidad`: manifiesto, reglas de limpieza, definición de evento y censura.
2. `02_kaplan_meier`: validación contra lifelines, experimento del sesgo, curvas y log-rank.
3. `03_cox`: modelos A y B, supuesto PH y lectura de negocio.
4. `04_hallazgos`: equidad territorial y evolución mensual.

En la app eliges un tipo de queja y uno o varios boroughs y ves su curva de supervivencia con banda del 95 %,
la mediana con su IC y el % cerrado a 1, 7 y 30 días.

## 5. Cómo contar el proyecto en 1 minuto

> «Analicé {{filas_limpias}} solicitudes al 311 de Nueva York para medir cuánto tarda la ciudad en resolverlas.
> Como hay solicitudes que siguen abiertas, usé análisis de supervivencia: Kaplan-Meier trata las abiertas como
> censuradas en lugar de ignorarlas. Demostré el sesgo con datos reales: fingiendo un corte antiguo, la mediana
> ingenua de Parques daba {{sesgo_dpr_ingenua}}, Kaplan-Meier {{sesgo_dpr_km}} y la verdad resultó {{sesgo_dpr_verdad}}. Con un modelo
> de Cox estratificado por tipo de queja encontré que el Bronx cierra más lento el primer día, pero no a la
> semana, y que el supuesto de riesgos proporcionales no se cumple, lo que cambia la lectura del hazard ratio.»

## 6. Preguntas de entrevista (con respuesta)

**1. ¿Qué es la censura y qué tipo de censura hay en este proyecto?**
Una observación está censurada cuando no vimos el evento, pero sí sabemos que no ocurrió antes de cierto tiempo.
Aquí es **censura por la derecha administrativa**: una solicitud abierta en la fecha de corte tardó *al menos*
`corte − creación`. Es «administrativa» porque solo la produce el corte de la descarga, no el abandono del caso;
por eso es razonable suponer que es **no informativa**, que es el supuesto central de Kaplan-Meier y Cox. Hay
{{censuradas_abiertas}} censuradas ({{pct_censuradas}} %), pero en Taxis y Limusinas (TLC) son el {{km_tlc_censura}} %.

**2. ¿Por qué no usar el promedio de las solicitudes cerradas?**
Porque descarta justamente las lentas (las que aún no cierran) y lo sesga hacia abajo; además, con una cola tan
larga, la media no representa el caso típico. En el experimento de corte retrospectivo, la mediana ingenua de
Edificios (DOB) era {{sesgo_dob_ingenua}}, pero la real fue {{sesgo_dob_verdad}}, y Kaplan-Meier, con los mismos datos
incompletos, daba {{sesgo_dob_km}}. Tratar las abiertas como cerradas en el corte también sesga: las acorta. Si se
necesita un «promedio», lo correcto es el **tiempo medio restringido (RMST)**, el área bajo la curva KM hasta un horizonte.

**3. ¿Cómo funciona Kaplan-Meier?**
En cada tiempo en que ocurre un evento, estima la probabilidad condicional de «sobrevivir» (seguir abierta) como
`1 − eventos / en riesgo` y multiplica esas probabilidades. Las censuradas cuentan en el conjunto en riesgo hasta su
tiempo de censura y luego salen sin bajar la curva. La varianza sale de la fórmula de Greenwood y el IC se calcula
en escala log(−log) para que no salga de [0, 1]. La mediana es el primer tiempo con S(t) ≤ 0,5; si la curva nunca
baja de 0,5, la mediana es «no alcanzada», como pasó con EDC en el corte ficticio.

**4. ¿Qué compara la prueba log-rank y por qué aquí todos los p-valores son ≈ 0?**
Compara, en cada tiempo con eventos, los cierres observados de cada grupo con los esperados si todos compartieran
la misma curva, y suma esas diferencias ponderadas (χ² con k − 1 grados de libertad). Con millones de solicitudes,
cualquier diferencia mínima es estadísticamente significativa. Por eso la prueba solo sirve para descartar el azar;
lo que importa para el negocio es el **tamaño**: medianas, % cerrado a 7 días y hazard ratios.

**5. Kaplan-Meier frente a Cox: ¿cuándo usar cada uno?**
Kaplan-Meier es descriptivo y no paramétrico: da la curva de un grupo, sin covariables. Para comparar muchos grupos
a la vez, o un factor controlando otros, hace falta un modelo. Cox es semiparamétrico: no supone ninguna forma para
el riesgo base, pero sí que las covariables lo multiplican por un factor constante (el hazard ratio). Aquí KM
describe cada agencia y tipo; Cox responde «¿el Bronx es más lento **a igual tipo de queja, canal y horario**?».

**6. ¿Cómo se interpreta un hazard ratio cuando el evento es «bueno» (el cierre)?**
Al revés que en medicina: HR > 1 significa que se cierra **más rápido**. En el modelo B, el HR del Bronx es
{{hr_b_borough_bronx}}: en cada momento, una solicitud del Bronx abierta tiene un {{hr_b_borough_bronx_pct}} % menos de probabilidad de
cerrarse que una equivalente de Manhattan. No es «tarda un {{hr_b_borough_bronx_pct}} % más»: el HR habla de tasas instantáneas, no de
duraciones. Para hablar de tiempos, conviene traducirlo a medianas o a % cerrado a 7 días.

**7. ¿Qué es el supuesto de riesgos proporcionales y cómo se verificó?**
Que el HR es constante en el tiempo (con curvas log(−log S) paralelas). Se verificó de tres formas: la prueba de
Grambsch-Therneau sobre residuos de Schoenfeld escalados, las curvas log(−log S) por borough y reestimando el modelo
en ventanas de tiempo. No se cumple para agencia (por eso se estratifica) y solo parcialmente para borough: el HR
del Bronx va de {{hr_bronx_ventana_0}} el primer día a {{hr_bronx_ventana_3}} pasados 30 días. Las salidas son estratificar,
interactuar la covariable con el tiempo o reportar HR por ventana, como aquí.

**8. ¿Qué hace la estratificación en Cox y por qué la usaste en el modelo B?**
Cada estrato (tipo de queja) tiene su propio riesgo base, sin forma impuesta, y los coeficientes se estiman
comparando solicitudes **dentro** del mismo estrato. Así se controla el tipo de queja aunque viole PH, a cambio de no
obtener un HR para él. Por eso la concordancia del modelo B ({{cox_c_b}}) es mucho menor que la del A ({{cox_c_a}}): ya no
predice usando el tipo de queja, que es lo que más explica el tiempo.

**9. ¿Cómo mediste la equidad territorial sin depender del supuesto PH?**
Con estandarización indirecta: para cada solicitud, la probabilidad esperada de cerrarse en ≤ 7 días es la de toda
la ciudad en su celda tipo × descriptor. El O/E de un borough o ZIP compara lo observado con lo que predice su mezcla
de quejas. Sin ajustar, Manhattan parecía el más lento ({{pct7_manhattan}} % en 7 días); ajustado, está prácticamente en lo esperado
(O/E {{oe_manhattan}}). Para los {{n_zip_analizados}} ZIP se corrigió por comparaciones múltiples con Benjamini-Hochberg.

**10. ¿Por qué no hay sesgo por censura en el O/E a 7 días?**
Porque la cohorte termina el 30-09-2026 y el corte es posterior en 26 días: toda solicitud tuvo al menos 7 días de
seguimiento, y la censura solo la produce el corte. «¿Cerró en ≤ 7 días?» es entonces un dato completo para todas.
Con un horizonte de 60 días ya no lo sería, y habría que usar Kaplan-Meier.

**11. ¿Cómo validaste que tu Kaplan-Meier está bien?**
Con tres pruebas automáticas: (1) el ejemplo clásico de Freireich (leucemia, 6-MP frente a placebo), donde la
curva coincide con la tabla del libro y el log-rank da χ² = 16,79; (2) comparación con lifelines en datos aleatorios
con empates, censura y duraciones 0 (diferencia < 1e-10 en curva, IC y mediana); (3) casos límite: RMST sin censura
igual al promedio, censura total con mediana «no alcanzada» y duraciones negativas rechazadas.

**12. ¿Qué limitaciones le dirías a un gerente antes de usar estos números?**
Que el «cierre» es un registro administrativo: Salud cierra las quejas de comida a los 60 días exactos y cambió su
política de cierres instantáneos (del {{dohmh_inst_1}} % al {{dohmh_inst_2}} %), lo que movió su mediana de
{{anual_dohmh_1}} a {{anual_dohmh_2}} sin que necesariamente cambiara la atención. Que el análisis es observacional:
controla el tipo de queja, no la gravedad ni los recursos. Y que el 311 mide la demanda **reportada**: un barrio que
reporta menos no necesita menos.

**13. ¿Cómo hiciste la descarga robusta?**
Un mes por tarea, páginas con `$order=unique_key`, reintentos con espera exponencial ante errores de red, 429 y
5xx, escritura atómica de cada página (archivo temporal y renombrado) y un manifiesto con la fecha de corte. Las
pruebas usan respuestas grabadas de la API para comprobar la paginación, la reanudación tras un «apagón» y los
reintentos, sin red.
