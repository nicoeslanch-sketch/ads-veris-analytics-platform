/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_KEEP_ALIVE_ENABLED?: string
}

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_CONSOLIDATION_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
