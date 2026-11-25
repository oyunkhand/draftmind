import { NavLink, Outlet } from 'react-router-dom'
import { useApp } from '../lib/store'
import { Spinner, TeamSelect } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'M3 12l9-8 9 8M5 10v10h14V10' },
  { to: '/scouting', label: 'Scouting Report', icon: 'M11 4a7 7 0 100 14 7 7 0 000-14zm10 17l-5-5' },
  { to: '/draft', label: 'Live Draft Board', icon: 'M4 5h16M4 12h16M4 19h10' },
  { to: '/series', label: 'Series History', icon: 'M12 8v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  { to: '/model', label: 'AI Model', icon: 'M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4M7 7h10v10H7z' },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 64 64" className="h-8 w-8">
        <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#6366f1" /></linearGradient></defs>
        <rect width="64" height="64" rx="14" fill="#0f172a" stroke="#ffffff14" />
        <path d="M14 44 L26 20 L32 32 L38 20 L50 44" fill="none" stroke="url(#lg)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="32" cy="48" r="4" fill="#22d3ee" />
      </svg>
      <div className="leading-none">
        <div className="font-display text-lg font-bold tracking-wide text-white">DraftMind <span className="text-accent">AI</span></div>
        <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-slate-500">Coach's draft room</div>
      </div>
    </div>
  )
}

export default function Layout() {
  const { ready, error, health, ourTeam, opponent, setOurTeam, setOpponent, toasts } = useApp()
  return (
    <div className="flex min-h-full">
      <aside className="no-print sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-ink-900/70 px-4 py-5 lg:flex">
        <Logo />
        <nav className="mt-8 space-y-1">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${isActive ? 'bg-accent/10 text-accent ring-1 ring-accent/20' : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-100'}`}>
              <Icon d={n.icon} /> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-[11px] text-slate-400">
          <div className="flex items-center justify-between">
            <span>Data</span>
            <span className={`chip ${health?.data_source === 'grid' ? 'bg-emerald-400/10 text-emerald-300' : 'bg-amber-400/10 text-amber-300'}`}>
              {health?.data_source === 'grid' ? 'GRID live' : 'Sample'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Explanations</span>
            <span className="chip bg-white/5 text-slate-300">{health?.llm_provider === 'none' ? 'Templated' : health?.llm_provider === 'anthropic' ? 'Claude' : health?.llm_provider ?? '…'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Games indexed</span><span className="font-mono text-slate-300">{health?.dataset?.matches ?? '…'}</span>
          </div>
          <div className="pt-1 text-[10px] leading-snug text-slate-500">Champion art © Riot Games via Data Dragon {health?.ddragon_version}</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex flex-wrap items-center gap-4 border-b border-white/[0.06] bg-ink-950/85 px-5 py-3 backdrop-blur">
          <div className="lg:hidden"><Logo /></div>
          <nav className="flex gap-1 lg:hidden">
            {NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.to === '/'} title={n.label}
                className={({ isActive }) => `rounded-md p-2 ${isActive ? 'bg-accent/10 text-accent' : 'text-slate-400'}`}>
                <Icon d={n.icon} />
              </NavLink>
            ))}
          </nav>
          {ready && (
            <div className="ml-auto flex items-end gap-3">
              <TeamSelect label="Our team" value={ourTeam} onChange={setOurTeam} />
              <span className="pb-2 font-display text-sm font-bold text-slate-500">VS</span>
              <TeamSelect label="Opponent" value={opponent} onChange={setOpponent} exclude={ourTeam} />
            </div>
          )}
        </header>
        <main className="flex-1 p-5">
          {error ? (
            <div className="panel mx-auto mt-16 max-w-lg p-6 text-center">
              <div className="font-display text-xl font-bold text-rose-300">Backend unreachable</div>
              <p className="mt-2 text-sm text-slate-400">{error}</p>
              <p className="mt-3 text-xs text-slate-500">Start the API with <code className="text-slate-300">make dev</code> or <code className="text-slate-300">docker compose up</code>.</p>
            </div>
          ) : ready ? <Outlet /> : <Spinner label="Loading teams, champions and match data…" />}
        </main>
      </div>

      <div className="no-print pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-2">
        {toasts.map(t => (
          <div key={t.id} className={`pointer-events-auto rounded-lg px-4 py-2.5 text-sm shadow-xl ring-1 backdrop-blur ${t.kind === 'err' ? 'bg-rose-950/90 text-rose-200 ring-rose-500/40' : 'bg-ink-800/95 text-slate-100 ring-white/10'}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  )
}
