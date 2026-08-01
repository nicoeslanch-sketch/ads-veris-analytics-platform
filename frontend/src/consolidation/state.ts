import type { SourceAssignment, SourceRole } from './types'

export const TERMINAL_RUN_STATUSES = new Set([
  'partial', 'certified', 'valid_with_warnings', 'blocked', 'failed',
])

export function consolidationModeVisible(enabled: boolean, isAdmin: boolean): boolean {
  return enabled && isAdmin
}

export function canActivateResult(status: string, hasAnnual: boolean): boolean {
  return hasAnnual && ['partial', 'certified', 'valid_with_warnings'].includes(status)
}

export function upsertSource(
  sources: SourceAssignment[],
  role: SourceRole,
  datasetId: string,
  required: boolean,
): SourceAssignment[] {
  return [
    ...sources.filter((source) => source.role !== role),
    ...(datasetId ? [{ role, dataset_id: datasetId, required }] : []),
  ]
}
