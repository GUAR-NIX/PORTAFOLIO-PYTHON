"""Configuración general, rutas, URLs oficiales del INEC y catálogos de la ENEMDU."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DIR_DATOS = RAIZ / "data"
DIR_RAW = DIR_DATOS / "raw"
DIR_PROCESADOS = DIR_DATOS / "procesados"
DIR_MUESTRA = DIR_DATOS / "muestra"
DIR_REPORTS = RAIZ / "reports"
DIR_FIGURAS = DIR_REPORTS / "figures"
DIR_TABLAS = DIR_REPORTS / "tablas"
DIR_APP_CAPTURAS = DIR_REPORTS / "app"

ANIO_ENCUESTA = 2025
SBU_USD_2025 = 470.0  # Salario Básico Unificado vigente en 2025 (USD/mes)

# Fuentes oficiales del Instituto Nacional de Estadística y Censos (INEC)
URLS_INEC_2025: dict[str, str] = {
    "microdatos_csv": (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/"
        "2025/anual/2_BDD_DATOS_ABIERTOS_ENEMDU_2025_CSV.zip"
    ),
    "tabulados_csv": (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/"
        "2025/anual/ENEMDU_Tabulados_anual_2025-CSV.zip"
    ),
    "diccionario_variables": (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/"
        "2025/anual/Diccionario_de_variables.zip"
    ),
    "sintaxis_spss": (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/"
        "2025/anual/Sintaxis_anual_2025.zip"
    ),
}

# Microdatos de años anteriores usados solo para validar la serie publicada por el INEC
URLS_MICRODATOS_VALIDACION: dict[int, str] = {
    2024: (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/EMPLEO/"
        "2024/anual/2_BDD_DATOS_ABIERTOS_ENEMDU_2024_CSV.zip"
    ),
}

# SHA-256 esperado de cada paquete descargado (los mismos de docs/fuentes.md; una prueba lo comprueba).
# `descarga.py` aborta si lo que llega del INEC no coincide.
SHA256_ESPERADO: dict[str, str] = {
    "2_BDD_DATOS_ABIERTOS_ENEMDU_2025_CSV.zip": "a2dc06b14b84ac2908f59313a70676f9b5c1b697b4780e744452585e60dbcbe8",
    "ENEMDU_Tabulados_anual_2025-CSV.zip": "1cec576fbf544e0d060103ab57952ec1721871caf0626113113b8d6ae5ab458e",
    "Diccionario_de_variables.zip": "ec8d257e7012de02ade61d3d7bbf6b254f758f08c595d2e9a68f72bafd31ad22",
    "Sintaxis_anual_2025.zip": "873049c52eec09ac7a61cfc4cbbff7eaa7d94c82b235a2612d914a49130fc536",
    "2_BDD_DATOS_ABIERTOS_ENEMDU_2024_CSV.zip": "24244a7e7b525730b6c33081bbabb82c4bd030d6ed4cc278f875e046447a8d95",
}

# Catálogo de provincias (código DPA INEC)
PROVINCIAS: dict[int, str] = {
    1: "Azuay",
    2: "Bolívar",
    3: "Cañar",
    4: "Carchi",
    5: "Cotopaxi",
    6: "Chimborazo",
    7: "El Oro",
    8: "Esmeraldas",
    9: "Guayas",
    10: "Imbabura",
    11: "Loja",
    12: "Los Ríos",
    13: "Manabí",
    14: "Morona Santiago",
    15: "Napo",
    16: "Pastaza",
    17: "Pichincha",
    18: "Tungurahua",
    19: "Zamora Chinchipe",
    20: "Galápagos",
    21: "Sucumbíos",
    22: "Orellana",
    23: "Santo Domingo",
    24: "Santa Elena",
    90: "Zonas No Delimitadas",
}

# Regiones naturales según sintaxis oficial INEC (01 Variables para tabulados.sps)
PROVINCIA_A_REGION_INEC: dict[int, str] = {
    **{p: "Sierra" for p in (1, 2, 3, 4, 5, 6, 10, 11, 17, 18, 23)},
    **{p: "Costa" for p in (7, 8, 9, 12, 13, 24, 90)},
    **{p: "Amazonía" for p in (14, 15, 16, 19, 21, 22)},
    20: "Insular",
}

# Dominios autorrepresentados de estudio
DOMINIOS: dict[int, str] = {
    1: "Quito",
    2: "Guayaquil",
    3: "Cuenca",
    4: "Machala",
    5: "Ambato",
    6: "Resto Sierra Urbano",
    7: "Resto Costa Urbano",
    8: "Amazonía Urbano",
    9: "Sierra Rural",
    10: "Costa Rural",
    11: "Amazonía Rural",
    12: "Región Insular",
}

AREAS: dict[int, str] = {
    1: "Urbana",
    2: "Rural",
}

SEXO: dict[int, str] = {
    1: "Hombre",
    2: "Mujer",
}

CONDACT_ETIQUETAS: dict[int, str] = {
    0: "Menor de 15 años",
    1: "Empleo adecuado/pleno",
    2: "Subempleo por insuficiencia de tiempo",
    3: "Subempleo por insuficiencia de ingresos",
    4: "Otro empleo no pleno",
    5: "Empleo no remunerado",
    6: "Empleo no clasificado",
    7: "Desempleo abierto",
    8: "Desempleo oculto",
    9: "Población económicamente inactiva",
}

SECEMP_ETIQUETAS: dict[int, str] = {
    1: "Sector formal",
    2: "Sector informal",
    3: "Empleo doméstico",
    4: "No clasificado por sector",
}

# Recodificación oficial INEC de p15 (autoidentificación étnica)
P15_A_ETNIA: dict[int, str] = {
    1: "Indígena",
    2: "Afroecuatoriano",
    3: "Afroecuatoriano",
    4: "Afroecuatoriano",
    5: "Montubio",
    6: "Mestizo/a",
    7: "Blanco/a",
}

NIVEL_INSTRUCCION: dict[int, str] = {
    1: "Ninguno",
    2: "Centro de alfabetización",
    3: "Educación Básica",
    4: "Educación Media / Bachillerato",
    5: "Superior",
}

# Ramas de actividad CIIU Rev. 4 (rama1 en ENEMDU)
RAMA_ACTIVIDAD: dict[int, str] = {
    1: "Agricultura, ganadería, caza y silvicultura y pesca",
    2: "Explotación de minas y canteras",
    3: "Industrias manufactureras",
    4: "Suministro de electricidad, gas, vapor y aire acondicionado",
    5: "Distribución de agua, alcantarillado y gestión de desechos",
    6: "Construcción",
    7: "Comercio al por mayor y al por menor; reparación de vehículos",
    8: "Transporte y almacenamiento",
    9: "Actividades de alojamiento y de servicio de comidas",
    10: "Información y comunicación",
    11: "Actividades financieras y de seguros",
    12: "Actividades inmobiliarias",
    13: "Actividades profesionales, científicas y técnicas",
    14: "Actividades de servicios administrativos y de apoyo",
    15: "Administración pública y defensa; planes de seguridad social",
    16: "Enseñanza",
    17: "Actividades de atención de la salud humana y asistencia social",
    18: "Artes, entretenimiento y recreación",
    19: "Otras actividades de servicios",
    20: "Actividades de los hogares como empleadores",
    21: "Actividades de organizaciones y órganos extraterritoriales",
}

# Grupos de ocupación CIUO-08 (grupo1 en ENEMDU)
GRUPO_OCUPACION: dict[int, str] = {
    1: "Directores y gerentes",
    2: "Profesionales científicos e intelectuales",
    3: "Técnicos y profesionales del nivel medio",
    4: "Personal de apoyo administrativo",
    5: "Trabajadores de los servicios y vendedores",
    6: "Agricultores y trabajadores calificados agropecuarios",
    7: "Oficiales, operarios y artesanos",
    8: "Operadores de instalaciones y máquinas",
    9: "Ocupaciones elementales",
    10: "Ocupaciones militares",
}

# Paleta editorial consistente
PALETA: dict[str, str] = {
    "primario": "#1f4e78",
    "secundario": "#2e75b6",
    "acento": "#d95f02",
    "alerta": "#c0392b",
    "exito": "#27ae60",
    "formal": "#1b6ca8",
    "informal": "#e67e22",
    "adecuado": "#1b7837",
    "subempleo": "#d95f02",
    "otro_no_pleno": "#e6ab02",
    "no_remunerado": "#7570b3",
    "desempleo": "#c0392b",
    "hombre": "#2b5c8f",
    "mujer": "#c94a6a",
    "urbano": "#2b5c8f",
    "rural": "#2e8b57",
    "gris": "#6c757d",
    "gris_claro": "#e9ecef",
}
