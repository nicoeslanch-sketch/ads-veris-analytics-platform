"""Clasificador IA de columnas sin match (Fase 9) — costura preparada y APAGADA.

Cuando el diccionario (≈15.600 claves) no reconoce un encabezado, este es el
fallback que convierte la cobertura finita en cobertura "universal": la IA
clasifica la columna dentro de la MISMA taxonomía cerrada de 64 roles usando
el nombre del encabezado + una muestra de valores ([PROMPT B] de la biblioteca
de prompts).

Estado: **preparada pero APAGADA** (Settings.ai_classifier_enabled = False),
igual que las costuras de la Fase 7. El pipeline la invoca solo con el flag
encendido; hoy devuelve {} (sin clasificaciones). La interfaz es estable:
activar la IA será reemplazar el cuerpo, no tocar el pipeline.

Contrato al activarla:
- Enviar system_prompt() + classifier_prompt() con las variables rellenas
  (fill(columna=..., muestra=..., columnas=...)), SOLO desde el backend.
- Validar el JSON devuelto: el rol debe existir en la taxonomía del CSV; con
  confianza < 0.75 se marca sugerir_al_usuario y la UI pide confirmación en la
  tarjeta "Mapeo de columnas" en vez de aplicar en silencio.
- El resultado se materializa como DictMatch con metodo="ia".
"""

import pandas as pd

from .dictionary import DictMatch


def classify_columns_with_ai(
    columns: list[str],
    df: pd.DataFrame,
) -> dict[str, DictMatch]:
    """Clasifica columnas sin match del diccionario. Devuelve {columna: DictMatch}.

    # TODO IA: implementar con la Anthropic API (SOLO backend): por cada
    # columna, prompt_library.system_prompt() + fill(classifier_prompt(),
    # columna=col, columnas=list(df.columns), muestra=<10-30 valores
    # aleatorios no vacíos>). Parsear el JSON, validar el rol contra la
    # taxonomía del diccionario y devolver DictMatch(metodo="ia",
    # confianza=<la reportada>). La firma y el tipo de retorno NO cambian.
    """
    return {}
