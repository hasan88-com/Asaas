import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  getStrategies,
  createStrategy,
  deleteStrategy,
  runStrategy,
} from '@/lib/api'
import type {
  StrategyResponse,
  StrategyKind,
  StrategyRunResult,
  ScreenerCondition,
} from '@/types/api'

const RISK_OPTIONS = [
  'conservative',
  'moderately_conservative',
  'moderate',
  'aggressive',
  'very_aggressive',
] as const
const HORIZON_OPTIONS = ['short', 'medium', 'long'] as const
const METHOD_OPTIONS = ['max_sharpe', 'min_vol', 'risk_parity', 'hrp'] as const
const ASSET_CLASSES = ['psx_stock', 'crypto', 'commodity', 'tbill'] as const
const SCREENER_FIELDS = ['sector', 'asset_class', 'price'] as const
const STRING_OPS = ['eq', 'neq', 'in'] as const
const NUM_OPS = ['gt', 'gte', 'lt', 'lte', 'eq', 'neq'] as const

function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function Strategies() {
  const [strategies, setStrategies] = useState<StrategyResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [wizardOpen, setWizardOpen] = useState(false)
  const [runResults, setRunResults] = useState<Record<string, StrategyRunResult>>({})
  const [running, setRunning] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    try {
      setStrategies(await getStrategies())
      setError(null)
    } catch {
      setError("Couldn't load your strategies.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleRun(id: string) {
    setRunning(id)
    try {
      const res = await runStrategy(id)
      setRunResults((prev) => ({ ...prev, [id]: res }))
    } catch {
      setRunResults((prev) => ({
        ...prev,
        [id]: { kind: 'allocation', error: 'Run failed. Try again.' },
      }))
    } finally {
      setRunning(null)
    }
  }

  async function handleDelete(id: string) {
    await deleteStrategy(id)
    setStrategies((prev) => prev.filter((s) => s.id !== id))
    setRunResults((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-[28px] font-semibold text-ink leading-[1.1]">Strategies</h1>
          <p className="font-sans text-[14px] text-ink-soft">
            Build no-code investing rules — allocation strategies (MPT optimiser) and
            screeners — and run them on demand.
          </p>
        </div>
        {!wizardOpen && (
          <Button variant="primary" onClick={() => setWizardOpen(true)} className="shrink-0">
            New strategy
          </Button>
        )}
      </div>

      {wizardOpen && (
        <NewStrategyWizard
          onCancel={() => setWizardOpen(false)}
          onCreated={async () => {
            setWizardOpen(false)
            await refresh()
          }}
        />
      )}

      {error && <p className="font-sans text-[13px] text-loss">{error}</p>}

      {loading ? (
        <p className="font-sans text-[14px] text-ink-faint">Loading…</p>
      ) : strategies.length === 0 && !wizardOpen ? (
        <div className="bg-card border border-line rounded-[10px] p-6">
          <p className="font-sans text-[14px] text-ink-faint">
            No strategies yet. Create one to get started.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {strategies.map((s) => (
            <li key={s.id} className="bg-card border border-line rounded-[10px] p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="font-sans text-[15px] font-semibold text-ink">{s.name}</span>
                  <span
                    className={cn(
                      'font-mono text-[10px] uppercase tracking-[0.12em] px-2 py-0.5 rounded-full',
                      s.kind === 'allocation' ? 'bg-jade-soft text-jade' : 'bg-paper text-ink-soft border border-line',
                    )}
                  >
                    {s.kind}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => handleRun(s.id)}
                    disabled={running === s.id}
                  >
                    {running === s.id ? 'Running…' : 'Run'}
                  </Button>
                  <Button variant="ghost" onClick={() => handleDelete(s.id)}>
                    Delete
                  </Button>
                </div>
              </div>

              {runResults[s.id] && <RunResultView result={runResults[s.id]} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ---- Run result rendering ------------------------------------------------ */

function RunResultView({ result }: { result: StrategyRunResult }) {
  if (result.error) {
    return <p className="font-sans text-[13px] text-loss border-t border-line-soft pt-3">{result.error}</p>
  }

  if (result.kind === 'allocation' && result.allocation) {
    const a = result.allocation as Record<string, unknown>
    const weights = (a.target_weights ?? {}) as Record<string, string>
    const rows = Object.entries(weights).sort((x, y) => Number(y[1]) - Number(x[1]))
    return (
      <div className="border-t border-line-soft pt-3 flex flex-col gap-2">
        <div className="flex gap-4 flex-wrap font-mono text-[12px] text-ink-soft">
          {a.expected_return != null && <span>Expected p.a. {(Number(a.expected_return) * 100).toFixed(2)}%</span>}
          {a.expected_risk != null && <span>Risk {(Number(a.expected_risk) * 100).toFixed(2)}%</span>}
          {a.sharpe != null && <span>Sharpe {Number(a.sharpe).toFixed(2)}</span>}
        </div>
        <ul className="flex flex-col divide-y divide-line-soft">
          {rows.map(([sym, w]) => (
            <li key={sym} className="flex items-center justify-between py-1.5">
              <span className="font-mono text-[13px] text-ink">{sym}</span>
              <span className="font-mono text-[13px] tabular-nums text-ink-soft">
                {(Number(w) * 100).toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  if (result.kind === 'screener') {
    const matches = result.matches ?? []
    return (
      <div className="border-t border-line-soft pt-3 flex flex-col gap-2">
        <p className="font-mono text-[12px] text-ink-faint">{result.count ?? matches.length} match(es)</p>
        {matches.length === 0 ? (
          <p className="font-sans text-[13px] text-ink-faint">No instruments matched these conditions.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line-soft">
            {matches.map((m) => (
              <li key={m.symbol} className="flex items-center justify-between py-1.5 gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-[13px] font-semibold text-ink">{m.symbol}</span>
                  <span className="font-sans text-[12px] text-ink-soft truncate">{m.sector ?? m.asset_class}</span>
                </div>
                {m.current_price != null && (
                  <span className="font-mono text-[13px] tabular-nums text-ink-soft">
                    ₨{Number(m.current_price).toLocaleString('en-PK', { maximumFractionDigits: 2 })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return null
}

/* ---- 2-step wizard ------------------------------------------------------- */

function NewStrategyWizard({
  onCancel,
  onCreated,
}: {
  onCancel: () => void
  onCreated: () => void
}) {
  const [kind, setKind] = useState<StrategyKind | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // allocation form
  const [risk, setRisk] = useState<string>('moderate')
  const [horizon, setHorizon] = useState<string>('long')
  const [method, setMethod] = useState<string>('')
  const [excludedClasses, setExcludedClasses] = useState<string[]>([])
  const [excludedSectors, setExcludedSectors] = useState('')

  // screener form
  const [conditions, setConditions] = useState<ScreenerCondition[]>([
    { field: 'asset_class', op: 'eq', value: 'psx_stock' },
  ])

  function buildConfig(): Record<string, unknown> {
    if (kind === 'allocation') {
      const constraints: Record<string, unknown> = {}
      const sectors = excludedSectors.split(',').map((s) => s.trim()).filter(Boolean)
      if (sectors.length) constraints.excluded_sectors = sectors
      if (excludedClasses.length) constraints.excluded_asset_classes = excludedClasses
      const config: Record<string, unknown> = { risk_tolerance: risk, horizon }
      if (method) config.method = method
      if (Object.keys(constraints).length) config.constraints = constraints
      return config
    }
    return { logic: 'AND', conditions }
  }

  async function handleSave() {
    if (!kind || !name.trim()) {
      setErr('Give the strategy a name.')
      return
    }
    setSaving(true)
    try {
      await createStrategy({ name: name.trim(), kind, config: buildConfig() })
      onCreated()
    } catch {
      setErr('Could not save — check the form and try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-card border border-line rounded-[10px] p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">New strategy</h2>
        <button type="button" onClick={onCancel} className="font-sans text-[13px] text-ink-faint hover:text-ink">
          Cancel
        </button>
      </div>

      {/* Step 1 — choose kind */}
      {!kind ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setKind('allocation')}
            className="text-left border border-line rounded-[8px] p-4 hover:border-jade transition-colors"
          >
            <p className="font-sans font-semibold text-[14px] text-ink">Allocation</p>
            <p className="font-sans text-[12px] text-ink-soft mt-1">
              Pick risk, horizon and optimiser method → produces a draft portfolio.
            </p>
          </button>
          <button
            type="button"
            onClick={() => setKind('screener')}
            className="text-left border border-line rounded-[8px] p-4 hover:border-jade transition-colors"
          >
            <p className="font-sans font-semibold text-[14px] text-ink">Screener</p>
            <p className="font-sans text-[12px] text-ink-soft mt-1">
              Filter instruments by sector, asset class or price conditions (AND).
            </p>
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <Field label="Name">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={kind === 'allocation' ? 'e.g. Conservative long-term' : 'e.g. Cheap PSX stocks'}
              className="w-full bg-paper border border-line rounded-[8px] px-3 py-2 font-sans text-[14px] text-ink"
            />
          </Field>

          {kind === 'allocation' ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <Field label="Risk tolerance">
                  <Select value={risk} onChange={setRisk} options={RISK_OPTIONS as readonly string[]} />
                </Field>
                <Field label="Horizon">
                  <Select value={horizon} onChange={setHorizon} options={HORIZON_OPTIONS as readonly string[]} />
                </Field>
                <Field label="Method">
                  <Select
                    value={method}
                    onChange={setMethod}
                    options={['', ...METHOD_OPTIONS] as readonly string[]}
                    labels={{ '': 'Auto (from profile)' }}
                  />
                </Field>
              </div>
              <Field label="Exclude asset classes">
                <div className="flex flex-wrap gap-2">
                  {ASSET_CLASSES.map((ac) => {
                    const on = excludedClasses.includes(ac)
                    return (
                      <button
                        key={ac}
                        type="button"
                        onClick={() =>
                          setExcludedClasses((prev) =>
                            on ? prev.filter((x) => x !== ac) : [...prev, ac],
                          )
                        }
                        className={cn(
                          'font-mono text-[12px] px-2.5 py-1 rounded-full border transition-colors',
                          on ? 'bg-loss/10 text-loss border-loss/40' : 'bg-paper text-ink-soft border-line',
                        )}
                      >
                        {titleCase(ac)}
                      </button>
                    )
                  })}
                </div>
              </Field>
              <Field label="Exclude sectors (comma-separated)">
                <input
                  value={excludedSectors}
                  onChange={(e) => setExcludedSectors(e.target.value)}
                  placeholder="e.g. Tobacco, Banks"
                  className="w-full bg-paper border border-line rounded-[8px] px-3 py-2 font-sans text-[14px] text-ink"
                />
              </Field>
            </>
          ) : (
            <ScreenerBuilder conditions={conditions} setConditions={setConditions} />
          )}

          {err && <p className="font-sans text-[13px] text-loss">{err}</p>}

          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save strategy'}
            </Button>
            <Button variant="ghost" onClick={() => setKind(null)}>
              Back
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function ScreenerBuilder({
  conditions,
  setConditions,
}: {
  conditions: ScreenerCondition[]
  setConditions: (c: ScreenerCondition[]) => void
}) {
  function update(i: number, patch: Partial<ScreenerCondition>) {
    setConditions(conditions.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  }
  function add() {
    setConditions([...conditions, { field: 'price', op: 'lt', value: '' }])
  }
  function remove(i: number) {
    setConditions(conditions.filter((_, idx) => idx !== i))
  }

  return (
    <Field label="Conditions (all must match)">
      <div className="flex flex-col gap-2">
        {conditions.map((c, i) => {
          const ops = c.field === 'price' ? NUM_OPS : STRING_OPS
          return (
            <div key={i} className="flex items-center gap-2">
              <Select
                value={c.field}
                onChange={(v) =>
                  update(i, {
                    field: v as ScreenerCondition['field'],
                    op: v === 'price' ? 'lt' : 'eq',
                  })
                }
                options={SCREENER_FIELDS as readonly string[]}
              />
              <Select
                value={c.op}
                onChange={(v) => update(i, { op: v as ScreenerCondition['op'] })}
                options={ops as readonly string[]}
              />
              <input
                value={String(c.value ?? '')}
                onChange={(e) => update(i, { value: e.target.value })}
                placeholder={c.field === 'price' ? 'e.g. 100' : 'e.g. Cement'}
                className="flex-1 bg-paper border border-line rounded-[8px] px-3 py-2 font-sans text-[13px] text-ink"
              />
              {conditions.length > 1 && (
                <button
                  type="button"
                  onClick={() => remove(i)}
                  className="font-mono text-[16px] text-ink-faint hover:text-loss px-1"
                  aria-label="Remove condition"
                >
                  ×
                </button>
              )}
            </div>
          )
        })}
        <button
          type="button"
          onClick={add}
          className="self-start font-sans text-[13px] text-jade hover:underline"
        >
          + Add condition
        </button>
      </div>
    </Field>
  )
}

/* ---- small form primitives ----------------------------------------------- */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">{label}</span>
      {children}
    </label>
  )
}

function Select({
  value,
  onChange,
  options,
  labels,
}: {
  value: string
  onChange: (v: string) => void
  options: readonly string[]
  labels?: Record<string, string>
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-paper border border-line rounded-[8px] px-3 py-2 font-sans text-[13px] text-ink"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {labels?.[o] ?? titleCase(o)}
        </option>
      ))}
    </select>
  )
}
