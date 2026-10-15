import type { Period } from '../data/DatasetContext'
import { formatMonthShort } from './charts'

export function periodSelectValue(period: Period): string {
  if (!period.from && !period.to) return 'all'
  if (!period.from || !period.to) return 'custom'
  if (/^\d{4}$/.test(period.label)
    && period.from.startsWith(period.label + '-')
    && period.to.startsWith(period.label + '-')) return period.label
  const month = period.from.slice(0, 7)
  if (period.from === month + '-01' && period.to === lastDateOfMonth(month)) return month
  return 'custom'
}

function lastDateOfMonth(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return `${month}-${String(new Date(year, number, 0).getDate()).padStart(2, '0')}`
}

export function compactPeriodLabel(period: Period): string {
  const selection = periodSelectValue(period)
  if (selection === 'all') return 'Todo'
  if (/^\d{4}$/.test(selection)) return selection
  if (/^\d{4}-\d{2}$/.test(selection)) return formatMonthShort(selection)
  if (/^\d{4}-T[1-4]$/.test(period.label)) return period.label
  return 'Rango'
}
