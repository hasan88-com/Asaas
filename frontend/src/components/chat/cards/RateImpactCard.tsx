import { Button } from '@/components/ui/button'
import { CardShell } from './CardShell'
import { postSuggest } from '@/lib/api'
import type { RateImpactCardData } from '@/types/api'
import { cn } from '@/lib/utils'

const ACCENT = '#B8801A'

function pct(val: string | undefined): string {
  if (!val) return '—'
  const n = parseFloat(val)
  return `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
}

interface BeforeAfterRowProps {
  label: string
  before: string | undefined
  after: string | undefined
}

function BeforeAfterRow({ label, before, after }: BeforeAfterRowProps) {
  const delta = before && after ? parseFloat(after) - parseFloat(before) : null
  const positive = delta !== null && delta >= 0

  return (
    <div className="flex items-center justify-between py-1.5 border-b border-line-soft last:border-0">
      <span className="text-[14px] text-ink-soft">{label}</span>
      <div className="flex items-center gap-3 font-mono text-[14px]">
        <span className="text-ink-faint line-through">{before ?? '—'}</span>
        <span
          className={cn(
            'font-semibold',
            delta !== null && (positive ? 'text-gain' : 'text-loss'),
          )}
          aria-label={`${positive ? 'Increase' : 'Decrease'} to ${after}`}
        >
          {positive ? '▲' : delta !== null ? '▼' : ''} {after ?? '—'}
        </span>
      </div>
    </div>
  )
}

interface RateImpactCardProps {
  data: RateImpactCardData
}

export function RateImpactCard({ data }: RateImpactCardProps) {
  const rateDelta = parseFloat(data.rate_delta) * 100
  const positive = rateDelta >= 0

  return (
    <CardShell
      eyebrow="SBP Rate Impact"
      accentColor={ACCENT}
      actions={
        data.is_material ? (
          <Button onClick={() => postSuggest()} variant="primary" size="sm">
            Review &amp; re-optimize
          </Button>
        ) : undefined
      }
    >
      {/* Rate move headline */}
      <p className="font-sans font-medium text-[19px] leading-[1.3] text-ink mb-4">
        SBP rate{' '}
        <span className={positive ? 'text-gain' : 'text-loss'}>
          {positive ? '▲' : '▼'} {Math.abs(rateDelta).toFixed(0)} bps
        </span>{' '}
        ({data.sbp_rate_before} → {data.sbp_rate_after})
      </p>

      {/* Effects */}
      {(data.price_impact_pct || data.yield_impact_pct) && (
        <div className="flex gap-4 mb-4 text-[14px]">
          {data.price_impact_pct && (
            <div>
              <p className="text-ink-faint mb-0.5">Price impact</p>
              <p
                className={cn(
                  'font-mono font-semibold',
                  parseFloat(data.price_impact_pct) >= 0 ? 'text-gain' : 'text-loss',
                )}
              >
                {pct(data.price_impact_pct)}
              </p>
            </div>
          )}
          {data.yield_impact_pct && (
            <div>
              <p className="text-ink-faint mb-0.5">Yield impact</p>
              <p
                className={cn(
                  'font-mono font-semibold',
                  parseFloat(data.yield_impact_pct) >= 0 ? 'text-gain' : 'text-loss',
                )}
              >
                {pct(data.yield_impact_pct)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Before / after values */}
      {(data.value_before || data.value_after) && (
        <div className="rounded-[10px] border border-line overflow-hidden">
          <BeforeAfterRow label="Portfolio value" before={data.value_before} after={data.value_after} />
        </div>
      )}
    </CardShell>
  )
}
