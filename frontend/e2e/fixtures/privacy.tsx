import React from 'react'
import { createRoot } from 'react-dom/client'
import PrivacyCenter from '../../src/components/PrivacyCenter'
import PrivacyAcceptanceGate from '../../src/auth/PrivacyAcceptanceGate'
import '../../src/index.css'
const gate = new URLSearchParams(location.search).has('gate')
createRoot(document.getElementById('root')!).render(<React.StrictMode>{gate
  ? <PrivacyAcceptanceGate><p>Espacio de trabajo de prueba</p></PrivacyAcceptanceGate>
  : <main className="mx-auto max-w-3xl p-4"><PrivacyCenter /></main>}</React.StrictMode>)
