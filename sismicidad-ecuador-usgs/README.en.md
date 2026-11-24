🇪🇸 [Español (full version)](README.md) · 🇬🇧 **English (summary)**

# 🌋 How often does Ecuador shake hard? Seismicity and the Ring of Fire with the USGS catalog

The **USGS FDSN API** (paginated, with retries and cache) is used to build three catalogs: **3,214 M≥2.5 earthquakes in the
extended Ecuador region (1970–2025)**, **87,784 M≥5 earthquakes worldwide (1973–2025)** to compare **13 zones of the Ring of
Fire**, and M≥6 since 1900.

> ⚠️ **Seismic statistics estimate long-term average frequencies. They do not predict when or where the next earthquake will
> be.**

| Question | Technique | Answer |
|---|---|---|
| Where do earthquakes concentrate? | Maps by depth, east–west section | **58%** are shallow (<70 km), on the coast: the plate contact. The remaining **42%** are intermediate: the **sinking Nazca plate** |
| What is Ecuador's b-value? | Aki-Utsu + Shi-Bolt + bootstrap | **b = 0.85 [0.72–0.97]** with Mc = 5.6. With the "textbook" Mc (5.0) it comes out as 1.30, but that is an **artifact** of mixing mb and Mw scales |
| Is it different from the rest of the Ring? | Same catalog and method in 13 zones | Ecuador has the **lowest b (0.88 [0.76–1.01])**; its 95% CI does not overlap with 10 of the other 12 zones |
| How often an M≥7 in the region? | Declustered Gutenberg-Richter + Poisson | **Every 5.0 years on average [3.3–8.5]**: annual probability **18% [11–26%]** |
| And a shallow M≥7, like Pedernales? | Same, depth <70 km only | **Every 10.4 years [6.0–21.9]** (9% a year); 7 were observed in 56 years |
| How did the Pedernales aftershocks decay? | Omori-Utsu (maximum likelihood) vs. exponential | **p = 0.91 ± 0.08**; **53%** of the year's M≥4.9 aftershocks came in the first week |

**Architecture, data quality, figures, limitations and reproduction commands:** [full README (Spanish)](README.md). Commands are
language-independent.
