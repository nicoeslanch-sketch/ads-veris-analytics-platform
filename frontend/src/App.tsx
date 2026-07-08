import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { DatasetProvider } from './data/DatasetContext'
import ProtectedRoute from './auth/ProtectedRoute'
import AppShell from './components/layout/AppShell'
import Login from './pages/Login'
import Resumen from './pages/Resumen'
import Explorar from './pages/Explorar'
import Estandarizacion from './pages/Estandarizacion'
import Limpieza from './pages/Limpieza'
import Historial from './pages/Historial'
import Conectores from './pages/Conectores'
import Alertas from './pages/Alertas'
import Reportes from './pages/Reportes'
import Planes from './pages/Planes'
import Configuracion from './pages/Configuracion'

export default function App() {
  return (
    <AuthProvider>
      <DatasetProvider>
        <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<Resumen />} />
              <Route path="/explorar" element={<Explorar />} />
              <Route path="/estandarizacion" element={<Estandarizacion />} />
              <Route path="/limpieza" element={<Limpieza />} />
              <Route path="/historial" element={<Historial />} />
              <Route path="/conectores" element={<Conectores />} />
              <Route path="/alertas" element={<Alertas />} />
              <Route path="/reportes" element={<Reportes />} />
              <Route path="/planes" element={<Planes />} />
              <Route path="/configuracion" element={<Configuracion />} />
            </Route>
          </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </DatasetProvider>
    </AuthProvider>
  )
}
