import { useState } from 'react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { DraftAnalysis, Explanation, Prediction, Recommendation } from '../lib/types'
import { ChampIcon, FactorBars, RoleChip, pct } from './ui'

function ExplainButton({ draftId, champion, kind }: { draftId: string; champion: string; kind: 'recommendation' | 'prediction' }) {
  const [exp, setExp] = useState<Explanation | null>(null)
  const [loading, setLoading] = useState(false)
  if (exp) {
    return (
      <div className="mt-3 rounded-lg border border-accent/20 bg-accent/[0.05] p-3 text-xs leading-relaxed text-slate-200">
        <div className="mb-1 flex items-center gap-2">
          <span className="chip bg-accent/15 text-accent">{exp.source === 'template' ? 'Explanation' : `AI · ${exp.source === 'anthropic' ? 'Claude' : exp.source}`}</span>
        </div>
        {exp.text}
      </div>
    )
  }
  return (
    <button className="mt-3 text-xs font-medium text-accent hover:underline" disabled={loading}
      onClick={async () => { setLoading(true); try { setExp(await api.explain(draftId, champion, kind)) } finally { setLoading(false) } }}>
      {loading ? 'Writing explanation…' : 'Explain in plain English →'}
    </button>
  )
}

export function RecCard({ rec, a, actionable, busy, onDecide, onModify, modifying }: {
  rec: Recommendation; a: DraftAnalysis; actionable: boolean; busy: boolean; modifying: boolean
  onDecide: (r: Recommendation, d: 'accept' | 'reject') => void; onModify: (r: Recommendation) => void
}) {
  const [open, setOpen] = useState(false)
  const isBan = a.recommendations.type === 'ban'
  return (
    <div className={`rounded-lg border transition ${modifying ? 'border-amber-400/60 bg-amber-400/[0.06]' : rec.rank === 1 ? 'border-accent/30 bg-accent/[0.04]' : 'border-white/[0.06] bg-white/[0.02]'}`}>
      <div className="flex items-start gap-3 p-2.5">
        <div className="relative">
          <ChampIcon id={rec.champion} size={44} />
          <span className="absolute -top-1.5 -left-1.5 grid h-5 w-5 place-items-center rounded-full bg-ink-950 font-display text-[11px] font-bold text-slate-300 ring-1 ring-white/15">{rec.rank}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold text-slate-50">{rec.name}</span>
            <RoleChip role={rec.role} />
            {isBan && <span className="chip bg-rose-500/10 text-rose-300">ban</span>}
            {a.win_probability?.what_if?.[rec.champion] != null && (
              <span className={`ml-auto chip tabular-nums ${Math.abs(a.win_probability.what_if[rec.champion]) < 0.005 ? 'bg-white/5 text-slate-500' : a.win_probability.what_if[rec.champion] > 0 ? 'bg-emerald-400/10 text-emerald-300' : 'bg-rose-400/10 text-rose-300'}`}
                title="Change in our win probability if we pick this now (changes under 0.5% are within noise)">
                {Math.abs(a.win_probability.what_if[rec.champion]) < 0.005 ? '≈0% win'
                  : `${a.win_probability.what_if[rec.champion] > 0 ? '+' : '−'}${Math.abs(100 * a.win_probability.what_if[rec.champion]).toFixed(1)}% win`}
              </span>
            )}
            <span className={`${a.win_probability?.what_if?.[rec.champion] != null ? '' : 'ml-auto '}font-display text-lg font-bold text-accent`}>{rec.score}</span>
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-indigo-400" style={{ width: `${rec.score}%` }} />
          </div>
          <div className="mt-1.5 line-clamp-2 text-[11.5px] leading-snug text-slate-400">{rec.pros[0] ?? rec.summary}</div>
        </div>
      </div>
      <div className="flex items-center gap-1.5 border-t border-white/[0.05] px-2.5 py-1.5">
        {actionable ? (
          <>
            <button className="btn-ok px-2 py-1 text-xs" disabled={busy} onClick={() => onDecide(rec, 'accept')} title="Lock this in">✓ Accept</button>
            <button className="btn-warn px-2 py-1 text-xs" disabled={busy} onClick={() => onModify(rec)} title="Pick a different champion in the grid">✎ Modify</button>
            <button className="btn-bad px-2 py-1 text-xs" disabled={busy} onClick={() => onDecide(rec, 'reject')} title="Hide and log as rejected">✕ Reject</button>
          </>
        ) : <span className="text-[11px] text-slate-500">Preview — waiting for opponent</span>}
        <button className="ml-auto text-xs font-medium text-slate-400 hover:text-white" onClick={() => setOpen(o => !o)}>
          Why? {open ? '▴' : '▾'}
        </button>
      </div>
      {open && (
        <div className="border-t border-white/[0.05] p-3">
          <FactorBars factors={rec.factors} />
          {rec.risks.length > 0 && <div className="mt-2 text-[11px] text-rose-300">⚠ {rec.risks.join(' · ')}</div>}
          <ExplainButton draftId={a.id} champion={rec.champion} kind="recommendation" />
        </div>
      )}
    </div>
  )
}

export function PredictionRow({ p, a, canLock, busy, onLock, color }: {
  p: Prediction; a: DraftAnalysis; canLock: boolean; busy: boolean; onLock: (c: string) => void; color: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02]">
      <div className="flex items-center gap-3 p-2">
        <ChampIcon id={p.champion} size={36} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm">
            <span className="truncate font-semibold text-slate-100">{p.name}</span>
            <RoleChip role={p.role} />
            <span className="ml-auto font-display text-base font-bold" style={{ color }}>{pct(p.probability)}</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full" style={{ width: `${Math.max(3, p.probability * 100)}%`, background: color }} />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 px-2 pb-1.5">
        <span className="line-clamp-1 flex-1 text-[11px] text-slate-400">{p.why}</span>
        {canLock && <button className="text-[11px] font-semibold text-accent hover:underline" disabled={busy} onClick={() => onLock(p.champion)}>Lock in</button>}
        <button className="text-[11px] text-slate-400 hover:text-white" onClick={() => setOpen(o => !o)}>Why {open ? '▴' : '▾'}</button>
      </div>
      {open && (
        <div className="border-t border-white/[0.05] p-3">
          <FactorBars factors={p.factors} />
          <ExplainButton draftId={a.id} champion={p.champion} kind="prediction" />
        </div>
      )}
    </div>
  )
}

export function DecisionMini({ a }: { a: DraftAnalysis }) {
  const { champById } = useApp()
  const ds = a.decisions.filter(d => d.decision !== 'manual').slice(-5).reverse()
  if (!ds.length) return <div className="text-xs text-slate-500">No coach decisions yet. Accept, modify or reject a suggestion — DraftMind learns your preferences.</div>
  const badge: Record<string, string> = { accept: 'bg-emerald-400/15 text-emerald-300', modify: 'bg-amber-400/15 text-amber-300', reject: 'bg-rose-400/15 text-rose-300' }
  return (
    <ul className="space-y-1.5">
      {ds.map(d => (
        <li key={d.id} className="flex items-center gap-2 text-xs">
          <span className={`chip ${badge[d.decision]}`}>{d.decision}</span>
          <span className="text-slate-300">{champById[d.suggested_champion ?? '']?.name ?? d.suggested_champion}</span>
          {d.decision === 'modify' && <><span className="text-slate-500">→</span><span className="text-slate-100">{champById[d.final_champion ?? '']?.name}</span></>}
          <span className="ml-auto text-slate-500">{d.action_type} #{d.step + 1}</span>
        </li>
      ))}
    </ul>
  )
}
