import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Bar, ChampIcon, Panel, RoleChip, Spinner, Stat, TeamBadge, TeamSelect, fmtDate, fmtDuration, pct } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { MatchRow, RateRow, ScoutingReport } from '../lib/types'

function heat(comfort: number) {
  // cyan heat scale for the champion-pool heatmap
  const a = 0.08 + comfort * 0.62
  return { background: `rgba(34, 211, 238, ${a.toFixed(2)})` }
}

function RateTable({ rows, showWr = false, empty = 'No data' }: { rows: RateRow[]; showWr?: boolean; empty?: string }) {
  const { champById } = useApp()
  if (!rows.length) return <div className="text-sm text-slate-500">{empty}</div>
  const max = Math.max(...rows.map(r => r.rate))
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(r => (
          <tr key={r.champion} className="border-b border-white/[0.04] last:border-0">
            <td className="py-1.5 pr-2"><div className="flex items-center gap-2"><ChampIcon id={r.champion} size={26} rounded="rounded-md" /><span className="text-slate-200">{champById[r.champion]?.name ?? r.champion}</span></div></td>
            <td className="w-24 py-1.5"><Bar value={r.rate} max={max} /></td>
            <td className="w-10 py-1.5 text-right font-mono text-xs text-slate-300">{r.count}</td>
            {showWr && <td className={`w-12 py-1.5 text-right font-mono text-xs ${(r.wr ?? 0) >= 0.5 ? 'text-emerald-300' : 'text-rose-300'}`}>{pct(r.wr)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function MatchList({ rows, team }: { rows: MatchRow[]; team: string }) {
  void team
  return (
    <div className="space-y-1.5">
      {rows.map(m => (
        <div key={m.id} className="flex items-center gap-3 rounded-lg bg-white/[0.02] px-2.5 py-1.5">
          <span className={`w-6 text-center font-display text-sm font-bold ${m.win ? 'text-emerald-300' : 'text-rose-300'}`}>{m.win ? 'W' : 'L'}</span>
          <span className={`h-2 w-2 shrink-0 rounded-full ${m.side === 'blue' ? 'bg-blue-side' : 'bg-red-side'}`} title={`${m.side} side`} />
          <div className="flex gap-0.5">{m.picks.map(p => <ChampIcon key={p.champion} id={p.champion} size={24} rounded="rounded" />)}</div>
          <span className="text-xs text-slate-500">vs</span>
          <TeamBadge id={m.opponent} size="sm" />
          <div className="hidden gap-0.5 opacity-70 md:flex">{m.opp_picks.map(p => <ChampIcon key={p.champion} id={p.champion} size={20} rounded="rounded" />)}</div>
          <span className="ml-auto hidden text-[11px] text-slate-500 sm:block">{m.gold_diff_15 !== null ? `${m.gold_diff_15 > 0 ? '+' : ''}${(m.gold_diff_15 / 1000).toFixed(1)}k@15 · ` : ''}{fmtDuration(m.duration_s)} · {fmtDate(m.date)}</span>
        </div>
      ))}
    </div>
  )
}

export default function Scouting() {
  const { teamId } = useParams()
  const nav = useNavigate()
  const { opponent, ourTeam, teamById, champById } = useApp()
  const team = teamId ?? opponent
  const [r, setR] = useState<ScoutingReport | null>(null)

  useEffect(() => {
    setR(null)
    api.scouting(team, team !== ourTeam ? ourTeam : undefined).then(setR)
  }, [team, ourTeam])

  if (!r) return <Spinner label="Building scouting report…" />
  const s = r.summary
  const obj = s.objectives
  const gold = s.gold_diff_15.avg

  return (
    <div className="mx-auto max-w-7xl space-y-4 print-dark-text">
      {/* Header */}
      <div className="panel flex flex-wrap items-center gap-5 p-5" style={{ boxShadow: `inset 4px 0 0 ${r.team.color}` }}>
        <TeamBadge id={r.team.id} size="lg" />
        <div>
          <div className="label">Scouting report</div>
          <h1 className="font-display text-3xl font-bold text-white">{r.team.name}</h1>
          <div className="text-sm text-slate-400">{r.team.region} · {s.games} games · prepared for {teamById[ourTeam]?.name}</div>
        </div>
        <div className="no-print ml-auto flex flex-wrap items-end gap-2">
          <TeamSelect label="Team" value={team} onChange={v => nav(`/scouting/${v}`)} />
          <a className="btn-ghost" href={api.scoutingMarkdownUrl(team, team !== ourTeam ? ourTeam : undefined)} download>⬇ Markdown</a>
          <button className="btn-ghost" onClick={() => window.print()}>⬇ PDF</button>
          <button className="btn-primary" onClick={() => nav('/draft')}>Draft vs {r.team.tag} →</button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Record" value={`${s.wins}-${s.games - s.wins}`} sub={`${pct(s.wr)} win rate`} />
        <Stat label="Blue side" value={pct(s.sides.blue.wr)} sub={`${s.sides.blue.wins}/${s.sides.blue.games} games`} accent="text-blue-400" />
        <Stat label="Red side" value={pct(s.sides.red.wr)} sub={`${s.sides.red.wins}/${s.sides.red.games} games`} accent="text-red-400" />
        <Stat label="First dragon" value={pct(obj.first_dragon.rate)} sub={`herald ${pct(obj.first_herald.rate)}`} />
        <Stat label="Gold @15" value={gold === null ? 'n/a' : `${gold > 0 ? '+' : ''}${Math.round(gold).toLocaleString()}`} sub={`ahead in ${pct(s.gold_diff_15.ahead_rate)}`} accent={gold !== null && gold > 0 ? 'text-emerald-300' : 'text-rose-300'} />
        <Stat label="Avg game time" value={fmtDuration(s.avg_duration_s)} sub={`first blood ${pct(obj.first_blood.rate)}`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="Key insights">
          <ul className="space-y-2.5">
            {r.insights.map((i, k) => (
              <li key={k} className="flex gap-3 text-sm text-slate-200">
                <span className={`chip mt-0.5 shrink-0 ${i.type === 'threat' ? 'bg-rose-400/15 text-rose-300' : i.type === 'early' ? 'bg-amber-400/15 text-amber-300' : i.type === 'side' ? 'bg-blue-400/15 text-blue-300' : 'bg-accent/15 text-accent'}`}>{i.type}</span>
                {i.text}
              </li>
            ))}
          </ul>
        </Panel>
        {r.ban_plan && (
          <Panel title={`Ban plan for ${teamById[ourTeam]?.tag}`}>
            <ol className="space-y-2">
              {r.ban_plan.map((b, i) => (
                <li key={b.champion} className="flex items-center gap-3">
                  <span className="w-4 font-display text-sm font-bold text-slate-500">{i + 1}</span>
                  <ChampIcon id={b.champion} size={34} />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-100">{champById[b.champion]?.name}</div>
                    <div className="truncate text-xs text-slate-400">{b.reason}</div>
                  </div>
                  <RoleChip role={b.role} />
                </li>
              ))}
            </ol>
          </Panel>
        )}
      </div>

      <Panel title="Champion pools — heatmap" right={<span className="text-[11px] text-slate-500">cell = comfort (recency-weighted games × win rate)</span>}>
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full border-separate border-spacing-1">
            <tbody>
              {r.players.map(p => (
                <tr key={p.id}>
                  <td className="w-40 pr-2 align-middle">
                    <div className="flex items-center gap-2"><RoleChip role={p.role} /><span className="font-semibold text-slate-100">{p.name}</span></div>
                    <div className="text-[11px] text-slate-500">{p.games} games · {pct(p.wr)} · {p.unique_champions} champs</div>
                  </td>
                  {Array.from({ length: 8 }).map((_, i) => {
                    const e = p.pool[i]
                    if (!e) return <td key={i} className="min-w-[96px] rounded-lg bg-white/[0.02]" />
                    return (
                      <td key={i} className="min-w-[96px] rounded-lg p-1.5" style={heat(e.comfort)} title={`last played ${fmtDate(e.last_played)}`}>
                        <div className="flex items-center gap-1.5">
                          <ChampIcon id={e.champion} size={28} rounded="rounded-md" />
                          <div className="min-w-0 leading-tight">
                            <div className="truncate text-[11px] font-semibold text-white">{champById[e.champion]?.name}</div>
                            <div className="text-[10px] text-slate-200/80">{e.games}g · {pct(e.wr)}</div>
                          </div>
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Panel title="Most picked"><RateTable rows={r.most_picked.slice(0, 8)} showWr /></Panel>
        <Panel title="Banned by them"><RateTable rows={r.most_banned_by.slice(0, 8)} /></Panel>
        <Panel title="Banned against them"><RateTable rows={r.most_banned_against.slice(0, 8)} /></Panel>
        <Panel title="First-pick priorities">
          <RateTable rows={r.first_picks.slice(0, 5)} />
          <div className="mt-4 space-y-1.5">
            <div className="label">First pick by role</div>
            {r.first_pick_roles.map(fr => (
              <div key={fr.role} className="flex items-center gap-2 text-xs">
                <span className="w-14"><RoleChip role={fr.role} /></span>
                <Bar value={fr.rate} className="flex-1" />
                <span className="w-9 text-right font-mono text-slate-300">{pct(fr.rate)}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.6fr]">
        <Panel title="Side & early game">
          <div className="space-y-3">
            {(['blue', 'red'] as const).map(side => (
              <div key={side}>
                <div className="flex justify-between text-xs"><span className={side === 'blue' ? 'text-blue-400' : 'text-red-400'}>{side} side win rate</span><span className="font-mono">{pct(s.sides[side].wr)} ({s.sides[side].games})</span></div>
                <Bar value={s.sides[side].wr} color={side === 'blue' ? 'bg-blue-side' : 'bg-red-side'} className="mt-1 h-2" />
              </div>
            ))}
            <div className="grid grid-cols-2 gap-3 pt-2">
              {([['first_blood', 'First blood'], ['first_dragon', 'First dragon'], ['first_herald', 'First herald'], ['first_tower', 'First tower']] as const).map(([k, label]) => (
                <div key={k}>
                  <div className="flex justify-between text-xs"><span className="text-slate-400">{label}</span><span className="font-mono">{pct(obj[k].rate)}</span></div>
                  <Bar value={obj[k].rate ?? 0} color="bg-gold" className="mt-1" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 pt-1">
              <div><div className="label">Phase-1 bans</div><div className="mt-1 flex flex-wrap gap-1">{r.phase1_bans.slice(0, 6).map(b => <ChampIcon key={b.champion} id={b.champion} size={26} rounded="rounded-md" title={`${champById[b.champion]?.name} ×${b.count}`} />)}</div></div>
              <div><div className="label">Phase-2 bans</div><div className="mt-1 flex flex-wrap gap-1">{r.phase2_bans.slice(0, 6).map(b => <ChampIcon key={b.champion} id={b.champion} size={26} rounded="rounded-md" title={`${champById[b.champion]?.name} ×${b.count}`} />)}</div></div>
            </div>
          </div>
        </Panel>
        <Panel title="Recent matches"><MatchList rows={r.recent} team={r.team.id} /></Panel>
      </div>
    </div>
  )
}
