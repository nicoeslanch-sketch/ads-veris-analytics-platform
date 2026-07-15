interface PageHeaderProps {
  title: string
  subtitle: string
  className?: string
}

export default function PageHeader({ title, subtitle, className = '' }: PageHeaderProps) {
  return (
    <div className={`mb-6 sm:mb-8 ${className}`}>
      <h1 className="text-xl font-bold text-navy sm:text-2xl">{title}</h1>
      <p className="mt-1 text-sm text-navy/60">{subtitle}</p>
    </div>
  )
}
