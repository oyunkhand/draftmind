import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChampIcon, Panel, RoleChip, Spinner, TeamBadge, pct } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { Backtest, DashboardData, TeamSummary } from '../lib/types'
import { MatchList } from './Scouting'

function Compare({ label, a, b, fmt = pct }: { label: string; a: number | null; b: number | null; fmt?: (x: number | null) => string }) {
  const total = (a ?? 0) + (b ?? 0) || 1
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="font-mono text-slate-200">{fmt(a)}</span><span className="text-slate-500">{label}</span><span className="font-mono text-slate-200">{fmt(b)}</span></div>
      <div className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-white/5">
        <div className="bg-accent" style={{ width: `${((a ?? 0) / total) * 100}%` }} />
        <div className="bg-rose-400/80" style={{ width: `${((b ?? 0) / total) * 100}%` }} />
      </div>
    </div>
  )
}

function TeamCard({ id, s, tag }: { id: string; s: TeamSummary; tag: string }) {
  const { teamById } = useApp()
  return (
    <div className="flex items-center gap-4">
      <TeamBadge id={id} size="lg" />
      <div>
        <div className="label">{tag}</div>
        <div className="font-display text-2xl font-bold text-white">{teamById[id]?.name}</div>
        <div className="text-sm text-slate-400">{s.wins}-{s.games - s.wins} · {pct(s.wr)} WR</div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { ourTeam, opponent, teamById, champById } = useApp()
  const [d, setD] = useState<DashboardData | null>(null)
  const [bt, setBt] = useState<Backtest | null>(null)

  useEffect(() => { setD(null); api.dashboard(ourTeam, opponent).then(setD) }, [ourTeam, opponent])
  useEffect(() => { api.backtest().then(setBt) }, [])

  if (!d) return <Spinner label="Loading matchup…" />
  const opp = teamById[opponent]
  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="panel relative overflow-hidden p-6">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-accent/[0.08] via-transparent to-rose-500/[0.08]" />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <TeamCard id={ourTeam} s={d.our} tag="Our team" />
          <div className="text-center">
            <div className="label">Head to head</div>
            <div className="font-display text-4xl font-bold text-white">{d.h2h.a_wins}<span className="mx-2 text-slate-600">–</span>{d.h2h.games - d.h2h.a_wins}</div>
            <div className="text-xs text-slate-500">{d.h2h.games} games in dataset</div>
          </div>
          <div className="flex flex-row-reverse items-center gap-4 text-right"><TeamCard id={opponent} s={d.opp} tag="Next opponent" /></div>
        </div>
        <div className="relative mt-6 grid gap-x-8 gap-y-3 md:grid-cols-3">
          <Compare label="Win rate" a={d.our.wr} b={d.opp.wr} />
          <Compare label="Blue side WR" a={d.our.sides.blue.wr} b={d.opp.sides.blue.wr} />
          <Compare label="Red side WR" a={d.our.sides.red.wr} b={d.opp.sides.red.wr} />
          <Compare label="First dragon" a={d.our.objectives.first_dragon.rate} b={d.opp.objectives.first_dragon.rate} />
          <Compare label="First herald" a={d.our.objectives.first_herald.rate} b={d.opp.objectives.first_herald.rate} />
          <Compare label="Gold ahead @15" a={d.our.gold_diff_15.ahead_rate} b={d.opp.gold_diff_15.ahead_rate} />
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2">
          <Link to="/draft" className="btn-primary">Start draft vs {opp?.tag} →</Link>
          <Link to={`/scouting/${opponent}`} className="btn-ghost">Full scouting report</Link>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={`What to expect from ${opp?.tag}`} className="lg:col-span-2">
          <ul className="space-y-2.5">
            {d.insights.map((i, k) => <li key={k} className="flex gap-2 text-sm text-slate-200"><span className="text-accent">▸</span>{i.text}</li>)}
          </ul>
        </Panel>
        <Panel title="Suggested bans">
          <ul className="space-y-2">
            {d.ban_plan.slice(0, 4).map(b => (
              <li key={b.champion} className="flex items-center gap-3">
                <ChampIcon id={b.champion} size={32} />
                <div className="min-w-0 flex-1"><div className="text-sm font-semibold">{champById[b.champion]?.name}</div><div className="truncate text-[11px] text-slate-400">{b.reason}</div></div>
                <RoleChip role={b.role} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={`${teamById[ourTeam]?.tag} recent games`}><MatchList rows={d.our_recent} team={ourTeam} /></Panel>
        <Panel title={`${opp?.tag} recent games`}><MatchList rows={d.opp_recent} team={opponent} /></Panel>
      </div>

      {bt && (
        <Panel title="Prediction model — held-out accuracy" right={<Link to="/model" className="text-xs text-accent hover:underline">How it works →</Link>}>
          <div className="grid gap-4 sm:grid-cols-4">
            {(['pick', 'ban'] as const).map(k => (
              <div key={k} className="sm:col-span-2 grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-white/[0.02] p-3"><div className="label">{k}s · top-5 hit rate</div><div className="font-display text-3xl font-bold text-accent">{pct(bt[k].top5)}</div><div className="text-xs text-slate-500">baseline {pct(bt[k].baseline_top5)} (meta only)</div></div>
                <div className="rounded-lg bg-white/[0.02] p-3"><div className="label">{k}s · top-1</div><div className="font-display text-3xl font-bold text-slate-100">{pct(bt[k].top1)}</div><div className="text-xs text-slate-500">baseline {pct(bt[k].baseline_top1)} · {bt[k].actions} actions</div></div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Trained on the first {bt.train_games} games, tested on the {bt.test_games} most recent (chronological split, fearless locks applied).</p>
        </Panel>
      )}
    </div>
  )
}
