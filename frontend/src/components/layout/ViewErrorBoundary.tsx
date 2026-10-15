import { Component, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'

export function isViewModuleError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : ''
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Loading chunk \S+ failed/i.test(message)
}

export default class ViewErrorBoundary extends Component<
  { children: ReactNode }, { failed: boolean; moduleError: boolean }
> {
  state = { failed: false, moduleError: false }

  static getDerivedStateFromError(error: unknown) {
    return { failed: true, moduleError: isViewModuleError(error) }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <section role="alert" className="mx-auto max-w-xl py-10 text-navy">
        <h1 className="text-xl font-semibold">{this.state.moduleError ? 'La interfaz necesita volver a cargarse' : 'No se pudo cargar esta vista'}</h1>
        <p className="mt-3 text-sm text-navy/70">
          {this.state.moduleError
            ? 'No se pudo descargar una parte de la interfaz. Puede ocurrir tras una actualizacion o un corte de conexion. Este aviso no es un error de limpieza del archivo.'
            : 'Puedes volver a otra seccion desde el menu o recargar la pagina.'}
        </p>
        <p className="mt-3 text-sm text-navy/70">
          No recargamos automaticamente para no interrumpir tu trabajo. Al recargar,
          solo se recupera lo que se haya guardado; los cambios pendientes pueden perderse.
        </p>
        <button type="button" onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2 text-sm font-semibold text-white">
          <RefreshCw className="h-4 w-4" /> Recargar pagina
        </button>
      </section>
    )
  }
}
