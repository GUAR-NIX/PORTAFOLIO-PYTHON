# Fuente de datos y términos de uso

| Elemento | Detalle |
| :--- | :--- |
| Dataset | **311 Service Requests from 2010 to Present** (NYC Open Data, id `erm2-nwe9`) |
| Publicador | City of New York · NYC 311 / Office of Technology and Innovation (OTI) |
| Ficha | <https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9> |
| API usada | `https://data.cityofnewyork.us/resource/erm2-nwe9.csv` (Socrata SODA, sin clave de aplicación) |
| Consulta | `$select` con 10 columnas, `$where` por mes de `created_date`, `$order=unique_key`, `$limit=50000`, `$offset` |
| Ventana | Solicitudes creadas del 1-oct-2024 al 30-sep-2026 (24 meses) |
| Fecha de corte | `created_date` más reciente publicada al iniciar la descarga (ver `reports/resultados.json → fuente.fecha_corte`) |
| Términos | [NYC.gov Terms of Use](https://www.nyc.gov/home/terms-of-use.page): los datos de NYC Open Data son de acceso público y uso libre; la ciudad no garantiza su exactitud ni su integridad y no respalda los análisis de terceros. |
| Redistribución en este repositorio | No se versionan los datos crudos ni la tabla limpia (`data/` está en `.gitignore`); solo agregados en `reports/` y 5 filas grabadas de la API en `tests/datos/` para las pruebas sin red. |

**Cita sugerida:** *City of New York, NYC Open Data — 311 Service Requests from 2010 to Present (erm2-nwe9), consultado en octubre de 2026.*

Las cifras de este proyecto son cálculo propio y no son estadísticas oficiales de la ciudad. El 311 tiene sus
propios indicadores de cumplimiento (*Service Level Agreements*) por tipo de queja, que no se usan aquí.

## Columnas usadas

| Columna | Uso |
| --- | --- |
| `unique_key` | Identificador; control de duplicados y orden estable de la paginación |
| `created_date`, `closed_date` | Duración (hora local de Nueva York, sin zona horaria) |
| `status` | Define el evento: solo `Closed` cuenta como cierre |
| `agency`, `complaint_type`, `descriptor` | Agencia responsable y tipo de queja (estratos y estandarización) |
| `borough`, `incident_zip` | Análisis territorial |
| `open_data_channel_type` | Canal de entrada (teléfono, web, app móvil, otro) |
