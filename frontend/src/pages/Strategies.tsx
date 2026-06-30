import { useEffect, useState } from 'react'
import { getStrategies, createStrategy, deleteStrategy, runStrategy } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { StrategyResponse, StrategyKind, StrategyRunResult } from '@/types/api'

const RISK_OPTIONS = ['conservative', 'moderate', 'aggressive']
const METHOD_OPTIONS = ['max_sharpe', 'min_vol', 'risk_parity', 'hrp']
const FIELD_OPTIONS = ['sector', 'asset_class', 'price']
const OP_OPTIONS = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte']

interface Condition {
  field: string
  op: string
  value: string
}

function emptyCondition(): Condition {
  return { field: 'sector', op: 'eq', value: '' }
}

export default function Strategies() {
  const [strategies, setStrategies] = useState<StrategyResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [showWizard, setShowWizard] = useState(false)
  const [kind, setKind] = useState<StrategyKind>('allocation')
  const [name, setName] = useState('')
  const [riskTolerance, setRiskTolerance] = useState('moderate')
  const [method, setMethod] = useState('max_sharpe')
  const [excludedSectors, setExcludedSectors] = useState('')
  const [conditions, setConditions] = useState<Condition[]>([emptyCondition()])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<Record<string, StrategyRunResult>>({})

  const load = () => {
    setLoading(true)
    getStrategies()
      .then(setStrategies)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const resetWizard = () => {
    setShowWizard(false)
    setName('')
    setKind('allocation')
    setRiskTolerance('moderate')
    setMethod('max_sharpe')
    setExcludedSectors('')
    setConditions([emptyCondition()])
    setError(null)
  }

  const handleCreate = async () => {
    if (!name.trim()) {
      setError('Name your strategy.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const config =
        kind === 'allocation'
          ? {
              risk_tolerance: riskTolerance,
              constraints: {
                method,
                excluded_sectors: excludedSectors
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
            }
          : {
              conditions: conditions.filter((c) => c.value.trim() !== ''),
            }
      await createStrategy({ name: name.trim(), kind, config })
      resetWizard()
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create strategy.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    await deleteStrategy(id)
    load()
  }

  const handleRun = async (id: string) => {
    setRunningId(id)
    try {
      const result = await runStrategy(id)
      setRunResults((prev) => ({ ...prev, [id]: result }))
    } catch (err) {
      setRunResults((prev) => ({
        ...prev,
        [id]: { kind: 'allocation', result: { error: err instanceof Error ? err.message : 'Run failed.' } },
      }))
    } finally {
      setRunningId(null)
    }
  }

  const updateCondition = (i: number, patch: Partial<Condition>) => {
    setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  }

  return (
    <div className="flex flex-col gap-8 max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-[28px] font-semibold text-ink">Strategies</h1>
          <p className="font-sans text-[14px] text-ink-soft mt-1">
            No-code rules for allocation and screening — parameterizes the same optimizer and
            data engine used elsewhere in Asaasa.
          </p>
        </div>
        {!showWizard && (
          <Button variant="primary" onClick={() => setShowWizard(true)} className="shrink-0">
            New strategy
          </Button>
        )}
      </div>

      {showWizard && (
        <section className="bg-card border border-line rounded-[10px] p-5 flex flex-col gap-5">
          <div className="flex gap-2">
            {(['allocation', 'screener'] as StrategyKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={cn(
                  'font-mono text-[12px] uppercase tracking-[0.12em] px-3 py-1.5 rounded-[6px] border',
                  kind === k
                    ? 'border-jade bg-jade-soft text-jade'
                    : 'border-line text-ink-faint'
                )}
              >
                {k}
              </button>
            ))}
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
              Name
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={kind === 'allocation' ? 'Conservative growth' : 'Cheap banking stocks'}
              className="font-sans text-[14px] bg-bg border border-line rounded-[6px] px-3 py-2 text-ink"
            />
          </label>

          {kind === 'allocation' ? (
            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                  Risk tolerance
                </span>
                <select
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  className="font-sans text-[14px] bg-bg border border-line rounded-[6px] px-3 py-2 text-ink"
                >
                  {RISK_OPTIONS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                  Optimization method
                </span>
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  className="font-sans text-[14px] bg-bg border border-line rounded-[6px] px-3 py-2 text-ink"
                >
                  {METHOD_OPTIONS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                  Excluded sectors (comma-separated)
                </span>
                <input
                  value={excludedSectors}
                  onChange={(e) => setExcludedSectors(e.target.value)}
                  placeholder="Tobacco, Sugar"
                  className="font-sans text-[14px] bg-bg border border-line rounded-[6px] px-3 py-2 text-ink"
                />
              </label>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
                Conditions (all must match)
              </span>
              {conditions.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <select
                    value={c.field}
                    onChange={(e) => updateCondition(i, { field: e.target.value })}
                    className="font-sans text-[13px] bg-bg border border-line rounded-[6px] px-2 py-1.5 text-ink"
                  >
                    {FIELD_OPTIONS.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                  <select
                    value={c.op}
                    onChange={(e) => updateCondition(i, { op: e.target.value })}
                    className="font-sans text-[13px] bg-bg border border-line rounded-[6px] px-2 py-1.5 text-ink"
                  >
                    {OP_OPTIONS.map((o) => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                  <input
                    value={c.value}
                    onChange={(e) => updateCondition(i, { value: e.target.value })}
                    placeholder="value"
                    className="font-sans text-[13px] bg-bg border border-line rounded-[6px] px-2 py-1.5 text-ink flex-1"
                  />
                  <button
                    type="button"
                    onClick={() => setConditions((prev) => prev.filter((_, idx) => idx !== i))}
                    className="font-mono text-[12px] text-loss px-1"
                    aria-label="Remove condition"
                  >
                    ✕
                  </button>
                </div>
              ))}
              <Button
                variant="outline"
                onClick={() => setConditions((prev) => [...prev, emptyCondition()])}
                className="self-start"
              >
                Add condition
              </Button>
            </div>
          )}

          {error && <p className="font-sans text-[13px] text-loss" role="alert">{error}</p>}

          <div className="flex gap-2">
            <Button variant="primary" onClick={handleCreate} disabled={saving}>
              {saving ? 'Saving…' : 'Save strategy'}
            </Button>
            <Button variant="outline" onClick={resetWizard} disabled={saving}>
              Cancel
            </Button>
          </div>
        </section>
      )}

      <section className="flex flex-col gap-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">
          Saved strategies
        </h2>

        {loading ? (
          <div className="h-24 bg-line animate-pulse rounded-[10px]" />
        ) : strategies.length === 0 ? (
          <p className="font-sans text-[14px] text-ink-faint">No strategies yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {strategies.map((s) => (
              <li key={s.id} className="bg-card border border-line rounded-[10px] p-4 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-sans text-[14px] font-semibold text-ink">{s.name}</span>
                    <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-faint ml-2">
                      {s.kind}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      onClick={() => handleRun(s.id)}
                      disabled={runningId === s.id}
                    >
                      {runningId === s.id ? 'Running…' : 'Run'}
                    </Button>
                    <button
                      type="button"
                      onClick={() => handleDelete(s.id)}
                      className="font-mono text-[12px] text-loss px-1"
                      aria-label="Delete strategy"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {runResults[s.id] && (
                  <pre className="font-mono text-[11px] bg-bg border border-line-soft rounded-[6px] p-3 overflow-x-auto text-ink-soft">
                    {JSON.stringify(runResults[s.id].result, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
