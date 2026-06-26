import { Button } from '@/components/ui/button'
import { CardShell } from './CardShell'
import { AllocationDonut, assetClassColor, assetClassLabel } from '@/components/charts/AllocationDonut'
import { postConfirm, postSuggest } from '@/lib/api'
import type { PortfolioResponse, HoldingResponse } from '@/types/api'
import { cn } from '@/lib/utils'

const ACCENT = '#0F6E56'

function StatCell({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-0.5', className)}>
      <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">{label}</span>
      <span className="font-mono text-[16px] font-medium text-ink tabular-nums">{value}</span>
    </div>
  )
}

interface LegendEntry {
  key: string
  /** Primary label — a symbol, or an asset-class name when grouped. */
  title: string
  /** Instrument name (e.g. "Habib Bank Limited"); empty when grouped by class. */
  name: string
  assetClass: string
  pct: number
  color: string
}

/** Small coloured asset-class badge. */
function ClassBadge({ assetClass, color }: { assetClass: string; color: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full font-mono text-[10px] font-medium"
      style={{ backgroundColor: `${color}1A`, color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {assetClassLabel(assetClass)}
    </span>
  )
}

/** Per-holding legend entries (symbol + class). */
function perHoldingEntries(holdings: HoldingResponse[]): LegendEntry[] {
  return holdings
    .filter((h) => (h.weight ?? 0) > 0)
    .map((h) => ({
      key: h.symbol || h.instrument_id || h.id,
      title: h.symbol || h.name || '—',
      // Show the name only when we have a distinct symbol to pair it with.
      name: h.symbol && h.name ? h.name : '',
      assetClass: h.asset_class ?? 'equity',
      pct: (h.weight ?? 0) * 100,
      color: assetClassColor(h.asset_class),
    }))
}

/** Aggregate holdings into asset-class categories (used for "start fresh"). */
function byClassEntries(holdings: HoldingResponse[]): LegendEntry[] {
  const totals = new Map<string, number>()
  for (const h of holdings) {
    const ac = (h.asset_class ?? 'equity').toLowerCase()
    totals.set(ac, (totals.get(ac) ?? 0) + (h.weight ?? 0))
  }
  return [...totals.entries()]
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([ac, w]) => ({
      key: ac,
      title: assetClassLabel(ac),
      name: '',
      assetClass: ac,
      pct: w * 100,
      color: assetClassColor(ac),
    }))
}

interface OptimizerCardProps {
  data: PortfolioResponse
  mode?: 'suggest' | 'analyze'
  currentHoldings?: HoldingResponse[]
  /** When true (e.g. user started fresh), show allocation by asset-class category. */
  groupByClass?: boolean
}

export function OptimizerCard({ data, mode = 'suggest', currentHoldings, groupByClass = false }: OptimizerCardProps) {
  const handleConfirm = () => postConfirm(data.holdings)
  const handleAdjust = () => postSuggest()

  const ret = `${(parseFloat(data.expected_return) * 100).toFixed(1)}%`
  const risk = `${(parseFloat(data.expected_risk) * 100).toFixed(1)}%`
  const sharpe = parseFloat(data.sharpe).toFixed(2)

  const entries = groupByClass ? byClassEntries(data.holdings) : perHoldingEntries(data.holdings)

  return (
    <CardShell
      eyebrow={mode === 'suggest' ? 'Suggested Portfolio' : 'Portfolio Analysis'}
      accentColor={ACCENT}
      actions={
        mode === 'suggest' ? (
          <>
            <Button onClick={handleConfirm} variant="primary" size="sm">
              Confirm holdings
            </Button>
            <Button onClick={handleAdjust} variant="ghost" size="sm">
              Adjust
            </Button>
          </>
        ) : undefined
      }
    >
      {mode === 'suggest' ? (
        <div className="flex flex-col gap-5">
          <div className="flex gap-4 items-start">
            {/* Donut — coloured per asset class with "SYMBOL (Asset)" labels */}
            <div className="shrink-0">
              <AllocationDonut
                size={180}
                labels={entries.map((e) => (groupByClass ? e.title : `${e.title} (${assetClassLabel(e.assetClass)})`))}
                data={entries.map((e) => e.pct)}
                colors={entries.map((e) => e.color)}
              />
            </div>

            {/* Stats */}
            <div className="flex flex-col gap-3 pt-2">
              <StatCell label="Expected return" value={ret} />
              <StatCell label="Risk (σ)" value={risk} />
              <StatCell label="Sharpe" value={sharpe} />
            </div>
          </div>

          {/* Legend / holdings summary — symbol, asset-class badge, weight % */}
          <div className="flex flex-col divide-y divide-line-soft border border-line rounded-[8px] overflow-hidden">
            <div className="px-3 py-2 bg-paper">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
                {groupByClass ? 'Suggested allocation by asset class' : 'Suggested holdings'}
              </p>
            </div>
            {entries.map((e) => (
              <div key={e.key} className="px-3 py-2.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: e.color }} />
                  {groupByClass ? (
                    <span className="font-mono text-[13px] font-semibold text-ink truncate">{e.title}</span>
                  ) : (
                    <>
                      {/* Symbol as a monospace badge */}
                      <span className="font-mono text-[11px] font-semibold text-ink px-1.5 py-0.5 rounded bg-paper border border-line shrink-0">
                        {e.title}
                      </span>
                      {e.name && (
                        <span className="font-sans text-[12px] text-ink-soft truncate">{e.name}</span>
                      )}
                      <ClassBadge assetClass={e.assetClass} color={e.color} />
                    </>
                  )}
                </div>
                <span className="font-mono text-[13px] font-medium text-ink tabular-nums shrink-0">
                  {e.pct.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>

          {data.rationale && (
            <p className="text-[14px] text-ink-soft leading-[1.5]">{data.rationale}</p>
          )}
        </div>
      ) : (
        /* Analyze mode — two side-by-side donuts */
        <div className="flex gap-6 items-start flex-wrap">
          {currentHoldings && currentHoldings.length > 0 && (
            <div className="flex flex-col items-center gap-1">
              <AllocationDonut holdings={currentHoldings} size={120} centerLabel="Current" />
              <span className="font-mono text-[11px] text-ink-faint uppercase tracking-wide">Current</span>
            </div>
          )}
          {data.holdings.length > 0 && (
            <div className="flex flex-col items-center gap-1">
              <AllocationDonut holdings={data.holdings} size={120} centerLabel="Suggested" />
              <span className="font-mono text-[11px] text-ink-faint uppercase tracking-wide">Suggested</span>
            </div>
          )}
          {data.concentration_warning && (
            <p className="text-[14px] text-loss leading-[1.5] mt-1">{data.concentration_warning}</p>
          )}
        </div>
      )}
    </CardShell>
  )
}
