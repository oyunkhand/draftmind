import type {
  Backtest, Champion, DashboardData, DraftAnalysis, Explanation, Health, ScoutingReport, SeriesDetail,
  SeriesSummary, Team, Weights, WeightsResponse,
} from './types'

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

const post = <T,>(path: string, body?: unknown) => req<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  health: () => req<Health>('/api/health'),
  champions: () => req<{ version: string; champions: Champion[] }>('/api/champions'),
  teams: () => req<Team[]>('/api/teams'),
  dashboard: (our: string, opp: string) => req<DashboardData>(`/api/dashboard?our=${our}&opp=${opp}`),
  scouting: (team: string, vs?: string) => req<ScoutingReport>(`/api/teams/${team}/scouting${vs ? `?vs=${vs}` : ''}`),
  scoutingMarkdownUrl: (team: string, vs?: string) => `${API_BASE}/api/teams/${team}/scouting.md${vs ? `?vs=${vs}` : ''}`,
  backtest: () => req<Backtest>('/api/model/backtest'),
  weights: () => req<WeightsResponse>('/api/settings/weights'),
  saveWeights: (w: Weights) => req<WeightsResponse>('/api/settings/weights', { method: 'PUT', body: JSON.stringify(w) }),
  resetWeights: () => post<WeightsResponse>('/api/settings/weights/reset'),
  listSeries: () => req<SeriesSummary[]>('/api/series'),
  getSeries: (id: string) => req<SeriesDetail>(`/api/series/${id}`),
  deleteSeries: (id: string) => req<{ ok: boolean }>(`/api/series/${id}`, { method: 'DELETE' }),
  createSeries: (b: { our_team: string; opponent: string; best_of: number; fearless_mode: string; title?: string }) =>
    post<SeriesDetail>('/api/series', b),
  createGame: (sid: string, our_side: string) => post<{ id: string; series_id: string; game_number: number }>(`/api/series/${sid}/games`, { our_side }),
  draft: (id: string) => req<DraftAnalysis>(`/api/drafts/${id}`),
  action: (id: string, champion: string) => post<DraftAnalysis>(`/api/drafts/${id}/actions`, { champion }),
  undo: (id: string) => post<DraftAnalysis>(`/api/drafts/${id}/undo`),
  decide: (id: string, champion: string, decision: 'accept' | 'modify' | 'reject', final_champion?: string, note?: string) =>
    post<DraftAnalysis>(`/api/drafts/${id}/decisions`, { champion, decision, final_champion, note }),
  result: (id: string, result: 'win' | 'loss' | null) => post<DraftAnalysis>(`/api/drafts/${id}/result`, { result }),
  explain: (id: string, champion: string, kind: 'recommendation' | 'prediction') =>
    post<Explanation>(`/api/drafts/${id}/explain`, { champion, kind }),
}
