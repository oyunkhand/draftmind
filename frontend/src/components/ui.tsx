import { useState, type ReactNode } from 'react'
import { useApp } from '../lib/store'
import type { Factor, Role } from '../lib/types'

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? 'n/a' : `${(100 * x).toFixed(digits)}%`

export const ROLE_SHORT: Record<string, string> = { top: 'TOP', jungle: 'JNG', mid: 'MID', bot: 'BOT', support: 'SUP' }
const ROLE_COLOR: Record<string, string> = {
  top: 'text-orange-300 bg-orange-400/10', jungle: 'text-emerald-300 bg-emerald-400/10', mid: 'text-sky-300 bg-sky-400/10',
  bot: 'text-rose-300 bg-rose-400/10', support: 'text-violet-300 bg-violet-400/10',
}

export function RoleChip({ role }: { role: Role | string | null | undefined }) {
  if (!role) return null
  return <span className={`chip ${ROLE_COLOR[role] ?? 'bg-white/5 text-slate-300'}`}>{ROLE_SHORT[role] ?? role}</span>
}

export function champIconUrl(version: string, id: string) {
  return `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${id}.png`
}

export function ChampIcon({ id, size = 40, className = '', dim = false, title, rounded = 'rounded-lg' }: {
  id: string | null | undefined; size?: number; className?: string; dim?: boolean; title?: string; rounded?: string
}) {
  const { ddVersion, champById } = useApp()
  const [failed, setFailed] = useState(false)
  if (!id) {
    return <div className={`${rounded} bg-ink-800 ring-1 ring-white/5 ${className}`} style={{ width: size, height: size }} />
  }
  const name = champById[id]?.name ?? id
  const style = { width: size, height: size }
  if (failed || !ddVersion) {
    const initials = name.replace(/[^A-Za-z ]/g, '').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    return (
      <div title={title ?? name} style={style}
        className={`${rounded} grid place-items-center bg-gradient-to-br from-ink-600 to-ink-800 font-display text-xs font-bold text-slate-300 ring-1 ring-white/10 ${dim ? 'opacity-30 grayscale' : ''} ${className}`}>
        {initials}
      </div>
    )
  }
  return (
    <img src={champIconUrl(ddVersion, id)} alt={name} title={title ?? name} loading="lazy" style={style}
      onError={() => setFailed(true)}
      className={`${rounded} object-cover ring-1 ring-white/10 ${dim ? 'opacity-25 grayscale' : ''} ${className}`} />
  )
}

export function TeamBadge({ id, size = 'md', showName = false }: { id: string; size?: 'sm' | 'md' | 'lg'; showName?: boolean }) {
  const { teamById } = useApp()
  const t = teamById[id]
  const color = t?.color ?? '#64748b'
  const dims = size === 'lg' ? 'h-12 w-12 text-base' : size === 'sm' ? 'h-6 w-6 text-[9px]' : 'h-8 w-8 text-[11px]'
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`grid place-items-center rounded-lg font-display font-bold ${dims}`}
        style={{ background: `${color}22`, color, boxShadow: `inset 0 0 0 1px ${color}55` }}>
        {t?.tag ?? id}
      </span>
      {showName && <span className="font-medium text-slate-100">{t?.name ?? id}</span>}
    </span>
  )
}

export function Bar({ value, color = 'bg-accent', className = '', max = 1 }: { value: number; color?: string; className?: string; max?: number }) {
  const w = Math.max(0, Math.min(1, value / max)) * 100
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06] ${className}`}>
      <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${w}%` }} />
    </div>
  )
}

export function Stat({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="label">{label}</div>
      <div className={`mt-0.5 font-display text-2xl font-bold ${accent ?? 'text-slate-50'}`}>{value}</div>
      {sub && <div className="text-xs text-slate-400">{sub}</div>}
    </div>
  )
}

export function Panel({ title, right, children, className = '', bodyClass = 'p-4' }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <div className="panel-head">
          <h2 className="panel-title">{title}</h2>
          {right}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 p-6 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
      {label}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-white/10 p-6 text-center text-sm text-slate-400">{children}</div>
}

/** Diverging contribution bars: the "why" behind a score is exactly these numbers. */
export function FactorBars({ factors, compact = false }: { factors: Factor[]; compact?: boolean }) {
  const max = Math.max(0.5, ...factors.map(f => Math.abs(f.contribution)))
  return (
    <div className="space-y-2">
      {factors.map(f => {
        const w = (Math.abs(f.contribution) / max) * 50
        const pos = f.contribution >= 0
        return (
          <div key={f.key} className="text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-medium text-slate-300">{f.label}</span>
              <span className={`font-mono ${pos ? 'text-emerald-300' : 'text-rose-300'}`}>
                {pos ? '+' : ''}{f.contribution.toFixed(2)}
                <span className="ml-1 text-slate-500">({f.value.toFixed(2)} × {f.weight})</span>
              </span>
            </div>
            <div className="relative mt-1 h-1.5 rounded-full bg-white/[0.05]">
              <div className="absolute top-0 left-1/2 h-1.5 w-px bg-white/20" />
              <div className={`absolute top-0 h-1.5 rounded-full ${pos ? 'bg-emerald-400/80' : 'bg-rose-400/80'}`}
                style={pos ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }} />
            </div>
            {!compact && <div className="mt-1 text-[11px] leading-snug text-slate-400">{f.evidence}</div>}
          </div>
        )
      })}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange, size = 'sm' }: {
  value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: 'sm' | 'md'
}) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 bg-ink-850 p-0.5">
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={`rounded-md ${size === 'md' ? 'px-3 py-1.5 text-sm' : 'px-2.5 py-1 text-xs'} font-medium transition ${value === o.value ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function TeamSelect({ value, onChange, exclude, label }: { value: string; onChange: (v: string) => void; exclude?: string; label?: string }) {
  const { teams } = useApp()
  return (
    <label className="flex flex-col gap-1">
      {label && <span className="label">{label}</span>}
      <select className="input" value={value} onChange={e => onChange(e.target.value)}>
        {teams.filter(t => t.id !== exclude).map(t => (
          <option key={t.id} value={t.id}>{t.name} ({t.tag})</option>
        ))}
      </select>
    </label>
  )
}

export function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function fmtDuration(s: number | null) {
  if (!s) return 'n/a'
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
}
