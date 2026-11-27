export type Side = 'blue' | 'red'
export type ActionType = 'pick' | 'ban'
export type Role = 'top' | 'jungle' | 'mid' | 'bot' | 'support'
export const ROLES: Role[] = ['top', 'jungle', 'mid', 'bot', 'support']

export interface Champion {
  id: string
  key: number
  name: string
  title: string
  tags: string[]
  roles: Role[]
  curated: boolean
}

export interface Player { id: string; name: string; role: Role }
export interface Team {
  id: string; name: string; tag: string; color: string; region: string
  players: Player[]; games: number; wins: number
}

export interface Health {
  status: string
  data_source: string
  llm_provider: 'anthropic' | 'openai' | 'none'
  ddragon_version: string
  dataset: { source: string; matches: number; teams: number; series: number; adapter?: { name: string; note?: string; fallback_reason?: string } }
}

export interface Factor {
  key: string; label: string; value: number; weight: number; contribution: number; evidence: string
  stats: Record<string, unknown>
}

export interface Recommendation {
  champion: string; name: string; role: Role | null; total: number; score: number; rank?: number
  factors: Factor[]; summary: string; pros: string[]; risks: string[]
}

export interface Prediction {
  champion: string; name: string; role: Role | null; probability: number; score: number
  factors: Factor[]; why: string
}

export interface StepInfo { index: number; side: Side; type: ActionType; phase: string; label: string }

export interface TimelineSlot extends StepInfo { team: string; champion: string | null; current: boolean }

export interface Decision {
  id: number; step: number; action_type: ActionType; suggested_champion: string | null
  decision: 'accept' | 'modify' | 'reject' | 'manual'; final_champion: string | null; note: string | null
  created_at: string; suggested_rank?: number | null; suggested_score?: number | null
  top_suggestions?: { champion: string; score: number }[]
}

export interface DraftAnalysis {
  id: string; series_id: string; game_number: number; best_of: number
  our_team: string; opponent: string; our_side: Side; result: 'win' | 'loss' | null
  fearless_mode: 'off' | 'hard' | 'soft'; locked: Record<Side, string[]>
  state: {
    index: number; complete: boolean
    current: (StepInfo & { team: string; ours: boolean }) | null
    timeline: TimelineSlot[]
    roles: Record<Side, Partial<Record<Role, string>>>
  }
  recommendations: { step: StepInfo | null; type?: ActionType; weights?: Record<string, number>; recommendations: Recommendation[] }
  prediction: { step: StepInfo | null; team?: string; predictions: Prediction[] }
  win_probability?: WinProbability
  rejected_this_step: string[]
  decisions: Decision[]
}

export interface Weights { pick: Record<string, number>; ban: Record<string, number> }
export interface WeightsResponse { weights: Weights; defaults: Weights; labels: Record<string, string> }

export interface SeriesGameSummary { id: string; game_number: number; our_side: Side; result: string | null; complete: boolean }
export interface SeriesSummary {
  id: string; our_team: string; opponent: string; best_of: number; fearless_mode: string; title: string | null
  created_at: string; games: SeriesGameSummary[]; score: [number, number]; decisions: number
}
export interface SeriesDetail extends Omit<SeriesSummary, 'games' | 'decisions'> {
  games: {
    id: string; game_number: number; our_side: Side; result: string | null; complete: boolean
    timeline: TimelineSlot[]; locked: Record<Side, string[]>; blue_team: string; red_team: string
    decisions: Decision[]; created_at: string
  }[]
  fearless_pool: { champion: string; team: string; game: number }[]
}

export interface PoolEntry { champion: string; games: number; wins: number; wr: number; weighted: number; comfort: number; last_played: string }
export interface RateRow { champion: string; count: number; rate: number; wins?: number; wr?: number }
export interface Objective { rate: number | null; count: number; games: number }
export interface TeamSummary {
  games: number; wins: number; wr: number
  sides: Record<Side, { games: number; wins: number; wr: number }>
  objectives: Record<'first_blood' | 'first_dragon' | 'first_herald' | 'first_tower', Objective>
  gold_diff_15: { avg: number | null; ahead_rate: number | null; games: number }
  avg_duration_s: number | null
  first_pick_roles: Record<string, number>
}
export interface MatchRow {
  id: string; date: string; patch: string | null; tournament: string | null; series_id: string | null; game_number: number
  side: Side; opponent: string; win: boolean; duration_s: number | null; gold_diff_15: number | null
  picks: { role: Role; champion: string }[]; opp_picks: { role: Role; champion: string }[]
  bans: string[]; opp_bans: string[]
}
export interface Insight { type: string; text: string }
export interface BanPlanItem { champion: string; player: string; role: Role; games: number; wr: number; value: number; reason: string }
export interface ScoutingReport {
  team: { id: string; name: string; tag: string; color: string; region: string }
  summary: TeamSummary
  players: { id: string; name: string; role: Role; games: number; wr: number; pool: PoolEntry[]; unique_champions: number }[]
  most_picked: RateRow[]; most_banned_by: RateRow[]; most_banned_against: RateRow[]
  first_picks: RateRow[]; phase1_bans: RateRow[]; phase2_bans: RateRow[]
  first_pick_roles: { role: Role; count: number; rate: number }[]
  recent: MatchRow[]; insights: Insight[]; ban_plan?: BanPlanItem[]
  fearless?: FearlessProfile; ban_impact?: BanImpact
}
export interface ChampCount { champion: string; name: string; count: number; rate: number }
export interface FearlessProfile {
  available: boolean; games?: number; core_pool?: number; shifts?: string[]
  buckets?: { game: string; games: number; wins: number; wr: number; core_share: number | null
    first_pick_roles: { role: Role; rate: number; count: number }[]; top_picks: ChampCount[]; top_bans: ChampCount[] }[]
}
export interface BanImpact {
  available: boolean; overall_wr?: number; games?: number; method?: string
  items: { champion: string; name: string; picked: number; pick_rate: number; g1_pick_rate: number | null
    wr_when_picked: number | null; banned_games: number; wr_when_banned: number; delta: number; impact: number; text: string }[]
}
export interface DashboardData {
  our: TeamSummary; opp: TeamSummary
  h2h: { games: number; a_wins: number; matches: MatchRow[] }
  our_recent: MatchRow[]; opp_recent: MatchRow[]; insights: Insight[]; ban_plan: BanPlanItem[]
}
export interface BacktestMetrics {
  actions: number; top1: number; top3: number; top5: number; baseline_top1: number; baseline_top5: number
  log_loss: number; avg_top1_confidence: number
}
export interface Backtest {
  train_games: number; test_games: number; walk_forward?: boolean; pick: BacktestMetrics; ban: BacktestMetrics
  model?: { source: string; fitted_on?: string; fitted_at?: string; pick: Record<string, number>; ban: Record<string, number> }
}
export interface Explanation { text: string; source: string; template: string; llm_error?: boolean }

export interface FsRate { games: number; wins: number; wr: number | null }
export interface FsOutcome { side: Side; turn: 'first' | 'second'; wr: number; parts: { league: number; side: number; turn: number; form: number } }
export interface FirstSelection {
  available: boolean; reason?: string; recommendation?: string; summary?: string; method?: string
  choices?: { choice: string; kind: 'side' | 'turn'; value: string; opponent_reply: string; wr: number; outcome: FsOutcome }[]
  league?: { events: string[]; games: number; blue_wr: number; first_wr: number; combos: ({ side: Side; turn: string } & FsRate)[] }
  teams?: Record<string, { overall: FsRate; sides: Record<Side, FsRate>; turns_fs_era: Record<'first' | 'second', FsRate> }>
}
export interface WinProbability {
  p: number
  factors: { key: string; label: string; value: number; logit: number }[]
  curve: { index: number; p: number; label: string; champion: string | null }[]
  what_if: Record<string, number>
  model: { source?: string; fitted_on?: string; held_out?: { games: number; final_draft: { model: { accuracy: number; log_loss: number }; elo_and_side_only: { accuracy: number; log_loss: number } } } }
}
