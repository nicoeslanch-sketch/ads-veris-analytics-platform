export const PASSWORD_RECOVERY_PATH = '/restablecer-contrasena'

interface AuthUrlParts {
  hash: string
  search: string
}

function paramsFrom(value: string): URLSearchParams {
  return new URLSearchParams(value.replace(/^[?#]/, ''))
}

export function hasPasswordRecoveryHint(location: AuthUrlParts): boolean {
  const hash = paramsFrom(location.hash)
  const search = paramsFrom(location.search)
  return hash.get('type') === 'recovery' || search.get('type') === 'recovery'
}

export function getPasswordRecoveryError(location: AuthUrlParts): string | null {
  const hash = paramsFrom(location.hash)
  const search = paramsFrom(location.search)
  const description = hash.get('error_description') ?? search.get('error_description')

  if (description) {
    const normalized = description.toLowerCase()
    if (normalized.includes('invalid') || normalized.includes('expired')) {
      return 'El enlace de recuperación no es válido o ya venció.'
    }
    return description
  }
  if (hash.has('error') || search.has('error')) {
    return 'El enlace de recuperación no es válido o ya venció.'
  }
  return null
}

export function buildPasswordRecoveryRedirect(origin: string): string {
  return new URL(PASSWORD_RECOVERY_PATH, `${origin.replace(/\/$/, '')}/`).toString()
}
