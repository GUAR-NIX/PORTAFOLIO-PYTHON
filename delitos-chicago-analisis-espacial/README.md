# Delitos en Chicago 2001–2025: dónde se concentran, cómo cambiaron y cuánto se puede anticipar

¿Dónde y cuándo se concentran los delitos de Chicago? ¿Cuánto cambiaron con la pandemia? ¿Qué zonas tienen más delitos por habitante y cuánto se puede anticipar la demanda por distrito? Para responderlo proceso **8.665.676 registros reales del Chicago Data Portal** (enero de 2001 al 16-10-2026) con **DuckDB + Parquet**, y los analizo con pandas, statsmodels, geopandas y esda: tendencia anual, patrón hora × día, descomposición **STL**, una **serie temporal interrumpida** para el COVID-19, **tasas anuales por 100 mil habitantes** en las 77 áreas comunitarias, **hotspots Getis-Ord Gi\*** con su estabilidad año a año, tasas de arresto con **IC de Wilson** y un **pronóstico mensual por distrito** evaluado con **backtesting de origen móvil** e intervalos de predicción.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-Parquet-FFF200?logo=duckdb&logoColor=black)
![Datos](https://img.shields.io/badge/Chicago%20Data%20Portal-2001--2026-1f77b4)
![esda](https://img.shields.io/badge/esda-Getis--Ord%20Gi*-139C5A)
![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)

> **Años completos y año parcial.** Los totales, rankings y tasas usan solo años completos (2001–2025, 8.480.999 registros). 2026 tiene datos hasta el 16-10-2026 (184.677 registros): aparece marcado como parcial en la tendencia y solo entra al pronóstico hasta su último mes completo (2026-09).

---

## Preguntas que responde

| # | Pregunta | Técnica | Respuesta |
|---|---|---|---|
| 1 | ¿Los delitos están bajando? | Tendencia anual (años completos) | **Sí**: de 486.843 (2002) a 238.176 (2025), −51,1 %; mínimo de 210.017 en 2021 |
| 2 | ¿Qué cambió entre 2019 y 2024? | Variación por tipo con **categorías armonizadas** | Robo de vehículos **+141,8 %**; narcóticos **−60,2 %**. La agresión sexual criminal **no** subió +114,6 %: fue un cambio de nombre (−0,4 % al armonizar) |
| 3 | ¿Cuándo ocurren? | Mapa de calor hora × día + STL | Franja de más actividad **18:00–22:00** (22,0 % de los delitos), mínimo a las 05:00; pico estacional en agosto |
| 4 | ¿Cuánto cambió con el COVID-19? | Serie interrumpida con contrafactual ajustado antes de 2020 | **−21,4 %** entre 2020-03 y 2021-12 (IC 95 %: −23,3 a −19,6 %): 104.878 delitos menos de lo esperado |
| 5 | ¿Qué zonas tienen más delito por habitante? | Tasa **anual** por 100 mil hab., 2019–2025 | **West Garfield Park** (25.176 por 100 mil al año). Austin es la 1.ª en volumen pero la 22.ª en tasa |
| 6 | ¿Los hotspots son estables? | **Getis-Ord Gi\*** en grilla de 1 km + índice de Jaccard | **Sí**: Jaccard medio entre años consecutivos 0,79; 42 celdas son hotspot los 7 años |
| 7 | ¿Cuál es la tasa de arresto? | IC de Wilson al 95 % por tipo | **25,17 %** global; > 99 % en narcóticos y prostitución, < 8 % en robo de vehículo y robo a vivienda |
| 8 | ¿Se puede anticipar la demanda por distrito? | Backtesting de origen móvil (8 cortes) | **Sí**: Ridge con WAPE 6,21 % frente a 9,16 % de la base estacional; intervalo del 90 % con cobertura real de 86,4 % |

## Arquitectura

```mermaid
flowchart LR
    API["Chicago Data Portal · Socrata<br/>Crimes 2001-Present (ijzp-q8t2)"] -->|"descargar_datos.py<br/>CSV anual · reanudable · SHA-256"| R[("data/raw/<br/>26 CSV · 2,4 GB")]
    GEO["GeoJSON oficiales<br/>77 áreas · 25 distritos"] --> R
    CMAP["CMAP · censo 2020<br/>población por área"] --> REF[("data/referencia/")]
    R --> I["ingesta.py<br/>DuckDB: tipos · dedup por id<br/>bbox · Parquet por año"]
    I --> P[("data/procesados/<br/>anio=YYYY/")]
    P --> A["armonizacion.py<br/>renombres detectados por IUCR"]
    A --> T["temporal.py<br/>tendencia · hora×día · STL ·<br/>serie interrumpida"]
    A --> E["espacial.py<br/>tasas anuales · Gi* · Jaccard"]
    REF --> E
    A --> PO["policial.py<br/>arresto IC Wilson"]
    A --> PR["pronostico.py<br/>origen móvil · intervalos"]
    T & E & PO & PR --> F["reports/<br/>13 figuras · 17 CSV · resultados.json"]
    F --> RD["cifras_readme.py<br/>README y guía desde reports/"]
```

Dos comandos: `python descargar_datos.py` (descarga reanudable, unos 30 min la primera vez) y `python -m delitos_chicago.pipeline` (análisis completo, 36,2 s con el Parquet ya creado). Después, `python -m delitos_chicago.cifras_readme` vuelve a escribir este README con las cifras de `reports/`.

## Ingeniería y calidad de datos

| Problema real | Solución |
|---|---|
| 2,4 GB de CSV no caben cómodos en pandas | **DuckDB** lee los 26 CSV, normaliza tipos, deduplica por `id` (0 duplicados) y escribe **Parquet particionado por año**. El pipeline carga solo las columnas que usa |
| Un tipo de delito cambió de nombre a mitad de la serie | **Armonización detectada con datos** (ver abajo): `CRIM SEXUAL ASSAULT` → `CRIMINAL SEXUAL ASSAULT` |
| El año en curso está incompleto | Se excluye de totales, tasas y rankings; se marca en la tendencia; el pronóstico corta en 2026-09 |
| Coordenadas desplazadas a nivel de cuadra (privacidad) | Válidas para agregar en áreas y celdas de 1 km, no para puntos exactos. 149 filas caen fuera del rectángulo de Chicago |
| 100.954 registros (1,16 %) sin coordenadas | Se usan en el análisis temporal y policial y se excluyen solo del espacial |
| Trazabilidad de la fuente | [`data/manifiesto_fuente.json`](data/manifiesto_fuente.json) registra 29 archivos con URL de descarga, fecha, filas, bytes y **SHA-256** |
| Tasas de arresto cerca de 0 o 1 | **Intervalo de Wilson** en vez de Wald |

### Control de calidad: un salto de +114,6 % que era un cambio de nombre

Al comparar 2019 con 2024, `CRIMINAL SEXUAL ASSAULT` pasa de 814 a 1.747 (+114,6 %). Pero `CRIM SEXUAL ASSAULT` pasa de 940 a 0 en el mismo periodo: la policía cambió la etiqueta. Sumadas, pasan de **1.754 a 1.747 (−0,4 %)**.

En lugar de corregir este caso a mano, [`armonizacion.py`](src/delitos_chicago/armonizacion.py) busca las categorías que dejan de aparecer y comprueba si sus **códigos IUCR** (el código de delito de Illinois, que no depende de la etiqueta) siguen registrándose después bajo otra categoría. `CRIM SEXUAL ASSAULT` usa 13 códigos IUCR y, después de 2020, el 100,0 % de sus registros corresponde a códigos que aparecen bajo `CRIMINAL SEXUAL ASSAULT`. La tabla se aplica a **todo** el análisis ([`reports/armonizacion_categorias.csv`](reports/armonizacion_categorias.csv)):

| Categoría que desaparece | Último año | Registros | Cobertura IUCR | Decisión |
|---|---:|---:|---:|---|
| `CRIM SEXUAL ASSAULT` | 2020 | 27.237 | 100,0 % | renombre: se armoniza → `CRIMINAL SEXUAL ASSAULT` |
| `RITUALISM` | 2020 | 24 | 0,0 % | sin sucesor: sus códigos IUCR no vuelven a aparecer |
| `DOMESTIC VIOLENCE` | 2001 | 1 | 0,0 % | sin sucesor: sus códigos IUCR no vuelven a aparecer |

## Resultados

### 1 · El delito registrado cayó a la mitad y cambió de composición

![Tendencia anual](reports/figures/01_tendencia_anual.png)

| Año | Delitos |
|---|---:|
| 2001 | 485.979 |
| 2002 (máx.) | 486.843 |
| 2010 | 370.590 |
| 2019 | 261.942 |
| 2020 | 213.083 |
| 2021 (mín.) | 210.017 |
| 2022 | 240.506 |
| 2023 | 263.863 |
| 2024 | 259.670 |
| 2025 | 238.176 |
| 2026 (parcial, hasta 16-10) | 184.677 |

* La caída desde el máximo de 2002 es de **−51,1 %** hasta 2025. 2020 cayó **−18,7 %** frente a 2019, y la serie repuntó en 2022–2023.

| Tipo (categorías armonizadas) | 2019 | 2024 | Δ |
|---|---:|---:|---:|
| Robo de vehículo motorizado | 8.979 | 21.713 | +141,8 % |
| Acoso (*stalking*) | 228 | 520 | +128,1 % |
| Homicidio | 509 | 597 | +17,3 % |
| Robo con violencia (*robbery*) | 7.997 | 9.120 | +14,0 % |
| Agresión sexual criminal | 1.754 | 1.747 | −0,4 % |
| Hurto (*theft*) | 62.505 | 60.561 | −3,1 % |
| Narcóticos | 15.080 | 5.998 | −60,2 % |
| Juego ilegal | 142 | 22 | −84,5 % |

*Tabla completa en [`reports/cambio_porcentual_2019_2024.csv`](reports/cambio_porcentual_2019_2024.csv), ya con las categorías armonizadas.* El robo de vehículos más que se duplica; este análisis describe el aumento registrado, pero no identifica su causa. Narcóticos (−60,2 %) y juego ilegal (−84,5 %) son delitos que casi solo se registran cuando hay un arresto, así que reflejan sobre todo la actividad policial. Por eso no conviene leer esas series como incidencia.

### 2 · COVID-19: serie temporal interrumpida

Ajusté un modelo **solo con datos de 2015-01 a 2020-02** (62 meses): logaritmo de la media diaria de delitos por mes con tendencia lineal y estacionalidad mensual. El error del ajuste antes de la pandemia es 1,9 % (MAPE) y la tendencia previa, −0,3 % al año. Con ese modelo proyecté un **contrafactual** para 2020-03–2021-12 con intervalos de predicción del 95 %, simulando la incertidumbre de los coeficientes y la variación mes a mes.

![Serie interrumpida](reports/figures/04_efecto_covid.png)

* Se registraron **384.717 delitos** frente a **489.595** esperados: **−21,4 %** (IC 95 %: −23,3 a −19,6 %), unos 104.878 delitos menos (entre 93.521 y 116.985). 22 de los 22 meses evaluados quedan fuera del intervalo de predicción.
* La caída no fue igual para todos los tipos ([`reports/covid_por_serie.csv`](reports/covid_por_serie.csv)):

| Serie | Abr–may 2020 | 2020-03 a 2021-12 (IC 95 %) | Meses fuera del intervalo | Error de ajuste pre |
|---|---:|---:|---:|---:|
| Todos los delitos | −31,6 % | −21,4 % (−23,3 a −19,6) | 22 de 22 | 1,9 % |
| Hurto (THEFT) | −49,0 % | −41,1 % (−43,6 a −38,7) | 22 de 22 | 3,7 % |
| Agresión (BATTERY) | −29,9 % | −19,2 % (−21,5 a −17,0) | 22 de 22 | 2,4 % |
| Robo a vivienda (BURGLARY) | +25,0 % | −17,3 % (−25,0 a −10,1) | 14 de 22 | 8,3 % |
| Narcóticos (NARCOTICS) | −68,9 % | −49,7 % (−60,8 a −40,2) | 13 de 22 | 20,6 % |
| Robo de vehículo (MOTOR VEHICLE THEFT) | +5,4 % | +16,9 % (+6,4 a +26,7) | 5 de 22 | 7,9 % |
| Violencia doméstica (indicador) | −23,8 % | −10,8 % (−13,1 a −8,7) | 20 de 22 | 2,2 % |

* Frente al contrafactual, en el confinamiento (abril–mayo de 2020) el hurto quedó en **−49,0 %** y la violencia doméstica registrada en **−23,8 %**, mientras que el robo a vivienda o local quedó en **+25,0 %** en esos dos meses y el robo de vehículo cerró el periodo en **+16,9 %**. El modelo de narcóticos ajusta mal antes de 2020 (error 20,6 %), así que su intervalo es poco fiable.
* Es una comparación contra lo esperado según la tendencia, no un efecto causal aislado: en 2020 coincidieron el confinamiento, las protestas de mayo–junio y cambios en el patrullaje.

### 3 · Cuándo ocurren: hora, día y estación

![Mapa de calor hora × día](reports/figures/02_mapa_calor_hora_dia.png)

* La franja de cuatro horas con más delitos es **18:00–22:00**, con el 22,0 % del total (si el reparto fuera uniforme sería 16,7 %). El mínimo cae a las **05:00**. Las 00:00 concentran el 5,9 % de los registros, en buena parte porque los incidentes sin hora exacta se guardan con esa hora, así que la medianoche no se usa para buscar la franja pico.
* El **viernes** es el día con más delitos y el **domingo**, el de menos; la diferencia es de 9,8 %.
* La descomposición **STL** del hurto mensual separa la tendencia del ciclo anual: el máximo estacional cae en **agosto** y el mínimo en **febrero**, con una amplitud de 37,6 % de la media mensual.

![Descomposición STL](reports/figures/03_descomposicion_stl.png)

### 4 · Tipos de delito más frecuentes

![Top tipos](reports/figures/05_top_tipos.png)

| Tipo primario | Total 2001–2025 |
|---|---:|
| Hurto (*theft*) | 1.800.510 |
| Agresión física (*battery*) | 1.544.312 |
| Daño a la propiedad | 963.854 |
| Narcóticos | 765.164 |
| Amenaza o asalto (*assault*) | 568.894 |
| Otro delito | 529.153 |
| Robo a vivienda o local (*burglary*) | 447.926 |
| Robo de vehículo motorizado | 434.854 |
| Fraude (*deceptive practice*) | 393.500 |
| Robo con violencia (*robbery*) | 315.691 |

### 5 · Dónde: tasa anual por habitante frente a volumen

La tasa es **anual**: delitos de cada año entre la población del área (censo 2020, [CMAP](data/referencia/poblacion_areas_cmap_2020.csv)), promediada en 2019–2025. Ranking por tasa ([`reports/delitos_por_area_comunitaria.csv`](reports/delitos_por_area_comunitaria.csv); serie por año en [`reports/tasas_anuales_area.csv`](reports/tasas_anuales_area.csv)):

![Coropleta](reports/figures/06_mapa_coropleta_tasa.png)

**Mapas interactivos** (Folium, un HTML cada uno en `reports/`): [`mapa_chicago_coropleta.html`](reports/mapa_chicago_coropleta.html) muestra la tasa anual por área comunitaria con un cuadro al pasar el ratón, y [`mapa_calor_hotspots.html`](reports/mapa_calor_hotspots.html) un mapa de calor sobre 12.000 puntos al azar. GitHub no ejecuta HTML: descarga el archivo y ábrelo con doble clic en el navegador (necesita conexión a internet para las teselas de OpenStreetMap). Se regeneran con `python -m delitos_chicago.pipeline`.

| Puesto por tasa | Área comunitaria | Delitos por año por 100 mil hab. | Delitos por año | Puesto por volumen | Ranking de tasa: medio (mín.–máx.) |
|---:|---|---:|---:|---:|---:|
| 1 | West Garfield Park (26) | 25.176 | 4.389 | 18 | 1,3 (1–3) |
| 2 | Englewood (68) | 21.157 | 5.156 | 14 | 2,4 (1–4) |
| 3 | North Lawndale (29) | 20.505 | 7.134 | 6 | 4,0 (2–7) |
| 4 | East Garfield Park (27) | 19.919 | 3.982 | 20 | 4,1 (2–5) |
| 5 | Greater Grand Crossing (69) | 19.420 | 6.255 | 10 | 4,9 (3–8) |
| 6 | Washington Park (40) | 18.036 | 2.292 | 37 | 6,9 (2–10) |
| 7 | Fuller Park (37) | 18.025 | 702 | 71 | 7,7 (5–9) |
| 8 | Chatham (44) | 17.959 | 5.914 | 11 | 7,9 (6–9) |

El ranking por **volumen** cuenta otra historia: las áreas más pobladas o con mucha población flotante encabezan la lista, aunque su tasa sea media.

| Puesto por volumen | Área comunitaria | Delitos por año | Población 2020 | Tasa por 100 mil | Puesto por tasa |
|---:|---|---:|---:|---:|---:|
| 1 | Austin (25) | 12.737 | 96.557 | 13.191 | 22 |
| 2 | Near North Side (8) | 10.401 | 106.983 | 9.722 | 30 |
| 3 | Near West Side (28) | 9.164 | 67.881 | 13.501 | 20 |
| 4 | South Shore (43) | 8.261 | 53.971 | 15.306 | 12 |
| 5 | Loop (32) | 8.020 | 47.614 | 16.844 | 10 |

![Ranking](reports/figures/07_ranking_hotspots_areas.png)

* **Austin** tiene el mayor volumen (12.737 delitos al año), pero con 96.557 habitantes su tasa (13.191 por 100 mil) lo deja en el puesto 22. Comparar áreas por conteo confunde tamaño con riesgo.
* El ranking de tasas es persistente: en las 10 primeras áreas, la desviación estándar mediana del puesto año a año es 1,6. La excepción es **Loop** (desviación 8,0, del puesto 4 al 25): su tasa depende de la población flotante del centro, que se desplomó en 2020–2021.

### 6 · Hotspots estadísticos: Getis-Ord Gi\*

Un ranking de áreas no dice si una concentración es estadísticamente significativa. Para eso calculé **Getis-Ord Gi\*** (con `esda`) sobre una **grilla de 1 km** (672 celdas con delitos), con vecindad de tipo reina, para cada año de 2019–2025. Usé la p bilateral con **corrección FDR de Benjamini-Hochberg** al 5 % para no inflar los hotspots con miles de pruebas. La estabilidad se mide con el **índice de Jaccard** entre los conjuntos de celdas hotspot ([`reports/estabilidad_espacial_hotspots.csv`](reports/estabilidad_espacial_hotspots.csv)):

![Hotspots por año](reports/figures/12_hotspots_gi_por_anio.png)

| Año | Celdas hotspot | % de celdas | % de delitos en hotspots | Jaccard vs año anterior | Jaccard vs 2019 |
|---:|---:|---:|---:|---:|---:|
| 2019 | 57 | 8,5 % | 27,2 % | — | 1,00 |
| 2020 | 86 | 12,8 % | 34,5 % | 0,64 | 0,64 |
| 2021 | 83 | 12,4 % | 33,1 % | 0,88 | 0,69 |
| 2022 | 64 | 9,5 % | 27,6 % | 0,65 | 0,68 |
| 2023 | 57 | 8,5 % | 24,1 % | 0,83 | 0,68 |
| 2024 | 57 | 8,5 % | 24,6 % | 0,87 | 0,70 |
| 2025 | 59 | 8,8 % | 25,6 % | 0,87 | 0,61 |

* Los hotspots son **estables**: el Jaccard medio entre años consecutivos es **0,79** y el 77,2 % de las celdas hotspot de 2019 lo sigue siendo en el último año (Jaccard entre extremos: 0,61).
* **42 celdas** (6,2 % del área de estudio) son hotspot los 7 años y concentran el **18,7 %** de los delitos del último año. Las áreas comunitarias con más celdas persistentes (número de celdas entre paréntesis, según el centro de la celda) son Greater Grand Crossing (6), North Lawndale (6), Near North Side (5), West Garfield Park (4), South Shore (4), East Garfield Park (4) y Loop (4) ([`reports/hotspots_persistentes_por_area.csv`](reports/hotspots_persistentes_por_area.csv)).
* En 2020 el área hotspot se expandió a 86 celdas y luego volvió a unas 57. En cada año, los hotspots concentran entre el 24,1 % y el 34,5 % de los delitos.

![Persistencia de hotspots](reports/figures/13_persistencia_hotspots.png)

*Gi\* se calcula sobre conteos por celda, no sobre tasas: las celdas no tienen población, así que un hotspot puede deberse a mucha actividad (comercio, transporte) y no solo a mucho riesgo por residente.*

### 7 · Arrestos: la tasa depende de cómo se registra el delito

![Tasa de arresto por tipo](reports/figures/08_tasa_arresto_por_tipo.png)

* **Tasa de arresto global 2001–2025: 25,17 %**.

| Tipo | Tasa de arresto | IC 95 % (Wilson) |
|---|---:|---:|
| Prostitución | 99,6 % | 99,5–99,6 % |
| Narcóticos | 99,3 % | 99,3–99,4 % |
| Juego ilegal | 99,3 % | 99,1–99,4 % |
| Infracción de armas | 72,7 % | 72,4–72,9 % |
| Homicidio | 49,2 % | 48,4–50,0 % |
| Hurto (*theft*) | 10,8 % | 10,8–10,9 % |
| Robo de vehículo motorizado | 7,5 % | 7,5–7,6 % |
| Daño a la propiedad | 6,5 % | 6,4–6,5 % |
| Robo a vivienda o local (*burglary*) | 5,7 % | 5,7–5,8 % |

* Narcóticos, prostitución y juego superan el 99 % porque **el delito se registra en el mismo acto del arresto**. En el otro extremo, el robo a vivienda y el daño a la propiedad dependen de denuncias y casi nunca terminan en arresto.
* **Violencia doméstica**: 1.465.160 delitos (**17,28 %**), con una tasa de arresto **menor** que la del resto (19,2 % frente a 26,4 %). Los tipos más frecuentes son agresión física (*battery*) (818.641), otro delito (196.207) y amenaza o asalto (*assault*) (166.553).
* **Por distrito policial**, volumen y tasa de arresto no van de la mano ([`reports/metricas_distritos_policiales.csv`](reports/metricas_distritos_policiales.csv)):

![Distritos](reports/figures/09_distritos_policiales_efectividad.png)

| Distrito | Delitos 2001–2025 | Tasa de arresto |
|---:|---:|---:|
| 8 | 568.522 | 21,8 % |
| 11 | 537.379 | 41,0 % |
| 6 | 495.336 | 24,7 % |
| 4 | 479.977 | 21,5 % |

*Los distritos 31 y 61 apenas registran incidentes (286 y 2.301), frente a más de 150.000 en cada uno de los demás (salvo el distrito 21, con 4).*

### 8 · Pronóstico mensual por distrito con backtesting de origen móvil

Pronostico el mes siguiente para 22 distritos. En lugar de una sola partición, uso **8 cortes**: en cada uno reentreno con todo lo anterior y pronostico los 3 meses siguientes, un mes adelante cada vez. Así se evalúan 24 meses distintos (2024-10 a 2026-09), sin el mes incompleto de 2026. Los **intervalos de predicción del 90 %** se calibran fuera de muestra: en cada corte, el modelo se ajusta también con datos de hasta 12 meses antes, y los errores relativos de esos 12 meses, que el modelo no vio, dan los cuantiles.

![Pronóstico vs real](reports/figures/10_pronostico_vs_real.png)

| Modelo | MAE | WAPE global | WAPE por corte (media ± desv.) | Sesgo | Cortes ganados | Cobertura IP 90 % |
|---|---:|---:|---:|---:|---:|---:|
| Línea base estacional (t−12) | 82,3 | 9,16 % | 9,20 ± 1,34 | +6,61 % | 0 de 8 | 85,4 % |
| Media móvil 3 meses | 80,4 | 8,94 % | 9,02 ± 2,02 | +1,19 % | 0 de 8 | 85,4 % |
| **Ridge** | 55,8 | **6,21 %** | 6,28 ± 2,02 | +1,96 % | 5 de 8 | 86,4 % |
| Random Forest | 56,5 | 6,28 % | 6,32 ± 1,34 | +2,11 % | 3 de 8 | 86,2 % |

![WAPE por corte](reports/figures/11_comparativa_errores_modelos.png)

* El mejor modelo es **Ridge** (WAPE 6,21 %, gana 5 de 8 cortes), **32,2 % menos error** que la línea base estacional (9,16 %). Random Forest queda muy cerca (6,28 %): con rezagos y medias móviles, una relación lineal captura casi toda la señal.
* El intervalo del 90 % cubrió el **86,4 %** de los valores reales: un poco menos de lo nominal, así que conviene leerlo como un rango algo optimista. Su ancho mediano es 24,0 % del pronóstico, y el sesgo del ganador es +1,96 %. Las métricas por corte están en [`reports/backtesting_por_corte.csv`](reports/backtesting_por_corte.csv).

## App interactiva

`streamlit run app/streamlit_app.py`: filtra por tipo (armonizado), rango de años y violencia doméstica, y muestra la tendencia, el mapa de calor hora × día, la coropleta de tasas, la efectividad por distrito y las métricas del pronóstico. Lee el Parquet con DuckDB; si no existe, usa la muestra versionada.

## Notebooks (ejecutados, con figuras)

1. [Ingesta y calidad](notebooks/01_ingesta_y_calidad.ipynb): auditoría, manifiesto con SHA-256 y armonización de categorías
2. [Análisis temporal](notebooks/02_analisis_temporal.ipynb): tendencia, hora × día, STL y serie interrumpida
3. [Análisis espacial](notebooks/03_analisis_espacial.ipynb): tasas anuales, Gi\* y estabilidad de hotspots
4. [Pronóstico](notebooks/04_pronostico.ipynb): variables sin fuga, backtesting de origen móvil e intervalos

## Decisiones técnicas

* **DuckDB y Parquet por año**: motor columnar embebido; agrega 8,7 M de filas en segundos sin clúster y el pipeline carga solo las columnas necesarias.
* **Armonizar antes de comparar**: los renombres se detectan con los códigos IUCR, no a ojo, y la tabla queda en `reports/`.
* **Tasas anuales, no acumuladas**: una tasa de 25 años sobre la población de un solo censo no se puede interpretar; el ranking usa la media de tasas anuales en 2019–2025, años cercanos al censo 2020.
* **Gi\* con FDR y Jaccard**: el ranking dice dónde hay más delitos; Gi\* dice dónde la concentración es significativa, y Jaccard mide si se mantiene.
* **Contrafactual ajustado solo con el pasado**: el modelo del COVID no ve ningún dato de 2020; los intervalos incluyen la variación mes a mes.
* **Backtesting de origen móvil**: un solo corte de 12 meses depende de qué año toque; 8 cortes dan una media y una dispersión del error, y el titular es el modelo que gana.
* **Línea base siempre**: estacional ingenua (t−12) y media móvil de 3 meses.

## Cómo ejecutarlo

Guía detallada para Windows, con preguntas de entrevista: **[docs/GUIA_PASO_A_PASO.md](docs/GUIA_PASO_A_PASO.md)**

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python descargar_datos.py                    # CSV anuales, GeoJSON y población CMAP (reanudable)
python -m delitos_chicago.pipeline           # análisis completo, figuras y reports/
python -m delitos_chicago.cifras_readme      # README y guía con las cifras de reports/
pytest                                       # 31 pruebas (incluida la de cifras del README)
streamlit run app/streamlit_app.py           # explorador interactivo
```

## Estructura

```
├── descargar_datos.py          descarga reanudable y manifiesto (URL, fecha, SHA-256)
├── src/delitos_chicago/
│   ├── ingesta.py              DuckDB: tipos, dedup, bbox, Parquet particionado, muestra
│   ├── armonizacion.py         detección de renombres de categorías por código IUCR
│   ├── temporal.py             tendencia, hora×día, STL, serie interrumpida
│   ├── espacial.py             tasas anuales, Getis-Ord Gi*, Jaccard, mapas
│   ├── policial.py             tasas de arresto con IC de Wilson, violencia doméstica
│   ├── pronostico.py           variables sin fuga, backtesting de origen móvil, intervalos
│   ├── pipeline.py             orquestador
│   └── cifras_readme.py        README y guía generados desde reports/
├── scripts/plantillas/         plantillas del README y la guía
├── notebooks/                  4 notebooks ejecutados con figuras
├── app/streamlit_app.py        explorador interactivo
├── tests/                      pruebas con datos sintéticos + verificación de cifras
├── data/referencia/            población 2020 por área comunitaria (CMAP, versionada)
├── data/muestra/               muestra aleatoria: 10.000 registros en Parquet y 500 en CSV
├── data/raw/, data/procesados/ CSV crudos y Parquet (ignorados por git)
└── reports/                    figuras, CSV, JSON y mapas HTML
```

## Fuentes y licencias

* **Crimes 2001 to Present**: [Chicago Data Portal](https://data.cityofchicago.org/Public-Safety/Crimes-2001-to-Present/ijzp-q8t2), dataset `ijzp-q8t2`, bajo los [términos de uso del portal](https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html). Descargado el 24-10-2026; URL, filas y SHA-256 de cada archivo en [`data/manifiesto_fuente.json`](data/manifiesto_fuente.json).
* **Áreas comunitarias**: GeoJSON `igwz-8jzy` del mismo portal. **Distritos policiales**: GeoJSON `24zt-jpfn`.
* **Población por área comunitaria**: censo 2020 según CMAP, [Community Data Snapshots](https://www.cmap.illinois.gov/data/community-snapshots) (campo `F2020_POP`). La suma de las 77 áreas es 2.784.433.
* Métodos: STL (Cleveland et al., 1990); Getis y Ord (1992) y Ord y Getis (1995); Benjamini y Hochberg (1995); intervalo de Wilson (1927); series temporales interrumpidas (Bernal, Cummins y Gasparrini, 2017).

> **Limitaciones:** los datos son delitos *registrados* (denunciados o detectados), no la incidencia real. Las coordenadas están desplazadas a nivel de cuadra. La población es la del censo 2020 para todos los años, así que las tasas anteriores a 2019 son aproximadas. Gi\* usa conteos, no riesgo por residente. El contrafactual del COVID supone que la tendencia de 2015–2019 habría seguido igual. El pronóstico solo usa la historia de cada distrito, sin variables externas. No se infiere causalidad.

**Licencia:** el **código** de este repositorio es [MIT](LICENSE) (© 2026 Erick Guarnizo); los **datos** siguen la licencia o los términos de uso de cada fuente, los citados arriba.

## Autor

**Erick Guarnizo** · Ingeniero en Sistemas · [LinkedIn](https://www.linkedin.com/in/erick-g-571a7b3b4)
