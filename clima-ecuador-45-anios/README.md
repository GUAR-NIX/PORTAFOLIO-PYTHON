🇺🇸 **English (summary)** · 🇪🇸 [Español (full version)](README.es.md)

# 🌦️ 45 years of climate in Ecuador: what changed and how much can we trust the answer?

Is Ecuador warming? Are there more heat waves or heavy rains? How much does El Niño matter? To answer, **11.8 million hourly
records from the ERA5 reanalysis** (1980–2024) are extracted for **22 cities** of the Coast, the Highlands, the Amazon and
Galápagos, plus 8 points with NOAA stations.

| Question | Technique | Answer |
|---|---|---|
| Is Ecuador warming? | Mann-Kendall + Hamed-Rao, Sen's slope, FDR | **Yes: +0.24 °C per decade** (p = 0.002), **+1.06 °C since 1980**; significant in 18 of 22 cities |
| Do days or nights warm more? | Tmax and Tmin trends | **Nights**: Tmin rises significantly in 19 cities (all survive FDR) and Tmax in 12 (only 6 survive FDR) |
| Are heat waves increasing? | ETCCDI indices with each city's own thresholds | **Yes: from 13 to 52 days per year** in heat waves (1981–90 vs. 2015–24) |
| Does it rain more or less? | Rain trends and 9 extreme-rain indices | **No clear change**: 18 of 22 cities show no trend |
| How much does El Niño matter? | Lagged correlations, effective sample size | Temperature: r = 0.70 in Galápagos and 0.60 on the Coast; Highlands and Amazon respond **2–3 months later** |
| Does the ONI anticipate the Coast's rains? | ONI vs. Niño 1+2 by rainy season | **Not as much as believed**: Jan–Apr rain is explained far better by **Niño 1+2 (r = 0.84) than by the ONI (r = 0.43)** |
| Can ERA5 be trusted in the Andes? | Validation against 8 NOAA GHCN-Daily stations | **For temperature variability, yes; for absolute values and rain totals, no**: errors from ×0.3 to ×4.6 |

**Architecture, data engineering, figures, limitations and reproduction commands:** [full README (Spanish)](README.es.md).
Commands are language-independent.
