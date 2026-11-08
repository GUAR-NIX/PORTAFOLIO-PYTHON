# Guía paso a paso — Sismicidad del Ecuador y el Cinturón de Fuego

Esta guía explica cómo correr el proyecto, qué hace cada pieza y cómo defenderlo en una entrevista.
Todas las cifras salen de `reports/resultados.json` y de los CSV de `reports/`.

---

## 1. Preparar el entorno (Windows, Python 3.14)

```bash
cd sismicidad-ecuador-usgs
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .            # instala el paquete src/sismos en modo editable
```

## 2. Descargar los datos (reanudable)

```bash
python descargar_datos.py
```

* Baja tres catálogos del USGS: Ecuador ampliado M≥2,5 1970–2025 (56 consultas, una por año), mundo M≥5
  1973–2025 (53 consultas) y Ecuador M≥6 1900–2025 (6 consultas de 25 años). Más tres capas GeoJSON para los mapas.
* Cada respuesta queda en `data/raw/usgs/<catálogo>/<inicio>_<fin>.csv`. **Si se corta** (apagón, internet),
  vuelve a correr el mismo comando: lo que está en caché no se pide otra vez.
* Pausa de 1 s entre llamadas y reintentos con espera creciente (respeta `Retry-After` en 429/503).
* Si un año tuviera más de 20 000 eventos, el cliente lo parte en mitades hasta que cada trozo quepa.
* `reports/log_descarga.csv` registra cuántas consultas fueron a la red y cuántas salieron de caché.

## 3. Ejecutar el análisis

```bash
python -m sismos.pipeline --sin-descarga   # ~10 s
```

Orden interno (`src/sismos/pipeline.py`):

1. **Calidad** (`calidad.py`): solo `type == earthquake`, duplicados por `id` y casi duplicados (<16 s, <50 km),
   profundidad fija marcada, **mb/Ms → Mw** con Scordilis (2006) repartiendo cada magnitud en su clase de 0,1.
2. **Exploratorio**: sismos por año, histogramas, mapa por profundidad, corte este–oeste.
3. **Gutenberg-Richter** (`gutenberg_richter.py`): Mc por máxima curvatura (+0,2) y por estabilidad de b (MBS);
   b de Aki-Utsu con IC de Shi-Bolt y bootstrap; mínimos cuadrados como línea base; 13 zonas del Cinturón.
4. **Periodos de retorno** (`retorno.py` + `desagrupar.py`): Gardner-Knopoff, Poisson, bootstrap; conteos como línea base.
5. **Omori-Utsu** (`omori.py`): réplicas a ≤150 km en 365 días; máxima verosimilitud; comparación por AIC.

Salidas: `data/procesados/*.parquet`, `reports/resultados.json`, `reports/*.csv`, `reports/figures/01–13`.

## 4. Pruebas, notebooks y app

```bash
pytest                                                        # 38 pruebas, sin internet
jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
streamlit run app/streamlit_app.py                            # o ?region=Japón en la URL
```

* `tests/test_cliente_usgs.py`: paginación con **respuestas reales grabadas** en `tests/grabadas/` (una semana de
  abril de 2016, el error 400 real de "exceeds search limit" y una respuesta vacía). Una sesión HTTP falsa imita
  al servidor: filtra por fechas y responde el 400 si se supera el límite. Prueba caché, partición, reintentos
  ante 503/429 y que no quede nada a medias en caché si todo falla.
* `tests/test_estadistica.py`: el estimador de b recupera b = 0,8 / 1,0 / 1,3 en catálogos simulados; la
  cobertura del IC 95 % está entre 90 % y 99 % en 200 simulaciones; MAXC subestima Mc con una rampa de
  detección y MBS lo acierta; Omori-Utsu recupera p con datos simulados y le gana al exponencial; Gardner-Knopoff.
* `tests/test_calidad.py`: familias de magnitud, fórmulas de Scordilis, duplicados, casi duplicados, explosiones.
* `tests/test_app.py`: la app corre y los filtros (región, años, magnitud) cambian los resultados.

## 5. Cómo leer los resultados en 1 minuto

* **Dónde:** 58 % superficial en la costa (interfaz), 42 % intermedio bajo los Andes (placa de Nazca hundida).
* **Valor b:** 0,85 [0,72–0,97] con Mc = 5,6. Con Mc = 5,0 sale 1,30, pero es un artefacto de la mezcla mb/Mw
  y contradice el conteo real de M≥7.
* **Cinturón:** Ecuador tiene el b más bajo de 13 zonas (0,88 con M≥5,5); Tonga el más alto (1,42).
* **Retorno:** M≥7 en la región cada 5,0 años [3,3–8,5] (18 % al año); M≥7 superficial cada 10,4 años.
  Conteo real: 16 M≥7 en 1970–2025, 25 en 1900–2025.
* **Pedernales:** p = 0,91 ± 0,08 (compatible con 1); 53 % de las réplicas en la primera semana; ΔAIC = 80 contra
  el exponencial.

---

## 6. Preguntas de entrevista (con respuesta)

**1. ¿Qué es la ley de Gutenberg-Richter y qué significa el valor b?**
log10 N(≥M) = a − b·M: el número de sismos cae exponencialmente con la magnitud. Con b = 1, por cada sismo
M≥7 hay unos 10 de M≥6 y 100 de M≥5. Un b bajo (como el del Ecuador, 0,85) indica proporcionalmente más
sismos grandes; se asocia a zonas con esfuerzos altos. `a` mide la productividad total de la región.

**2. ¿Por qué estimaste b por máxima verosimilitud y no con una regresión?**
La regresión sobre log N acumulado tiene dos problemas: los puntos acumulados no son independientes (cada uno
contiene a los siguientes), así que su error estándar no vale, y los puntos de magnitud alta con 1–2 sismos
pesan igual que los de miles. El estimador de Aki (b = log10 e / (media − Mc + ΔM/2)) es el de máxima
verosimilitud para una distribución exponencial, tiene error conocido (Shi-Bolt) y lo validé con catálogos
simulados: recupera el b real y su IC cubre el 90–99 % de las veces.

**3. ¿Qué es la magnitud de completitud y cómo la elegiste?**
Es la magnitud desde la cual el catálogo registra todos los sismos. Debajo, la red no detecta todo y la
distribución se aplana. Usé máxima curvatura + 0,2 (el método estándar) y la estabilidad de b (MBS). En el
Ecuador dieron 5,0 y 5,6. Me quedé con 5,6 porque con 5,0 el b no es estable y la recta predice un M≥7 cada
15,5 años cuando en realidad hubo 16 en 56 años. Validé con simulaciones que MAXC subestima Mc cuando la
detección cae en rampa.

**4. ¿Por qué cambia tanto b entre M5,0 y M5,6?**
Porque el catálogo mezcla escalas: el 83 % de los sismos viene en mb (ondas de cuerpo) y los grandes en Mw.
mb se satura y no es lineal con Mw; aun convirtiendo con Scordilis (Mw = 0,85·mb + 1,03) la distribución se
quiebra donde termina el dominio de mb. Es un problema real de los catálogos y la lección es: **no confiar en
un solo Mc**, mirar la curva de b contra Mc y contrastar con una línea base.

**5. ¿Por qué repartiste las magnitudes dentro de su clase antes de convertir?**
mb viene redondeada a 0,1. Al multiplicar por 0,85, a veces dos valores de mb caen en la misma clase de Mw y
otras ninguno: aparecen picos y huecos falsos en el histograma, y la máxima curvatura elige el pico falso.
Sumar un ruido uniforme de ±0,05 (con semilla fija) antes de convertir reconstruye una distribución continua
sin cambiar la media.

**6. ¿Cómo calculaste el periodo de retorno y qué supuestos tiene?**
Con la recta de Gutenberg-Richter: λ(M≥7) = λ(M≥Mc)·10^(−b(7−Mc)), periodo = 1/λ, y la probabilidad de al
menos uno en t años = 1 − e^(−λt) (Poisson). Supone sismos independientes (por eso desagrupé con
Gardner-Knopoff), tasa constante en el tiempo y que la recta se puede extrapolar hasta M7. El IC sale de un
bootstrap que remuestrea las magnitudes (incertidumbre de b) y el número de sismos (Poisson).

**7. ¿Entonces se puede decir que habrá un M7 en los próximos 5 años?**
No. "Cada 5 años en promedio" es una frecuencia de largo plazo para una región de 9° × 8°. El modelo de
Poisson no tiene memoria: la probabilidad en un año dado es 18 %, haya habido o no un sismo reciente. La
estadística sísmica **no predice** el momento ni el lugar; sirve para dimensionar el peligro (normas de
construcción, seguros, planes de emergencia).

**8. ¿Cuál fue tu línea base y qué te enseñó?**
Dos: (a) contar los M≥6 y M≥7 y dividir por los años (con IC exacto de Poisson), y (b) mínimos cuadrados para b.
El conteo fue clave: con Mc = 5,0 el modelo daba 15,5 años para M≥7 y el conteo 3,5 años, lo que delató el
problema del Mc. En las 13 zonas del Cinturón, extrapolar desde M5,5 subestimó los M≥7 en 12 (mediana ×1,38).

**9. ¿Qué es la ley de Omori-Utsu y qué encontraste en Pedernales?**
La tasa de réplicas decae como λ(t) = K/(t + c)^p. La ajusté por máxima verosimilitud de un proceso de Poisson
no homogéneo (Ogata, 1983): log L = Σ log λ(tᵢ) − ∫λ dt. Para Pedernales p = 0,91 ± 0,08, compatible con 1;
el AIC prefiere incluso el modelo con p = 1 fijo (no hace falta el parámetro extra). El decaimiento exponencial
pierde por 80 puntos de AIC. El 53 % de las réplicas M≥4,9 del año llegó en la primera semana.

**10. ¿Por qué desagrupar el catálogo y qué hace Gardner-Knopoff?**
Las réplicas no son independientes: inflan la tasa (con réplicas, la de M≥6 sube un 34 %) y rompen el
supuesto de Poisson. Gardner-Knopoff recorre los sismos de mayor a menor y marca como réplicas o premonitores
a los menores que caen en una ventana de distancia y tiempo que crece con la magnitud (para M7,8: ~90 km y
~2,7 años). En el Ecuador quitó el 48 % de los eventos.

**11. ¿Cómo manejaste el límite de 20 000 eventos y los cortes de internet?**
Una consulta por año (la más grande, el mundo M≥5, trae ~2 700). Si la API responde el 400 de "exceeds search
limit" o la página llega llena, el intervalo se parte en dos recursivamente. Cada respuesta se escribe en un
temporal y se renombra (escritura atómica), así un corte no deja un CSV a medias, y volver a correr solo pide
lo que falta. Lo probé con respuestas grabadas, sin internet.

**12. ¿Qué limitaciones tiene el análisis?**
El catálogo mundial solo es completo desde M~5 en el Ecuador (el IG-EPN tiene mucho más detalle, pero sin API
abierta); la conversión de magnitudes es global, no regional; la caja incluye partes de Perú y Colombia;
extrapolar a M7–M8 ignora la magnitud máxima de cada falla; y Gardner-Knopoff es una aproximación (ETAS sería
el siguiente paso). Nada de esto es un análisis de peligro sísmico para diseño.

**13. ¿Por qué la app usa pydeck y no Plotly?**
En el Streamlit 1.66 que instala Python 3.14, `st.plotly_chart` y los gráficos Altair con capas no se dibujan
en el navegador (las pruebas automáticas no lo detectan). pydeck sí funciona y además dibuja miles de puntos
con WebGL. Para el Pacífico, que cruza el meridiano 180°, paso las longitudes este a negativas para que el
cinturón quede continuo.
