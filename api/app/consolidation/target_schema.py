"""Contrato aprobado desde ``DEMRE 2020-2025_ACTUALIZADA.xlsx``.

No basta con tener 92 columnas: nombre, orden y tipo lógico deben coincidir con
la hoja real ``BASE DE DATOS``.  Este contrato no se aplica al modo general.
"""

from __future__ import annotations

import pandas as pd


TARGET_COLUMNS: tuple[str, ...] = (
    "id_aux", "cohorte", "nac_rec", "nac", "region_domicilio",
    "regiondomicilio", "sexo", "edad_ingresou", "estado_civil", "ec",
    "decil_ingr", "di_60", "di", "jefe_fam", "jf", "economicamente",
    "educacion_madre", "nivel_madre", "completo_educacion_madre",
    "educacion_padre", "nivel_padre", "completo_educacion_padre",
    "PRIMERAGENERACIÓN", "herederos", "trab_remun", "TRAB", "horario_trab",
    "rbdx", "dep_estab", "Dep", "dep", "rama", "rama1",
    "situacion_egreso", "años_desdeegreso", "ptje_pond", "preferencia2",
    "Pref_rec1", "Pref_rec2", "Estudió_ES", "ES", "via", "VIA_rec1",
    "via2", "TipoInstitución1", "TipoInstitución2", "TipoInstitución3",
    "RegiónSede", "provinciasede", "comunasede", "estudiaenregiondomicilio",
    "reg_domic", "Áreadelconocimiento", "CineF97Área", "CineF13Área",
    "CineF13Subárea", "CódigoIES", "nombreies", "CódigoSede", "nombresede",
    "CódigoCarrera", "nombrecarrera", "MEDICINA", "PEDAGOGÍA", "modalidad",
    "jornada", "DuraciónEstudios", "DuraciónTitulación", "DuraciónTotal",
    "NombreTítulo", "GradoAcadémico", "nivelcarrera",
    "AcreditaciónCarreraoPrograma", "PedagogíaMedicinaOdontologíaOtro",
    "arancelanual", "promedio_notas", "ptje_nem", "ptje_ranking",
    "clec_reg_actual", "mate1_reg_actual", "mate2_reg_actual",
    "hcsoc_reg_actual", "cien_reg_actual", "cuartiles_Nem",
    "cuartiles_PjeNem", "cuartiles_Ranking", "cuartiles_Lenguaje",
    "cuartiles_Matematica", "cuartiles_historia", "cuartiles_ciencia",
    "cuartiles_Matematica_elect", "Edad_Q4",
)

if len(TARGET_COLUMNS) != 92 or len(set(TARGET_COLUMNS)) != 92:
    raise RuntimeError("El contrato histórico DEMRE debe contener 92 columnas únicas.")


NUMERIC_TARGET_COLUMNS: frozenset[str] = frozenset({
    "cohorte", "nac", "region_domicilio", "edad_ingresou", "ec", "decil_ingr",
    "di_60", "di", "jf", "educacion_madre", "completo_educacion_madre",
    "educacion_padre", "completo_educacion_padre", "PRIMERAGENERACIÓN",
    "herederos", "TRAB", "dep_estab", "Dep", "rama1", "situacion_egreso",
    "años_desdeegreso", "preferencia2", "Pref_rec1", "Pref_rec2", "ES",
    "via", "VIA_rec1", "reg_domic", "CódigoIES", "CódigoSede",
    "CódigoCarrera", "MEDICINA", "PEDAGOGÍA", "DuraciónEstudios",
    "DuraciónTitulación", "DuraciónTotal", "arancelanual", "promedio_notas",
    "ptje_nem", "ptje_ranking", "clec_reg_actual", "mate1_reg_actual",
    "mate2_reg_actual", "hcsoc_reg_actual", "cien_reg_actual", "cuartiles_Nem",
    "cuartiles_PjeNem", "cuartiles_Ranking", "cuartiles_Lenguaje",
    "cuartiles_Matematica", "cuartiles_historia", "cuartiles_ciencia",
    "cuartiles_Matematica_elect", "Edad_Q4",
})

TARGET_LOGICAL_TYPES: dict[str, str] = {
    column: "number" if column in NUMERIC_TARGET_COLUMNS else "text"
    for column in TARGET_COLUMNS
}


def coerce_target_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Aplica los tipos lógicos del histórico sin inventar valores."""
    for column in frame.columns:
        if column in NUMERIC_TARGET_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Float64")
        else:
            frame[column] = frame[column].astype("string")
    return frame


def resolve_target_columns(template: list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Valida una plantilla configurable; las 92 columnas no rigen el modo general."""
    columns = tuple(str(column).strip() for column in (template or TARGET_COLUMNS))
    if not columns or any(not column for column in columns):
        raise ValueError("La plantilla objetivo contiene columnas vacías.")
    if len(columns) != len(set(columns)):
        raise ValueError("La plantilla objetivo contiene columnas duplicadas.")
    missing = sorted({"id_aux", "cohorte"} - set(columns))
    if missing:
        raise ValueError(f"La plantilla no contiene el grano mínimo: {', '.join(missing)}")
    return columns
