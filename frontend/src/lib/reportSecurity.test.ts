import { describe, expect, it } from 'vitest'
import { csvCell } from './report'

describe('CSV export safety', () => {
  it.each(['=1+1', '+SUM(1)', '-CMD()', '@SUM(1)', '   =1+1', '\t=1+1', '\r=1+1', '\n=1+1'])('neutralizes %j', value => {
    expect(csvCell(value).replace(/^"/, '').startsWith("'")).toBe(true)
  })
  it('quotes carriage returns so untrusted labels cannot create new rows', () => {
    expect(csvCell('product\r=1+1')).toBe('"product\r=1+1"')
  })
  it('preserves ordinary labels and escapes quotes', () => {
    expect(csvCell('Retail')).toBe('Retail')
    expect(csvCell('A;"B"')).toBe('"A;""B"""')
  })
})
