🇪🇸 [Español](README.md) · 🇬🇧 **English**

# Python portfolio for data analysis

Statistical and spatial analysis, time series, surveys with expansion factors and survival analysis with open data.

**Main tools:** pandas · Polars/DuckDB · statsmodels · geopandas · Streamlit

Each folder is an independent project with its own README (results first), step-by-step guide, automated tests and
reproduction instructions. Raw data are not versioned: every project ships a script that downloads them from the official
source.

> 🌐 Each project has an English summary with its key results; the full documentation is in Spanish.

## Projects

| Project | What it is about |
|---|---|
| [**🌦️ 45 years of climate in Ecuador: what changed and how much can we trust the answer?**](clima-ecuador-45-anios/README.en.md) | 11.8 million hourly ERA5 records (1980–2024) for 22 cities: trends, heat waves, rain and El Niño |
| [**Crime in Chicago 2001–2025: where it concentrates, how it changed and how much can be anticipated**](delitos-chicago-analisis-espacial/README.en.md) | 8.67 million real records with DuckDB and Parquet: hotspots, interrupted time series and forecasting |
| [**🌎 Growing without emitting more? Development and CO2 in Latin America**](desarrollo-co2-latam/README.en.md) | Decoupling, LMDI decomposition and the Kuznets curve for 20 countries, 1990–2024 |
| [**Ecuador's labor market with a weighted survey · INEC ENEMDU 2025 microdata**](mercado-laboral-ecuador-enemdu/README.en.md) | Taylor linearization from scratch for a complex sampling design; 80/80 cells match INEC's official table |
| [**How long does New York take to resolve a 311 request? · Survival analysis with censored cases**](nyc311-analisis-supervivencia/README.en.md) | 7.5 million requests with Kaplan-Meier and stratified Cox models |
| [**🌋 How often does Ecuador shake hard? Seismicity and the Ring of Fire with the USGS catalog**](sismicidad-ecuador-usgs/README.en.md) | Gutenberg-Richter, return periods and Omori-Utsu aftershocks |

## How to use this repository

```bash
git clone https://github.com/GUAR-NIX/PORTAFOLIO-PYTHON.git
cd PORTAFOLIO-PYTHON/<project>
```

Inside each project, follow the reproduction section of its README and `docs/GUIA_PASO_A_PASO.md` (Spanish).

## Author

**Erick Guarnizo** · [LinkedIn](https://www.linkedin.com/in/erick-g-571a7b3b4)

## License

Code is under the [MIT](LICENSE) license. Each project's data keep the license of their source, stated in its README.
