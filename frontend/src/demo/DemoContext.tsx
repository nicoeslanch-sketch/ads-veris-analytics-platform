/** Demo ficticia (Fase 14) — proveedor INDEPENDIENTE del DatasetContext.
 *
 * Los snapshots (data/*.json) nacen del motor real vía
 * api/scripts/generate_demo.py y quedan congelados en el bundle: la demo no
 * llama al backend, no toca Storage, no escribe en el historial y JAMÁS pisa
 * el DatasetContext — entrar y salir de la demo deja el estado real intacto.
 * Un test de contrato (api/tests/test_demo.py) regenera y compara los
 * snapshots: si el esquema del motor cambia, falla ruidosamente.
 *
 * Empresa ficticia: "Comercial Andes SpA" (distribuidora chilena). Los datos
 * exhiben a propósito devoluciones, costos incompletos, duplicados y un mes
 * parcial — así la demo muestra la plataforma explicando datos imperfectos,
 * que es el caso real de una PyME.
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { CleanResult, MetricsResult, StandardizeResult } from '../lib/types'
import demoStandardizationJson from './data/demo_standardization.json'
import demoCleaningJson from './data/demo_cleaning.json'
import demoMetricsJson from './data/demo_metrics.json'

export const DEMO_LABEL = 'Datos ficticios de ejemplo'
export const DEMO_COMPANY = 'Comercial Andes SpA (empresa ficticia)'

const demoStandardization = demoStandardizationJson as unknown as StandardizeResult
const demoCleaning = demoCleaningJson as unknown as CleanResult
const demoMetrics = demoMetricsJson as unknown as MetricsResult

interface DemoState {
  active: boolean
  enter: () => void
  exit: () => void
  standardization: StandardizeResult
  cleaning: CleanResult
  metrics: MetricsResult
}

const DemoContext = createContext<DemoState | undefined>(undefined)

export function DemoProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(false)
  const enter = useCallback(() => setActive(true), [])
  const exit = useCallback(() => setActive(false), [])

  const value = useMemo(
    () => ({
      active,
      enter,
      exit,
      standardization: demoStandardization,
      cleaning: demoCleaning,
      metrics: demoMetrics,
    }),
    [active, enter, exit],
  )

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>
}

export function useDemo(): DemoState {
  const ctx = useContext(DemoContext)
  if (!ctx) throw new Error('useDemo debe usarse dentro de <DemoProvider>')
  return ctx
}
