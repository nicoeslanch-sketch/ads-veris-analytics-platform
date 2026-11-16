type SkeletonKind = 'dashboard' | 'table' | 'form'

export function SkeletonLayout({ kind = 'dashboard', compact = false }: { kind?: SkeletonKind; compact?: boolean }) {
  return <div aria-hidden="true" className="min-w-0 space-y-5" data-testid={`skeleton-${kind}`}>
    {kind === 'dashboard' && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Array.from({ length: 4 }, (_, i) => <div key={i} className="min-w-0 space-y-3 rounded-lg border border-navy/10 p-4">
        <div className="loading-skeleton h-3 w-2/3" /><div className="loading-skeleton h-7 w-4/5" />
      </div>)}
    </div>}
    {kind === 'dashboard' ? <div className={`grid gap-5 ${compact ? '' : 'lg:grid-cols-2'}`}>
      {Array.from({ length: compact ? 1 : 2 }, (_, panel) => <div key={panel} className="min-w-0 space-y-5">
        <div className="loading-skeleton h-4 w-1/2" />
        <div className="flex h-44 items-end gap-3 border-b border-navy/10 pb-2">
          {[42, 68, 51, 82, 60, 74].map((height, i) => <div key={i} className="loading-skeleton min-w-0 flex-1" style={{ height: `${height}%` }} />)}
        </div>
      </div>)}
    </div> : kind === 'table' ? <div className="space-y-4">
      <div className="loading-skeleton h-8 w-full" />
      {Array.from({ length: compact ? 3 : 6 }, (_, i) => <div key={i} className="grid grid-cols-[2fr_1fr_1fr] gap-5 border-b border-navy/5 pb-3">
        {[0, 1, 2].map(j => <div key={j} className="loading-skeleton h-4" />)}
      </div>)}
    </div> : <div className="grid gap-5 sm:grid-cols-2">
      {Array.from({ length: compact ? 2 : 4 }, (_, i) => <div key={i} className="space-y-2"><div className="loading-skeleton h-3 w-1/3" /><div className="loading-skeleton h-10 w-full" /></div>)}
    </div>}
  </div>
}

export default function LoadingSkeleton({ label = 'Cargando datos', ...props }: { label?: string; kind?: SkeletonKind; compact?: boolean }) {
  return <div role="status" aria-busy="true" className="min-w-0 py-4">
    <span className="sr-only">{label}</span><SkeletonLayout {...props} />
  </div>
}
