# Fuentes de datos, fechas de descarga y términos de uso

Todos los datos provienen del **Instituto Nacional de Estadística y Censos (INEC)** del Ecuador, sección *Empleo* de [ecuadorencifras.gob.ec](https://www.ecuadorencifras.gob.ec/). Las URL, tamaños y sumas SHA-256 de 2025 se copian del manifiesto que escribe `descargar_datos.py` (`data/raw/manifiesto_descarga.json`); las de 2024, de `reports/validacion_microdatos_2024.json`.

## 1. ENEMDU anual 2025 (base del análisis)

Descargados el **21-10-2026** con `python descargar_datos.py`.

| Paquete | URL | Tamaño | SHA-256 |
| :--- | :--- | ---: | :--- |
| Microdatos CSV (personas y vivienda) | https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2025/anual/2_BDD_DATOS_ABIERTOS_ENEMDU_2025_CSV.zip | 13.860.758 B | `a2dc06b14b84ac2908f59313a70676f9b5c1b697b4780e744452585e60dbcbe8` |
| Tabulados CSV (Mercado laboral, Vivienda, Educación, Pobreza; serie 2018–2025) | https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2025/anual/ENEMDU_Tabulados_anual_2025-CSV.zip | 140.641 B | `1cec576fbf544e0d060103ab57952ec1721871caf0626113113b8d6ae5ab458e` |
| Diccionario de variables | https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2025/anual/Diccionario_de_variables.zip | 37.905 B | `ec8d257e7012de02ade61d3d7bbf6b254f758f08c595d2e9a68f72bafd31ad22` |
| Sintaxis SPSS oficial | https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2025/anual/Sintaxis_anual_2025.zip | 6.438 B | `873049c52eec09ac7a61cfc4cbbff7eaa7d94c82b235a2612d914a49130fc536` |

## 2. ENEMDU anual 2024 (solo para validar la serie oficial)

Descargado el **25-10-2026** con `python -m empleo_enemdu.validacion_anual --anio 2024` (se guarda en `data/raw/2024/`).

| Paquete | URL | Tamaño | SHA-256 |
| :--- | :--- | ---: | :--- |
| Microdatos CSV 2024 | https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/2024/anual/2_BDD_DATOS_ABIERTOS_ENEMDU_2024_CSV.zip | 14.138.561 B | `24244a7e7b525730b6c33081bbabb82c4bd030d6ed4cc278f875e046447a8d95` |

## 3. Qué se usa de cada fuente

| Uso en el proyecto | Fuente |
| :--- | :--- |
| Todas las cifras 2025 (tasas, provincias, Mincer, Oaxaca, Gini) | Microdatos 2025 (cálculo propio) |
| Valores oficiales con los que se comparan las 80 celdas | `00 …Mercado_Laboral_CSV/1. Estimadores.csv` (2025) |
| Serie 2018–2025 de la figura 02 | Mismo tabulado: **valores publicados por el INEC, no recalculados** (no hay 2020) |
| Gini y pobreza oficiales de referencia | `03 …Pobreza_Desigualdad_CSV/1. Estimadores.csv` |
| Reglas de construcción de variables laborales | `00 Indicadores de Mercado Laboral.sps` |
| Validación de otro año | Microdatos 2024 frente a la serie oficial 2024 |

## 4. Términos de uso

* El INEC publica los microdatos, tabulados, diccionarios y sintaxis de la ENEMDU en **acceso abierto y gratuito**, sin registro.
* No encontré un documento de términos específico para estas bases. Algunas páginas de ecuadorencifras.gob.ec muestran un aviso de licencia **Creative Commons Atribución 4.0**, pero no está confirmado que cubra estos archivos; por eso este repositorio aplica la regla más prudente:
  * **cita siempre la fuente**: *Instituto Nacional de Estadística y Censos (INEC), Encuesta Nacional de Empleo, Desempleo y Subempleo (ENEMDU) anual 2025 [y 2024]*;
  * **no redistribuye los microdatos completos**: `data/raw/` y el parquet persona a persona (`data/procesados/enemdu_pet_2025.parquet`) están en `.gitignore` y se regeneran desde el INEC;
  * solo se versionan **agregados** (tablas, figuras, `resultados.json`), la serie y estimadores oficiales ya publicados, y una **muestra de 120 UPM** (`data/muestra/muestra_enemdu_2025.parquet`, 5.552 personas, 180 KB) extraída de los microdatos públicos, sin nombres ni direcciones, para que las pruebas corran sin red. **Su redistribución no está confirmada por el INEC**: si no fuera posible, se borra `data/muestra/` y las pruebas que la usan se omiten.
* Los microdatos son anónimos (sin nombres ni direcciones). No se intenta reidentificar a ninguna persona ni hogar.
* Las cifras y conclusiones de este repositorio son del autor y **no son estadísticas oficiales del INEC**.

## 5. Verificación de las descargas

`src/empleo_enemdu/descarga.py` descarga con el contexto TLS por defecto (certificado y nombre del servidor verificados) y compara el SHA-256 de cada archivo con los de las tablas de arriba, copiados en `SHA256_ESPERADO` (`config.py`); una prueba comprueba que ambos coinciden. Si no coincide, **aborta sin guardar el archivo**. Si el certificado del INEC no se valida en tu equipo, la alternativa es explícita: `python descargar_datos.py --certificados certifi` (o la variable `ENEMDU_CERTIFICADOS`, con `certifi` o la ruta a un `.pem`). La verificación TLS nunca se desactiva.

## 6. Cómo regenerar todo

```powershell
python descargar_datos.py                              # paquetes 2025 y manifiesto
python -m empleo_enemdu.pipeline --sin-descarga        # parquet, tablas, figuras, resultados.json
python -m empleo_enemdu.validacion_anual --anio 2024   # microdatos 2024 y su validación
python -m empleo_enemdu.cifras_readme                  # README y guía con las cifras actuales
```
