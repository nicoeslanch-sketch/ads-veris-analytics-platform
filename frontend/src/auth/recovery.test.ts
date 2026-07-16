import { describe, expect, it } from 'vitest'
import {
  buildPasswordRecoveryRedirect,
  getPasswordRecoveryError,
  hasPasswordRecoveryHint,
} from './recovery'

describe('password recovery URL', () => {
  it('detecta enlaces antiguos que llegan a la raíz con type=recovery', () => {
    expect(hasPasswordRecoveryHint({ hash: '#access_token=token&type=recovery', search: '' })).toBe(true)
  })

  it('no confunde una sesión normal con una recuperación', () => {
    expect(hasPasswordRecoveryHint({ hash: '#access_token=token&type=signup', search: '' })).toBe(false)
  })

  it('construye la ruta pública sin depender de una barra final', () => {
    expect(buildPasswordRecoveryRedirect('https://ads-veris.cl')).toBe(
      'https://ads-veris.cl/restablecer-contrasena',
    )
    expect(buildPasswordRecoveryRedirect('http://localhost:5173/')).toBe(
      'http://localhost:5173/restablecer-contrasena',
    )
  })

  it('extrae el motivo de un enlace rechazado por Supabase', () => {
    expect(
      getPasswordRecoveryError({
        hash: '#error=access_denied&error_description=Email+link+is+invalid+or+has+expired',
        search: '',
      }),
    ).toBe('El enlace de recuperación no es válido o ya venció.')
  })
})
