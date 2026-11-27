import { useEffect, useState } from 'react'
import { Panel, Spinner, pct } from '../components/ui'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { Backtest, WeightsResponse } from '../lib/types'

function Metric({ label, model, base }: { label: string; model: number; base?: number }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs"><span className="text-slate-400">{label}</span><span className="font-mono text-slate-200">{pct(model)}{base !== undefined && <span className="text-slate-500"> vs {pct(base)}</span>}</span></div>
      <div className="relative h-2 rounded-full bg-white/[0.05]">
        {base !== undefined && <div className="absolute h-2 rounded-full bg-slate-500/50" style={{ width: `${base * 100}%` }} />}
        <div className="absolute h-2 rounded-full bg-accent/80 mix-blend-screen" style={{ width: `${model * 100}%` }} />
      </div>
    </div>
  )
}

export default function ModelPage() {
  const { health } = useApp()
  const [bt, setBt] = useState<Backtest | null>(null)
  const [w, setW] = useState<WeightsResponse | null>(null)
  useEffect(() => { api.backtest().then(setBt); api.weights().then(setW) }, [])

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-3xl font-bold text-white">How DraftMind thinks</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          Every number on the draft board is a transparent weighted sum of factors computed from match data — no black box.
          The opponent model is validated on games it has never seen.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Opponent prediction — backtest" right={<span className="text-[11px] text-slate-500">grey = meta-only baseline</span>}>
          {!bt ? <Spinner /> : (
            <div className="space-y-5">
              {(['pick', 'ban'] as const).map(k => (
                <div key={k} className="space-y-2.5">
                  <div className="font-display text-sm font-semibold tracking-wider text-accent uppercase">{k}s ({bt[k].actions} held-out actions)</div>
                  <Metric label="Top-1 hit rate" model={bt[k].top1} base={bt[k].baseline_top1} />
                  <Metric label="Top-5 hit rate" model={bt[k].top5} base={bt[k].baseline_top5} />
                  <div className="flex gap-6 text-xs text-slate-400">
                    <span>Calibration: avg top-1 confidence <b className="text-slate-200">{pct(bt[k].avg_top1_confidence)}</b> vs actual <b className="text-slate-200">{pct(bt[k].top1)}</b></span>
                    <span>log-loss <b className="text-slate-200">{bt[k].log_loss.toFixed(2)}</b></span>
                  </div>
                </div>
              ))}
              <p className="text-xs text-slate-500">Walk-forward test: the model starts from the first {bt.train_games} games, then every draft action of the last {bt.test_games} games is predicted (fearless locks applied) before that game is added, so each prediction only uses earlier games. {bt.model?.source === 'fitted' ? <>Opponent weights were fitted by conditional logit on {bt.model.fitted_on}, all before the test period.</> : <>Opponent weights are hand-tuned defaults.</>}</p>
            </div>
          )}
        </Panel>

        <Panel title="Opponent model">
          <ol className="space-y-3 text-sm text-slate-300">
            <li><b className="text-white">Player comfort</b> — recency-weighted games (half-life 45 days) of the player who would play the champion in the role still open, scaled by smoothed win rate.</li>
            <li><b className="text-white">Team pattern at this phase</b> — how often the team took the champion in this exact phase (first pick, phase-1 picks, phase-2 bans…).</li>
            <li><b className="text-white">Meta</b> — recency-weighted pro presence (pick + ban rate) blended with Bayesian-smoothed win rate.</li>
            <li><b className="text-white">Counter / target</b> — picks that counter our revealed champions; bans that target our players' comfort picks.</li>
            <li><b className="text-white">Hot right now</b> — pick + ban presence over the last 80 pro games, which follows patch shifts faster than long averages.</li>
            <li><b className="text-white">Role for this pick</b> — which open role teams usually fill with their 1st…5th pick.</li>
            <li><b className="text-white">Recently played / team habit</b> — days since the player last played the champion; the team's overall pick and ban habits; what opponents usually ban against us.</li>
            <li><b className="text-white">Role still open</b> — hard gate: role assignment is solved exactly over flex picks (e.g. Corki mid ↔ bot).</li>
          </ol>
          <div className="mt-3 rounded-lg bg-white/[0.03] p-3 font-mono text-xs text-slate-300">P(champion) = softmax(Σ wᵢ·fᵢ / T)</div>
          {bt?.model?.source === 'fitted' && (
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-400">
              {(['pick', 'ban'] as const).map(typ => (
                <div key={typ}>
                  <div className="label mb-1">Fitted {typ} weights</div>
                  {Object.entries(bt.model![typ]).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <div key={k} className="flex justify-between"><span>{k}</span><span className="tabular-nums">{v.toFixed(2)}</span></div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Our recommendations — factors & current weights">
        {!w ? <Spinner /> : (
          <div className="grid gap-6 md:grid-cols-2">
            {(['pick', 'ban'] as const).map(typ => (
              <div key={typ}>
                <div className="mb-2 font-display text-sm font-semibold tracking-wider text-accent uppercase">{typ}</div>
                <table className="w-full text-sm">
                  <tbody>
                    {Object.entries(w.weights[typ]).map(([k, v]) => (
                      <tr key={k} className="border-b border-white/[0.04]">
                        <td className="py-1.5 text-slate-200">{w.labels[k] ?? k}</td>
                        <td className="w-32"><div className="h-1.5 rounded-full bg-white/[0.06]"><div className="h-1.5 rounded-full bg-accent" style={{ width: `${(v / 3) * 100}%` }} /></div></td>
                        <td className="w-12 text-right font-mono text-xs">{v.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
        <ul className="mt-4 grid gap-2 text-xs text-slate-400 md:grid-cols-2">
          <li><b className="text-slate-200">Counter</b>: lane win rate vs revealed enemies, blending pro games with solo-queue priors (pseudo-count 20) and shrinking small samples to 50%.</li>
          <li><b className="text-slate-200">Synergy</b>: pair win rate with our locked champions vs. what their individual win rates predict.</li>
          <li><b className="text-slate-200">Deny</b>: the opponent player's comfort on a champion we could take first.</li>
          <li><b className="text-slate-200">Coach history</b>: tanh of your Accept (+1) / Modify (+1 new, −0.4 old) / Reject (−1) log — the AI adapts to you.</li>
        </ul>
      </Panel>

      <Panel title="Data & explanations">
        <div className="grid gap-3 text-sm text-slate-300 md:grid-cols-3">
          <div><div className="label">Data source</div>{health?.dataset.adapter?.name === 'grid-files' ? "Official GRID data (Sky's The Limit 2026 hackathon starter)" : health?.data_source === 'grid' ? 'GRID esports API (Central Data + Series State)' : 'Bundled sample dataset (synthetic, offline)'} — {health?.dataset.matches} games, {health?.dataset.teams} teams.</div>
          <div><div className="label">Explanations</div>{health?.llm_provider === 'none' ? 'Templated from score factors (no API key needed).' : `LLM rewrite via ${health?.llm_provider}, grounded strictly in factor numbers; templated fallback.`}</div>
          <div><div className="label">Champion data</div>Riot Data Dragon {health?.ddragon_version} (names & icons) + curated pro role map.</div>
        </div>
      </Panel>
    </div>
  )
}
