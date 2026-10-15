import React from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider } from './session-auth'
import WorkspaceProviders from '../../src/data/WorkspaceProviders'
import { useDataset } from '../../src/data/DatasetContext'
import type { CleanResult, StandardizeResult } from '../../src/lib/types'
import standardization from '../../src/demo/data/demo_standardization.json'
import cleaning from '../../src/demo/data/demo_cleaning.json'
import '../../src/index.css'

function DatasetProbe() {
  const data = useDataset()
  const load = () => {
    data.setUploaded(new File(['private synthetic contents'], 'sin-guardar.csv'), null, null)
    data.setStandardization(standardization as unknown as StandardizeResult)
    data.setCleaning(cleaning as unknown as CleanResult)
    data.setPeriod({ from: '2025-01-01', to: '2025-12-31', label: '2025' })
  }
  return <section aria-label="Documento de prueba">
    <button onClick={load}>Preparar documento sin guardar</button>
    <p>{data.file?.name ?? 'Sin archivo'}</p>
    <p>{data.cleaning ? 'Limpieza conservada' : 'Sin limpieza'}</p>
    <p>{data.period.label}</p>
    <button onClick={() => data.file?.text().then(text => alert(text))}>Comprobar contenido original</button>
  </section>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <AuthProvider><WorkspaceProviders><DatasetProbe /></WorkspaceProviders></AuthProvider>
</React.StrictMode>)
