export type SourceRole =
  | 'matricula' | 'archivo_b' | 'archivo_c' | 'archivo_d' | 'oferta' | 'historica'
  | 'codebook_matricula' | 'codebook_b' | 'codebook_c' | 'codebook_d'

export interface DatasetOption {
  id: string
  name: string
  status: string
  created_at: string
}

export interface SourceAssignment {
  dataset_id: string
  role: SourceRole
  required: boolean
  selected_sheet?: string | null
}

export interface ConsolidationProject {
  id: string
  name: string
  status: string
  config: { cohort: number; target_columns: string[]; include_historical_output: boolean }
  sources?: Array<SourceAssignment & { profile?: { name?: string } }>
}

export interface ValidationResult {
  status: 'valid' | 'valid_with_warnings' | 'blocked'
  blocking: string[]
  warnings: string[]
  source_count: number
  target_columns: number
}

export interface QualityIssue {
  code: string
  severity: 'blocking' | 'warning' | 'info'
  message: string
  count: number
}

export interface ConsolidationRun {
  id: string
  project_id: string
  status: string
  report?: {
    row_counts?: Record<string, number>
    recoding_coverage?: Record<string, number>
    issues?: QualityIssue[]
    timings_ms?: Record<string, number>
    preview?: Array<Record<string, string>>
    relationship_summary?: Array<Record<string, string | number>>
  }
  artifacts?: Array<{ kind: string; bytes: number; storage_path: string }>
  error_message?: string
}
