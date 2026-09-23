import type { RelationshipDashboard } from './types'

export function relationshipBotContext(dashboard: RelationshipDashboard | null) {
  if (!dashboard) return null
  return {
    relation: { label: dashboard.relation.label },
    currency: dashboard.currency,
    available: dashboard.available,
    period: { desde: dashboard.period.desde, hasta: dashboard.period.hasta },
    kpis: dashboard.kpis.slice(0, 30),
    findings: dashboard.findings.slice(0, 10),
    alerts: dashboard.alerts.slice(0, 10),
    charts: dashboard.charts.slice(0, 12).map(chart => ({
      title: chart.title, category_key: chart.category_key,
      series: chart.series.slice(0, 6).map(({ key, label, format }) => ({ key, label, format })),
      data: chart.data.slice(0, 30).map(row => Object.fromEntries(
        [chart.category_key, ...chart.series.slice(0, 6).map(series => series.key)].map(key => [
          key, typeof row[key] === 'string' ? (row[key] as string).slice(0, 500) : row[key] ?? null,
        ]),
      )),
    })),
  }
}
