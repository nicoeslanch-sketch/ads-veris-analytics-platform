"""Contrato inmutable de la salida compatible con DEMRE 2020-2025."""

TARGET_COLUMNS: tuple[str, ...] = (
    "id_aux", "cohorte", "sexo", "tipo_de_enseñanza", "rama_educacional",
    "dependencia", "rbd", "anyo_egreso", "region", "provincia", "comuna",
    "nem", "percentil_nem", "puntaje_nem", "ranking_notas",
    "percentil_ranking", "puntaje_ranking", "ingreso_percapita",
    "rindio_prueba", "preferencia2", "codigo_carrera", "puntaje_ponderado",
    "institucion", "nombre_carrera", "grado_academico", "tipo_plan_estudio",
    "area_conocimiento", "duracion_estudios", "vacantes", "puntaje_minimo",
    "ponderacion_nem", "ponderacion_ranking", "ponderacion_lenguaje",
    "ponderacion_matematicas", "ponderacion_historia", "ponderacion_ciencias",
    "vacantes_b", "puntos_b", "modalidad", "tipo_carrera",
    "tipo_institucion", "cod_institucion", "entidad", "nombre_de_la_sede",
    "region_sede", "comuna_sede", "latitud", "longitud", "ID", "ESTUDIÓ",
    "AGNO_TERMINO", "COD_TIPO_INST1", "COD_INST1", "COD_CARRERA1",
    "ESTUDIÓ2", "AGNO_TERMINO2", "COD_TIPO_INST2", "COD_INST2",
    "COD_CARRERA2", "ESTUDIÓ3", "AGNO_TERMINO3", "COD_TIPO_INST3",
    "COD_INST3", "COD_CARRERA3", "ESTUDIÓ_ES", "AGNO_TERMINO_ES",
    "COD_TIPO_INST_ES", "COD_INST_ES", "COD_CARRERA_ES", "institucion1",
    "nombre_carrera1", "institucion2", "nombre_carrera2", "institucion3",
    "nombre_carrera3", "institucion_es", "nombre_carrera_es", "cohorte_id",
    "cohorte_id_repetido", "Pref_rec1", "Pref_rec2", "CARRERA_CON_TESORERÍA",
    "IPO_TIPO CARRERA", "CARRERAS_UNO", "SEMESTRE_ACADÉMICO_2",
    "NIVEL_GLOBAL", "RETENIDO_SIES", "RETENIDO_OCTUBRE_PLATAFORMA",
    "RETENIDO_ENERO_PLATAFORMA", "RETENIDO_MARZO_PLATAFORMA",
    "RETENIDO_MAYO_PLATAFORMA", "RETENIDO_JULIO_PLATAFORMA",
)

if len(TARGET_COLUMNS) != 92 or len(set(TARGET_COLUMNS)) != 92:
    raise RuntimeError("El contrato DEMRE debe contener 92 columnas únicas.")

DIRECT_MAPPINGS: dict[str, tuple[str, str]] = {
    "id_aux": ("matricula", "ID_aux"),
    "preferencia2": ("matricula", "PREFERENCIA"),
    "codigo_carrera": ("matricula", "CODIGO"),
    "puntaje_ponderado": ("matricula", "PTJE_POND"),
    "nombre_carrera": ("matricula", "NOMBRE_PREF"),
}

TEMPORALLY_UNAVAILABLE_COLUMNS: frozenset[str] = frozenset(TARGET_COLUMNS[48:])


def resolve_target_columns(template: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Valida una plantilla configurable sin convertir las 92 columnas en regla universal."""
    columns = tuple(str(column).strip() for column in (template or TARGET_COLUMNS))
    if not columns or any(not column for column in columns):
        raise ValueError("La plantilla objetivo contiene columnas vacías.")
    if len(columns) != len(set(columns)):
        raise ValueError("La plantilla objetivo contiene columnas duplicadas.")
    return columns
