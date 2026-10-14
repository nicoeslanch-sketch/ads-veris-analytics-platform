import { describe, expect, it, vi } from 'vitest'
import type { AuthChangeEvent, Session } from '@supabase/supabase-js'
import { observeSession } from './sessionSubscription'

describe('session ordering', () => {
  function setup() {
    let event!: (event: AuthChangeEvent, session: Session | null) => void
    let resolve!: (result: { data: { session: Session | null }; error: null }) => void
    const unsubscribe = vi.fn()
    const auth = {
      getSession: () => new Promise(r => { resolve = r }),
      onAuthStateChange: (callback: typeof event) => { event = callback; return { data: { subscription: { unsubscribe } } } },
    } as unknown as Parameters<typeof observeSession>[0]
    const update = vi.fn()
    const stop = observeSession(auth, update, vi.fn())
    return { emit: (type: AuthChangeEvent, session: Session | null) => event(type, session),
      resolve: (session: Session | null) => resolve({ data: { session }, error: null }), update, stop, unsubscribe }
  }
  it('does not clear a signed-in user when an older bootstrap resolves null', async () => {
    const s = setup()
    const session = { user: { id: 'synthetic-user' } } as Session
    s.emit('SIGNED_IN', session)
    s.resolve(null)
    await Promise.resolve()
    expect(s.update.mock.calls).toEqual([[session, 'SIGNED_IN']])
  })
  it('does not restore a signed-out user from an older bootstrap', async () => {
    const s = setup()
    s.emit('SIGNED_OUT', null)
    s.resolve({ user: { id: 'old-user' } } as Session)
    await Promise.resolve()
    expect(s.update.mock.calls).toEqual([[null, 'SIGNED_OUT']])
  })
  it('unsubscribes and ignores late callbacks on unmount', async () => {
    const s = setup()
    s.stop()
    s.resolve(null)
    s.emit('TOKEN_REFRESHED', null)
    await Promise.resolve()
    expect(s.update).not.toHaveBeenCalled()
    expect(s.unsubscribe).toHaveBeenCalledOnce()
  })
  it('uses bootstrap when no newer event was delivered', async () => {
    const s = setup()
    s.resolve(null)
    await Promise.resolve()
    expect(s.update).toHaveBeenCalledWith(null)
  })
})
