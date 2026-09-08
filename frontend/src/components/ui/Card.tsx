import type { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  children: ReactNode
}

export default function Card({ children, className = '', ...props }: CardProps) {
  return (
    <div
      data-dashboard-card
      className={`min-w-0 max-w-full break-words rounded-xl border border-navy/10 bg-white p-4 shadow-sm sm:p-6 ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
