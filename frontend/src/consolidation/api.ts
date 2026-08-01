import { apiGet, apiPostJson, apiPutJson } from '../lib/api'
import { supabase } from '../lib/supabase'
import type {
  ConsolidationProject,
  ConsolidationAvailability,
  ConsolidationRun,
  DatasetInspection,
  DatasetOption,
  SourceAssignment,
  ValidationResult,
} from './types'

export async function listDatasets(): Promise<DatasetOption[]> {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('datasets')
    .select('id,name,status,created_at')
    .not('storage_path', 'is', null)
    .order('created_at', { ascending: false })
    .limit(100)
  if (error) throw new Error('No se pudieron cargar los documentos disponibles.')
  return (data ?? []) as DatasetOption[]
}

export const getConsolidationStatus = () =>
  apiGet<ConsolidationAvailability>('/consolidation/status')

export const inspectDataset = (datasetId: string) =>
  apiGet<DatasetInspection>(`/consolidation/datasets/${datasetId}/inspect`)

export const createProject = (
  name: string,
  template: 'general' | 'demre_2026',
  includeHistorical: boolean,
  periodLabel?: string,
) =>
  apiPostJson<ConsolidationProject>('/consolidation/projects', {
    name,
    template,
    cohort: 2026,
    period_label: periodLabel || null,
    include_historical_output: includeHistorical,
    aliases: template === 'demre_2026' ? { ID_RBD: 'RBD' } : {},
  })

export const saveSources = (projectId: string, sources: SourceAssignment[]) =>
  apiPutJson<ConsolidationProject>(`/consolidation/projects/${projectId}/sources`, { sources })

export const validateProject = (projectId: string) =>
  apiPostJson<ValidationResult>(`/consolidation/projects/${projectId}/validate`, {})

export const enqueuePreview = (projectId: string) =>
  apiPostJson<ConsolidationRun>(`/consolidation/projects/${projectId}/preview`, {})

export const enqueueRun = (projectId: string) =>
  apiPostJson<ConsolidationRun>(`/consolidation/projects/${projectId}/runs`, {})

export const getRun = (runId: string) => apiGet<ConsolidationRun>(`/consolidation/runs/${runId}`)

export const activateRun = (runId: string, name: string) =>
  apiPostJson<{ status: string }>(`/consolidation/runs/${runId}/activate`, { name })

export const getExport = (runId: string, kind: string) =>
  apiGet<{ url?: string; local_path?: string }>(`/consolidation/runs/${runId}/export/${kind}`)
