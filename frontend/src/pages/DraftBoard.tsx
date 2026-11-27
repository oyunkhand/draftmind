import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DecisionMini, PredictionRow, RecCard } from '../components/AiPanels'
import { ChampIcon, RoleChip, Segmented, Spinner, TeamBadge, pct } from '../components/ui'
import WeightsDrawer from '../components/WeightsDrawer'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { DraftAnalysis, Recommendation, Role, Side, TimelineSlot } from '../lib/types'
import { ROLES } from '../lib/types'

const SIDE_COLOR: Record<Side, string> = { blue: '#3b82f6', red: '#ef4444' }

function TeamColumn({ a, side }: { a: DraftAnalysis; side: Side }) {
  const { teamById, champById } = useApp()
  const slots = a.state.timeline.filter(s => s.side === side)
  const picks = slots.filter(s => s.type === 'pick')
  const bans = slots.filter(s => s.type === 'ban')
  const team = side === a.our_side ? a.our_team : a.opponent
  const roles = a.state.roles[side]
  const roleOf: Record<string, Role> = Object.fromEntries(Object.entries(roles).map(([r, c]) => [c as string, r as Role]))
  const players = teamById[team]?.players ?? []
  const ours = side === a.our_side
  return (
    <div className="panel flex flex-col overflow-hidden" style={{ boxShadow: `inset 0 3px 0 ${SIDE_COLOR[side]}` }}>
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <TeamBadge id={team} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-100">{teamById[team]?.name}</div>
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: SIDE_COLOR[side] }}>{side} side {ours && '· us'}</div>
        </div>
      </div>
      <div className="flex gap-1 px-3 pb-3">
        {bans.map(b => (
          <div key={b.index} className={`relative rounded-md ${b.current ? 'pulse-ring ring-1 ring-accent' : ''}`} title={b.label}>
            <ChampIcon id={b.champion} size={30} rounded="rounded-md" className={b.champion ? 'grayscale-[60%]' : ''} />
            {b.champion && <div className="pointer-events-none absolute inset-0 rounded-md bg-[linear-gradient(135deg,transparent_45%,rgba(244,63,94,.9)_47%,rgba(244,63,94,.9)_53%,transparent_55%)]" />}
          </div>
        ))}
      </div>
      <div className="flex-1 space-y-1.5 px-2 pb-2">
        {picks.map(p => {
          const role = p.champion ? roleOf[p.champion] : undefined
          const player = role ? players.find(x => x.role === role) : undefined
          return (
            <div key={p.index}
              className={`flex items-center gap-2.5 rounded-lg p-1.5 transition ${p.current ? 'pulse-ring bg-accent/10 ring-1 ring-accent/60' : p.champion ? 'bg-white/[0.03]' : 'bg-white/[0.015]'}`}>
              <ChampIcon id={p.champion} size={44} />
              <div className="min-w-0 flex-1">
                {p.champion ? (
                  <>
                    <div className="truncate text-sm font-semibold text-slate-50">{champById[p.champion]?.name}</div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-400"><RoleChip role={role} /> {player?.name}</div>
                  </>
                ) : (
                  <div className={`text-xs ${p.current ? 'font-semibold text-accent' : 'text-slate-600'}`}>{p.current ? 'Picking…' : p.label}</div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Timeline({ slots }: { slots: TimelineSlot[] }) {
  const phases = [
    { key: 'ban1', label: 'Bans 1' }, { key: 'pick1', label: 'Picks 1' }, { key: 'ban2', label: 'Bans 2' }, { key: 'pick2', label: 'Picks 2' },
  ]
  return (
    <div className="panel scroll-thin flex gap-3 overflow-x-auto px-3 py-2">
      {phases.map(ph => (
        <div key={ph.key} className="shrink-0">
          <div className="label mb-1">{ph.label}</div>
          <div className="flex gap-1">
            {slots.filter(s => s.phase === ph.key).map(s => (
              <div key={s.index} title={s.label}
                className={`relative rounded-md ${s.current ? 'pulse-ring ring-2 ring-accent' : ''}`}
                style={{ boxShadow: s.current ? undefined : `inset 0 -2px 0 ${SIDE_COLOR[s.side]}` }}>
                {s.champion ? <ChampIcon id={s.champion} size={28} rounded="rounded-md" className={s.type === 'ban' ? 'grayscale' : ''} />
                  : <div className="grid h-7 w-7 place-items-center rounded-md bg-ink-800 text-[9px] font-bold" style={{ color: SIDE_COLOR[s.side] }}>{s.label.split(' ')[0]}</div>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function DraftBoard() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { champions, teamById, toast } = useApp()
  const [a, setA] = useState<DraftAnalysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [role, setRole] = useState<'all' | Role>('all')
  const [hideUnavailable, setHideUnavailable] = useState(false)
  const [modifying, setModifying] = useState<Recommendation | null>(null)
  const [weightsOpen, setWeightsOpen] = useState(false)
  const [nextSide, setNextSide] = useState<Side>('blue')
  const [nextFirst, setNextFirst] = useState<Side>('blue')

  const load = useCallback(() => api.draft(id).then(setA).catch(e => toast(e.message, 'err')), [id, toast])
  useEffect(() => { setA(null); load() }, [load])

  const run = useCallback(async (fn: () => Promise<DraftAnalysis>, msg?: string) => {
    setBusy(true)
    try {
      setA(await fn())
      if (msg) toast(msg)
    } catch (e) {
      toast((e as Error).message, 'err')
    } finally {
      setBusy(false)
    }
  }, [toast])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !busy) { e.preventDefault(); run(() => api.undo(id)) }
      if (e.key === 'Escape') setModifying(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [id, busy, run])

  const cur = a?.state.current ?? null
  const taken = useMemo(() => new Set(a?.state.timeline.map(s => s.champion).filter(Boolean) as string[]), [a])
  const predMap = useMemo(() => {
    if (!a || !cur || cur.ours || a.prediction.step?.index !== cur.index) return {} as Record<string, number>
    return Object.fromEntries(a.prediction.predictions.map(p => [p.champion, p.probability]))
  }, [a, cur])
  const recRank = useMemo(() => {
    if (!a || !cur?.ours) return {} as Record<string, number>
    return Object.fromEntries(a.recommendations.recommendations.slice(0, 5).map((r, i) => [r.champion, i + 1]))
  }, [a, cur])

  if (!a) return <Spinner label="Loading draft…" />

  const unavailable = (c: string): string | null => {
    if (taken.has(c)) return 'taken'
    if (!cur) return null
    if (cur.type === 'pick' && a.locked[cur.side]?.includes(c)) return 'fearless'
    if (cur.type === 'ban' && a.locked.blue.includes(c) && a.locked.red.includes(c)) return 'fearless'
    return null
  }
  const lockedAny = new Set([...a.locked.blue, ...a.locked.red])
  const list = champions
    .filter(c => (role === 'all' || c.roles.includes(role)) && c.name.toLowerCase().includes(q.toLowerCase()))
    .filter(c => !hideUnavailable || !unavailable(c.id))
    .sort((x, y) => x.name.localeCompare(y.name))

  const clickChamp = (c: string) => {
    if (!cur || busy) return
    const why = unavailable(c)
    if (why) { toast(why === 'fearless' ? 'Fearless: already used in this series' : 'Already picked or banned', 'err'); return }
    if (modifying) {
      const m = modifying
      setModifying(null)
      run(() => api.decide(id, m.champion, 'modify', c), `Modified: ${m.name} → ${champions.find(x => x.id === c)?.name}`)
      return
    }
    run(() => api.action(id, c))
  }

  const us = teamById[a.our_team]
  const them = teamById[a.opponent]
  const oppSide: Side = a.our_side === 'blue' ? 'red' : 'blue'
  const recStep = a.recommendations.step
  const predStep = a.prediction.step

  const startNext = async () => {
    try {
      const g = await api.createGame(a.series_id, nextSide, nextFirst)
      toast(`Game ${g.game_number} created — fearless pool updated`)
      nav(`/draft/${g.id}`)
    } catch (e) { toast((e as Error).message, 'err') }
  }

  return (
    <div className="mx-auto max-w-[1800px] space-y-3">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3">
          <TeamBadge id={a.our_team} size="md" />
          <span className="font-display text-xl font-bold text-white">{us?.name}</span>
          <span className="font-display text-sm text-slate-500">vs</span>
          <span className="font-display text-xl font-bold text-white">{them?.name}</span>
          <TeamBadge id={a.opponent} size="md" />
        </div>
        <span className="chip bg-white/5 text-slate-300">Game {a.game_number} · Bo{a.best_of}</span>
        <span className={`chip ${a.fearless_mode === 'off' ? 'bg-white/5 text-slate-400' : 'bg-gold/15 text-gold'}`}>
          {a.fearless_mode === 'off' ? 'Standard draft' : `Fearless · ${a.fearless_mode}`}{lockedAny.size ? ` · ${lockedAny.size} locked` : ''}
        </span>
        <div className="ml-auto flex gap-2">
          <button className="btn-ghost" disabled={busy || a.state.index === 0} onClick={() => run(() => api.undo(id))} title="Undo (Ctrl/Cmd+Z)">↶ Undo</button>
          <button className="btn-ghost" onClick={() => setWeightsOpen(true)}>⚖ Weights</button>
          <Link className="btn-ghost" to={`/series/${a.series_id}`}>Series log</Link>
        </div>
      </div>

      <Timeline slots={a.state.timeline} />

      <div className="grid gap-3 xl:grid-cols-[210px_minmax(0,1fr)_210px_400px] lg:grid-cols-[200px_minmax(0,1fr)_200px]">
        <TeamColumn a={a} side="blue" />

        {/* Center: turn banner + champion grid */}
        <div className="panel flex min-h-[560px] flex-col">
          <div className="border-b border-white/[0.06] p-3">
            {a.state.complete ? (
              <div className="flex flex-wrap items-center gap-3">
                <div className="font-display text-lg font-bold text-white">Draft complete</div>
                <span className="text-sm text-slate-400">Record the result to track the series:</span>
                <button className={`btn ${a.result === 'win' ? 'bg-emerald-500 text-ink-950' : 'btn-ghost'}`} onClick={() => run(() => api.result(id, 'win'), 'Result saved')}>We won</button>
                <button className={`btn ${a.result === 'loss' ? 'bg-rose-500 text-white' : 'btn-ghost'}`} onClick={() => run(() => api.result(id, 'loss'), 'Result saved')}>We lost</button>
                {a.game_number < a.best_of && (
                  <div className="ml-auto flex items-center gap-2">
                    <span className="text-xs text-slate-500">Our side</span>
                    <Segmented value={nextSide} onChange={setNextSide} options={[{ value: 'blue', label: 'Blue' }, { value: 'red', label: 'Red' }]} />
                    <span className="text-xs text-slate-500">Drafts first</span>
                    <Segmented value={nextFirst} onChange={setNextFirst} options={[{ value: 'blue', label: 'Blue' }, { value: 'red', label: 'Red' }]} />
                    <button className="btn-primary" onClick={startNext}>Start game {a.game_number + 1} →</button>
                  </div>
                )}
              </div>
            ) : modifying ? (
              <div className="flex items-center gap-3 rounded-lg bg-amber-400/10 px-3 py-2 ring-1 ring-amber-400/40">
                <ChampIcon id={modifying.champion} size={28} />
                <span className="text-sm text-amber-200">Modify: choose the champion to {cur?.type} instead of <b>{modifying.name}</b></span>
                <button className="btn-ghost ml-auto" onClick={() => setModifying(null)}>Cancel (Esc)</button>
              </div>
            ) : cur && (
              <div className="flex flex-wrap items-center gap-3">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SIDE_COLOR[cur.side] }} />
                <span className="font-display text-lg font-bold text-white">{cur.label}</span>
                <span className="text-sm text-slate-400">— {teamById[cur.team]?.name}</span>
                <span className={`chip ${cur.ours ? 'bg-accent/15 text-accent' : 'bg-white/5 text-slate-300'}`}>
                  {cur.ours ? 'Your turn — use the AI panel or click a champion' : `Enter ${them?.tag}'s ${cur.type}: click the champion they chose`}
                </span>
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input className="input w-48" placeholder="Search champion…" value={q} onChange={e => setQ(e.target.value)} />
              <Segmented value={role} onChange={setRole}
                options={[{ value: 'all', label: 'All' }, ...ROLES.map(r => ({ value: r, label: r === 'jungle' ? 'Jungle' : r === 'support' ? 'Support' : r[0].toUpperCase() + r.slice(1) }))]} />
              <label className="ml-auto flex items-center gap-2 text-xs text-slate-400">
                <input type="checkbox" checked={hideUnavailable} onChange={e => setHideUnavailable(e.target.checked)} className="accent-cyan-400" />
                Hide unavailable
              </label>
            </div>
          </div>
          <div className="scroll-thin grid max-h-[calc(100vh-330px)] min-h-[420px] flex-1 grid-cols-[repeat(auto-fill,minmax(62px,1fr))] content-start gap-2 overflow-y-auto p-3">
            {list.map(c => {
              const why = unavailable(c.id)
              const prob = predMap[c.id]
              const rank = recRank[c.id]
              return (
                <button key={c.id} onClick={() => clickChamp(c.id)} disabled={!!why || a.state.complete}
                  className={`group relative flex flex-col items-center gap-1 rounded-lg p-1 transition ${why ? 'cursor-not-allowed' : 'hover:bg-white/[0.06]'} ${modifying && !why ? 'hover:ring-1 hover:ring-amber-400/60' : ''}`}>
                  <ChampIcon id={c.id} size={52} dim={!!why} className={!why ? 'group-hover:ring-accent/60' : ''} />
                  <span className={`w-full truncate text-center text-[10.5px] ${why ? 'text-slate-600' : 'text-slate-300'}`}>{c.name}</span>
                  {why === 'fearless' && <span className="absolute top-1 right-1 rounded bg-gold/90 px-1 text-[9px] font-bold text-ink-950">🔒</span>}
                  {prob !== undefined && prob >= 0.02 && (
                    <span className="absolute top-0 right-0 rounded-md px-1 text-[10px] font-bold text-white" style={{ background: SIDE_COLOR[oppSide] }}>{pct(prob)}</span>
                  )}
                  {rank && <span className="absolute top-0 left-0 rounded-md bg-accent px-1 text-[10px] font-bold text-ink-950">#{rank}</span>}
                </button>
              )
            })}
          </div>
        </div>

        <TeamColumn a={a} side="red" />

        {/* AI rail */}
        <div className="flex flex-col gap-3 lg:col-span-3 xl:col-span-1">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title text-accent">Our move</h2>
                <div className="text-[11px] text-slate-500">{recStep ? `${recStep.label}${cur?.ours ? '' : ' · preview'}` : 'Draft finished'}</div>
              </div>
              <span className="chip bg-white/5 text-slate-400">{a.recommendations.type ?? ''}</span>
            </div>
            <div className={`scroll-thin space-y-2 overflow-y-auto p-3 ${cur?.ours ? 'max-h-[52vh]' : 'max-h-[34vh]'}`}>
              {a.recommendations.recommendations.slice(0, 6).map(r => (
                <RecCard key={r.champion} rec={r} a={a} busy={busy} modifying={modifying?.champion === r.champion}
                  actionable={!!cur?.ours && !a.state.complete}
                  onDecide={(rec, d) => run(() => api.decide(id, rec.champion, d), d === 'accept' ? `Locked in ${rec.name}` : `Rejected ${rec.name} — logged`)}
                  onModify={rec => setModifying(rec)} />
              ))}
              {!a.recommendations.recommendations.length && <div className="text-sm text-slate-500">No further actions for us.</div>}
              {a.rejected_this_step.length > 0 && (
                <div className="text-[11px] text-slate-500">Hidden after reject: {a.rejected_this_step.map(c => champions.find(x => x.id === c)?.name ?? c).join(', ')}</div>
              )}
            </div>
          </section>
          {predStep && <section className={`panel ${cur && !cur.ours ? 'order-first ring-1 ring-white/10' : ''}`}>
            <div className="panel-head">
              <div>
                <h2 className="panel-title" style={{ color: SIDE_COLOR[oppSide] }}>Opponent prediction</h2>
                <div className="text-[11px] text-slate-500">{predStep ? `${them?.tag} ${predStep.label}${cur && !cur.ours ? ' · now' : ' · next'}` : '—'}</div>
              </div>
            </div>
            <div className="space-y-2 p-3">
              {a.prediction.predictions.map(p => (
                <PredictionRow key={p.champion} p={p} a={a} color={SIDE_COLOR[oppSide]} busy={busy}
                  canLock={!!cur && !cur.ours && predStep?.index === cur.index}
                  onLock={c => run(() => api.action(id, c))} />
              ))}
            </div>
          </section>}
          <section className="panel">
            <div className="panel-head"><h2 className="panel-title">Coach decisions</h2><span className="text-[11px] text-slate-500">feeds future suggestions</span></div>
            <div className="p-3"><DecisionMini a={a} /></div>
          </section>
        </div>
      </div>

      <WeightsDrawer open={weightsOpen} onClose={() => setWeightsOpen(false)} onSaved={load} />
    </div>
  )
}
