import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AnalysisLoadingPanel from './AnalysisLoadingPanel'

describe('AnalysisLoadingPanel', () => {
  it('anuncia la operacion, no cada segundo, y permite cancelar con teclado', () => {
    const html = renderToStaticMarkup(createElement(AnalysisLoadingPanel, {
      operation: 'Calculando relaciones', detail: 'Ventas y productos', onCancel: () => {},
    }))
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-live="polite"')
    expect(html).toContain('aria-label="Calculando relaciones"')
    expect(html).not.toContain('aria-label="Calculando relaciones. 0 segundos')
    expect(html).toContain('motion-reduce:animate-none')
    expect(html).toContain('focus-visible:ring-2')
    expect(html).toContain('Cancelar')
  })
})
