import React from 'react'
import { createRoot } from 'react-dom/client'
import PrivacyCenter from '../../src/components/PrivacyCenter'
import '../../src/index.css'
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <main className="mx-auto max-w-3xl p-4"><PrivacyCenter /></main>
</React.StrictMode>)
