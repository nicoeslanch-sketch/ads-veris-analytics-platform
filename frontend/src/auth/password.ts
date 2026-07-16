export const PASSWORD_POLICY_RE = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/

export const PASSWORD_POLICY_MESSAGE =
  'La contraseña debe tener al menos 8 caracteres e incluir letras y números.'

export function isValidPassword(password: string): boolean {
  return PASSWORD_POLICY_RE.test(password)
}
