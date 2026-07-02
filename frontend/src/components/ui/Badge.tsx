import type { ReactNode } from 'react'

type Tone = 'teal' | 'gold' | 'green' | 'coral' | 'navy'

const tones: Record<Tone, string> = {
  teal: 'bg-teal/10 text-teal',
  gold: 'bg-gold/15 text-gold',
  green: 'bg-green/10 text-green',
  coral: 'bg-coral/10 text-coral',
  navy: 'bg-navy/10 text-navy',
}

export default function Badge({
  tone = 'teal',
  children,
}: {
  tone?: Tone
  children: ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  )
}
