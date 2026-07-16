import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { AuthProvider } from './auth/AuthContext'
import { AccessProvider } from './lib/access'
import { DatasetProvider } from './data/DatasetContext'
import { DemoProvider } from './demo/DemoContext'
import ProtectedRoute from './auth/ProtectedRoute'
import AppShell from './components/layout/AppShell'
import Login from './pages/Login'

const Resumen = lazy(() => import('./pages/Resumen'))
const Explorar = lazy(() => import('./pages/Explorar'))
const Estandarizacion = lazy(() => import('./pages/Estandarizacion'))
const Limpieza = lazy(() => import('./pages/Limpieza'))
const Historial = lazy(() => import('./pages/Historial'))
const Conectores = lazy(() => import('./pages/Conectores'))
const Alertas = lazy(() => import('./pages/Alertas'))
const Reportes = lazy(() => import('./pages/Reportes'))
const Planes = lazy(() => import('./pages/Planes'))
const Configuracion = lazy(() => import('./pages/Configuracion'))
const AdminCuentas = lazy(() => import('./pages/AdminCuentas'))

function lazyPage(Page: LazyExoticComponent<ComponentType>) {
  return (
    <Suspense
      fallback={(
        <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-navy/60">
          <Loader2 className="h-5 w-5 animate-spin text-teal" /> Cargando módulo…
        </div>
      )}
    >
      <Page />
    </Suspense>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AccessProvider>
      <DatasetProvider>
        <DemoProvider>
        <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={lazyPage(Resumen)} />
              <Route path="/explorar" element={lazyPage(Explorar)} />
              <Route path="/estandarizacion" element={lazyPage(Estandarizacion)} />
              <Route path="/limpieza" element={lazyPage(Limpieza)} />
              <Route path="/historial" element={lazyPage(Historial)} />
              <Route path="/conectores" element={lazyPage(Conectores)} />
              <Route path="/alertas" element={lazyPage(Alertas)} />
              <Route path="/reportes" element={lazyPage(Reportes)} />
              <Route path="/planes" element={lazyPage(Planes)} />
              <Route path="/configuracion" element={lazyPage(Configuracion)} />
              <Route path="/admin" element={lazyPage(AdminCuentas)} />
            </Route>
          </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        </DemoProvider>
      </DatasetProvider>
      </AccessProvider>
    </AuthProvider>
  )
}
