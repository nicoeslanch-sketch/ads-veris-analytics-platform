import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { ConsolidationProject, ConsolidationRun, SourceAssignment, ValidationResult } from './types'

interface ConsolidationState {
  project: ConsolidationProject | null
  sources: SourceAssignment[]
  validation: ValidationResult | null
  run: ConsolidationRun | null
  setProject: (value: ConsolidationProject | null) => void
  setSources: (value: SourceAssignment[]) => void
  setValidation: (value: ValidationResult | null) => void
  setRun: (value: ConsolidationRun | null) => void
}

const Context = createContext<ConsolidationState | null>(null)

export function ConsolidationProvider({ children }: { children: ReactNode }) {
  const [project, setProject] = useState<ConsolidationProject | null>(null)
  const [sources, setSources] = useState<SourceAssignment[]>([])
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [run, setRun] = useState<ConsolidationRun | null>(null)
  const value = useMemo(
    () => ({ project, sources, validation, run, setProject, setSources, setValidation, setRun }),
    [project, run, sources, validation],
  )
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useConsolidation(): ConsolidationState {
  const value = useContext(Context)
  if (!value) throw new Error('useConsolidation requiere ConsolidationProvider')
  return value
}
