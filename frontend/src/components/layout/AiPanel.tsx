import { Sparkles, Lock } from 'lucide-react'

/**
 * Panel derecho del Asistente IA (SPEC §8). En Fase 0 está inactivo:
 * se ancla a los datos limpios del negocio, y sin datos no hay asistente.
 */
export default function AiPanel() {
  return (
    <aside className="hidden h-full w-80 shrink-0 flex-col bg-navy-deep text-white xl:flex">
      <div className="flex h-16 items-center gap-2 border-b border-white/10 px-5">
        <Sparkles className="h-5 w-5 text-gold" />
        <h2 className="text-base font-semibold">Asistente IA</h2>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white/5">
          <Lock className="h-6 w-6 text-white/40" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white/90">
            El asistente se activa cuando cargas tus datos
          </p>
          <p className="mt-2 text-xs leading-relaxed text-white/50">
            Sube y limpia tu primer archivo. Después, tu analista de datos con IA
            resumirá qué pasó en tu negocio, te sugerirá preguntas y responderá las
            tuyas.
          </p>
        </div>
      </div>

      <div className="border-t border-white/10 p-4">
        <div className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2.5">
          <input
            disabled
            placeholder="Escribe tu pregunta..."
            className="w-full bg-transparent text-sm text-white/40 placeholder-white/30 outline-none"
          />
        </div>
        <p className="mt-2 text-center text-[10px] text-white/30">
          IA puede cometer errores. Verifica la información.
        </p>
      </div>
    </aside>
  )
}
