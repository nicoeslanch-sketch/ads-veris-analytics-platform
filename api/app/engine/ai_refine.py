"""Costura IA del motor (Fase 7 §5.13) — refinado final del dataset limpio.

El motor determinista hace el 80–90% del trabajo. Esta función es el gancho
para que la IA "termine el último 10–20%": revisar el reporte de calidad,
proponer correcciones finas (typos que el fuzzy no alcanzó, categorías
inconsistentes, celdas dudosas) y devolver el dataset refinado + notas.

Estado en Fase 7: **preparada pero APAGADA** (Settings.ai_refine_enabled =
False). El pipeline la invoca solo si el flag está encendido; hoy devuelve el
DataFrame sin cambios. La interfaz es estable: activar la IA será reemplazar
el cuerpo, no tocar el pipeline.
"""

import pandas as pd


def refine_with_ai(df: pd.DataFrame, quality_report: dict) -> tuple[pd.DataFrame, list[str]]:
    """Refina el dataset limpio con IA. Devuelve (df_refinado, notas).

    # TODO IA: implementar con la Anthropic API (SOLO backend): enviar una
    # muestra acotada + el reporte de calidad por columna, recibir correcciones
    # dentro de un catálogo validado (nunca celdas arbitrarias sin validar),
    # aplicarlas y devolver notas legibles de qué se afinó. La firma y el tipo
    # de retorno NO cambian.
    """
    return df, []
