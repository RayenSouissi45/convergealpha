import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle }: { title: ReactNode; subtitle?: ReactNode }) {
  return (
    <header className="mb-5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-600 dark:text-zinc-400">{subtitle}</p>}
    </header>
  )
}

export function Card({
  title,
  aside,
  children,
  className = '',
}: {
  title?: ReactNode
  aside?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900 ${className}`}
    >
      {(title || aside) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  )
}

export function PhaseChip({ phase }: { phase: number }) {
  return (
    <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
      Arrives in phase {phase}
    </span>
  )
}

/** A section that is not built yet: says what it will show and when. Never shows sample data. */
export function Planned({
  title,
  phase,
  children,
}: {
  title: ReactNode
  phase: number
  children: ReactNode
}) {
  return (
    <Card title={title} aside={<PhaseChip phase={phase} />}>
      <div className="space-y-2 text-sm text-slate-600 dark:text-zinc-400">{children}</div>
    </Card>
  )
}

export type Tone = 'good' | 'warn' | 'bad' | 'neutral'

const TONE: Record<Tone, string> = {
  good: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300 dark:ring-emerald-400/30',
  warn: 'bg-amber-50 text-amber-900 ring-amber-600/25 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-400/30',
  bad: 'bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-950 dark:text-red-300 dark:ring-red-400/30',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-500/20 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-500/30',
}

const DOT: Record<Tone, string> = {
  good: 'bg-emerald-500',
  warn: 'bg-amber-500',
  bad: 'bg-red-500',
  neutral: 'bg-slate-400 dark:bg-zinc-500',
}

/** Status pill: the colour is never the only signal, the text always says it too. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${TONE[tone]}`}
    >
      <span className={`size-1.5 rounded-full ${DOT[tone]}`} aria-hidden="true" />
      {children}
    </span>
  )
}

export function Row({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-slate-100 py-2.5 text-sm last:border-0 dark:border-zinc-800">
      <dt className="text-slate-600 dark:text-zinc-400">{label}</dt>
      <dd className="text-right font-medium tabular-nums">{children}</dd>
    </div>
  )
}
