import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ViewErrorBoundary, { isViewModuleError } from './ViewErrorBoundary'

describe('view recovery', () => {
  it('recognizes module download failures without treating API failures as stale code', () => {
    for (const message of ['Failed to fetch dynamically imported module: /assets/view.js',
      'Importing a module script failed.', 'error loading dynamically imported module', 'Loading chunk 42 failed.']) {
      expect(isViewModuleError(new TypeError(message))).toBe(true)
    }
    for (const error of [null, {}, new Error('Failed to fetch'), new Error('Invalid data')]) {
      expect(isViewModuleError(error)).toBe(false)
    }
  })
  it('requires explicit reload and does not promise unsaved data can be recovered', () => {
    const boundary = new ViewErrorBoundary({ children: createElement('p', null, 'Content') })
    boundary.state = ViewErrorBoundary.getDerivedStateFromError(new Error('Failed to fetch dynamically imported module'))
    const html = renderToStaticMarkup(boundary.render())
    expect(html).toContain('La interfaz necesita volver a cargarse')
    expect(html).toContain('los cambios pendientes pueden perderse')
    expect(html).toContain('Recargar pagina')
    expect(html).not.toContain('/assets/')
  })
})
