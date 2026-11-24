🇺🇸 **English** · 🇪🇸 [Español](README.es.md)

# Reproducible data analysis in Python

[![CI](https://github.com/GUAR-NIX/PORTAFOLIO-PYTHON/actions/workflows/ci.yml/badge.svg)](https://github.com/GUAR-NIX/PORTAFOLIO-PYTHON/actions/workflows/ci.yml)

Six analyses of public data with automated tests and uncertainty estimates.

| Project | Measured result | Code | Tests |
|---|---|---|---|
| [Labor market with a complex survey design](mercado-laboral-ecuador-enemdu/README.md) | **80 of 80** cells match the official INEC table after rounding | [code](mercado-laboral-ecuador-enemdu/src/empleo_enemdu) | [tests](mercado-laboral-ecuador-enemdu/tests) |
| [NYC 311 resolution times](nyc311-analisis-supervivencia/README.md) | **7.54 million** requests; Kaplan-Meier median 27.2 days where the naive one says 4.6 (Parks) | [code](nyc311-analisis-supervivencia/src/nyc311) | [tests](nyc311-analisis-supervivencia/tests) |
| [Crime in Chicago](delitos-chicago-analisis-espacial/README.md) | **8.67 million** records; forecast WAPE **6.21%** vs. 9.16% for the seasonal baseline | [code](delitos-chicago-analisis-espacial/src/delitos_chicago) | [tests](delitos-chicago-analisis-espacial/tests) |
| [45 years of climate in Ecuador](clima-ecuador-45-anios/README.md) | **11.8 million** hourly records; +0.24 °C per decade (p = 0.002) | [code](clima-ecuador-45-anios/src/clima_ecuador) | [tests](clima-ecuador-45-anios/tests) |
| [Seismicity with the USGS catalog](sismicidad-ecuador-usgs/README.md) | b = **0.85** [0.72–0.97]; M≥7 every 5.0 years on average [3.3–8.5] | [code](sismicidad-ecuador-usgs/src/sismos) | [tests](sismicidad-ecuador-usgs/tests) |
| [Growth and CO2 in Latin America](desarrollo-co2-latam/README.md) | 14 of 18 countries decoupled only in relative terms; none in absolute terms (2000–2024) | [code](desarrollo-co2-latam/src/desarrollo_co2) | [tests](desarrollo-co2-latam/tests) |

## Start here

| If you are looking for… | Go to |
|---|---|
| **Validation against an official source** | [Labor market](mercado-laboral-ecuador-enemdu/README.md) |
| **Large data on one machine** | [Crime in Chicago](delitos-chicago-analisis-espacial/README.md): DuckDB and Parquet |
| **How it is checked** | [CI workflow](.github/workflows/ci.yml): Ruff, Markdown links and the tests of the six projects |
| **Design and decisions** | The full README of each project (Spanish) has the architecture, limits and reproduction commands |

## How results were measured

- In the labor market, NYC 311 and Chicago projects, README figures are generated from `reports/` and checked by tests.
- Intervals are 95%; methods and limits are in each project.
- Own calculations are not official statistics.

## How to use this repository

```bash
git clone https://github.com/GUAR-NIX/PORTAFOLIO-PYTHON.git
cd PORTAFOLIO-PYTHON/<project>
```

Each project has its own README, tests and `docs/GUIA_PASO_A_PASO.md` (Spanish). Raw data are not versioned: a script gets them from
the official source. The English page of each project is a summary; the full documentation is in Spanish.
See [CONTRIBUTING.md](CONTRIBUTING.md) to run the checks.

## Author

**Erick Guarnizo** · [LinkedIn](https://www.linkedin.com/in/erick-g-571a7b3b4) · [GitHub profile](https://github.com/GUAR-NIX)

## License

Code is under the [MIT](LICENSE) license. Each project's data keep the license of their source, stated in its README.
