import type { CSSProperties, ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  /** Estilos inline (ej: tinte suave con el color del indicador — Fase 8). */
  style?: CSSProperties
}

export default function Card({ children, className = '', style }: CardProps) {
  return (
    <div
      className={`rounded-xl border border-navy/10 bg-white p-4 shadow-sm sm:p-6 ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}
