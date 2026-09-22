import { describe, expect, it, vi } from 'vitest'
import { createCommercialPoster } from './commercialCommands'
import { apiPostJson } from './api'

describe('commercial operation retries', () => {
  it('reuses an ID after a lost response and rotates it after confirmed success', async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error('timeout')).mockResolvedValue({ ok: true })
    const post = createCommercialPoster(send as typeof apiPostJson)
    const payload = { user_id: 'account', amount: 100 }
    await expect(post('/admin/grant-coins', payload)).rejects.toThrow('timeout')
    await post('/admin/grant-coins', payload)
    await post('/admin/grant-coins', payload)
    expect(send.mock.calls[0][1].operation_id).toBe(send.mock.calls[1][1].operation_id)
    expect(send.mock.calls[2][1].operation_id).not.toBe(send.mock.calls[1][1].operation_id)
  })

  it('does not reuse an operation for a different target or amount', async () => {
    const send = vi.fn().mockRejectedValue(new Error('timeout'))
    const post = createCommercialPoster(send as typeof apiPostJson)
    for (const user_id of ['first', 'second']) {
      await expect(post('/admin/grant-coins', { user_id, amount: 100 })).rejects.toThrow()
    }
    expect(send.mock.calls[0][1].operation_id).not.toBe(send.mock.calls[1][1].operation_id)
  })
})
