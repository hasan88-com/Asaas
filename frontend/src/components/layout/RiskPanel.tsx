import { useEffect, useState } from 'react'
import { getRiskMetrics } from '@/lib/api'
import type { RiskMetricsResponse } from '@/types/api'

const pct = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const num = (v?: number | null) => (v == null ? '—' : v.toFixed(2))

/**
 * Dashboard "Risk" card — VaR / max drawdown / rolling Sharpe / beta from the
 * backfilled price history (/portfolio/risk). Renders nothing until there's
 * enough overlapping history. Read-only; mirrors MarketSentimentGauge.
 */
export function RiskPanel() {
  const [data, setData] = useState<RiskMetricsResponse | null>(null)

  useEffect(() => {
    getRiskMetrics().then(setData).catch(() => {})
  }, [])

  if (!data || data.insufficient_data) return null

  const rows: { label: string; value: string; tone?: 'loss' }[] = [
    { label: 'VaR 95% (1d)', value: pct(data.var_95?.value), tone: 'loss' },
    { label: 'VaR 99% (1d)', value: pct(data.var_99?.value), tone: 'loss' },
    { label: 'CVaR 95%', value: pct(data.cvar_95?.value), tone: 'loss' },
    { label: 'Max drawdown', value: pct(data.max_drawdown?.value), tone: 'loss' },
    { label: 'Volatility (30d)', value: pct(data.rolling_vol_30?.value) },
    { label: 'Sharpe (30d)', value: num(data.rolling_sharpe_30?.value) },
    { label: 'Sortino', value: num(data.sortino?.value) },
    { label: 'Beta (vs PSX)', value: num(data.beta_vs_kse_proxy?.value) },
  ]

  return (
    <div className="bg-card border border-line rounded-[10px] p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">Risk</p>
      <div className="flex flex-col gap-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between">
            <span className="font-sans text-[12px] text-ink-soft">{r.label}</span>
            <span className={`font-mono text-[13px] tabular-nums ${r.tone === 'loss' ? 'text-loss' : 'text-ink'}`}>
              {r.value}
            </span>
          </div>
        ))}
      </div>
      {data.as_of && (
        <p className="font-mono text-[10px] text-ink-faint mt-3">
          {data.observations ?? 0} obs · as of {data.as_of}
        </p>
      )}
    </div>
  )
}
