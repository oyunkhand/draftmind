import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import type { Champion, Health, Team } from './types'

interface AppState {
  ready: boolean
  error: string | null
  health: Health | null
  teams: Team[]
  teamById: Record<string, Team>
  champions: Champion[]
  champById: Record<string, Champion>
  ddVersion: string
  ourTeam: string
  opponent: string
  setOurTeam: (id: string) => void
  setOpponent: (id: string) => void
  toast: (msg: string, kind?: 'ok' | 'err') => void
  toasts: { id: number; msg: string; kind: 'ok' | 'err' }[]
}

const Ctx = createContext<AppState | null>(null)

function stored(key: string, fallback: string) {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [champions, setChampions] = useState<Champion[]>([])
  const [ddVersion, setDdVersion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ourTeam, setOur] = useState(() => stored('dm.our', ''))
  const [opponent, setOpp] = useState(() => stored('dm.opp', ''))
  const [toasts, setToasts] = useState<AppState['toasts']>([])

  useEffect(() => {
    Promise.all([api.health(), api.teams(), api.champions()])
      .then(([h, t, c]) => {
        setHealth(h)
        setTeams(t)
        setChampions(c.champions)
        setDdVersion(c.version)
        const ids = t.map(x => x.id)
        setOur(prev => (ids.includes(prev) ? prev : ids.includes('NMB') ? 'NMB' : ids[0]))
        setOpp(prev => (ids.includes(prev) ? prev : ids.includes('IWF') ? 'IWF' : ids[1]))
      })
      .catch(e => setError(String(e.message ?? e)))
  }, [])

  const setOurTeam = useCallback((id: string) => {
    setOur(id)
    localStorage.setItem('dm.our', id)
    if (id === opponent) {
      const alt = teams.find(t => t.id !== id)?.id ?? ''
      setOpp(alt)
      localStorage.setItem('dm.opp', alt)
    }
  }, [opponent, teams])
  const setOpponent = useCallback((id: string) => {
    setOpp(id)
    localStorage.setItem('dm.opp', id)
  }, [])

  const toast = useCallback((msg: string, kind: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, msg, kind }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3500)
  }, [])

  const value = useMemo<AppState>(() => ({
    ready: !!health && teams.length > 0 && champions.length > 0,
    error, health, teams, champions, ddVersion, ourTeam, opponent, setOurTeam, setOpponent, toast, toasts,
    teamById: Object.fromEntries(teams.map(t => [t.id, t])),
    champById: Object.fromEntries(champions.map(c => [c.id, c])),
  }), [health, teams, champions, ddVersion, ourTeam, opponent, setOurTeam, setOpponent, error, toast, toasts])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useApp() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp outside AppProvider')
  return v
}
