import { Component, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'

export default class ViewErrorBoundary extends Component<
  { children: ReactNode }, { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <section role="alert" className="mx-auto max-w-xl py-10 text-navy">
        <h1 className="text-xl font-semibold">No se pudo cargar esta vista</h1>
        <p className="mt-3 text-sm text-navy/70">
          Puede haber una nueva version o una interrupcion de conexion. Puedes
          volver a otra seccion desde el menu o recargar la pagina.
        </p>
        <button type="button" onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-teal px-4 py-2 text-sm font-semibold text-white">
          <RefreshCw className="h-4 w-4" /> Recargar pagina
        </button>
      </section>
    )
  }
}
