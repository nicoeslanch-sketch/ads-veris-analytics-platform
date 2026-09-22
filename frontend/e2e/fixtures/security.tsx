// Development-only component harness, not an entry point of the production build.
import React from 'react'
import { createRoot } from 'react-dom/client'
import SecurityGate from '../../src/auth/SecurityGate'
import MfaPanel from '../../src/auth/MfaPanel'
import CommercialReadiness from '../../src/components/admin/CommercialReadiness'
import '../../src/index.css'

const gate = new URLSearchParams(location.search).has('gate')
const readiness = new URLSearchParams(location.search).has('readiness')
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  {readiness ? <main className="p-4"><CommercialReadiness /></main>
    : gate ? <SecurityGate><p>Datos privados de prueba</p></SecurityGate>
    : <main className="mx-auto max-w-md p-4"><MfaPanel admin /></main>}
</React.StrictMode>)
