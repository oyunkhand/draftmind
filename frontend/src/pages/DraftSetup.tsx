import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Panel, Segmented, TeamBadge, fmtDate } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { SeriesSummary, Side } from '../lib/types'

const FEARLESS_HELP: Record<string, string> = {
  off: 'Classic tournament draft — every game starts fresh.',
  hard: 'Any champion picked earlier in the series is locked for BOTH teams (LCK/LTA 2025+ format).',
  soft: 'A team cannot re-pick its own previous champions; the opponent still can.',
}

export default function DraftSetup() {
  const { ourTeam, opponent, teamById, toast } = useApp()
  const nav = useNavigate()
  const [bestOf, setBestOf] = useState('3')
  const [fearless, setFearless] = useState<'off' | 'hard' | 'soft'>('hard')
  const [side, setSide] = useState<Side>('blue')
  const [series, setSeries] = useState<SeriesSummary[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.listSeries().then(setSeries) }, [])

  const start = async () => {
    setBusy(true)
    try {
      const s = await api.createSeries({
        our_team: ourTeam, opponent, best_of: Number(bestOf), fearless_mode: fearless,
        title: `${teamById[ourTeam]?.tag} vs ${teamById[opponent]?.tag}`,
      })
      const g = await api.createGame(s.id, side)
      nav(`/draft/${g.id}`)
    } catch (e) {
      toast((e as Error).message, 'err')
    } finally {
      setBusy(false)
    }
  }

  const nextGame = async (s: SeriesSummary) => {
    const lastSide = s.games[s.games.length - 1]?.our_side ?? 'blue'
    try {
      const g = await api.createGame(s.id, lastSide === 'blue' ? 'red' : 'blue')
      nav(`/draft/${g.id}`)
    } catch (e) { toast((e as Error).message, 'err') }
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[1.1fr_1fr]">
      <Panel title="New draft series">
        <div className="flex items-center justify-center gap-6 rounded-xl border border-white/[0.06] bg-gradient-to-r from-blue-side/10 via-transparent to-red-side/10 py-6">
          <div className="flex flex-col items-center gap-2"><TeamBadge id={ourTeam} size="lg" /><span className="text-sm font-semibold">{teamById[ourTeam]?.name}</span><span className="chip bg-accent/15 text-accent">us</span></div>
          <span className="font-display text-3xl font-bold text-slate-600">VS</span>
          <div className="flex flex-col items-center gap-2"><TeamBadge id={opponent} size="lg" /><span className="text-sm font-semibold">{teamById[opponent]?.name}</span><span className="chip bg-white/5 text-slate-400">opponent</span></div>
        </div>
        <p className="mt-2 text-center text-xs text-slate-500">Change teams in the top bar.</p>
        <div className="mt-5 grid gap-5 sm:grid-cols-2">
          <div>
            <div className="label mb-1.5">Series format</div>
            <Segmented size="md" value={bestOf} onChange={setBestOf} options={[{ value: '1', label: 'Bo1' }, { value: '3', label: 'Bo3' }, { value: '5', label: 'Bo5' }]} />
          </div>
          <div>
            <div className="label mb-1.5">Our side (game 1)</div>
            <Segmented size="md" value={side} onChange={setSide} options={[{ value: 'blue', label: '🔵 Blue' }, { value: 'red', label: '🔴 Red' }]} />
          </div>
          <div className="sm:col-span-2">
            <div className="label mb-1.5">Fearless draft</div>
            <Segmented size="md" value={fearless} onChange={setFearless} options={[{ value: 'off', label: 'Off' }, { value: 'hard', label: 'Hard fearless' }, { value: 'soft', label: 'Soft fearless' }]} />
            <p className="mt-2 text-xs text-slate-400">{FEARLESS_HELP[fearless]}</p>
          </div>
        </div>
        <button className="btn-primary mt-6 w-full py-2.5 text-base" disabled={busy} onClick={start}>Start draft →</button>
      </Panel>

      <Panel title="Resume a series" bodyClass="p-3">
        {series.length === 0 ? <p className="p-3 text-sm text-slate-500">No series yet — start one on the left.</p> : (
          <ul className="space-y-2">
            {series.slice(0, 8).map(s => {
              const last = s.games[s.games.length - 1]
              const canNext = s.games.length < s.best_of && (!last || last.complete)
              return (
                <li key={s.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <div className="flex items-center gap-2">
                    <TeamBadge id={s.our_team} size="sm" /><span className="text-xs text-slate-500">vs</span><TeamBadge id={s.opponent} size="sm" />
                    <span className="ml-2 font-display text-lg font-bold">{s.score[0]}–{s.score[1]}</span>
                    <span className="chip bg-white/5 text-slate-400">Bo{s.best_of}</span>
                    {s.fearless_mode !== 'off' && <span className="chip bg-gold/10 text-gold">fearless</span>}
                    <span className="ml-auto text-[11px] text-slate-500">{fmtDate(s.created_at)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {s.games.map(g => (
                      <Link key={g.id} to={`/draft/${g.id}`} className="btn-ghost px-2 py-1 text-xs">
                        G{g.game_number} {g.result === 'win' ? '✓' : g.result === 'loss' ? '✕' : g.complete ? '•' : '…'}
                      </Link>
                    ))}
                    {canNext && <button className="btn-ghost px-2 py-1 text-xs text-accent" onClick={() => nextGame(s)}>+ Game {s.games.length + 1}</button>}
                    <Link to={`/series/${s.id}`} className="ml-auto text-xs text-slate-400 hover:text-white">History →</Link>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
    </div>
  )
}
