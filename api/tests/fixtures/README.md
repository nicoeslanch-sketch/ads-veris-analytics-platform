# Fixtures XLSX de regresión

Estos libros son bases **sintéticas** creadas para probar ADS Veris. No
contienen clientes, credenciales, RUT, teléfonos ni información empresarial
real. Los correos de la base de estrés son identificadores ficticios del
dominio genérico `empresa.cl`.

- `Prueba_Fase17_Multihoja_ADS_VerIs.xlsx`: regresión pequeña de apilado,
  relación y duplicados.
- `Prueba_Estres_Multihoja_ADS_VerIs_2025.xlsx`: regresión multihoja grande de
  selección, limpieza, monedas, relaciones, costos, exportación y auditoría.

`test_phase18_multi_sheet.py` usa estas copias por defecto. Las variables
`ADSVERIS_SMALL_XLSX` y `ADSVERIS_STRESS_XLSX` permiten reemplazarlas por otra
versión local durante una auditoría.

La discrepancia entre los montos declarados en `CONTROL_ESPERADO` y los
montos reconstruibles desde las celdas visibles está documentada en
`docs/FASE_18_RECONCILIACION_CONTROL.md`.
