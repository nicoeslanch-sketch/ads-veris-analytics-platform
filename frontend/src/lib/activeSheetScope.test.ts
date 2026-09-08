import { expect, it } from 'vitest'
import { scopeForActiveSheet } from './multiSheet'

it('keeps the restored single-sheet label and the active data synchronized', () => {
  expect(scopeForActiveSheet({ mode: 'single', sheets: ['Anterior'], active_sheet: 'Anterior' }, 'Nueva')).toEqual({ mode: 'single', sheets: ['Nueva'], active_sheet: 'Nueva' })
  expect(scopeForActiveSheet(null, null)).toBeNull()
  const combined = { mode: 'append' as const, sheets: ['A', 'B'], active_sheet: 'A' }
  expect(scopeForActiveSheet(combined, 'B')).toBe(combined)
})
