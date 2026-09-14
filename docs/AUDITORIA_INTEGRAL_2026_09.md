# Auditoria integral: cierre del 13 de septiembre de 2026

## Resultado

Motor 0.31.0. Se refuerzan el bot determinista, las relaciones por ID, la
lectura explicativa de Explorar, la validacion de solicitudes y la admision
de trabajos. No se promete soporte universal de cualquier archivo, una IA
general, seguridad absoluta ni equivalencia completa con Power Query.

Los originales privados y los resultados locales de las conversaciones no
se incluyen en Git. Las pruebas no generaron carga contra produccion.

## Evidencia final

| Verificacion | Resultado |
| --- | --- |
| Suite completa de API | 984 aprobadas; 29 avisos |
| Regresion de version/migracion posterior | 15 aprobadas |
| Tests unitarios frontend | 180 aprobados en 22 archivos |
| Navegacion Chromium | 19 aprobadas; una prueba opcional omitida |
| Conversaciones reproducibles del bot | 88 turnos, 20 conversaciones, cero fallos de las aserciones definidas |
| Compilacion frontend | Correcta |
| Dependencias Python y npm de produccion | Sin vulnerabilidades conocidas en los inventarios auditados |
| Revision visual | Explorar escritorio/movil y ajuste de textos largos del bot |

Las pruebas del bot combinan respuestas reales del motor con pruebas de
interfaz que simulan el transporte. No equivalen a 88 mensajes enviados al
servicio publico ni demuestran que cualquier pregunta pueda responderse.

## Informes detallados

- [Bot y conversaciones](AUDITORIA_BOT_2026_09.md).
- [Calidad, importes, duplicados y relaciones](AUDITORIA_CALIDAD_RELACIONES_2026_09.md).
- [Explorar explicativo](EXPLORAR_ANALITICO_2026_09.md).
- [Seguridad y capacidad](AUDITORIA_SEGURIDAD_CAPACIDAD_2026_09.md).

## Limites operativos

Render mantiene una instancia gratuita de 512 MiB: un calculo pesado por
proceso, hasta 32 trabajos activos y tres por cuenta. El presupuesto de
originales retenidos en cola (32 MiB globales, 16 MiB por cuenta) puede
rechazar antes. No es un limite exacto de toda la RAM del proceso.

Un piloto de 5 a 10 usuarios mayormente leyendo resultados es una hipotesis
prudente, no una medicion de capacidad. No hay una cifra certificada de
usuarios ni archivos: faltan carga controlada en staging y uso/cuota real
de Storage, incluidos los derivados. La cola actual no sobrevive de forma
durable a reinicios del worker.

Siguen pendientes una cuota dura de Storage, un worker y cola durables para
crecer, limites de trafico en el borde, MFA administrativo y proteccion de
contrasenas filtradas. No se contrataron planes ni servicios facturables.

## Base de datos y publicacion

Se comprobaron 27 tablas publicas con RLS activo. La migracion aplicada
`20260914004735_harden_public_function_permissions` restringe dos triggers
internos y fija el search_path de cinco funciones, sin cambiar registros.
Sus permisos y resultados de validacion de RUT se verificaron despues.

El despliegue de frontend y API se verifica por separado contra el commit
publicado; la version nueva invalida snapshots de calculos anteriores para
no reutilizar resultados previos a las correcciones de relaciones.
