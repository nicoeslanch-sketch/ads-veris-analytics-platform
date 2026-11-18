import React from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '../../src/auth/AuthContext'
import Login from '../../src/pages/Login'
import '../../src/index.css'

createRoot(document.getElementById('root')!).render(<React.StrictMode><AuthProvider>
  <MemoryRouter initialEntries={['/login']}><Routes>
    <Route path="/login" element={<Login />} />
    <Route path="/" element={<p>Authenticated test view</p>} />
  </Routes></MemoryRouter>
</AuthProvider></React.StrictMode>)
