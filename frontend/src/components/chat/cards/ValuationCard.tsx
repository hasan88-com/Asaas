import { CardShell } from './CardShell'
import { MonteCarloRange } from '@/components/charts/MonteCarloRange'
import type { ValuationResponse, DurationResult } from '@/types/api'
import { cn } from '@/lib/utils'

const ACCENT = '#2F4858'

function MultiplesCell({ label, value, peer }: { label: string; value?: string; peer?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">{label}</span>
      <span className="font-mono text-[16px] font-medium text-ink tabular-nums">{value ?? '—'}</span>
      {peer && (
        <span className="font-mono text-[11px] text-ink-faint">peer: {peer}</span>
      )}
    </div>
  )
}

interface ValuationCardProps {
  data: ValuationResponse
  className?: string
}

function Metric({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">{label}</span>
      <span className="font-mono text-[16px] font-medium text-ink tabular-nums">
        {value ? `₨${parseFloat(value).toLocaleString('en-PK', { maximumFractionDigits: 2 })}` : '—'}
      </span>
    </div>
  )
}

/** Interest-rate risk panel for fixed income (shown for both real-YTM and the
 *  zero-coupon T-bill case where duration ≈ time to maturity). */
function DurationPanel({ d }: { d: DurationResult }) {
  const rs = (v: string) => `₨${parseFloat(v).toLocaleString('en-PK', { maximumFractionDigits: 0 })}`
  const cell = (label: string, value: string, span2 = false) => (
    <div className={cn('flex flex-col gap-0.5', span2 && 'col-span-2')}>
      <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">{label}</span>
      <span className="font-mono text-[15px] font-medium text-ink tabular-nums">{value}</span>
    </div>
  )
  return (
    <div className="mt-4 pt-3 border-t border-line-soft">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint mb-2">Interest-rate risk</p>
      <div className="grid grid-cols-3 gap-3">
        {cell('Modified duration', `${parseFloat(d.modified_years).toFixed(2)} yr`)}
        {cell('Macaulay duration', `${parseFloat(d.macaulay_years).toFixed(2)} yr`)}
        {cell('Convexity', parseFloat(d.convexity).toFixed(2))}
        {cell('DV01', rs(d.dv01))}
        {cell('Price move per ±100 bps', `≈ ${rs(d.price_change_per_100bps)}`, true)}
      </div>
      <p className="font-mono text-[10px] text-ink-faint mt-2">
        DV01 = rupee P&amp;L per 1 bp move on face value; modified = Macaulay ÷ (1 + y).
      </p>
    </div>
  )
}

export function ValuationCard({ data, className }: ValuationCardProps) {
  const dcfMissing = data.dcf.insufficient_data
  const mcMissing = data.monte_carlo.insufficient_data
  const bothMissing = dcfMissing && mcMissing

  const currentPrice = data.company_info.current_price
    ? parseFloat(data.company_info.current_price)
    : undefined

  // ---- Crypto / commodity → market-price comparison ----------------------
  if (data.method === 'market_comparison') {
    const mc = data.market_comparison
    return (
      <CardShell eyebrow="Valuation — Market comparison" accentColor={ACCENT} className={className}>
        <div className="mb-4">
          <p className="font-sans font-semibold text-[16px] text-ink">{data.company_info.name || data.symbol}</p>
        </div>
        {!mc || mc.insufficient_data ? (
          <p className="text-[13px] text-ink-faint">{mc?.reason ?? 'Insufficient price history for a market comparison.'}</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3">
              <Metric label="Current" value={mc.current_price} />
              <Metric label="30-day avg" value={mc.sma_30} />
              <Metric label="90-day avg" value={mc.sma_90} />
              <Metric label="52-wk high" value={mc.high_52w} />
              <Metric label="52-wk low" value={mc.low_52w} />
              <div className="flex flex-col gap-0.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">52-wk position</span>
                <span className="font-mono text-[16px] font-medium text-ink tabular-nums">
                  {mc.range_position_pct ? `${parseFloat(mc.range_position_pct).toFixed(0)}%` : '—'}
                </span>
              </div>
            </div>
          </>
        )}
        <p className="text-[11px] text-ink-faint mt-4 leading-[1.4]">
          For informational purposes only. Not a buy, sell, or hold recommendation.
        </p>
      </CardShell>
    )
  }

  // ---- T-bill / bond → yield-to-maturity ---------------------------------
  if (data.method === 'yield_to_maturity') {
    const fi = data.fixed_income
    const fmtRs = (v?: string | null) =>
      v != null ? `₨${parseFloat(v).toLocaleString('en-PK', { maximumFractionDigits: 0 })}` : '—'

    // Honest fallback when no real coupon is available.
    if (!fi || fi.insufficient_data) {
      return (
        <CardShell eyebrow="Valuation — Yield to maturity" accentColor={ACCENT} className={className}>
          <div className="mb-4">
            <p className="font-sans font-semibold text-[16px] text-ink">{data.symbol}</p>
          </div>
          {fi?.benchmark_yield && (
            <div className="mb-3">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint mb-1">Benchmark yield (SBP policy rate)</p>
              <span className="font-display text-[34px] font-semibold leading-[1.1] text-ink">{parseFloat(fi.benchmark_yield).toFixed(2)}%</span>
            </div>
          )}
          {fi?.duration && <DurationPanel d={fi.duration} />}
          {fi?.reason && <p className="text-[12px] text-ink-faint leading-[1.4] mt-3">{fi.reason}</p>}
        </CardShell>
      )
    }

    const above = fi.verdict === 'above_market'
    const below = fi.verdict === 'below_market'
    const spread = fi.spread_bps ?? 0
    const held = fi.days_held ?? 0
    const remaining = fi.days_remaining ?? 0
    const total = held + remaining
    const progress = total > 0 ? Math.min(100, Math.round((held / total) * 100)) : 0

    return (
      <CardShell eyebrow="Valuation — Yield to maturity" accentColor={ACCENT} className={className}>
        <div className="mb-4">
          <p className="font-sans font-semibold text-[16px] text-ink">{data.symbol}</p>
        </div>

        {fi.risk_free_is_placeholder && (
          <div className="mb-3 rounded-[8px] bg-gold-soft border border-gold/40 px-3 py-2 text-[12px] text-ink-soft leading-[1.4]">
            SBP policy rate unavailable (no live, cached, or last-known-good value) — the spread below uses a placeholder and is unreliable.
          </div>
        )}

        {/* Locked yield vs SBP, with spread badge */}
        <div className="flex items-end justify-between gap-3 mb-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint mb-1">Locked yield (YTM)</p>
            <span className="font-display text-[34px] font-semibold leading-[1.1] text-ink">{fi.ytm ? `${parseFloat(fi.ytm).toFixed(2)}%` : '—'}</span>
            {fi.sbp_rate && (
              <p className="text-[12px] text-ink-faint mt-0.5">vs {parseFloat(fi.sbp_rate).toFixed(2)}% current SBP rate</p>
            )}
          </div>
          <span
            className={cn(
              'font-mono text-[12px] font-semibold px-2 py-1 rounded-full',
              above ? 'bg-gain/15 text-gain' : below ? 'bg-loss/15 text-loss' : 'bg-line text-ink-soft',
            )}
          >
            {spread >= 0 ? '+' : ''}{spread} bps
          </span>
        </div>

        {/* Accrued / remaining */}
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-line-soft">
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Face value</span>
            <span className="font-mono text-[15px] font-medium text-ink tabular-nums">{fmtRs(fi.face_value)}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Accrued value</span>
            <span className="font-mono text-[15px] font-medium text-ink tabular-nums">{fmtRs(fi.accrued_value)}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint">Remaining return</span>
            <span className="font-mono text-[15px] font-medium text-gain tabular-nums">{fmtRs(fi.remaining_return)}</span>
          </div>
        </div>

        {/* Days held / remaining progress */}
        {total > 0 && (
          <div className="mt-4">
            <div className="flex justify-between font-mono text-[11px] text-ink-faint mb-1">
              <span>{held}d held</span>
              <span>{remaining}d to maturity</span>
            </div>
            <div className="h-2 rounded-full bg-line overflow-hidden">
              <div className="h-full bg-jade rounded-full" style={{ width: `${progress}%` }} />
            </div>
            {fi.maturity_date && (
              <p className="font-mono text-[11px] text-ink-faint mt-1">Matures {fi.maturity_date}</p>
            )}
          </div>
        )}

        {/* Interest-rate risk: duration / DV01 / convexity */}
        {fi.duration && <DurationPanel d={fi.duration} />}

        {/* Verdict */}
        <div
          className={cn(
            'mt-4 rounded-[8px] px-3 py-2.5 text-[13px] font-sans',
            above ? 'bg-gain/10 text-gain' : below ? 'bg-loss/10 text-loss' : 'bg-paper text-ink-soft',
          )}
        >
          {above
            ? 'You locked in an above-market rate — hold to maturity.'
            : below
              ? 'Current market offers better rates — consider reinvesting at maturity.'
              : 'Your locked rate matches the current market.'}
        </div>

        <p className="text-[11px] text-ink-faint mt-4 leading-[1.4]">
          Data: {fi.source ?? 'PSX Debt Market'}. For informational purposes only.
        </p>
      </CardShell>
    )
  }

  return (
    <CardShell eyebrow="Valuation" accentColor={ACCENT} className={className}>
      {/* Company header */}
      <div className="mb-4">
        <p className="font-sans font-semibold text-[16px] text-ink">{data.company_info.name}</p>
        {data.company_info.sector && (
          <p className="text-[13px] text-ink-faint">{data.company_info.sector}</p>
        )}
      </div>

      {bothMissing ? (
        <p className="text-[12px] text-ink-faint mb-4">
          Insufficient cash-flow history for DCF &amp; Monte Carlo. Multiples only.
        </p>
      ) : (
        <>
          {/* DCF intrinsic value */}
          {!dcfMissing && data.dcf.intrinsic_value_per_share && (
            <div className="mb-4">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint mb-1">
                DCF intrinsic value
              </p>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-[34px] font-semibold leading-[1.1] text-ink">
                  ₨{parseFloat(data.dcf.intrinsic_value_per_share).toLocaleString('en-PK', { maximumFractionDigits: 2 })}
                </span>
                {currentPrice && (
                  <span className="font-mono text-[13px] text-ink-faint">
                    vs ₨{currentPrice.toLocaleString('en-PK', { maximumFractionDigits: 2 })} current
                  </span>
                )}
              </div>
              {data.dcf.wacc && (
                <p className="text-[12px] text-ink-faint mt-0.5">
                  WACC {(parseFloat(data.dcf.wacc) * 100).toFixed(1)}% (risk-free = SBP rate)
                </p>
              )}
              {data.dcf.risk_free_is_placeholder && (
                <p className="text-[12px] text-loss mt-0.5 leading-[1.4]">
                  ⚠ SBP risk-free rate unavailable — WACC uses a placeholder; treat this valuation as unreliable.
                </p>
              )}
            </div>
          )}

          {/* Monte Carlo range */}
          {!mcMissing && data.monte_carlo.p10 && data.monte_carlo.p50 && data.monte_carlo.p90 && (
            <div className="mb-4">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint mb-2">
                Monte Carlo range ({data.monte_carlo.num_simulations?.toLocaleString()} sims)
              </p>
              <MonteCarloRange
                p10={parseFloat(data.monte_carlo.p10)}
                p50={parseFloat(data.monte_carlo.p50)}
                p90={parseFloat(data.monte_carlo.p90)}
                current={currentPrice}
              />
            </div>
          )}
        </>
      )}

      {/* Multiples */}
      <div className={cn('grid grid-cols-3 gap-3 pt-3 border-t border-line-soft')}>
        <MultiplesCell
          label="P/E"
          value={data.multiples.pe_ratio}
          peer={data.multiples.peer_pe_median}
        />
        <MultiplesCell
          label="EV/EBITDA"
          value={data.multiples.ev_ebitda}
          peer={data.multiples.peer_ev_ebitda_median}
        />
        <MultiplesCell label="P/B" value={data.multiples.pb_ratio} />
      </div>

      <p className="text-[11px] text-ink-faint mt-4 leading-[1.4]">
        For informational purposes only. Not a buy, sell, or hold recommendation.
      </p>
    </CardShell>
  )
}
