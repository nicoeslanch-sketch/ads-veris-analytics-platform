import { soloMesesCompletos } from './partial'
import type { MetricsResult } from './types'

/** Lectura interpretada de los números: qué significan para el negocio y qué
 * conviene revisar. Es lo que diferencia "Explorar" de "Resumen": Resumen
 * muestra CUÁNTO, esto explica QUÉ QUIERE DECIR y QUÉ HACER.
 *
 * Todo sale de los datos del archivo. Nunca se inventa una cifra: si un dato
 * no está, la lectura correspondiente simplemente no aparece.
 */

export type InsightTone = 'riesgo' | 'oportunidad' | 'atencion' | 'positivo'

export interface BusinessInsight {
  id: string
  tone: InsightTone
  /** Lo que dicen los números, en una frase. */
  titulo: string
  /** Qué significa para el negocio, en lenguaje llano. */
  significado: string
  /** Qué conviene hacer o revisar. */
  accion: string
  /** Las cifras que respaldan la lectura. */
  evidencia: string
}

const pct = (value: number) => `${value.toLocaleString('es-CL', { maximumFractionDigits: 1 })}%`
const money = (value: number) => value.toLocaleString('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0,
})

/** Umbrales de lectura. Son convenciones de gestión, no verdades absolutas:
 * se documentan aquí para poder discutirlos en un solo lugar. */
const UMBRAL = {
  concentracionProducto: 25,
  concentracionCliente: 25,
  devolucionesAltas: 5,
  margenBajo: 10,
  cambioMesRelevante: 10,
  colaLargaAporte: 20,
}

export function computeBusinessInsights(m: MetricsResult): BusinessInsight[] {
  const insights: BusinessInsight[] = []
  const ingresos = m.kpis.ingresos_totales?.valor ?? 0
  const margen = m.kpis.margen_utilidad_pct?.valor ?? null
  const categorias = m.por_categoria ?? []
  const productos = m.top_productos ?? []

  // ── 1. Vender a pérdida: el costo se come el ingreso ──────────────────────
  if (margen != null && margen < 0) {
    insights.push({
      id: 'margen-negativo',
      tone: 'riesgo',
      titulo: 'Tus costos superan a tus ingresos',
      significado:
        'Cada venta que haces te cuesta más de lo que te deja. Vender más en estas condiciones agranda la pérdida en vez de reducirla.',
      accion:
        'Revisa precios y costos antes que volumen: subir precio, renegociar con proveedores o dejar de vender lo que pierde plata.',
      evidencia: `Margen del periodo: ${pct(margen)} sobre ${money(ingresos)} de ingresos.`,
    })
  } else if (margen != null && margen >= 0 && margen < UMBRAL.margenBajo) {
    insights.push({
      id: 'margen-ajustado',
      tone: 'atencion',
      titulo: `Tu margen es ajustado (${pct(margen)})`,
      significado:
        'Queda muy poco por cada peso vendido, así que cualquier alza de costos o un mes flojo puede dejarte en pérdida.',
      accion: 'Identifica qué productos o categorías bajan el promedio y decide si ajustar precio o dejarlos.',
      evidencia: `Margen del periodo: ${pct(margen)} sobre ${money(ingresos)}.`,
    })
  }

  // ── 2. Categorías que restan: margen negativo pese a facturar ─────────────
  const categoriaPerdida = categorias
    .filter((row) => row.margen_pct != null && row.margen_pct < 0)
    .sort((a, b) => (a.margen_pct ?? 0) - (b.margen_pct ?? 0))[0]
  if (categoriaPerdida?.margen_pct != null) {
    insights.push({
      id: 'categoria-perdida',
      tone: 'riesgo',
      titulo: `"${categoriaPerdida.nombre}" te está restando dinero`,
      significado:
        'Esta categoría vende, pero su costo supera lo que ingresa: está financiando ventas con la utilidad de las demás.',
      accion:
        'Revisa su precio y su costo. Si no puede corregirse, evalúa reducirla o descontinuarla y reinvertir en las que sí dejan margen.',
      evidencia: `${categoriaPerdida.nombre}: ${money(categoriaPerdida.ingresos)} de ingresos con margen ${pct(categoriaPerdida.margen_pct)}.`,
    })
  }

  // ── 3. Mucho volumen, poco margen ─────────────────────────────────────────
  const volumenSinMargen = categorias
    .filter((row) => (
      row.margen_pct != null && row.margen_pct >= 0 && row.margen_pct < UMBRAL.margenBajo
      && (row.participacion_bruta_pct ?? row.porcentaje) >= 15
    ))
    .sort((a, b) => (b.participacion_bruta_pct ?? b.porcentaje) - (a.participacion_bruta_pct ?? a.porcentaje))[0]
  if (volumenSinMargen?.margen_pct != null) {
    insights.push({
      id: 'volumen-sin-margen',
      tone: 'oportunidad',
      titulo: `"${volumenSinMargen.nombre}" vende mucho pero deja poco`,
      significado:
        'Es de lo que más mueves, pero aporta poca utilidad: mucho trabajo y poca ganancia. Un ajuste pequeño de precio aquí pesa más que en cualquier otra parte.',
      accion: 'Prueba un ajuste de precio o de costo en esta categoría: por su volumen, un punto de margen se nota de inmediato.',
      evidencia: `${pct(volumenSinMargen.participacion_bruta_pct ?? volumenSinMargen.porcentaje)} de tus ventas con margen ${pct(volumenSinMargen.margen_pct)}.`,
    })
  }

  // ── 4. Dependencia de un producto ─────────────────────────────────────────
  const topProducto = productos[0]
  const shareProducto = topProducto?.participacion_bruta_pct ?? topProducto?.porcentaje ?? null
  if (topProducto && shareProducto != null && shareProducto >= UMBRAL.concentracionProducto) {
    insights.push({
      id: 'concentracion-producto',
      tone: 'atencion',
      titulo: `Dependes mucho de "${topProducto.nombre}"`,
      significado:
        'Una parte grande de tus ventas se apoya en un solo producto. Si sube su costo, se agota o pasa de moda, el golpe es directo.',
      accion: 'Asegura su abastecimiento y trabaja en que otros productos ganen peso, para no depender de uno solo.',
      evidencia: `Concentra ${pct(shareProducto)} de tus ventas.`,
    })
  }

  // ── 5. Dependencia de un cliente ──────────────────────────────────────────
  const shareCliente = m.clientes?.concentracion_top_pct ?? null
  if (shareCliente != null && shareCliente >= UMBRAL.concentracionCliente && (m.clientes?.unicos ?? 0) > 1) {
    insights.push({
      id: 'concentracion-cliente',
      tone: 'atencion',
      titulo: 'Un solo cliente pesa demasiado en tus ventas',
      significado:
        'Si ese cliente se va o te pide plazo, el impacto en tu caja es inmediato. También te deja con poco poder para negociar.',
      accion: 'Trabaja en ampliar tu cartera antes de que sea urgente; una venta repartida es una venta más segura.',
      evidencia: `El cliente principal concentra ${pct(shareCliente)} de las ventas identificadas.`,
    })
  }

  // ── 6. Por qué cambió el mes: quién lo explica ────────────────────────────
  const completos = soloMesesCompletos(m.evolucion_mensual)
  if (completos.length >= 2) {
    const ultimo = completos[completos.length - 1]
    const previo = completos[completos.length - 2]
    if (previo.ingresos > 0) {
      const cambio = ((ultimo.ingresos - previo.ingresos) / previo.ingresos) * 100
      if (Math.abs(cambio) >= UMBRAL.cambioMesRelevante) {
        const subio = cambio > 0
        const lider = categorias[0]
        insights.push({
          id: 'cambio-mes',
          tone: subio ? 'positivo' : 'riesgo',
          titulo: `Tus ventas ${subio ? 'subieron' : 'cayeron'} ${pct(Math.abs(cambio))} en el último mes`,
          significado: subio
            ? 'Un salto de esta magnitud no suele ser casualidad: conviene saber qué lo produjo para poder repetirlo.'
            : 'Una caída de esta magnitud rara vez se corrige sola: conviene identificar la causa antes de que se repita.',
          accion: lider
            ? `Compara mes contra mes por categoría y producto. "${lider.nombre}" es tu mayor peso (${pct(lider.participacion_bruta_pct ?? lider.porcentaje)}), así que empieza por ahí.`
            : 'Compara el mes contra el anterior por categoría y producto para aislar de dónde viene el cambio.',
          evidencia: `${money(previo.ingresos)} → ${money(ultimo.ingresos)}.`,
        })
      }
    }
  }

  // ── 7. Devoluciones que se comen la venta ─────────────────────────────────
  const devoluciones = m.kpis.devoluciones
  if (devoluciones && ingresos > 0) {
    const share = Math.abs(devoluciones.monto) / (ingresos + Math.abs(devoluciones.monto)) * 100
    if (share >= UMBRAL.devolucionesAltas) {
      insights.push({
        id: 'devoluciones-altas',
        tone: 'riesgo',
        titulo: `Las devoluciones se llevan ${pct(share)} de tu venta`,
        significado:
          'Una devolución cuesta dos veces: pierdes la venta y pagas el trabajo de deshacerla. En este nivel ya no es ruido, es un problema de proceso o de calidad.',
        accion: 'Revisa qué productos o clientes concentran las devoluciones: casi siempre se explican por unos pocos casos.',
        evidencia: `${devoluciones.filas.toLocaleString('es-CL')} registros por ${money(Math.abs(devoluciones.monto))}.`,
      })
    }
  }

  // ── 9. Tendencia sostenida ────────────────────────────────────────────────
  const crecimiento = m.proyeccion?.crecimiento_pct
  if (crecimiento != null && completos.length >= 3) {
    if (crecimiento <= -3) {
      insights.push({
        id: 'tendencia-baja',
        tone: 'riesgo',
        titulo: `Tu tendencia mensual es negativa (${pct(crecimiento)})`,
        significado:
          'No es un mes malo aislado: el promedio de los últimos meses viene cayendo, y esa inercia es más difícil de revertir que un bache puntual.',
        accion: 'Busca la causa en el mix: suele ser una categoría o un canal que baja de forma sostenida mientras el resto se mantiene.',
        evidencia: `Promedio de ${completos.length} meses completos: ${pct(crecimiento)} mensual.`,
      })
    } else if (crecimiento >= 3) {
      insights.push({
        id: 'tendencia-alza',
        tone: 'positivo',
        titulo: `Tu tendencia mensual es positiva (+${pct(crecimiento)})`,
        significado:
          'El crecimiento se sostiene en el tiempo, no es un mes suelto. Es el momento de asegurar stock y capacidad para no frenarlo.',
        accion: 'Verifica que el abastecimiento y la caja acompañen: crecer sin respaldo termina en quiebres de stock.',
        evidencia: `Promedio de ${completos.length} meses completos: +${pct(crecimiento)} mensual.`,
      })
    }
  }

  return insights
}
