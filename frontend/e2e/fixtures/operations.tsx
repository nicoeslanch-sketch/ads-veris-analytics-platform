import React from 'react'
import { createRoot } from 'react-dom/client'
import OperationalHealth from '../../src/components/admin/OperationalHealth'
import '../../src/index.css'

createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <main className="mx-auto max-w-5xl p-4"><OperationalHealth /></main>
</React.StrictMode>)
