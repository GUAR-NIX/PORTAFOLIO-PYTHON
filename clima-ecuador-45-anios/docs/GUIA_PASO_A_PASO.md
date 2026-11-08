# Guía paso a paso (Windows)

El proyecto **ya viene ejecutado**: notebooks con resultados, figuras, reportes, capturas y las tablas que usa la app. Esta guía es para volver a correrlo, por ejemplo para demostrarlo en una entrevista.

## 1 · Requisitos (una sola vez)

* **Python 3.10 o superior** (probado con 3.14). Al instalarlo desde python.org marca ✅ *Add python.exe to PATH*.
* Internet para la descarga (~120 MB de ERA5 leídos por partes de archivos mucho más grandes). Nada pide clave ni cuenta: ni la API de Open-Meteo, ni AWS Open Data, ni NOAA.
* ~1 GB libre (datos crudos, serie horaria y entorno) y unos 4 GB de RAM libres para el pipeline.

```powershell
python --version
```

## 2 · Crear el entorno e instalar dependencias (3–5 min)

```powershell
cd clima-ecuador-45-anios
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

> Si PowerShell bloquea la activación, ejecuta una vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 3 · Ver la app (sin descargar nada)

```powershell
streamlit run app\streamlit_app.py
```

Se abre en `http://localhost:8501`. Prueba: **Quito** con temperatura media (+0,33 °C/década, significativa); cambia a **Puerto Ayora** (sin tendencia: manda El Niño); elige **Guayaquil** con lluvia y mira la correlación con El Niño. También puedes abrir `http://localhost:8501/?ciudad=Cuenca&variable=precip&desde=1990&hasta=2024`. Para cerrarla: **Ctrl + C**.

## 4 · Descargar los datos (20–40 min la primera vez)

```powershell
python descargar_datos.py
```

Hace, en orden:

1. Una llamada a la API de Open-Meteo para saber qué celda de ERA5 usa para cada uno de los 30 puntos (`data\procesados\celdas_era5.csv`).
2. ONI y Niño 1+2 (NOAA PSL), 8 estaciones GHCN-Daily (NOAA NCEI) y los límites provinciales (geoBoundaries).
3. Una muestra diaria de la API (2015 y 2023, 22 ciudades, con pausas de 1,5 s) para verificar la agregación.
4. **ERA5 horario 1980–2024** desde `s3://openmeteo`: 7 variables × 95 bloques = 665 archivos Parquet en `data\raw\era5\`.

**Se puede cortar y reanudar**: los bloques ya guardados y legibles se saltan; uno a medio escribir se vuelve a bajar. Al reanudar verás algo como `ERA5: 665 bloques, 643 ya en caché, 22 por bajar`. Para renovar todo: `python descargar_datos.py --forzar`.

## 5 · Ejecutar el análisis (~50 s)

```powershell
python -m clima_ecuador.pipeline --sin-descarga
```

Debe terminar con:

```
Horario: 11,834,820 filas · 30 puntos · 209 horas de viento espurio anuladas
Listo en 50 s · 493,110 días-punto · tendencia nacional Tmed 0.24 °C/década
```

Regenera `data\interim\era5_horario.parquet` (140 MB, no se versiona), las tablas de `data\procesados\`, las 18 figuras, 28 CSV y `reports\resultados.json` (todas las cifras del README salen de ahí). Si falla un control crítico (huecos, valores fuera de rango, Tmín > Tmáx) el pipeline se detiene con un `AssertionError`.

## 6 · Pruebas

```powershell
pytest
```

Resultado esperado: `42 passed`. Incluyen:

* **Contraste con `pymannkendall`**: mi Mann-Kendall, Hamed-Rao y Yue-Wang dan el mismo S, varianza, p y pendiente de Sen.
* Una simulación con ruido rojo: el test original rechaza > 15 % de las veces una serie **sin** tendencia; Hamed-Rao, menos.
* Datos sintéticos de respuesta conocida: +0,3 °C/década, olas de calor de 5 días, rachas secas de 20 días, la lluvia de medianoche asignada al día anterior, el rezago de 3 meses con el ONI.
* Controles sobre los datos reales (16 437 días por punto, Guayaquil más cálido que Quito, igualdad con la API) y dos pruebas de humo de la app.

## 7 · Notebooks

```powershell
jupyter notebook notebooks
```

Ya están ejecutados. Para volver a correrlos: `jupyter nbconvert --to notebook --execute --inplace notebooks\*.ipynb`.

## 8 · Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `429` o "Daily API request limit exceeded" | La API gratuita permite 10 000 llamadas ponderadas por día por IP. Solo la muestra la usa (~800); espera al día siguiente o salta ese paso: el análisis principal no depende de la API |
| La descarga de S3 se queda lenta | Es lectura por rangos HTTP; vuelve a ejecutar `descargar_datos.py`, retoma donde quedó |
| `FileNotFoundError: No hay bloques de …` | Falta la descarga: corre el paso 4 |
| La app no muestra gráficos | Usa Chrome o Edge actualizados; la app solo usa gráficos de una capa (Altair) y matplotlib |

---

## 🎤 Preguntas de entrevista (con respuesta)

**1. ¿Por qué no usaste la API de Open-Meteo para todo, como pedía la idea inicial?**
Porque la API gratuita pondera las peticiones: `ubicaciones × días/14 × variables/10`. 45 años × 22 ciudades × 7 variables son unas 25 000 llamadas, más del doble del límite diario de 10 000, que además comparte toda la IP. Open-Meteo publica el mismo ERA5 en AWS Open Data en su formato `.om`, organizado por bloques espaciales y temporales; con `omfiles` y `s3fs` leo solo los bytes de cada punto. La API la usé para lo que es buena: saber qué celda elige para cada ciudad y verificar mi agregación.

**2. ¿Cómo sabes que tu agregación diaria es correcta?**
La comparé con la API diaria en 16 060 días (22 ciudades × 2 años) pidiendo exactamente la misma celda: la lluvia y la radiación dan **cero de diferencia** y la temperatura media 0,025 °C, que es el redondeo de la API. Al principio la lluvia no cuadraba: la lluvia de la hora *t* es la de la hora que **termina** en *t*, así que el día suma de 01:00 a 24:00, no de 00:00 a 23:00. Hay una prueba automática que fija esa convención.

**3. ¿Qué es la autocorrelación y por qué importa en Mann-Kendall?**
Que el valor de un año se parezca al del anterior. El test original supone años independientes; si no lo son, subestima la varianza del estadístico S y declara significativas tendencias que pueden ser rachas. Hamed y Rao calculan un tamaño de muestra efectivo con la autocorrelación de los rangos de la serie sin tendencia. En este proyecto quitó la significancia a Salinas y Portoviejo.

**4. ¿Por qué pusiste un piso de 1 al factor de Hamed-Rao?**
Porque con autocorrelación negativa (en Galápagos, por el ciclo de 3–7 años de El Niño) el factor baja de 1 y el test se vuelve *más* permisivo que el original: Tmín de Puerto Ayora pasaría de p = 0,49 a p = 0,07. La corrección tiene sentido para no sobrestimar la evidencia, no para fabricarla. Yue-Wang daba un factor de 0,50 en Quito por la misma razón.

**5. ¿Por qué pendiente de Sen y no una regresión lineal?**
Sen es la mediana de las pendientes entre todos los pares de años: no supone errores normales y un año extremo (1997-98) no la arrastra. Su intervalo de confianza sale de la misma varianza del Mann-Kendall, así que pendiente y significancia son coherentes.

**6. Tienes 22 ciudades y 7 variables. ¿No encontrarás algo "significativo" por azar?**
Sí, por eso aplico Benjamini-Hochberg (tasa de falsos descubrimientos) por variable. Las 18 ciudades con calentamiento significativo lo siguen siendo tras la corrección.

**7. ¿Cómo distingues un calentamiento real de un salto artificial del reanálisis?**
Un cambio en los datos que asimila ERA5 (nuevos satélites, por ejemplo) puede crear un escalón. Usé el test de Pettitt, pero con cuidado: con una tendencia lineal Pettitt siempre encuentra un "cambio" a la mitad. Por eso lo apliqué también a la serie sin la recta de Sen: ninguna ciudad tiene un salto significativo.

**8. ¿Por qué los umbrales de las olas de calor son distintos en cada ciudad?**
Por dos razones: 30 °C es normal en Guayaquil y extremo en Quito, y ERA5 tiene sesgos absolutos de hasta 5 °C. Con el percentil 90 de cada ciudad y día del año en 1981–2010 (índices ETCCDI), el sesgo constante se cancela: medimos si hay más días "inusualmente cálidos para ese lugar".

**9. ¿Qué encontraste con El Niño que no esperabas?**
Que el ONI, el índice que citan las noticias, explica mal la lluvia de la Costa. En 2015-16 el ONI fue récord (2,59) y la Costa tuvo lluvia normal; en 1997-98 llovió cuatro veces lo normal. Lo que manda es la temperatura del mar frente a la costa (Niño 1+2): r = 0,84 con la lluvia de enero a abril, frente a 0,43 con el ONI. La Sierra, en cambio, responde al ONI y se seca con El Niño.

**10. ¿Por qué corriges las correlaciones con un "tamaño de muestra efectivo"?**
Porque 540 meses de ONI y de anomalías de temperatura están muy autocorrelacionados: equivalen a unos 35–100 datos independientes. Con el p clásico casi todo sale significativo; con el de Bretherton et al., la relación entre El Niño y la lluvia amazónica deja de serlo (p 0,035 → 0,13).

**11. ¿Se puede confiar en ERA5 en el Ecuador?**
Depende del uso. Lo validé contra 8 estaciones de NOAA: las anomalías diarias de temperatura se siguen razonablemente bien (r 0,39–0,71), así que sirve para variabilidad y extremos relativos. Lo que no pude contrastar con las estaciones es la pendiente de largo plazo (ninguna tiene 10 años con datos suficientes), así que las tendencias son las del reanálisis. Los valores absolutos no: aplana el ciclo diario en la montaña (Izobamba: Tmáx −2,9 °C y Tmín +2,4 °C) y en Galápagos la celda es mar (−5,1 °C en Tmáx). La lluvia falla en cantidad (×0,3 a ×4,6) y llueve casi todos los días en los Andes. Por eso no reporto tendencias de días secos en la Sierra como resultado firme.

**12. Encontraste picos de viento de 255 km/h. ¿Cómo decidiste que eran errores?**
Con una regla física, no estadística: el viento medio de una hora no puede superar la ráfaga máxima de esa hora. En 209 horas lo superaba por más de 20 km/h, con ráfagas de 10–20 km/h, y 195 de ellas caían a las 08–09 UTC: un patrón horario así no es meteorología, es un artefacto. Anulé solo esas horas y lo documenté; la API de Open-Meteo los sigue sirviendo (por eso su viento máximo diario correlaciona 0,988 y no 1 con el mío).

**13. ¿Qué harías con más tiempo?**
Usar ERA5-Land (0,1°) para temperatura y CHIRPS para lluvia, conseguir las series del INAMHI para validar con más estaciones y corregir sesgos por cuantiles, y probar si el pulso de lluvia amazónica de 2017–2019 es real comparándolo con CHIRPS o con caudales de ríos.
