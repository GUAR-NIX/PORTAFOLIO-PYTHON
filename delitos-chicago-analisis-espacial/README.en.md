🇪🇸 [Español (full version)](README.md) · 🇬🇧 **English (summary)**

# Crime in Chicago 2001–2025: where it concentrates, how it changed and how much can be anticipated

**8,665,676 real records from the Chicago Data Portal** (January 2001 to 16 Oct 2026) are processed with **DuckDB + Parquet**.
Totals, rankings and rates use complete years only (2001–2025, 8,480,999 records); 2026 is marked as partial.

| Question | Technique | Answer |
|---|---|---|
| Is crime going down? | Annual trend (complete years) | **Yes**: from 486,843 (2002) to 238,176 (2025), −51.1%; minimum of 210,017 in 2021 |
| What changed between 2019 and 2024? | Change by type with **harmonized categories** | Motor vehicle theft **+141.8%**; narcotics **−60.2%**. Criminal sexual assault did **not** rise +114.6%: it was a name change (−0.4% once harmonized) |
| When does it happen? | Hour × day heat map + STL | Busiest period **18:00–22:00** (22.0% of crimes); seasonal peak in August |
| How much did COVID-19 change it? | Interrupted series with a counterfactual fitted before 2020 | **−21.4%** between 2020-03 and 2021-12 (95% CI: −23.3 to −19.6%) |
| Which areas have more crime per inhabitant? | Annual rate per 100k inhabitants, 2019–2025 | **West Garfield Park**; Austin is 1st in volume but 22nd in rate |
| Are hotspots stable? | **Getis-Ord Gi\*** on a 1-km grid + Jaccard index | **Yes**: mean Jaccard between consecutive years 0.79; 42 cells are hotspots all 7 years |
| What is the arrest rate? | 95% Wilson CI by type | **25.17%** overall; > 99% in narcotics and prostitution, < 8% in vehicle theft and burglary |
| Can demand by district be anticipated? | Rolling-origin backtesting (8 cut-offs) | **Yes**: Ridge with WAPE 6.21% vs. 9.16% for the seasonal baseline; the 90% interval covers 86.4% |

**Architecture, data quality, figures, limitations and reproduction commands:** [full README (Spanish)](README.md). Commands are
language-independent.
