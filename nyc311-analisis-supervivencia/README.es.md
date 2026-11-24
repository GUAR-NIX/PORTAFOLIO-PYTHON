<!-- Archivo generado por `python -m nyc311.cifras_readme` desde scripts/plantillas/README.md.
     No lo edites a mano: cambia la plantilla y vuelve a generarlo. Todas las cifras salen de reports/. -->
🇪🇸 **Español** · 🇺🇸 [English (summary)](README.md)

# ¿Cuánto tarda Nueva York en resolver una solicitud del 311? · Análisis de supervivencia con casos censurados

![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![NYC Open Data](https://img.shields.io/badge/Datos-NYC_Open_Data_311-0F4C81)
![lifelines](https://img.shields.io/badge/Supervivencia-Kaplan--Meier_·_log--rank_·_Cox-6250D6)
![Pytest](https://img.shields.io/badge/Pruebas-pytest-16A34A?logo=pytest&logoColor=white)
![Streamlit](https://img.shields.io/badge/App-Streamlit-FF4B4B?logo=streamlit&logoColor=white)

Análisis de **7.544.678 solicitudes ciudadanas al 311 de Nueva York** creadas entre octubre de 2024 y septiembre de 2026, con **análisis de supervivencia**: el «evento» es el cierre de la solicitud y las que seguían abiertas en la fecha de corte (`2026-10-26 01:36:17`) son **casos censurados**, no casos que se puedan ignorar ni promediar como si hubieran cerrado.

## Resultados en 30 segundos

* **La solicitud típica se cierra en 9,0 horas** (mediana Kaplan-Meier, IC 95 %: 8,92–8,99 h). El 59,1 % se cierra en un día, el 81,1 % en una semana y el 4,7 % sigue abierta a los 90 días. El «promedio» de las cerradas (8,7 días) no describe a nadie: lo arrastra una cola larga.
* **El promedio de las cerradas engaña, y lo demostramos con datos reales.** Fingiendo un corte el 2025-01-15 sobre la cohorte de oct–dic 2024, la mediana ingenua de Parques (DPR) daba 4,6 días; Kaplan-Meier daba **27,2 días**, y la verdad, conocida casi dos años después, es **27,2 días** (la ingenua se queda corta 5,9 veces). Hoy pasa lo mismo con Taxis y Limusinas (TLC): mediana ingenua de 43,5 días frente a **122,5 días** con Kaplan-Meier, porque el 34,2 % de sus casos sigue abierto.
* **Lo que más explica el tiempo es la agencia y el tipo de queja, no el barrio.** La Policía (NYPD) cierra en **1,3 h**; Vivienda (HPD), en 4,0 días; Edificios (DOB), en 11,7 días; Parques (DPR), en 19,0 días. Entre los 20 tipos más frecuentes, la mediana va de 55 min en «Ruido comercial» a 13,0 días en «Puerta / ventana (vivienda)».
* **Equidad territorial: la brecha del Bronx es de horas, no de días.** Comparando dentro del mismo tipo de queja, en el Bronx la probabilidad de cierre es en cada momento un 13 % menor que en Manhattan (Cox estratificado, HR 0,87). Pero el efecto está en las primeras horas: en la primera hora el Bronx cierra un 18 % menos de lo que predice su mezcla de quejas (O/E 0,822), a las 24 h ya está en lo esperado (O/E 1,004) y, entre las que siguen abiertas pasados 30 días, cierra más rápido que Manhattan (HR 1,47). **Staten Island es el único borough claramente más rápido de lo esperado a 7 días** (O/E 1,030; el resto queda a menos de 0,5 % de 1).
* **El segundo año fue algo más lento.** El 79,9 % de las solicitudes se cerró en ≤ 7 días, frente al 82,4 % del año anterior (-2,5 pp), y el empeoramiento se mantiene después de ajustar por la mezcla de quejas (O/E 1,011 → 0,990). El pico de cada invierno (mediana de 28,3 h en 2026-01 frente a 3,7 h en 2025-06) se explica por la mezcla: en 2026-01, las quejas de calefacción son el 22,9 % del total.

![Sesgo del promedio frente a Kaplan-Meier](reports/figures/02_sesgo_promedio_vs_kaplan_meier.png)

---

## 1. Fuente de datos y licencia

| Elemento | Detalle |
| :--- | :--- |
| Dataset | [311 Service Requests from 2010 to Present](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9) · NYC Open Data (id `erm2-nwe9`) |
| Acceso | API Socrata `https://data.cityofnewyork.us/resource/erm2-nwe9.csv`, sin clave, con `$select` (10 columnas), `$where` por mes, `$order=unique_key`, `$limit`/`$offset` |
| Ventana | Solicitudes creadas del 01-10-2024 al 30-09-2026 · descarga del 2026-10-27 · corte de censura `2026-10-26 01:36:17` |
| Términos de uso | Datos públicos de la Ciudad de Nueva York, sujetos a los [NYC.gov Terms of Use](https://www.nyc.gov/home/terms-of-use.page): uso libre, sin garantía de exactitud y sin respaldo de la ciudad a los análisis de terceros. Detalle y cita sugerida en [`docs/fuentes.md`](docs/fuentes.md). |
| Qué se versiona | Solo agregados (`reports/`) y 5 filas grabadas de la API para las pruebas. Los datos crudos (93 MB) se descargan con `python descargar_datos.py`. |
| Licencia | El **código** es [MIT](LICENSE) (© 2026 Erick Guarnizo). Los **datos** siguen los términos de NYC Open Data. Las cifras son cálculo propio, no estadísticas oficiales. |

---

## 2. Hallazgos

### 2.1 Evento, censura y calidad de datos

* **Evento** = la solicitud tiene `status = Closed` y una `closed_date` no posterior al corte. **Censura** = cualquier otro caso: al corte seguía abierta y solo sabemos que tardó **al menos** `corte − creación`.
* La censura es **administrativa**: solo la produce la fecha de corte; ninguna solicitud se «pierde» antes. Por eso es no informativa (supuesto clave de Kaplan-Meier y Cox) y un resultado como «¿cerró en ≤ 7 días?» está observado para toda la cohorte, que termina 26 días antes del corte.
* De 7.559.591 filas quedan **7.544.678**: 7.342.811 cierres y **201.867 censuradas (2,68 %)**.

| Problema | Casos | Decisión |
| :--- | ---: | :--- |
| Cierre antes de la apertura (fecha imposible) | 2.082 | Se descartan (el 93 % son de DOT y DEP) |
| `Closed` sin fecha de cierre | 12.831 | Se descartan: sabemos que cerró, no cuándo |
| Fecha de cierre pero estado abierto (probablemente reabiertas) | 18.724 | Censura al corte: manda el estado |
| Cierre posterior al corte | 34 | Censura al corte |
| Cierre instantáneo (duración 0) | 119.871 | Se conservan y se marcan: son cierres administrativos reales |
| ZIP nulo o fuera de NYC · borough sin dato | 63.542 · 6.475 | Se conservan; solo salen de los análisis territoriales |
| `unique_key` duplicado | 0 | — |

![Calidad y censura](reports/figures/01_calidad_y_censura.png)

### 2.2 Por qué no usar el promedio de las cerradas

El promedio de las solicitudes cerradas tiene **dos** problemas: (1) **descarta las abiertas**, que son justamente las lentas, y (2) aun sin censura, la distribución tiene una cola enorme (59,1 % se cierra en un día, pero hay casos de meses), así que la media no representa al caso típico. Tratar las abiertas como «cerradas al corte» tampoco sirve: las acorta.

**Experimento de corte retrospectivo.** Para no depender de una simulación, se tomó la cohorte creada en oct–dic 2024 y se reconstruyó lo que habríamos visto si la descarga se hubiera hecho el **2025-01-15**. Se compara con la «verdad» que conocemos hoy, casi sin censura:

| Agencia | Solicitudes | Abiertas al corte ficticio | Mediana ingenua | Mediana KM | Mediana real | Promedio ingenuo | Promedio real |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Todas las agencias | 907.223 | 7,0 % | 9,1 h | **13,4 h** | 13,4 h | 3,5 días | 11,6 días |
| NYPD | 400.222 | 0,0 % | 1,6 h | **1,6 h** | 1,6 h | 3,8 h | 3,8 h |
| HPD | 235.836 | 10,0 % | 2,7 días | **3,0 días** | 3,0 días | 5,7 días | 14,8 días |
| DSNY | 73.806 | 2,3 % | 1,3 días | **1,3 días** | 1,3 días | 3,3 días | 4,6 días |
| DOT | 45.888 | 6,2 % | 1,8 días | **2,1 días** | 2,1 días | 4,9 días | 12,8 días |
| DOHMH | 19.811 | 14,9 % | 1,0 días | **2,6 días** | 2,6 días | 20,6 días | 25,6 días |
| DOB | 25.709 | 34,5 % | 2,5 días | **14,2 días** | 14,2 días | 11,1 días | 78,0 días |
| DPR | 21.559 | 40,8 % | 4,6 días | **27,2 días** | 27,2 días | 13,0 días | 78,0 días |
| TLC | 10.260 | 46,4 % | 25,6 días | **46,5 días** | 51,0 días | 26,0 días | 63,2 días |
| EDC | 7.823 | 94,7 % | 25,8 días | **no alcanzada** | 171,0 días | 25,7 días | 142,1 días |

* Donde hay mucha censura, la mediana ingenua se queda muy corta (DOB: 2,5 días frente a 14,2 días reales) y **Kaplan-Meier la recupera** (14,2 días). El promedio ingenuo es aún peor: 11,1 días frente a 78,0 días.
* Con la Corporación de Desarrollo Económico (EDC), el 95 % seguía abierto: Kaplan-Meier responde **«mediana no alcanzada»**, que es lo honesto. El promedio ingenuo (25,7 días) inventa una respuesta; la real era 171,0 días.
* En NYPD, con casi cero censura, todos los métodos coinciden: el sesgo aparece solo donde hay censura.

### 2.3 Kaplan-Meier por agencia, tipo de queja, borough y canal

Las 10 agencias con más solicitudes (IC 95 % de la mediana por el método de Brookmeyer-Crowley sobre la banda log(−log)):

| Agencia | Solicitudes | % censuradas | Mediana KM (IC 95 %) | Cerradas en 7 días | En 30 días | Promedio ingenuo |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: |
| NYPD | 3.404.989 | 0,0 % | **1,3 h** (1,3 h – 1,3 h) | 100,0 % | 100,0 % | 3,0 h |
| HPD | 1.647.990 | 2,0 % | **4,0 días** (4,0 días – 4,0 días) | 61,6 % | 85,5 % | 14,9 días |
| DSNY | 686.984 | 1,1 % | **1,5 días** (1,5 días – 1,5 días) | 88,8 % | 96,6 % | 3,6 días |
| DOT | 489.985 | 4,7 % | **2,5 días** (2,4 días – 2,5 días) | 68,3 % | 89,9 % | 9,4 días |
| DEP | 427.705 | 1,7 % | **23,4 h** (23,3 h – 23,5 h) | 83,2 % | 96,0 % | 4,5 días |
| DPR | 250.070 | 23,1 % | **19,0 días** (18,8 días – 19,4 días) | 38,8 % | 55,1 % | 41,5 días |
| DOB | 220.866 | 6,3 % | **11,7 días** (11,5 días – 12,2 días) | 44,9 % | 60,9 % | 46,7 días |
| DOHMH | 169.211 | 6,4 % | **5,1 días** (5,0 días – 5,3 días) | 52,1 % | 62,5 % | 22,6 días |
| DHS | 88.289 | 2,5 % | **7,7 h** (7,6 h – 7,8 h) | 87,0 % | 93,4 % | 4,1 días |
| TLC | 75.493 | 34,2 % | **122,5 días** (120,0 días – 124,7 días) | 18,4 % | 27,8 % | 80,6 días |

![Kaplan-Meier por agencia](reports/figures/03_kaplan_meier_agencias.png)

* **Canal:** por app móvil la mediana es 2,2 h y por web 6,1 h, frente a 1,9 días por teléfono. No es que el teléfono «funcione peor»: el 40 % de lo que llega por teléfono son quejas de vivienda (HPD), que tardan días, frente al 7 % en la app, donde el 77 % son asuntos policiales que se cierran en horas. El modelo de Cox separa ambos efectos (sección 2.4).
* **Borough sin ajustar:** Queens 5,4 h, Brooklyn 8,2 h, Bronx 12,0 h, Manhattan 14,2 h, Staten Island 16,5 h. Manhattan aparece entre los más lentos por su mezcla de quejas, y este orden cambia al ajustar.

![Kaplan-Meier por borough y canal](reports/figures/04_kaplan_meier_borough_y_canal.png)
![Medianas por tipo de queja](reports/figures/05_medianas_por_tipo_de_queja.png)

**Pruebas log-rank** (H0: misma curva en todos los grupos). Con millones de filas todo es «significativo»: la prueba descarta el azar, pero **el tamaño del efecto** se lee en las medianas y en los HR, no en el p-valor.

| Comparación | Grupos | χ² | gl | p-valor |
| :--- | ---: | ---: | ---: | ---: |
| agencia | 10 | 7.051.706 | 9 | < 1e-300 |
| tipo de queja | 21 | 6.128.322 | 20 | < 1e-300 |
| borough | 5 | 12.097 | 4 | < 1e-300 |
| canal | 4 | 834.874 | 3 | < 1e-300 |
| borough, dentro de Illegal Parking | 5 | 22.392 | 4 | < 1e-300 |
| borough, dentro de Noise - Residential | 5 | 56.252 | 4 | < 1e-300 |
| borough, dentro de HEAT/HOT WATER | 5 | 10.811 | 4 | < 1e-300 |
| borough, dentro de Street Condition | 5 | 1.390 | 4 | 1.3e-299 |
| borough, dentro de Rodent | 5 | 1.907 | 4 | < 1e-300 |

### 2.4 Modelo de Cox y supuesto de riesgos proporcionales

El «riesgo» es la tasa instantánea de **cierre**: **HR > 1 = se cierra más rápido** que la referencia; HR < 1, más lento. Se ajustan dos modelos con `lifelines` en una muestra aleatoria de 200.000 solicitudes:

* **Modelo A** (agencia + borough + canal + horario; C = 0,755): la agencia domina. Frente a NYPD, una solicitud de Parques tiene en cada momento un 97 % menos de probabilidad de cerrarse (HR 0,03); una de Vivienda (HPD), un 94 % menos (HR 0,06).
* **Modelo B** (estratificado por tipo de queja; C = 0,542): cada tipo de queja tiene su propio riesgo base, así que los boroughs se comparan **dentro del mismo tipo**. Su concordancia es baja a propósito: ya no «gana» prediciendo con el tipo de queja.

| Covariable (modelo B) | HR (IC 95 %) | Lectura de negocio |
| :--- | :--- | :--- |
| Creada en fin de semana | **0,98** (0,97–0,99) | en cada momento, 2 % menos probable cerrarse (más lento) |
| Creada de 22 h a 6 h | **1,06** (1,05–1,07) | en cada momento, 6 % más probable cerrarse (más rápido) |
| Borough Bronx | **0,87** (0,85–0,88) | en cada momento, 13 % menos probable cerrarse (más lento) |
| Borough Brooklyn | **0,94** (0,93–0,95) | en cada momento, 6 % menos probable cerrarse (más lento) |
| Borough Queens | **0,91** (0,90–0,92) | en cada momento, 9 % menos probable cerrarse (más lento) |
| Borough Staten Island | **1,04** (1,01–1,06) | en cada momento, 4 % más probable cerrarse (más rápido) |
| Canal App móvil | **0,96** (0,95–0,97) | en cada momento, 4 % menos probable cerrarse (más lento) |
| Canal Otro/desconocido | **0,79** (0,77–0,81) | en cada momento, 21 % menos probable cerrarse (más lento) |
| Canal Web | **1,04** (1,03–1,05) | en cada momento, 4 % más probable cerrarse (más rápido) |

Referencias: Manhattan, teléfono, día laborable de 6 h a 22 h.

![Hazard ratios](reports/figures/06_cox_hazard_ratios.png)

**¿Se cumple el supuesto de riesgos proporcionales (PH)? No del todo, y eso es un hallazgo.**

1. *Prueba de Grambsch-Therneau* (residuos de Schoenfeld escalados, 40.000 filas): en el modelo A, la mayor violación es `agencia=DEP` (χ² = 407,3), y 3 de las 5 mayores son agencias. Por eso el modelo B **estratifica** por tipo de queja en vez de estimar un HR por agencia. En el modelo B, la mayor es `borough=BRONX` (χ² = 21,5).
2. *Curvas log(−log S)* por borough: no son paralelas.
3. *HR por ventana de tiempo*: reestimando el modelo B solo con las solicitudes aún abiertas al inicio de cada ventana, el HR del Bronx pasa de **0,67** (0–1 d) a 1,08 (1–7 d), 1,29 (7–30 d) y **1,47** (> 30 d). **Lectura de negocio:** en el Bronx cuesta más que una queja se cierre en las primeras horas, pero entre las que siguen abiertas pasada una semana se cierran más rápido que en Manhattan. El HR global (0,87) es un promedio de ambas fases, dominado por el primer día, cuando ocurre la mayoría de los cierres.

![Supuesto PH](reports/figures/07_supuesto_riesgos_proporcionales.png)

### 2.5 Equidad territorial: ¿se atiende más lento en ciertos barrios?

Para una medida que no dependa del supuesto PH se usa **estandarización indirecta**: para cada solicitud, la probabilidad «esperada» de cerrarse dentro de un horizonte (1 hora, 8 horas, 1 día, 7 días) es la de toda la ciudad en su celda **tipo de queja × descriptor**. Un **O/E** (observado/esperado) menor que 1 significa que el borough o el ZIP cierra menos de lo que su mezcla de quejas predice.

| Borough | Solicitudes | Cerradas ≤ 7 d | Esperado ≤ 7 d | **O/E 7 d** (IC 95 %) | O/E ≤ 1 h | O/E ≤ 8 h | O/E ≤ 1 día |
| :--- | ---: | ---: | ---: | :--- | ---: | ---: | ---: |
| Brooklyn | 2.277.063 | 80,9 % | 81,2 % | **0,996** (0,995–0,996) | 1,057 | 1,008 | 0,986 |
| Bronx | 1.656.465 | 81,4 % | 81,6 % | **0,998** (0,998–0,999) | 0,822 | 0,954 | 1,004 |
| Queens | 1.829.773 | 83,3 % | 83,3 % | **1,000** (0,999–1,000) | 0,995 | 1,000 | 1,000 |
| Manhattan | 1.482.757 | 78,4 % | 78,1 % | **1,003** (1,003–1,004) | 1,129 | 1,031 | 1,014 |
| Staten Island | 292.145 | 80,9 % | 78,5 % | **1,030** (1,029–1,032) | 0,959 | 1,055 | 1,027 |

* **Sin ajustar, Manhattan parece el más lento** (78,4 % en 7 días); ajustado por su mezcla, está prácticamente en lo esperado. A 7 días el Bronx (O/E 0,998) y Brooklyn (0,996) quedan apenas por debajo, Manhattan apenas por encima (1,003) y Staten Island claramente por encima (1,030).
* **La brecha del Bronx está en las primeras horas:** su O/E es 0,822 a 1 hora, 0,954 a 8 horas y 1,004 a 1 día. Es el mismo patrón que muestran los HR por ventana del modelo de Cox, ahora sin el supuesto PH. Para un gerente, la pregunta útil no es «¿el Bronx es más lento?», sino «¿por qué la primera respuesta tarda más?» (una hipótesis por investigar, que estos datos no permiten confirmar: la carga de patrullas de NYPD en las horas pico de quejas de ruido).
* **Códigos postales:** de 181 ZIP con al menos 1.000 solicitudes, 114 se desvían de lo esperado con una tasa de falsos descubrimientos del 5 % (Benjamini-Hochberg): 56 más lentos y 58 más rápidos. Las desviaciones son pequeñas (90 % de los ZIP entre 0,980 y 1,025). 12 de los 58 ZIP más rápidos (21 %) están en Staten Island, que recibe apenas el 4 % de las solicitudes.

| ZIP | Borough | Solicitudes | Cerradas ≤ 7 d | Esperado | O/E |
| :--- | :--- | ---: | ---: | ---: | ---: |
| 10044 | Manhattan | 1.924 | 55,9 % | 63,4 % | **0,883** |
| 10037 | Manhattan | 22.180 | 69,1 % | 71,5 % | **0,966** |
| 10475 | Bronx | 10.764 | 75,9 % | 78,3 % | **0,969** |
| 10459 | Bronx | 55.257 | 72,6 % | 74,4 % | **0,976** |
| 11249 | Brooklyn | 29.366 | 79,0 % | 80,9 % | **0,977** |
| 10306 | Staten Island | 33.946 | 79,6 % | 77,3 % | **1,031** |
| 10308 | Staten Island | 13.842 | 78,6 % | 76,0 % | **1,034** |
| 10312 | Staten Island | 35.687 | 80,0 % | 77,3 % | **1,036** |
| 10301 | Staten Island | 33.706 | 81,6 % | 78,5 % | **1,039** |
| 10307 | Staten Island | 8.702 | 82,6 % | 79,2 % | **1,043** |

El ZIP más lento es el 10044 (O/E 0,883). Es Roosevelt Island: una isla residencial pequeña, con administración y accesos propios.

![Equidad territorial](reports/figures/08_equidad_territorial.png)

> **Correlación no es causalidad.** Un O/E bajo es compatible con menos recursos, pero también con casos más difíciles dentro de la misma celda (edificios más viejos, problemas recurrentes), con quejas repetidas que se cierran juntas, con diferencias en cómo cada agencia registra el «cierre» o con quién reporta (el 311 mide demanda reportada, no necesidad real). Sin datos socioeconómicos no se puede atribuir la diferencia a ingreso ni a composición del barrio.

### 2.6 Evolución en el tiempo: ¿mejora o empeora?

| Periodo | Mediana KM | Cerradas ≤ 7 días | O/E ajustado por mezcla |
| :--- | ---: | ---: | ---: |
| oct-2024 a sep-2025 | 8,0 h | 82,4 % | 1,011 |
| oct-2025 a sep-2026 | 10,0 h | 79,9 % | 0,990 |

* **Estacionalidad:** la mediana mensual sube cada invierno (máximo 28,3 h en 2026-01; mínimo 3,7 h en 2025-06) porque cambia la mezcla: las quejas de calefacción y agua caliente pasan del 1,0 % de las solicitudes (2025-07) al 22,9 % (2026-01), y se resuelven en días, no en horas.
* **Tendencia:** ajustando por la mezcla, el O/E mensual pasa de 1,032 (2024-10) a 0,967 (2026-08). El segundo año es un poco más lento, pero la diferencia es de unos pocos puntos.

| Agencia | Mediana año 1 | Mediana año 2 | Cambio |
| :--- | ---: | ---: | ---: |
| DOB | 14,3 días | 9,5 días | -34 % |
| DHS | 8,1 h | 7,4 h | -9 % |
| DEP | 23,9 h | 22,9 h | -4 % |
| DPR | 19,1 días | 19,0 días | -1 % |
| NYPD | 1,3 h | 1,3 h | +1 % |
| HPD | 3,7 días | 4,3 días | +18 % |
| DSNY | 1,3 días | 1,7 días | +27 % |
| DOT | 2,0 días | 2,9 días | +47 % |
| DOHMH | 1,1 días | 13,2 días | +1.101 % |

* **Cuidado con leer la tabla como desempeño:** el salto de Salud (DOHMH, de 1,1 días a 13,2 días) es sobre todo un **cambio de proceso**. Los cierres instantáneos de DOHMH bajaron del 31 % al 10 % (en roedores, del 60 % al 25 %), y el 72 % de las quejas de establecimientos de comida se cierra a los **60,0 días exactos**, un cierre administrativo por plazo (la caída vertical de la figura 03). El «tiempo hasta el cierre» mide el registro administrativo, no necesariamente la solución del problema.

![Evolución mensual](reports/figures/09_evolucion_mensual.png)

---

## 3. Arquitectura

```mermaid
flowchart LR
    A["API Socrata<br/>NYC Open Data 311<br/>(erm2-nwe9)"] -->|"$select · $where por mes<br/>$order + $offset · reintentos"| B["data/raw/paginas/<br/>AAAA-MM/pagina_*.parquet<br/>(caché reanudable)"]
    B --> C["nyc311_crudo.parquet<br/>7,5 M filas"]
    C --> D["limpieza.py<br/>validación · duración · censura"]
    D --> E["nyc311_supervivencia.parquet"]
    E --> F["supervivencia.py<br/>Kaplan-Meier · log-rank · RMST<br/>(numpy, validado con lifelines)"]
    E --> G["cox.py<br/>lifelines CoxPH · PH test<br/>HR por ventana"]
    E --> H["sesgo.py · equidad.py<br/>corte retrospectivo · O/E · FDR"]
    F & G & H --> I["reports/<br/>resultados.json · tablas · curvas"]
    I --> J["graficos.py<br/>figuras PNG"]
    I --> K["cifras_readme.py<br/>README y guía"]
    I --> L["app Streamlit"]
    I --> M["notebooks 01–04"]
```

## 4. Decisiones técnicas

| Decisión | Por qué |
| :--- | :--- |
| Kaplan-Meier y log-rank **propios** en numpy (`src/nyc311/supervivencia.py`) | Con 7,5 M de filas y duraciones al segundo hay millones de tiempos distintos. Agregar con `np.unique` + `np.bincount` y acumular el log-rank por bloques mantiene la RAM acotada. Las pruebas comprueban que coinciden con lifelines (diferencia < 1e-10) y con el ejemplo de libro de Freireich (χ² = 16,79). |
| `lifelines` para Cox, en una muestra de 200.000 | Ajustar Cox con empates (Efron) en 7,5 M de filas es lento y pesado. Con 200.000 filas los IC de los HR ya miden ±1–3 %, y el ajuste tarda unos 30 s. |
| Fecha de corte = última `created_date` publicada, fija en un manifiesto | El dataset se actualiza a diario: un cierre posterior a esa actualización aún no existe en la API. Usar el reloj local inflaría la duración de las abiertas. Fijarla en el manifiesto mantiene la definición aunque la descarga se reanude días después. |
| Estratificar por tipo de queja (modelo B) | La agencia y el tipo de queja violan PH con fuerza. Estratificar deja a cada tipo su propio riesgo base, sin imponerle forma, y compara boroughs dentro del mismo tipo. |
| HR por ventana con truncamiento por la izquierda (`entry_col`) | Muestra **cómo** se viola PH en lenguaje de negocio, en lugar de solo reportar un p-valor que, con este n, siempre es ≈ 0. |
| O/E con estandarización indirecta a 7 días | Es una medida de equidad sin supuesto PH, comprensible para gestión, y sin sesgo por censura: el resultado está observado para todas las solicitudes. |
| Benjamini-Hochberg para los ZIP | Con 181 comparaciones, un umbral de 5 % sin corregir produciría unos 9 falsos positivos por azar. |
| README y guía generados desde `reports/` | Ninguna cifra se escribe a mano; `tests/test_cifras_readme.py` falla si el texto se desfasa de los resultados. |

## 5. Limitaciones

* **El «cierre» es administrativo.** Algunas agencias cierran por plazo (comida a los 60 días), derivan (cierres instantáneos) o cierran en bloque. Un cambio de proceso mueve la mediana sin que cambie la atención real (sección 2.6).
* **Observacional, no causal.** Cox y O/E controlan el tipo de queja, el canal y el horario, pero no la gravedad dentro de cada tipo, la antigüedad de los edificios ni los recursos de cada distrito.
* **Supuesto PH violado parcialmente.** Los HR globales son promedios en el tiempo; las conclusiones de equidad se apoyan también en el O/E y en los HR por ventana.
* **Reaperturas.** Las 18.724 solicitudes con fecha de cierre y estado abierto se tratan como censuradas. Si en realidad hubo un primer cierre, se subestima un poco la rapidez de esas agencias.
* **Cohortes recientes.** Los meses de 2026 tienen menos seguimiento. Kaplan-Meier lo maneja, pero si alguna agencia registra cierres con retraso, los últimos meses se verían algo más lentos.
* **Cox en muestra.** Los HR provienen de 200.000 solicitudes (semilla fija); los demás resultados usan todas.

## 6. Cómo reproducir

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
pip install -e .

python descargar_datos.py         # ~15 min, 93 MB; reanudable si se corta
python -m nyc311.pipeline         # ~5 min, pico de ~4 GB de RAM: limpieza, análisis, tablas y figuras
python -m nyc311.cifras_readme    # regenera README y guía desde reports/
python scripts/crear_notebooks.py
jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
pytest -q                         # pruebas (no usan red)
streamlit run app/streamlit_app.py
```

La app solo lee archivos versionados de `reports/tablas/`, así que funciona sin descargar los datos.

## 7. Estructura

```
├── descargar_datos.py            # descarga reanudable (envoltorio de nyc311.descarga)
├── src/nyc311/
│   ├── descarga.py               # API Socrata: paginación, reintentos, caché, manifiesto
│   ├── limpieza.py               # validación, evento y censura
│   ├── supervivencia.py          # Kaplan-Meier, IC, mediana, RMST, log-rank
│   ├── sesgo.py                  # experimento de corte retrospectivo
│   ├── cox.py                    # Cox A/B, prueba PH, HR por ventana
│   ├── equidad.py                # O/E estandarizado, Benjamini-Hochberg
│   ├── pipeline.py · graficos.py · cifras_readme.py · etiquetas.py · config.py
├── notebooks/                    # 01 ingesta y calidad · 02 Kaplan-Meier · 03 Cox · 04 hallazgos
├── app/streamlit_app.py          # curva por tipo de queja y borough
├── reports/                      # resultados.json, tablas/, figures/
├── scripts/                      # plantillas del README y generador de notebooks
├── tests/                        # pytest (respuestas grabadas de la API en tests/datos/)
└── docs/                         # GUIA_PASO_A_PASO.md · fuentes.md
```
