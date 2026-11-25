import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import type { Weights, WeightsResponse } from '../lib/types'

const HELP: Record<string, string> = {
  meta: 'Pro presence (pick+ban rate) and smoothed win rate, recency weighted',
  counter: 'Win rate vs the enemy picks already revealed (lane opponent counts most)',
  synergy: 'Pair win rate with the champions we already picked',
  comfort: 'Our player\'s games and win rate on the champion (recent games count more)',
  deny: 'How much the opponent wants it: their player\'s comfort on it',
  coach: 'Your own Accept / Modify / Reject history for this champion',
  threat: 'Opponent player\'s comfort on the champion',
  predicted: 'Probability the opponent picks it next (prediction model)',
  protect: 'Penalty for banning one of our own comfort picks',
}

export default function WeightsDrawer({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const { toast } = useApp()
  const [data, setData] = useState<WeightsResponse | null>(null)
  const [draft, setDraft] = useState<Weights | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) api.weights().then(r => { setData(r); setDraft(r.weights) })
  }, [open])

  const save = async (fn: () => Promise<WeightsResponse>, msg: string) => {
    setSaving(true)
    try {
      const r = await fn()
      setData(r)
      setDraft(r.weights)
      onSaved()
      toast(msg)
    } catch (e) {
      toast(String((e as Error).message), 'err')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`no-print fixed inset-0 z-40 ${open ? '' : 'pointer-events-none'}`}>
      <div className={`absolute inset-0 bg-black/50 transition ${open ? 'opacity-100' : 'opacity-0'}`} onClick={onClose} />
      <aside className={`absolute top-0 right-0 flex h-full w-full max-w-md flex-col border-l border-white/10 bg-ink-900 shadow-2xl transition-transform ${open ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Recommendation weights</h2>
            <p className="text-xs text-slate-500">Score = Σ factor × weight. Tune how DraftMind thinks.</p>
          </div>
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
        <div className="scroll-thin flex-1 space-y-6 overflow-y-auto p-4">
          {data && draft && (['pick', 'ban'] as const).map(typ => (
            <div key={typ}>
              <div className="mb-3 font-display text-sm font-semibold tracking-wider text-accent uppercase">{typ} recommendations</div>
              <div className="space-y-4">
                {Object.keys(draft[typ]).map(k => (
                  <div key={k}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-sm font-medium text-slate-200">{data.labels[k] ?? k}</span>
                      <span className="font-mono text-sm text-accent">{draft[typ][k].toFixed(1)}</span>
                    </div>
                    <input type="range" min={0} max={3} step={0.1} value={draft[typ][k]}
                      onChange={e => setDraft({ ...draft, [typ]: { ...draft[typ], [k]: Number(e.target.value) } })}
                      className="mt-1 w-full accent-cyan-400" />
                    <div className="flex justify-between text-[11px] text-slate-500">
                      <span>{HELP[k]}</span>
                      <span className="shrink-0 pl-2">default {data.defaults[typ][k]}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-2 border-t border-white/[0.06] p-4">
          <button className="btn-ghost" disabled={saving} onClick={() => save(api.resetWeights, 'Weights reset to defaults')}>Reset defaults</button>
          <button className="btn-primary ml-auto" disabled={saving || !draft} onClick={() => draft && save(() => api.saveWeights(draft), 'Weights saved — recommendations updated')}>
            Save & re-score
          </button>
        </div>
      </aside>
    </div>
  )
}
