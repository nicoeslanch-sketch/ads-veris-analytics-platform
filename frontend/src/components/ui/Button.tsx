import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'gold' | 'ghost'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: ReactNode
}

const styles: Record<Variant, string> = {
  primary:
    'bg-teal text-white hover:bg-teal/90 focus-visible:outline-teal disabled:bg-teal/50',
  secondary:
    'bg-navy text-white hover:bg-navy-deep focus-visible:outline-navy disabled:bg-navy/50',
  gold: 'bg-gold text-navy-deep hover:bg-gold/90 focus-visible:outline-gold disabled:bg-gold/50',
  ghost:
    'bg-transparent text-navy border border-navy/20 hover:bg-navy/5 focus-visible:outline-navy',
}

export default function Button({
  variant = 'primary',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed ${styles[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
