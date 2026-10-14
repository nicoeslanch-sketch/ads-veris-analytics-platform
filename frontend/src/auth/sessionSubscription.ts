import type { AuthChangeEvent, Session, SupabaseClient } from '@supabase/supabase-js'

export function observeSession(
  auth: Pick<SupabaseClient['auth'], 'getSession' | 'onAuthStateChange'>,
  onSession: (session: Session | null, event?: AuthChangeEvent) => void,
  onBootstrapError: () => void,
) {
  let active = true
  let authEventReceived = false
  // Subscribe first; a delayed bootstrap must never undo a newer auth event.
  const { data: { subscription } } = auth.onAuthStateChange((event, session) => {
    if (!active) return
    authEventReceived = true
    onSession(session, event)
  })
  void auth.getSession().then(({ data }) => {
    if (active && !authEventReceived) onSession(data.session)
  }).catch(() => {
    if (active && !authEventReceived) onBootstrapError()
  })
  return () => {
    active = false
    subscription.unsubscribe()
  }
}
