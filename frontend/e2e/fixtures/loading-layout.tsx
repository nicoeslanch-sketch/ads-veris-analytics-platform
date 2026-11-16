import React from 'react'
import { createRoot } from 'react-dom/client'
import AnalysisLoadingPanel from '../../src/components/AnalysisLoadingPanel'
import LoadingSkeleton from '../../src/components/ui/LoadingSkeleton'
import '../../src/index.css'

createRoot(document.getElementById('root')!).render(<main className="mx-auto max-w-6xl p-4">
  <AnalysisLoadingPanel operation="Buscando conexiones seguras entre las hojas" detail="Validamos claves y cobertura antes de mostrar resultados." onCancel={() => { document.title = 'cancelled' }} />
  <LoadingSkeleton kind="table" label="Cargando archivos" />
  <LoadingSkeleton kind="form" label="Cargando perfil" />
</main>)
