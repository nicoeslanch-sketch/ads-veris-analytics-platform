// Development-only component harness, not an entry point of the production build.
import React from 'react'
import { createRoot } from 'react-dom/client'
import SecurityGate from '../../src/auth/SecurityGate'
import MfaPanel from '../../src/auth/MfaPanel'
import '../../src/index.css'

const gate = new URLSearchParams(location.search).has('gate')
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  {gate ? <SecurityGate><p>Datos privados de prueba</p></SecurityGate>
    : <main className="mx-auto max-w-md p-4"><MfaPanel admin /></main>}
</React.StrictMode>)
