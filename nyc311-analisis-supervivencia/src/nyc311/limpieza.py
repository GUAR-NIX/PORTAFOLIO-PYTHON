"""Tipado, validación y construcción de la duración con censura.

Definiciones (las mismas en todo el proyecto):
* **Evento** = la solicitud se cerró: `status == "Closed"` y `closed_date` existe y no es posterior a la fecha de corte.
* **Censura** = al corte la solicitud seguía abierta (cualquier otro estado). Su duración es
  `fecha_corte - created_date`: sabemos que tardó **al menos** eso, no cuánto.
* La censura es **administrativa** (solo la produce el corte de la descarga): ninguna solicitud se
  «pierde» antes. Por eso una pregunta binaria como «¿se cerró en ≤ 7 días?» está observada para toda
  solicitud creada al menos 7 días antes del corte.

Reglas de limpieza (cada una se cuenta en el informe de calidad):
1. `unique_key` duplicado → se conserva la primera fila.
2. `created_date` nula o ilegible → se descarta.
3. `closed_date < created_date` (fecha imposible) → se descarta: no hay duración creíble.
4. `status == "Closed"` sin `closed_date` → se descarta: sabemos que cerró, no cuándo.
5. `closed_date` presente pero `status` abierto (reabierta o fecha no actualizada) → censura al corte: el estado manda.
6. `closed_date` posterior al corte → censura al corte (ese cierre aún no existía en la fecha de corte).
7. `closed_date == created_date` → se conserva con duración 0 («cierre instantáneo») y se marca.
8. Borough fuera de los 5 oficiales → "SIN DATO". ZIP que no sea de NYC (10001–11697, 5 dígitos) → nulo.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from nyc311.config import BOROUGHS

FORMATO_FECHA = "%Y-%m-%dT%H:%M:%S.%f"
SEGUNDOS_DIA = 86_400.0

AGENCIAS = {
    "NYPD": "Policía (NYPD)",
    "HPD": "Vivienda (HPD)",
    "DSNY": "Saneamiento (DSNY)",
    "DOT": "Transporte (DOT)",
    "DEP": "Protección Ambiental (DEP)",
    "DOB": "Edificios (DOB)",
    "DPR": "Parques (DPR)",
    "DOHMH": "Salud (DOHMH)",
    "DHS": "Personas sin hogar (DHS)",
    "TLC": "Taxis y limusinas (TLC)",
    "DCWP": "Consumidores (DCWP)",
    "EDC": "Desarrollo Económico (EDC)",
    "HRA": "Recursos Humanos (HRA)",
    "DOE": "Educación (DOE)",
    "OTI": "Tecnología (OTI)",
}

CANALES = {"PHONE": "Teléfono", "ONLINE": "Web", "MOBILE": "App móvil", "OTHER": "Otro/desconocido", "UNKNOWN": "Otro/desconocido"}


def cargar_crudo(ruta: Path) -> pd.DataFrame:
    """Lee el Parquet crudo con poca RAM: fechas e identificador se convierten en Arrow (no como objetos
    Python) y las columnas con diccionario llegan como `category`.

    Una fecha ilegible queda nula y `limpiar` la cuenta como «sin fecha de creación válida».
    Socrata publica las horas con milisegundos siempre en `.000`, así que se leen al segundo.
    """
    tabla = pq.read_table(ruta)
    for col in ("created_date", "closed_date"):
        texto = pc.utf8_slice_codeunits(tabla.column(col), 0, 19)
        fecha = pc.strptime(texto, format="%Y-%m-%dT%H:%M:%S", unit="s", error_is_null=True)
        tabla = tabla.set_column(tabla.column_names.index(col), col, fecha)
    try:
        tabla = tabla.set_column(0, "unique_key", pc.cast(tabla.column("unique_key"), pa.int64()))
    except pa.ArrowInvalid:
        pass  # algún identificador no numérico: `limpiar` lo convierte con pd.to_numeric
    # Sin metadatos de pandas: si los hubiera, to_pandas devolvería las fechas como texto otra vez
    return tabla.replace_schema_metadata(None).to_pandas()


def por_categoria(serie: pd.Series, funcion: Callable[[pd.Series], pd.Series]) -> pd.Series:
    """Aplica `funcion` solo a los valores distintos y reconstruye una columna categórica.

    Con 7,5 M de filas y unas pocas cientos de categorías, transformar las categorías en lugar de cada
    fila ahorra gigabytes de RAM (nada se convierte a objetos Python fila por fila).
    """
    cat = serie if isinstance(serie.dtype, pd.CategoricalDtype) else serie.astype("category")
    nuevas = funcion(pd.Series(cat.cat.categories.astype(str), dtype="string"))
    codigos_nuevos, valores = pd.factorize(nuevas, sort=True, use_na_sentinel=True)
    codigos = cat.cat.codes.to_numpy()
    remapeo = np.append(codigos_nuevos, -1)  # el código -1 (nulo) sigue siendo nulo
    return pd.Series(pd.Categorical.from_codes(remapeo[codigos], categories=pd.Index(valores, dtype=object)),
                     index=serie.index, name=serie.name)


def rellenar(serie: pd.Series, valor: str) -> pd.Series:
    """`fillna` para categóricas (agrega la categoría si hace falta)."""
    if valor not in serie.cat.categories:
        serie = serie.cat.add_categories([valor])
    return serie.fillna(valor)


def _limpiar_texto(texto: pd.Series) -> pd.Series:
    texto = texto.str.strip().str.replace(r"\s+", " ", regex=True)
    return texto.where(texto.ne(""), pd.NA)


def normalizar_texto(serie: pd.Series) -> pd.Series:
    """Quita espacios sobrantes; el texto vacío pasa a nulo. Devuelve una categórica."""
    return por_categoria(serie, _limpiar_texto)


def normalizar_mayusculas(serie: pd.Series) -> pd.Series:
    return por_categoria(serie, lambda t: _limpiar_texto(t).str.upper())


def _zip_valido(texto: pd.Series) -> pd.Series:
    texto = texto.str.strip().str.slice(0, 5)
    valido = texto.str.fullmatch(r"\d{5}").fillna(False)
    numero = pd.to_numeric(texto.where(valido), errors="coerce")
    return texto.where(valido & numero.between(10001, 11697), pd.NA)


def normalizar_zip(serie: pd.Series) -> pd.Series:
    """Deja solo ZIP de NYC válidos (5 dígitos entre 10001 y 11697); el resto, nulo.

    Acepta formatos ZIP+4 ('10027-1234') tomando los 5 primeros dígitos.
    """
    return por_categoria(serie, _zip_valido)


def normalizar_borough(serie: pd.Series) -> pd.Series:
    def a_borough(texto: pd.Series) -> pd.Series:
        texto = _limpiar_texto(texto).str.upper()
        return texto.where(texto.isin(BOROUGHS), "SIN DATO")

    return rellenar(por_categoria(serie, a_borough), "SIN DATO")


def parsear_fecha(serie: pd.Series) -> pd.Series:
    """Fechas ya convertidas en Arrow se usan tal cual; el texto se convierte (ilegible → NaT)."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    return pd.to_datetime(serie.astype("string"), format=FORMATO_FECHA, errors="coerce")


def construir_duracion(
    creada: pd.Series, cerrada: pd.Series, estado: pd.Series, fecha_corte: pd.Timestamp
) -> pd.DataFrame:
    """Duración en días y bandera de evento (1 = cerrada, 0 = censurada al corte).

    Supone filas ya validadas (creada ≤ corte y, si cerró, cerrada ≥ creada).
    """
    cerrada_valida = cerrada.notna() & (cerrada <= fecha_corte)
    evento = estado.eq("Closed").fillna(False).astype(bool) & cerrada_valida
    fin = cerrada.where(evento, fecha_corte)
    duracion = (fin - creada).dt.total_seconds() / SEGUNDOS_DIA
    return pd.DataFrame({"duracion_dias": duracion.astype("float64"), "evento": evento.astype("int8")}, index=creada.index)


def limpiar(crudo: pd.DataFrame, fecha_corte: pd.Timestamp | str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aplica las reglas del módulo. Devuelve la tabla analítica y el informe de calidad (conteos)."""
    corte = pd.Timestamp(fecha_corte)
    inf: dict[str, Any] = {"filas_crudas": int(len(crudo)), "fecha_corte": corte.strftime("%Y-%m-%d %H:%M:%S")}

    df = crudo.copy()
    df["unique_key"] = pd.to_numeric(df["unique_key"], errors="coerce").astype("Int64")
    dup = df["unique_key"].duplicated(keep="first")
    inf["duplicados_unique_key"] = int(dup.sum())
    df = df.loc[~dup]

    creada = parsear_fecha(df["created_date"])
    cerrada = parsear_fecha(df["closed_date"])
    sin_creacion = creada.isna() | creada.gt(corte)
    inf["sin_fecha_creacion_valida"] = int(sin_creacion.sum())

    estado = rellenar(normalizar_texto(df["status"]), "Unspecified")
    imposible = cerrada.lt(creada).fillna(False)
    cerrada_sin_fecha = estado.eq("Closed") & cerrada.isna()
    inf["cierre_antes_de_apertura"] = int((imposible & ~sin_creacion).sum())
    inf["cerradas_sin_fecha_cierre"] = int((cerrada_sin_fecha & ~sin_creacion & ~imposible).sum())
    inf["cierre_posterior_al_corte"] = int((cerrada.gt(corte) & ~imposible).sum())
    inf["fecha_cierre_con_estado_abierto"] = int((cerrada.notna() & estado.ne("Closed") & ~imposible).sum())

    # Agencias con más fechas imposibles (para el informe de calidad)
    agencia_imp = normalizar_mayusculas(df.loc[imposible & ~sin_creacion, "agency"])
    conteo = agencia_imp.value_counts()
    inf["cierre_antes_de_apertura_por_agencia"] = {k: int(v) for k, v in conteo[conteo > 0].head(8).items()}

    conservar = ~(sin_creacion | imposible | cerrada_sin_fecha)
    df, creada, cerrada, estado = df.loc[conservar], creada[conservar], cerrada[conservar], estado[conservar]

    dur = construir_duracion(creada, cerrada, estado, corte)
    tipo = normalizar_texto(df["complaint_type"])
    agencia = normalizar_mayusculas(df["agency"])
    canal = por_categoria(df["open_data_channel_type"], lambda t: _limpiar_texto(t).str.upper().map(CANALES))
    zip_ = normalizar_zip(df["incident_zip"])
    borough = normalizar_borough(df["borough"])

    limpio = pd.DataFrame(
        {
            "unique_key": df["unique_key"].astype("int64"),
            "creada": creada,
            "cerrada": cerrada.where(dur["evento"].eq(1)),
            "estado": estado,
            "agencia": rellenar(agencia, "SIN DATO"),
            "tipo_queja": rellenar(tipo, "Sin tipo"),
            "descriptor": rellenar(normalizar_texto(df["descriptor"]), "Sin descriptor"),
            "borough": borough,
            "zip": zip_,
            "canal": rellenar(canal, "Otro/desconocido"),
            "duracion_dias": dur["duracion_dias"],
            "evento": dur["evento"],
        }
    ).reset_index(drop=True)
    limpio["cierre_instantaneo"] = (limpio["evento"].eq(1) & limpio["duracion_dias"].eq(0)).astype("int8")
    limpio["mes_creacion"] = limpio["creada"].dt.to_period("M").astype("string").astype("category")
    limpio["dia_semana"] = limpio["creada"].dt.dayofweek.astype("int8")
    limpio["hora"] = limpio["creada"].dt.hour.astype("int8")

    inf.update(
        {
            "filas_limpias": int(len(limpio)),
            "filas_descartadas": int(inf["filas_crudas"] - len(limpio)),
            "eventos_cerradas": int(limpio["evento"].sum()),
            "censuradas_abiertas": int((1 - limpio["evento"]).sum()),
            "pct_censuradas": float(100 * (1 - limpio["evento"].mean())),
            "cierres_instantaneos": int(limpio["cierre_instantaneo"].sum()),
            "borough_sin_dato": int(limpio["borough"].eq("SIN DATO").sum()),
            "zip_invalido_o_nulo": int(limpio["zip"].isna().sum()),
            "n_agencias": int(limpio["agencia"].nunique()),
            "n_tipos_queja": int(limpio["tipo_queja"].nunique()),
            "n_zip": int(limpio["zip"].nunique()),
            "creada_min": limpio["creada"].min().strftime("%Y-%m-%d"),
            "creada_max": limpio["creada"].max().strftime("%Y-%m-%d"),
        }
    )
    return limpio, inf


def agrupar_top(serie: pd.Series, n: int, otros: str = "Otros") -> pd.Series:
    """Conserva las `n` categorías más frecuentes y agrupa el resto en `otros`."""
    top = serie.value_counts().head(n).index
    resultado = serie.astype("string").where(serie.isin(top), otros)
    return resultado.astype("category")


def validar_tabla(df: pd.DataFrame) -> list[str]:
    """Comprobaciones de integridad de la tabla analítica. Devuelve la lista de problemas (vacía = OK)."""
    problemas = []
    if df["unique_key"].duplicated().any():
        problemas.append("unique_key duplicado")
    if (df["duracion_dias"] < 0).any():
        problemas.append("duraciones negativas")
    if df["duracion_dias"].isna().any():
        problemas.append("duraciones nulas")
    if not df["evento"].isin([0, 1]).all():
        problemas.append("evento fuera de {0, 1}")
    if (df.loc[df["evento"].eq(1), "cerrada"] < df.loc[df["evento"].eq(1), "creada"]).any():
        problemas.append("cierre antes de apertura")
    if not set(df["borough"].astype("string").unique()) <= set(BOROUGHS) | {"SIN DATO"}:
        problemas.append("borough desconocido")
    if df["cerrada"].notna().ne(df["evento"].eq(1)).any():
        problemas.append("fecha de cierre inconsistente con el evento")
    return problemas
