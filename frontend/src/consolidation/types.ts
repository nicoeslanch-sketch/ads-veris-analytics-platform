export type SourceRole =
  | 'primary' | 'supplement_1' | 'supplement_2' | 'supplement_3' | 'supplement_4'
  | 'equivalence_1' | 'equivalence_2' | 'historical'
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
  label?: string | null
  primary_key?: string | null
  source_key?: string | null
  target_column?: string | null
  value_column?: string | null
  output_column?: string | null
  prefix?: string | null
  include_columns?: string[]
}

export interface ConsolidationProject {
  id: string
  name: string
  status: string
  config: {
    template: 'general' | 'demre_2026'
    cohort: number
    period_label?: string | null
    target_columns: string[]
    include_historical_output: boolean
  }
  sources?: Array<SourceAssignment & { profile?: { name?: string } }>
}

export interface ConsolidationAvailability {
  available: boolean
  reason: 'backend_disabled' | 'admin_required' | 'access_check_failed' | null
  admin_only: boolean
}

export interface DatasetInspection {
  dataset_id: string
  name: string
  sha256: string
  kind?: string
  sheets: Array<{
    name: string
    columns: string[]
    approximate_rows?: number
    sample_rows?: number
  }>
}

export interface DetectionFile {
  dataset_id: string
  name: string
  kind: string
  sheet?: string | null
  columns: string[]
  column_count: number
  approximate_rows?: number | null
  sha256: string
  detected_role?: SourceRole | null
  suggested_role?: SourceRole | null
  role_label: string
  confidence: number
  suggested_keys: Array<{ base: string; related: string }>
  warnings: string[]
}

export interface DetectionProposal {
  template: 'general' | 'demre_2026'
  confidence: number
  message: string
  files: DetectionFile[]
  questions: string[]
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
  events?: Array<{
    stage: string
    status: 'started' | 'completed' | 'warning' | 'failed'
    duration_ms?: number | null
    created_at: string
  }>
  error_message?: string
}
