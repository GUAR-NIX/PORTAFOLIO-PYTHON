# Guía paso a paso (Windows)

El proyecto **ya viene ejecutado**: notebooks con resultados, figuras, reportes, capturas y el panel que usa la app. Esta guía es para volver a correrlo, por ejemplo para demostrarlo en una entrevista.

## 1 · Requisitos (una sola vez)

* **Python 3.14** (con el que se probó; debería funcionar desde 3.10). Al instalarlo desde python.org marca ✅ *Add python.exe to PATH*.
* Conexión a internet solo para descargar los datos (unos 16 MB). Las APIs no piden clave ni cuenta.

```powershell
python --version
```

## 2 · Crear el entorno e instalar dependencias (3 min)

```powershell
cd desarrollo-co2-latam
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

Se abre en `http://localhost:8501`. Prueba: elige **Brasil**, mueve el periodo a **2012–2024** y verás un desacople absoluto; cambia a **CO2 basado en consumo** con Ecuador y verás cómo pasa a "sin desacople". Para cerrarla: **Ctrl + C**.

## 4 · Descargar los datos (1 min)

```powershell
python descargar_datos.py
```

Baja 9 indicadores del Banco Mundial (JSON) y el CSV de Our World in Data a `data\raw\`. Si ya están, no los vuelve a pedir (columna `segundos` ≈ 0). Para renovarlos: `python descargar_datos.py --forzar`.

## 5 · Ejecutar todo el análisis (~1 min)

```powershell
python -m desarrollo_co2.pipeline
```

Debe terminar con `Listo en … s · panel de 735 filas · desacople: {'Absoluto': 0, 'Relativo': 14, …}`. Regenera `data\procesados\`, las 11 figuras de `reports\figures\`, los CSV y `reports\resultados.json` (todas las cifras del README salen de ahí).

## 6 · Pruebas

```powershell
pytest
```

Resultado esperado: `43 passed`. Hay pruebas con datos sintéticos de respuesta conocida (tasas, clasificación, LMDI sin residuo, punto de giro), pruebas de la limpieza y la unión, controles sobre el panel real y dos pruebas de humo de la app.

## 7 · Notebooks

```powershell
jupyter notebook notebooks
```

O ábrelos en **VS Code** con la extensión *Jupyter* eligiendo el intérprete `.venv`. Para re-ejecutarlos todos de una vez:

```powershell
cd notebooks
jupyter nbconvert --to notebook --execute --inplace 0*.ipynb
```

## 8 · Subir a GitHub

1. En github.com crea el repo **`desarrollo-co2-latam`** (público, sin README).
2. En PowerShell:

```powershell
cd desarrollo-co2-latam
git init -b main
git add .
git commit -m "Desacople PIB-CO2, Kaya y curva de Kuznets en América Latina (Banco Mundial + OWID)"
git remote add origin https://github.com/TU_USUARIO/desarrollo-co2-latam.git
git push -u origin main
```

`data\raw` (16 MB) no se sube; `data\procesados` (250 KB) sí, para que la app funcione al clonar el repo.

---

## Preguntas de entrevista (con respuesta)

**1. ¿Qué es el desacople y cómo lo mediste?**
Que el PIB crezca más rápido que las emisiones. Calculo la tasa anual compuesta del PIB real (PPA, constante) y del CO2 entre el promedio de 2000–2002 y el de 2022–2024. Absoluto: el PIB sube y el CO2 baja; relativo: ambos suben pero el CO2 más despacio; sin desacople: el CO2 crece igual o más rápido.

**2. ¿Por qué promedios de 3 años y no 2000 contra 2024?**
Porque un año atípico decide la etiqueta: 2020 (pandemia), una sequía o una crisis (por ejemplo, el repunte de Ecuador en 2024). Con promedios, la tasa refleja la tendencia y no un accidente del calendario.

**3. ¿Por qué usaste dos clasificaciones?**
La regla OCDE es binaria: una elasticidad de 0,96 (Paraguay) ya cuenta como "relativo". Tapio define una banda de acoplamiento (0,8–1,2) más honesta. Con OCDE son 14 países con desacople relativo; con Tapio, 6 de ellos están en realidad acoplados.

**4. ¿Por qué unir por código ISO y no por nombre?**
Porque los nombres cambian entre fuentes (`Venezuela, RB` en el Banco Mundial y `Venezuela` en OWID) y una unión por nombre pierde filas sin avisar. Además uso `validate="one_to_one"` e `indicator=True` para comprobar que las 700 filas país-año están en ambas fuentes.

**5. ¿Qué hiciste con los datos faltantes?**
No imputé. Construí una tabla de cobertura (qué años faltan por país y variable) y cada análisis decide: Cuba y Venezuela (sin PIB) salen del desacople; el CO2 de consumo se analiza hasta 2023; la pobreza no se usa como control porque tiene huecos enormes. La única excepción es poner 0 al gas o carbón de un país cuando los demás combustibles ya suman el total, porque ahí el vacío es lógicamente un cero.

**6. ¿Cómo construiste el agregado regional?**
Sumando PIB, población y CO2 de los 18 países con series completas, y recalculando los indicadores per cápita e intensidades sobre esas sumas. Promediar tasas daría el mismo peso a Haití que a Brasil. Si en un año falta un miembro, el total queda vacío para que no parezca que las emisiones bajaron.

**7. ¿Qué diferencia hay entre CO2 territorial y de consumo, y por qué importa?**
El territorial cuenta lo que se emite dentro del país; el de consumo suma lo emitido en otros países para producir lo que el país importa y resta lo que exporta. Un país puede "desacoplar" en su territorio porque importa lo que antes fabricaba. Con CO2 de consumo, Ecuador pasa de desacople relativo a sin desacople (elasticidad 1,01).

**8. ¿Qué es la identidad de Kaya y por qué LMDI?**
CO2 = población × PIB per cápita × energía/PIB × CO2/energía. El LMDI reparte el cambio del CO2 entre esos cuatro factores usando la media logarítmica, y la suma de los efectos da exactamente el cambio total (sin residuo; una prueba lo verifica). Otros métodos dejan un residuo sin explicar.

**9. ¿Qué te dijo Kaya sobre Ecuador?**
Que el CO2 subió 92 % porque creció la población (+47 puntos) y el ingreso (+57). Lo único que frenó fue el menor carbono por unidad de energía (−19), probablemente por la hidroelectricidad (no la medí aparte). La intensidad energética empeoró (+6), al revés que en la región (−7): Ecuador no ganó eficiencia, en parte por los combustibles subsidiados.

**10. ¿Qué es la curva de Kuznets ambiental y qué encontraste?**
La hipótesis de que las emisiones suben con el ingreso y luego bajan (U invertida). Estimé ln(CO2 pc) contra ln(PIB pc) y su cuadrado con efectos fijos por país y año. El término cuadrático nunca es significativo (p = 0,26 en el mejor modelo) y el punto de giro estimado, USD 338 mil, está 9 veces por encima del país más rico de la muestra. No hay evidencia de la curva en América Latina.

**11. ¿Por qué efectos fijos y errores agrupados?**
Los efectos fijos por país absorben lo que no cambia en el tiempo (geografía, ríos para hidroelectricidad, ser productor de petróleo); los de año, los choques comunes (2009, 2020). Los errores agrupados por país corrigen que 35 años de un mismo país no son 35 datos independientes; sin eso, los p-valores salen demasiado pequeños.

**12. ¿Por qué hiciste bootstrap por países?**
Para medir la incertidumbre del punto de giro, que es un cociente de coeficientes y no tiene una distribución sencilla. Remuestreo países completos (no años sueltos) para respetar la dependencia dentro de cada país. El intervalo del 90 % va de USD 8.300 a 6 × 10¹⁸: el dato no identifica un giro.

**13. ¿Cuáles son los límites de ese análisis?**
Rango de ingreso corto, correlación no es causalidad, variables omitidas, series con tendencia (posible regresión espuria; haría falta probar cointegración en panel), una forma funcional que obliga a que haya un máximo, fuga de emisiones y solo 18 grupos para los errores agrupados.

**14. ¿Qué le recomendarías a Ecuador con estos datos?**
Que el camino de la región para desacoplar fue cambiar la matriz (Uruguay, Costa Rica, Paraguay) y ganar eficiencia, no esperar a ser más rico. Ecuador tiene hidroelectricidad, pero el repunte de 2024 sugiere (hipótesis, no calculada aquí) que sin respaldo limpio la generación térmica vuelve a pesar. Los frentes son el transporte (86 % del CO2 es petróleo), la eficiencia energética y la quema de gas en antorchas (6,7 % del CO2).

**15. ¿Cómo garantizas que el proyecto se puede reproducir?**
Un script baja los datos de las fuentes oficiales con caché; un comando reconstruye todo; las cifras del README salen de `resultados.json`; hay 43 pruebas; el panel procesado se versiona para que la app funcione sin descargar; y cada notebook se re-ejecuta de principio a fin sin errores.
