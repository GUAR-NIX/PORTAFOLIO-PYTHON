<!-- Archivo generado por `python -m empleo_enemdu.cifras_readme` desde scripts/plantillas/GUIA_PASO_A_PASO.md.
     No lo edites a mano: cambia la plantilla y vuelve a generarlo. Todas las cifras salen de reports/. -->
# Guía paso a paso y preparación para entrevista · `mercado-laboral-ecuador-enemdu`

Esta guía explica las decisiones estadísticas y de ingeniería del estudio **Mercado laboral del Ecuador con encuesta ponderada (INEC ENEMDU anual 2025)** y termina con preguntas de entrevista técnica con su respuesta.

---

## 1. Paso 1: ingesta reproducible y auditoría de códigos centinela (`descarga.py` y `limpieza.py`)

### 1.1 Fuentes oficiales del INEC
[`descargar_datos.py`](../descargar_datos.py) descarga de forma idempotente (con TLS verificado, reintentos y comprobación obligatoria del SHA-256) los cuatro paquetes de la ENEMDU anual 2025; las URL y sumas de control están en [`fuentes.md`](fuentes.md):
1. **`2_BDD_DATOS_ABIERTOS_ENEMDU_2025_CSV.zip`**: microdatos de personas (`334.786` filas) y de vivienda/hogar (`104.738` hogares).
2. **`ENEMDU_Tabulados_anual_2025-CSV.zip`**: tabulados oficiales (estimación, error estándar, IC y CV) de Mercado Laboral, Vivienda, Educación y Pobreza, con la serie 2018–2025.
3. **`Diccionario_de_variables.zip`**: diccionario y metadatos de variables.
4. **`Sintaxis_anual_2025.zip`**: sintaxis SPSS oficial (`00 Indicadores de Mercado Laboral.sps`, `01 Variables para tabulados.sps`, `02 Tabulados de publicación.sps`), de donde se tradujeron las reglas de clasificación laboral.

### 1.2 Los códigos centinela
En encuestas de hogares los valores no declarados casi nunca vienen como `NULL`: se codifican con números extremos.
* En la ENEMDU 2025, `ingrl` vale **`999999`** cuando el ocupado no informa su ingreso (`480` casos) y **`-1`** cuando no tiene ingreso monetario (`1.471` casos).
* `df["ingrl"].mean()` sin limpiar da **`3.840,42 USD/mes`**; la media ponderada correcta es **`498,97 USD/mes`** (**`7,7` veces** menos).

### 1.3 Años de escolaridad (`p10a` nivel y `p10b` año aprobado)
La sintaxis 2025 incluida en el paquete no trae el cálculo de años de escolaridad, así que [`limpieza.py`](../src/empleo_enemdu/limpieza.py) implementa dos escalas y las documenta en sus docstrings:
* **Escala EGB (`escolaridad_egb`)**: Educación General Básica numerada de 1 a 10.
* **Escala clásica (`escolaridad`)**: primaria 1–6, secundaria 7–12, superior desde 13 y posgrado desde 18; es la que usan las regresiones de Mincer.

---

## 2. Paso 2: inferencia en muestras complejas con linealización de Taylor (`encuesta.py`)

### 2.1 Por qué no sirve el muestreo aleatorio simple (MAS)
La ENEMDU usa un diseño **probabilístico, estratificado y por conglomerados**:
1. **Estratos (`estrato = plan_muestreo`, `150`)**: dividen el país en dominios (ciudades autorrepresentadas y resto urbano/rural provincial). La estratificación **reduce** la varianza.
2. **Conglomerados (`upm = id_sector`, `7.780` UPM)**: se seleccionan sectores censales. Los hogares vecinos se parecen (correlación intraconglomerado $\rho > 0$), lo que **aumenta** la varianza frente a un MAS del mismo tamaño.
3. **Ponderación desigual (`fexp`)**: cada persona representa a $w_i$ habitantes.

### 2.2 Estimador de razón y su varianza
Para una tasa en el dominio $D$ (por ejemplo, empleo adecuado en mujeres urbanas), con indicadora de dominio $d_i \in \{0, 1\}$:

$$\hat{R}_D = \frac{\hat{Y}_D}{\hat{X}_D} = \frac{\sum_{i} w_i d_i y_i}{\sum_{i} w_i d_i}$$

El denominador también es aleatorio, por eso **no se filtran filas antes de calcular la varianza**. [`DisenoMuestralENEMDU`](../src/empleo_enemdu/encuesta.py) conserva las `7.780` UPM y calcula el residuo linealizado:

$$z_i = \frac{w_i d_i (y_i - \hat{R}_D)}{\hat{X}_D}$$

Sumando por UPM $\alpha$ dentro del estrato $h$ ($z_{h\alpha} = \sum_{i \in (h,\alpha)} z_i$), con $a_h$ UPM en el estrato:

$$\widehat{\text{Var}}_{\text{Taylor}}(\hat{R}_D) = \sum_{h=1}^{H} \frac{a_h}{a_h - 1} \sum_{\alpha=1}^{a_h} \left(z_{h\alpha} - \bar{z}_h\right)^2$$

> **Validación:** con `numpy.bincount` se calculan las `80` celdas del tabulado (`10 indicadores × 8 dominios`) y **80 coinciden** con el INEC al redondear a un decimal, en estimación y en error estándar. Con microdatos 2024, 80/80 celdas coinciden con la serie oficial.

### 2.3 Covarianza intra-UPM al comparar dos grupos
Hombres y mujeres comparten hogares y sectores censales, así que $\text{Cov}(\hat{R}_A, \hat{R}_B) \neq 0$. Restar los residuos linealizados antes de agregarlos por UPM ($\Delta z_i = z_i^{(A)} - z_i^{(B)}$) la incorpora:

$$\widehat{\text{Var}}(\hat{R}_A - \hat{R}_B) = \widehat{\text{Var}}(\hat{R}_A) + \widehat{\text{Var}}(\hat{R}_B) - 2\,\widehat{\text{Cov}}_{\text{UPM}}(\hat{R}_A, \hat{R}_B)$$

---

## 3. Paso 3: econometría laboral (`mincer.py`, `oaxaca.py`, `desigualdad.py`)

### 3.1 Mincer con errores agrupados por UPM
Cinco especificaciones de mínimos cuadrados ponderados (`WLS`, pesos `fexp`) sobre $\ln(\text{salario por hora})$, con errores agrupados por UPM (`cov_type="cluster"`):

$$\ln(w_i) = \beta_0 + \beta_1\,\text{Escolaridad}_i + \beta_2\,\text{Exp}_i + \beta_3\,\frac{\text{Exp}_i^2}{100} + \gamma'\mathbf{X}_i + \varepsilon_i$$

* Para variables dicotómicas se reporta $\Delta\% = (\exp(\hat{\beta}) - 1) \times 100$.
* El retorno por año de escolaridad baja de **7,34 %** (M1) a **4,32 %** (M2) al controlar informalidad (`-31,83 %`) y afiliación al IESS (`+35,33 %`). Dentro del sector formal es **7,66 %** y en el informal **2,17 %**.

### 3.2 Kitagawa-Oaxaca-Blinder con *bootstrap* por conglomerados
La brecha de log salario por hora es `0,0930` (`9,75 %`). Con coeficientes agrupados $\hat{\boldsymbol{\beta}}^*$ (Neumark):

$$\underbrace{\bar{Y}_H - \bar{Y}_M}_{0,0930} = \underbrace{(\bar{\mathbf{X}}_H - \bar{\mathbf{X}}_M)'\hat{\boldsymbol{\beta}}^*}_{-0,0775 \text{ (dotaciones)}} + \underbrace{\left[\bar{\mathbf{X}}_H'(\hat{\boldsymbol{\beta}}_H - \hat{\boldsymbol{\beta}}^*) + \bar{\mathbf{X}}_M'(\hat{\boldsymbol{\beta}}^* - \hat{\boldsymbol{\beta}}_M)\right]}_{+0,1705 \text{ (estructura)}}$$

Los intervalos salen de un *bootstrap* que remuestrea UPM completas con reemplazo (120 réplicas), así se respeta la correlación dentro de cada sector censal.

---

## 4. Preguntas y respuestas para entrevista técnica

### Pregunta 1: *«¿Por qué no basta con pasar `weights=fexp` a una regresión o a una prueba t cuando analizas la ENEMDU?»*
> **Respuesta:** `fexp` corrige el estimador puntual, pero no dice al modelo que los datos vienen de `7.780` conglomerados y no de `334.786` extracciones independientes. Ignorar los conglomerados subestima el error estándar: en la ENEMDU 2025 el del empleo adecuado es **5,04 veces** mayor que el de un MAS (`DEFF = 25,36`) y el de la informalidad **6,48 veces** (`DEFF = 42,03`). En Mincer, el error agrupado del retorno educativo es **3,51 veces** el ingenuo.

### Pregunta 2: *«Para la tasa de subempleo de jóvenes rurales, ¿puedes hacer `df.query("edad < 25 and rural == 1")` y luego aplicar la fórmula estratificada?»*
> **Respuesta:** **No.** El número de jóvenes rurales en cada UPM es aleatorio; al filtrar eliminas UPM, cambias el conteo $a_h$ por estrato y puedes dejar estratos con una sola UPM. Lo correcto (como en `estimar_razon_dominio`) es conservar todas las UPM y multiplicar el residuo por la indicadora de dominio, de modo que las UPM sin miembros del dominio aporten $z_{h\alpha} = 0$.

### Pregunta 3: *«En tu Oaxaca-Blinder la parte explicada sale negativa (`-0,0775`). ¿Es un error de signo?»*
> **Respuesta:** No. Mide $(\bar{\mathbf{X}}_H - \bar{\mathbf{X}}_M)'\hat{\boldsymbol{\beta}}^*$ y las mujeres ocupadas con ingreso tienen **más escolaridad que los hombres (`10,93` frente a `9,97` años)**; solo la escolaridad aporta `-0,0294` puntos log. Con sus características, las mujeres deberían ganar un **7,45 %** más; la brecha observada (`9,75 %` a favor de los hombres) esconde una parte no explicada de **+18,59 %** (`+0,1705` puntos log).

### Pregunta 4: *«¿Cómo cambia la brecha de género entre el sector formal y el informal a lo largo de los cuantiles?»*
> **Respuesta:** En el **sector informal** hay *piso pegajoso*: en $P_{10}$ los hombres ganan **35,5 % más por hora** (`0,89` frente a `0,58 USD/h`) y en $P_{25}$ **30,6 %**. En el **sector formal** el SBU actúa como piso: la brecha baja de 11,9 % en $P_{10}$ a **0,0 % en $P_{30}$** y **0,6 % en $P_{50}$**.

### Pregunta 5: *«Dices que coincides con el INEC en 80 de 80 celdas. ¿Eso significa error cero?»*
> **Respuesta:** No. El INEC publica con un decimal; comparo ambas cifras redondeadas a un decimal y la diferencia máxima es `0,0 pp`. Las cifras sin redondear pueden diferir en centésimas. Lo que demuestra la coincidencia es que las definiciones (sintaxis SPSS), los pesos y el diseño están bien replicados, en la estimación y en el error estándar.

### Pregunta 6: *«Tu gráfico muestra la informalidad desde 2018. ¿La calculaste tú?»*
> **Respuesta:** No: la serie 2018–2025 es la publicada por el INEC en el tabulado oficial (sin 2020). Yo calculé 2025 con microdatos y, para comprobar que el motor no estaba ajustado a un solo año, recalculé 2024: 80/80 celdas coinciden con la serie (por ejemplo, informalidad `52,37 %` frente a `52,4 %`).

### Pregunta 7: *«¿Cómo tratas a quien no informa su ingreso y qué sesgo introduce?»*
> **Respuesta:** Los `480` casos con `999999` pasan a faltante y se excluyen de las estadísticas de ingreso; los `-1` (sin ingreso monetario) no entran en medias de ingreso positivo. Si la no respuesta se concentra en ingresos altos, medias y Gini quedan subestimados. Una mejora sería imputar por *hot deck* dentro de celdas (rama, provincia, educación) y comparar resultados.

### Pregunta 8: *«¿Por qué usas errores agrupados por UPM en Mincer y no la linealización de Taylor completa?»*
> **Respuesta:** `statsmodels` ofrece errores robustos agrupados por UPM, que capturan la correlación intraconglomerado, la principal fuente de inflación de la varianza. No incorporan la estratificación, que suele reducir la varianza, así que el resultado es algo conservador. Para un informe oficial usaría una librería de encuestas (por ejemplo `survey` en R) para la regresión con diseño completo.

### Pregunta 9: *«El desempleo juvenil es 9,07 %. ¿Qué tan preciso es ese número y cómo lo comunicarías?»*
> **Respuesta:** Viene de `22.654` jóvenes de la PEA en la muestra, así que es preciso a nivel nacional; con el diseño complejo su error estándar es mayor que el de un MAS del mismo tamaño. Lo comunicaría junto al nacional (`3,6 %`, unas 2,5 veces menos) y con su IC, y advertiría que en cruces finos (joven × provincia) el CV puede superar el umbral de publicación del INEC.

### Pregunta 10: *«¿Qué significa que el Gini del ingreso per cápita sea 0,451 y el del ingreso laboral 0,429?»*
> **Respuesta:** Son poblaciones y variables distintas: el primero reparte el ingreso total del hogar entre todos sus miembros (incluye transferencias y hogares sin ocupados); el segundo mira solo a los ocupados con ingreso laboral. Que mi Gini per cápita sea igual al publicado (0,451) valida la construcción del ingreso y los pesos.

### Pregunta 11: *«¿Qué tan creíble es tu simulación de pobreza con el SBU?»*
> **Respuesta:** Es una cota superior contable: si en cada hogar el ocupado informal con mayor brecha llegara al SBU, la pobreza bajaría de `21,78 %` a `9,79 %`. Supone empleo constante; con `51,5 %` de informalidad, un alza por decreto sin productividad puede destruir empleo formal o empujar al autoempleo. La presentaría como orden de magnitud, no como pronóstico.

### Pregunta 12: *«¿Cómo evitas que el README diga cifras distintas a los resultados?»*
> **Respuesta:** El README y esta guía se generan desde plantillas con `python -m empleo_enemdu.cifras_readme`, que lee `reports/`. Una prueba (`tests/test_cifras_readme.py`) regenera el texto y falla si no coincide con el archivo, y los subtítulos de las figuras también se construyen desde los datos.
