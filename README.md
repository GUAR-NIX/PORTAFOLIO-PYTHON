# Portafolio de Python para análisis de datos

Análisis estadístico y espacial, series de tiempo, encuestas con factores de expansión y análisis de supervivencia con datos abiertos.

**Herramientas principales:** pandas · Polars/DuckDB · statsmodels · geopandas · Streamlit

Cada carpeta es un proyecto independiente, con su propio README (resultados primero), guía paso a paso, pruebas automáticas y cómo reproducirlo. Los datos crudos no se versionan: cada proyecto trae un script que los descarga desde la fuente oficial.

## Proyectos

| Proyecto | De qué trata |
|---|---|
| [**🌦️ 45 años de clima en Ecuador: ¿qué cambió y cuánto podemos confiar en la respuesta?**](clima-ecuador-45-anios/) | ¿Se está calentando el Ecuador? ¿Hay más olas de calor o lluvias intensas? ¿Cuánto pesa El Niño? Para responderlo extraigo 11,8 millones de registros horarios del reanálisis ERA5 (1980–2024) para 22 ciudades de la Costa, la… |
| [**Delitos en Chicago 2001–2025: dónde se concentran, cómo cambiaron y cuánto se puede anticipar**](delitos-chicago-analisis-espacial/) | ¿Dónde y cuándo se concentran los delitos de Chicago? ¿Cuánto cambiaron con la pandemia? ¿Qué zonas tienen más delitos por habitante y cuánto se puede anticipar la demanda por distrito? Para responderlo proceso 8.665.676… |
| [**🌎 ¿Crecer sin emitir más? Desarrollo y CO2 en América Latina**](desarrollo-co2-latam/) | ¿Los países de América Latina pueden crecer sin aumentar sus emisiones? Uno las cifras del Banco Mundial (PIB real, población, energía, pobreza) con las de Our World in Data / Global Carbon Project (CO2 territorial, de consumo y… |
| [**Mercado laboral del Ecuador con encuesta ponderada · microdatos INEC ENEMDU 2025 (validados con 2024) y serie oficial 2018–2025**](mercado-laboral-ecuador-enemdu/) | Análisis del mercado laboral ecuatoriano con los microdatos de la Encuesta Nacional de Empleo, Desempleo y Subempleo (ENEMDU anual 2025) del Instituto Nacional de Estadística y Censos (INEC), respetando su diseño muestral… |
| [**¿Cuánto tarda Nueva York en resolver una solicitud del 311? · Análisis de supervivencia con casos censurados**](nyc311-analisis-supervivencia/) | Análisis de 7.544.678 solicitudes ciudadanas al 311 de Nueva York creadas entre octubre de 2024 y septiembre de 2026, con análisis de supervivencia: el «evento» es el cierre de la solicitud y las que seguían abiertas en la fecha… |
| [**🌋 ¿Cada cuánto tiembla fuerte en el Ecuador? Sismicidad y Cinturón de Fuego con el catálogo del USGS**](sismicidad-ecuador-usgs/) | Consumo la API FDSN del USGS (paginada, con reintentos y caché) para armar tres catálogos: 3.214 sismos M≥2,5 del Ecuador ampliado (1970–2025), 87.784 sismos M≥5 del mundo (1973–2025) para comparar 13 zonas del Cinturón de Fuego,… |

## Cómo usar este repositorio

```bash
git clone https://github.com/GUAR-NIX/portafolio-python.git
cd portafolio-python/<proyecto>
```

Dentro de cada proyecto, sigue la sección «Cómo reproducir» de su README y `docs/GUIA_PASO_A_PASO.md`.

## Autor

**Erick Guarnizo** · [LinkedIn](https://www.linkedin.com/in/erick-g-571a7b3b4)

## Licencia

El código está bajo licencia [MIT](LICENSE). Los datos de cada proyecto conservan la licencia de su fuente, indicada en su README.
