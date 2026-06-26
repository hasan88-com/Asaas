import { CardShell } from './CardShell'
import { RSIGauge } from '@/components/charts/RSIGauge'
import { Badge } from '@/components/ui/badge'
import type { TechnicalResponse } from '@/types/api'
import { cn } from '@/lib/utils'

const ACCENT = 'var(--plum)'

function fmt(n: number | undefined, decimals = 2): string {
  if (n === undefined || n === null) return '—'
  return n.toFixed(decimals)
}

function fmtPrice(n: number | undefined): string {
  if (n === undefined || n === null) return '—'
  return `₨${n.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

interface TechnicalCardProps {
  data: TechnicalResponse
  className?: string
}

export function TechnicalCard({ data, className }: TechnicalCardProps) {
  if (data.insufficient_data) {
    return (
      <CardShell eyebrow="Technical Analysis" accentColor={ACCENT} className={className}>
        <p className="text-[14px] text-ink-faint">
          Insufficient price history for technical analysis (fewer than 30 bars).
        </p>
      </CardShell>
    )
  }

  const macdBullish = data.macd !== undefined && data.macd_signal !== undefined
    ? data.macd > data.macd_signal
    : undefined

  const crossoverVariant =
    data.crossover === 'golden_cross' ? 'gain' :
    data.crossover === 'death_cross' ? 'loss' :
    'neutral'

  const crossoverLabel =
    data.crossover === 'golden_cross' ? 'Golden cross' :
    data.crossover === 'death_cross' ? 'Death cross' :
    'No cross'

  const conflicting = data.rsi !== undefined && data.macd !== undefined && data.macd_signal !== undefined
    && data.rsi > 70 && data.macd > data.macd_signal

  return (
    <CardShell eyebrow="Technical Analysis" accentColor={ACCENT} className={className}>
      <div className="flex gap-4 items-start mb-4">
        {/* RSI gauge */}
        {data.rsi !== undefined && (
          <div className="shrink-0">
            <RSIGauge value={data.rsi} />
          </div>
        )}

        {/* Compact indicator row */}
        <div className="flex flex-col gap-2 pt-1">
          {macdBullish !== undefined && (
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] text-ink-soft">MACD</span>
              <Badge variant={macdBullish ? 'gain' : 'loss'}>
                {macdBullish ? '↑ Bullish' : '↓ Bearish'}
              </Badge>
            </div>
          )}
          {data.mfi !== undefined && (
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] text-ink-soft">MFI</span>
              <span className="font-mono text-[13px] text-ink tabular-nums">{fmt(data.mfi, 1)}</span>
            </div>
          )}
          {data.sma_20 !== undefined && (
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] text-ink-soft">SMA 20/50/200</span>
              <span className="font-mono text-[12px] text-ink-faint tabular-nums">
                {fmt(data.sma_20, 0)} / {fmt(data.sma_50, 0)} / {fmt(data.sma_200, 0)}
              </span>
            </div>
          )}
          {/* Crossover */}
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] text-ink-soft">MA signal</span>
            <Badge variant={crossoverVariant}>{crossoverLabel}</Badge>
          </div>
        </div>
      </div>

      {/* Conflicting signals — shown without resolution (color + text, never color alone) */}
      {conflicting && (
        <div className="flex gap-2 flex-wrap mb-3">
          <span className="font-mono text-[11px] px-2.5 py-1 rounded-[6px] bg-loss-soft text-loss">
            RSI overbought
          </span>
          <span className="font-mono text-[11px] px-2.5 py-1 rounded-[6px] bg-jade-soft text-gain">
            MACD bullish
          </span>
          {data.crossover === 'golden_cross' && (
            <span className="font-mono text-[11px] px-2.5 py-1 rounded-[6px] bg-gold-soft text-gold">
              Golden cross
            </span>
          )}
        </div>
      )}

      {/* Support / Resistance */}
      {(data.support !== undefined || data.resistance !== undefined) && (
        <div className="flex gap-4 font-mono text-[13px] text-ink-faint">
          <span>S: {fmtPrice(data.support)}</span>
          <span>R: {fmtPrice(data.resistance)}</span>
        </div>
      )}

      <p className="text-[11px] text-ink-faint mt-4 leading-[1.4]">
        Based on daily EOD data. Not a prediction or financial advice.
      </p>
    </CardShell>
  )
}
