import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChampIcon, Empty, Panel, Spinner, TeamBadge, fmtDate } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { Decision, SeriesDetail, SeriesSummary, TimelineSlot } from '../lib/types'

const DEC_STYLE: Record<string, string> = {
  accept: 'bg-emerald-400/15 text-emerald-300', modify: 'bg-amber-400/15 text-amber-300',
  reject: 'bg-rose-400/15 text-rose-300', manual: 'bg-white/5 text-slate-400',
}

function DraftStrip({ slots, side, team }: { slots: TimelineSlot[]; side: 'blue' | 'red'; team: string }) {
  const mine = slots.filter(s => s.side === side)
  return (
    <div className="flex items-center gap-3">
      <span className={`h-8 w-1 rounded-full ${side === 'blue' ? 'bg-blue-side' : 'bg-red-side'}`} />
      <TeamBadge id={team} size="sm" />
      <div className="flex gap-0.5">{mine.filter(s => s.type === 'ban').map(s => <ChampIcon key={s.index} id={s.champion} size={22} rounded="rounded" className="grayscale" title={`${s.label}`} />)}</div>
      <span className="text-slate-600">|</span>
      <div className="flex gap-1">{mine.filter(s => s.type === 'pick').map(s => <ChampIcon key={s.index} id={s.champion} size={32} title={s.label} />)}</div>
    </div>
  )
}

function DecisionTable({ ds }: { ds: Decision[] }) {
  const { champById } = useApp()
  const name = (c: string | null | undefined) => (c ? champById[c]?.name ?? c : '—')
  if (!ds.length) return <div className="text-xs text-slate-500">No decisions logged for this game.</div>
  return (
    <table className="w-full text-xs">
      <thead><tr className="text-left text-slate-500"><th className="py-1 font-medium">Step</th><th className="font-medium">Type</th><th className="font-medium">AI suggestion</th><th className="font-medium">Coach call</th><th className="font-medium">Final</th><th className="font-medium">AI top-3 at the time</th></tr></thead>
      <tbody>
        {ds.map(d => (
          <tr key={d.id} className="border-t border-white/[0.04]">
            <td className="py-1.5 font-mono text-slate-400">#{d.step + 1}</td>
            <td className="text-slate-300">{d.action_type}</td>
            <td className="text-slate-200">{name(d.suggested_champion)}{d.suggested_rank ? <span className="text-slate-500"> (#{d.suggested_rank}, {d.suggested_score})</span> : ''}</td>
            <td><span className={`chip ${DEC_STYLE[d.decision]}`}>{d.decision}</span></td>
            <td className="text-slate-100">{name(d.final_champion)}</td>
            <td><div className="flex gap-0.5">{(d.top_suggestions ?? []).slice(0, 3).map(t => <ChampIcon key={t.champion} id={t.champion} size={18} rounded="rounded" title={`${name(t.champion)} ${t.score}`} />)}</div></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SeriesHistory() {
  const { id } = useParams()
  const nav = useNavigate()
  const { toast } = useApp()
  const [list, setList] = useState<SeriesSummary[] | null>(null)
  const [detail, setDetail] = useState<SeriesDetail | null>(null)

  useEffect(() => { api.listSeries().then(setList) }, [])
  useEffect(() => {
    if (id) { setDetail(null); api.getSeries(id).then(setDetail).catch(e => toast(e.message, 'err')) }
    else setDetail(null)
  }, [id, toast])

  if (!list) return <Spinner />
  const decisions = detail?.games.flatMap(g => g.decisions).filter(d => d.decision !== 'manual') ?? []
  const accepted = decisions.filter(d => d.decision === 'accept').length

  return (
    <div className="mx-auto grid max-w-7xl gap-4 lg:grid-cols-[300px_1fr]">
      <Panel title="Series" bodyClass="p-2">
        {list.length === 0 ? <Empty>No series yet. <Link className="text-accent" to="/draft">Start a draft</Link>.</Empty> : (
          <ul className="space-y-1">
            {list.map(s => (
              <li key={s.id}>
                <Link to={`/series/${s.id}`} className={`flex items-center gap-2 rounded-lg px-2 py-2 text-sm transition ${s.id === id ? 'bg-accent/10 ring-1 ring-accent/30' : 'hover:bg-white/[0.04]'}`}>
                  <TeamBadge id={s.our_team} size="sm" /><span className="text-slate-500">v</span><TeamBadge id={s.opponent} size="sm" />
                  <span className="font-display font-bold">{s.score[0]}–{s.score[1]}</span>
                  <span className="ml-auto text-[11px] text-slate-500">{fmtDate(s.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="space-y-4">
        {!id && <Empty>Select a series to see every draft and coach decision.</Empty>}
        {id && !detail && <Spinner />}
        {detail && (
          <>
            <div className="panel flex flex-wrap items-center gap-4 p-4">
              <TeamBadge id={detail.our_team} size="md" showName /><span className="font-display text-2xl font-bold">{detail.score[0]}–{detail.score[1]}</span><TeamBadge id={detail.opponent} size="md" showName />
              <span className="chip bg-white/5 text-slate-300">Bo{detail.best_of}</span>
              <span className="chip bg-gold/10 text-gold">fearless: {detail.fearless_mode}</span>
              <div className="ml-auto flex items-center gap-4 text-sm">
                <div><span className="label">AI acceptance</span><div className="font-display text-xl font-bold text-accent">{decisions.length ? Math.round((100 * accepted) / decisions.length) : 0}%</div></div>
                <div><span className="label">Decisions</span><div className="font-display text-xl font-bold">{decisions.length}</div></div>
                <button className="btn-bad" onClick={async () => { if (confirm('Delete this series and its decision log?')) { await api.deleteSeries(detail.id); nav('/series'); setList(await api.listSeries()) } }}>Delete</button>
              </div>
            </div>
            {detail.fearless_mode !== 'off' && detail.fearless_pool.length > 0 && (
              <Panel title="Fearless pool — champions used in this series">
                <div className="flex flex-wrap gap-1.5">
                  {detail.fearless_pool.map(u => <div key={`${u.champion}-${u.game}`} className="relative"><ChampIcon id={u.champion} size={30} rounded="rounded-md" title={`G${u.game} · ${u.team}`} /><span className="absolute -right-1 -bottom-1 rounded bg-ink-950 px-0.5 text-[9px] text-slate-400">G{u.game}</span></div>)}
                </div>
              </Panel>
            )}
            {detail.games.map(g => (
              <Panel key={g.id} title={<span>Game {g.game_number} <span className="ml-2 text-xs font-normal normal-case text-slate-500">we were {g.our_side}</span></span>}
                right={<div className="flex items-center gap-2">
                  {g.result && <span className={`chip ${g.result === 'win' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-rose-400/15 text-rose-300'}`}>{g.result}</span>}
                  {!g.complete && <span className="chip bg-white/5 text-slate-400">in progress</span>}
                  <Link to={`/draft/${g.id}`} className="text-xs text-accent hover:underline">Open board →</Link>
                </div>}>
                <div className="space-y-2">
                  <DraftStrip slots={g.timeline} side="blue" team={g.blue_team} />
                  <DraftStrip slots={g.timeline} side="red" team={g.red_team} />
                </div>
                <div className="mt-4"><DecisionTable ds={g.decisions} /></div>
              </Panel>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
