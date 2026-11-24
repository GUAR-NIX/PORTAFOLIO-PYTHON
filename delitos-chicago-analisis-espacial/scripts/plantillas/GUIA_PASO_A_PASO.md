# Guía paso a paso: delitos en Chicago, análisis espacial y temporal

Cómo reproducir el proyecto en Windows, verificar sus resultados y responder preguntas de entrevista sobre las decisiones técnicas. Las cifras de esta guía se generan desde `reports/` con `python -m delitos_chicago.cifras_readme`.

---

## 1 · Requisitos

- Windows 11, Linux o macOS; Python 3.12 o superior (el proyecto se ejecutó con Python 3.14).
- **Memoria**: el pipeline completo usó un pico de **{{memoria_pico_gb}} GB** en la última ejecución (medido con psutil). DuckDB agrega en disco y el pipeline carga solo las columnas que usa.
- **Disco**: unos 3 GB (2,4 GB de CSV crudos y el Parquet).

## 2 · Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## 3 · Descarga de datos

```powershell
python descargar_datos.py
```

Descarga un CSV por año desde la API Socrata del portal de Chicago (reanudable: si se corta, al volver a ejecutarlo solo baja los años que faltan), los GeoJSON de áreas comunitarias y distritos, y la población del censo 2020 por área (CMAP). Al final escribe `data/manifiesto_fuente.json` con la URL, la fecha, las filas, los bytes y el SHA-256 de cada archivo. Con `python descargar_datos.py --solo-manifiesto` se recalcula el manifiesto sin descargar nada.

## 4 · Pipeline

```powershell
python -m delitos_chicago.pipeline
python -m delitos_chicago.cifras_readme
```

Con el Parquet ya creado tarda unos {{tiempo_pipeline}} s. Genera:

- `data/procesados/delitos_parquet/`: datos limpios particionados por año.
- `data/muestra/`: muestra aleatoria de {{muestra_parquet}} registros en Parquet (la usa la app si no hay Parquet completo) y {{muestra_csv}} en CSV para inspección rápida.
- `reports/`: {{n_figuras}} figuras, {{n_csv}} CSV, JSON de resultados y dos mapas HTML livianos.
- `README.es.md` y esta guía, con las cifras de `reports/`.

## 5 · Pruebas

```powershell
pytest
```

Las pruebas usan datos sintéticos (no necesitan internet) y prueban el código propio: la detección de renombres, Gi\* frente a la fórmula de Getis-Ord, la serie interrumpida, la STL, la ausencia de fuga en el pronóstico, la cobertura de los intervalos y que cada cifra del README coincida con `reports/`.

## 6 · App

```powershell
streamlit run app/streamlit_app.py
```

Disponible en `http://localhost:8501`.

## 7 · Problemas frecuentes

| Síntoma | Causa | Solución |
| :--- | :--- | :--- |
| `MemoryError` al leer los CSV con pandas | 2,4 GB de texto se multiplican en memoria | Usar el Parquet con DuckDB, como hace `pipeline.py` |
| `Bad Request 400` al probar la API desde PowerShell | PowerShell interpreta `$where` como variable | Llamar a la API desde Python (`descargar_datos.py`) |
| La prueba de cifras del README falla | Cambiaron los resultados o alguien editó el README a mano | `python -m delitos_chicago.cifras_readme` |

---

## 8 · Preguntas de entrevista (con respuestas)

### 1. ¿Por qué Parquet particionado por año y no un solo archivo?
Porque las consultas por rango de años leen solo las carpetas `anio=YYYY` necesarias (*partition pruning*) y el formato columnar comprime y permite leer solo las columnas usadas. El pipeline lee 12 de las 20 columnas y su pico de memoria fue de {{memoria_pico_gb}} GB.

### 2. ¿Cómo encontraste el problema de `CRIM SEXUAL ASSAULT`?
Al comparar 2019 con 2024, `CRIMINAL SEXUAL ASSAULT` subía {{cs_nuevo_cambio}} %, un salto sospechoso. La categoría vieja `CRIM SEXUAL ASSAULT` pasaba de {{cs_viejo_ini}} a {{cs_viejo_fin}}: era un cambio de etiqueta. Sumadas, el cambio es {{cs_arm_cambio}} %. Para no depender de detectarlo a ojo, el código busca las categorías que desaparecen y comprueba si sus códigos IUCR siguen apareciendo después bajo otra categoría; aquí, el {{cs_cobertura}} % de los registros cumple esa condición. De las {{categorias_desaparecidas}} categorías que desaparecen, solo esa es un renombre.

### 3. Las coordenadas están desplazadas a nivel de cuadra. ¿Cómo afecta?
No sirven para ubicar domicilios, pero un desplazamiento del orden de una cuadra es pequeño frente a una celda de 1 km o un área comunitaria. Por eso el análisis espacial agrega y no trabaja con puntos.

### 4. ¿Por qué tasas anuales por habitante y no conteos?
El conteo mezcla tamaño con riesgo. Austin es la primera área en volumen ({{austin_delitos}} delitos al año) pero la {{austin_tasa}}.ª en tasa, porque tiene {{austin_poblacion}} habitantes. **{{area_tasa_1}}** encabeza la tasa ({{area_tasa_1_tasa}} delitos por 100 mil al año) y es la {{area_tasa_1_vol}}.ª en volumen. La tasa es anual: una tasa acumulada de 25 años sobre un solo censo no tiene una interpretación clara. Además, la tabla de población original del proyecto tenía errores de hasta 75 % en algunas áreas; ahora se descarga del CMAP.

### 5. ¿Cómo comprobaste que los hotspots no son un artefacto de un año?
Con Getis-Ord Gi\* sobre una grilla de 1 km para cada año de {{ventana}}, con corrección FDR, y con el índice de Jaccard entre los conjuntos de hotspots. El Jaccard medio entre años consecutivos es {{gi_jaccard_medio}}, y {{gi_persistentes}} celdas son hotspot los {{n_anios_ventana}} años; concentran el {{gi_pct_delitos_persistentes}} % de los delitos del último año.

### 6. ¿Qué es Gi\* y en qué se diferencia de un ranking?
Gi\* compara la suma de una celda y sus vecinas con lo esperado si los conteos estuvieran repartidos al azar, y da un puntaje z. Un ranking ordena, pero no dice si una concentración es significativa ni si forma un grupo espacial. Como se prueban {{gi_celdas}} celdas por año, aplico Benjamini-Hochberg para controlar los falsos positivos. Comprobé en una prueba que el puntaje de `esda` coincide con la fórmula de Getis-Ord.

### 7. ¿Cómo mediste el efecto del COVID-19?
Con una serie temporal interrumpida: ajusté un modelo de tendencia y estacionalidad **solo con {{covid_pre_ini}} a {{covid_pre_fin}}** y lo proyecté a {{covid_ini}}–{{covid_fin}} como contrafactual, con intervalos de predicción por simulación. El total registrado se desvió **{{covid_cambio}} %** de lo esperado (IC 95 %: {{covid_cambio_inf}} a {{covid_cambio_sup}} %). En abril–mayo de 2020 la desviación fue de {{covid_choque_total}} % en el total, {{covid_choque_hurto}} % en el hurto y {{covid_choque_domestica}} % en la violencia doméstica registrada. No es un efecto causal puro: en 2020 coincidieron el confinamiento, las protestas y cambios en el patrullaje.

### 8. ¿Por qué el intervalo de Wilson para las tasas de arresto?
El de Wald (`p ± z·√(p(1−p)/n)`) puede salirse de [0, 1] y cubre menos de lo nominal cuando p está cerca de 0 o 1 o n es pequeño. Wilson se mantiene dentro de [0, 1] y su cobertura es cercana al 95 % incluso en esos casos. Aquí, con cientos de miles de casos por tipo, los dos dan casi lo mismo; la diferencia importa en tipos raros o en cortes finos.

### 9. ¿Cómo evitaste la fuga de información en el pronóstico?
Los rezagos y medias móviles solo usan meses anteriores, y en cada corte del backtesting el modelo se entrena con datos anteriores al corte. Una prueba lo verifica: si se cambian los datos posteriores al mes pronosticado, el pronóstico no cambia.

### 10. ¿Por qué backtesting de origen móvil y no una sola partición?
Con un solo corte, el resultado depende de qué año toque. Con {{pron_cortes}} cortes trimestrales se evalúan {{pron_meses}} meses ({{pron_primer_mes}} a {{pron_ultimo_mes}}) y se obtiene la media y la dispersión del error. El mes en curso (incompleto) se excluye: incluirlo parecería una caída falsa.

### 11. ¿Qué modelo ganó y cuánto mejora?
**{{pron_ganador}}**: WAPE {{pron_wape}} % frente a {{pron_base}} % de la línea base estacional ({{pron_mejora}} % menos error). {{pron_segundo}} queda muy cerca ({{pron_wape_segundo}} %), así que no se justifica un modelo más complejo.

### 12. ¿Cómo calculaste los intervalos de predicción y son fiables?
En cada corte ajusto el modelo también con datos de hasta 12 meses antes, pronostico esos 12 meses (que no vio) y uso los cuantiles 5 % y 95 % del cociente real/pronóstico. En el backtesting, el intervalo del 90 % cubrió el {{pron_cobertura}} % de los valores reales: algo menos de lo nominal, porque los errores de un año no siempre representan los del siguiente.

### 13. ¿Por qué WAPE y no MAPE?
El MAPE divide por cada valor real y se dispara en distritos o meses con pocos casos. El WAPE divide el error total entre el total real, es robusto a valores pequeños y se interpreta como el porcentaje del volumen que se equivoca.

### 14. ¿Qué limitaciones tienen estos datos?
Son delitos **registrados**: narcóticos y prostitución tienen tasas de arresto mayores al 99 % porque el delito se registra al arrestar, mientras el robo a vivienda depende de denuncias y tiene {{arresto_burglary}} %. Las caídas de narcóticos ({{cambio_narc}} % entre 2019 y 2024) reflejan sobre todo cambios en la actividad policial. Además, la población es del censo 2020 para todos los años y Gi\* trabaja con conteos, no con riesgo por residente. No se infiere causalidad.
