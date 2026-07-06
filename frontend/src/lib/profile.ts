/** Perfil del usuario (tabla profiles, migración 0001) — Fase 5 Configuración. */

import { supabase } from './supabase'
import type { PlanCode } from './plans'

export interface Profile {
  full_name: string | null
  company: string | null
  rut: string | null
  country: string | null
  phone: string | null
  plan: PlanCode
  preferences: Record<string, unknown>
}

export async function fetchProfile(): Promise<Profile | null> {
  if (!supabase) return null
  const { data: sessionData } = await supabase.auth.getSession()
  const userId = sessionData.session?.user.id
  if (!userId) return null
  const { data, error } = await supabase
    .from('profiles')
    .select('full_name, company, rut, country, phone, plan, preferences')
    .eq('id', userId)
    .maybeSingle()
  if (error) {
    console.warn('[perfil] No se pudo leer profiles:', error.message)
    return null
  }
  return (data as Profile) ?? null
}

export async function updateProfile(
  fields: Partial<Pick<Profile, 'full_name' | 'company' | 'rut' | 'country' | 'phone'>>,
): Promise<boolean> {
  if (!supabase) return false
  const { data: sessionData } = await supabase.auth.getSession()
  const userId = sessionData.session?.user.id
  if (!userId) return false
  const { error } = await supabase.from('profiles').update(fields).eq('id', userId)
  if (error) console.warn('[perfil] No se pudo actualizar profiles:', error.message)
  return !error
}
