🇪🇸 [Español (full version)](README.md) · 🇬🇧 **English (summary)**

# Ecuador's labor market with a weighted survey · INEC ENEMDU 2025 microdata (validated with 2024) and official series 2018–2025

Analysis of Ecuador's labor market with the microdata of the **National Survey of Employment, Unemployment and Underemployment
(annual ENEMDU 2025)** by **INEC**, respecting its complex sampling design. **Taylor linearization** is implemented from scratch
for a stratified cluster design; with that engine, the **80 cells** of the official table (10 indicators × 8 domains) **match what
INEC published within rounding to one decimal**.

> **What is own calculation and what is not.** The 2025 figures are computed from microdata. The 2018–2025 series is the one
> **published by INEC** (there is no 2020). To check that the engine also reproduces other years, the 2024 microdata were
> recalculated: 80/80 cells match.

## Main findings (annual ENEMDU 2025)

- **Sentinel codes:** averaging income without cleaning the codes `999999` (not reported) and `-1` gives **3,840.42 USD/month**,
  against the correct weighted mean of **498.97 USD/month**.
- **Complex design:** 150 strata and 7,780 primary sampling units. Ignoring the weights biases the rates, and ignoring the
  clusters underestimates standard errors: `DEFT` ranges from **2.84x** to **6.68x**.

| National indicator | Calculated | INEC official | Unweighted | `DEFT` | 95% CI (complex design) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Adequate/full employment** | **37.1%** | **37.1%** | 41.7% | 5.04x | [36.0; 38.3] |
| **Underemployment** | **19.4%** | **19.4%** | 17.1% | 3.73x | [18.7; 20.1] |
| **Other non-full employment** | **30.8%** | **30.8%** | 28.4% | 4.35x | [29.9; 31.8] |
| **Unpaid employment** | **8.8%** | **8.8%** | 8.0% | 6.68x | [7.9; 9.7] |
| **Unemployment** | **3.6%** | **3.6%** | 4.4% | 2.84x | [3.3; 3.8] |
| **Informal sector (% of employed)** | **51.5%** | **51.5%** | 43.7% | 6.48x | [49.9; 53.1] |

The figures are own calculations and are not official statistics.

**Source and terms of use, all findings, figures and reproduction commands:** [full README (Spanish)](README.md). Commands are
language-independent.
