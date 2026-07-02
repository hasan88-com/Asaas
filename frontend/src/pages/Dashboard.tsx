import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Info } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import {
  getPortfolio,
  getPerformance,
  getNewsFeed,
  getFlags,
  getProfile,
} from '@/lib/api'
import { PerformanceLine } from '@/components/charts/PerformanceLine'
import { AllocationDonut } from '@/components/charts/AllocationDonut'
import { FlagCard } from '@/components/layout/FlagCard'
import { MyActivity } from '@/components/layout/MyActivity'
import { WalletCard } from '@/components/layout/WalletCard'
import { MarketSentimentGauge } from '@/components/layout/MarketSentimentGauge'
import { RiskPanel } from '@/components/layout/RiskPanel'
import { cn } from '@/lib/utils'
import type {
  PortfolioResponse,
  PortfolioRecommendationResponse,
  PerformanceResponse,
  NewsItemResponse,
  FlagResponse,
} from '@/types/api'

/* ─── module-level cache — survives navigation, cleared on hard refresh ── */

interface DashCache {
  portfolio: PortfolioResponse | null
  recommendation: PortfolioRecommendationResponse | null
  perf: PerformanceResponse | null
  news: NewsItemResponse[]
  flags: FlagResponse[]
}
let _cache: DashCache | null = null

/* ─── helpers ─────────────────────────────────────────────────────────── */

const IMPACT_SYMBOL: Record<string, string> = { positive: '↑', negative: '↓', neutral: '→' }

function formatPkr(n: number): string {
  if (n >= 1_000_000_000_000) return `₨${(n / 1_000_000_000_000).toFixed(2)}T`
  if (n >= 1_000_000_000) return `₨${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000) return `₨${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `₨${(n / 1_000).toFixed(0)}K`
  return `₨${n.toFixed(0)}`
}

/** Full rupee amount with thousands separators (no K/M abbreviation). */
function formatPkrFull(n: number): string {
  return `₨${n.toLocaleString('en-PK', { maximumFractionDigits: 0 })}`
}

/* ─── sub-components ──────────────────────────────────────────────────── */

function Skel({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded-[6px]', className)} />
}

function StatCell({
  label, value, positive, sub, info,
}: {
  label: string; value: string; positive?: boolean; sub?: string; info?: string
}) {
  return (
    <div className="bg-card border border-line rounded-[10px] p-4 flex flex-col gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint flex items-center gap-1">
        {label}
        {info && (
          <span className="tooltip-trigger inline-flex" tabIndex={0} aria-label={info}>
            <Info size={11} className="text-ink-faint/70 hover:text-ink-soft cursor-help" />
            <span className="tooltip-content normal-case tracking-normal font-sans">{info}</span>
          </span>
        )}
      </span>
      <span className={cn(
        'font-mono text-[18px] font-medium tabular-nums',
        positive === true ? 'text-gain' : positive === false ? 'text-loss' : 'text-ink',
      )}>{value}</span>
      {sub && <span className="font-mono text-[10px] text-ink-faint">{sub}</span>}
    </div>
  )
}

type TimeRange = '1d' | '1w' | '1m' | '6m' | '1y'
const TIME_RANGES: TimeRange[] = ['1d', '1w', '1m', '6m', '1y']

/* ─── Dashboard ───────────────────────────────────────────────────────── */

export default function Dashboard() {
  const navigate = useNavigate()
  const { loading: authLoading } = useAuth()

  // Seed state from module cache so back-navigation is instant (no skeleton flash)
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(_cache?.portfolio ?? null)
  const [perf, setPerf] = useState<PerformanceResponse | null>(_cache?.perf ?? null)
  const [news, setNews] = useState<NewsItemResponse[]>(_cache?.news ?? [])
  const [flags, setFlags] = useState<FlagResponse[]>(_cache?.flags ?? [])
  // Per-section readiness — each section renders the moment its own call
  // resolves, so a slow /performance never hides an already-loaded holdings list.
  const seeded = _cache !== null
  const [portfolioReady, setPortfolioReady] = useState(seeded)
  const [perfReady, setPerfReady] = useState(seeded)
  const [newsReady, setNewsReady] = useState(seeded)
  const [flagsReady, setFlagsReady] = useState(seeded)
  const [timeRange, setTimeRange] = useState<TimeRange>('1m')
  // Distinguishes a transient load failure (server briefly unreachable) from
  // genuinely having no portfolio — so a 500/network blip never shows the
  // "Build your first portfolio" empty state.
  const [loadError, setLoadError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [walletRefreshKey, setWalletRefreshKey] = useState(0)

  useEffect(() => {
    if (authLoading) return   // wait for Supabase session to settle

    let cancelled = false

    // Each call resolves independently and flips only its own section's
    // readiness — no single gate behind all four. A mutable cache object is
    // updated in place so back-navigation still skips skeletons.
    function load() {
      const cache: DashCache = _cache ?? {
        portfolio: null, recommendation: null, perf: null, news: [], flags: [],
      }
      _cache = cache

      getPortfolio()
        .then((p) => {
          if (cancelled) return
          setPortfolio(p); cache.portfolio = p; setLoadError(false); setPortfolioReady(true)
        })
        .catch(async (err) => {
          if (cancelled) return
          const e = err as { status?: number }
          // 404 = genuinely no active portfolio → onboarding.
          if (e?.status === 404) {
            try {
              await getProfile()
              if (!cancelled) navigate('/onboarding/suggest', { replace: true })
            } catch {
              if (!cancelled) navigate('/onboarding', { replace: true })
            }
            return
          }
          // Any other error (500 / network / timeout) is transient — the
          // portfolio still exists. Keep any cached one and show a retry state
          // instead of the misleading "Build your first portfolio" empty state.
          if (!cancelled) { setLoadError(true); setPortfolioReady(true) }
        })

      getPerformance()
        .then((pf) => {
          if (cancelled) return
          setPerf(pf); cache.perf = pf; setPerfReady(true)
          // Stale-while-revalidate: the snapshot fast path lacks per-holding
          // figures, so re-fetch the live version and flip when it arrives.
          if (pf.stale) {
            getPerformance({ live: true })
              .then((live) => { if (!cancelled) { setPerf(live); cache.perf = live } })
              .catch(() => { /* keep the stale snapshot values */ })
          }
        })
        .catch(() => { if (!cancelled) setPerfReady(true) })

      getNewsFeed()
        .then((n) => { if (!cancelled) { setNews(n); cache.news = n; setNewsReady(true) } })
        .catch(() => { if (!cancelled) setNewsReady(true) })

      getFlags()
        .then((f) => { if (!cancelled) { setFlags(f); cache.flags = f } })
        .catch(() => { /* keep cached flags */ })
        .finally(() => { if (!cancelled) setFlagsReady(true) })
    }

    load()
    return () => { cancelled = true }
  }, [authLoading, reloadKey])

  // Re-fetch portfolio + performance after a portfolio-activity change.
  // Use live=true so the user sees accurate post-change figures (incl. per-holding).
  async function refresh() {
    setWalletRefreshKey((k) => k + 1) // buys/sells move cash
    const [p, pf] = await Promise.allSettled([getPortfolio(), getPerformance({ live: true })])
    if (p.status === 'fulfilled') setPortfolio(p.value)
    if (pf.status === 'fulfilled') setPerf(pf.value)
    _cache = {
      portfolio: p.status === 'fulfilled' ? p.value : (_cache?.portfolio ?? null),
      recommendation: _cache?.recommendation ?? null,
      perf: pf.status === 'fulfilled' ? pf.value : (_cache?.perf ?? null),
      news: _cache?.news ?? [],
      flags: _cache?.flags ?? [],
    }
  }

  /* derived */
  const pnlAbs = perf?.pnl_absolute && perf.pnl_absolute !== '0'
    ? parseFloat(perf.pnl_absolute) : null
  const pnlPct = perf?.pnl_percent && perf.pnl_percent !== '0'
    ? parseFloat(perf.pnl_percent) : null
  const isGain = pnlAbs !== null && pnlAbs >= 0
  const activeFlags = flags.filter((f) => !f.dismissed)
  const riskPct = portfolio ? Math.min(parseFloat(portfolio.expected_risk) * 100, 100) : 0
  const totalValue = perf?.total_value ? parseFloat(perf.total_value) : null
  const invested = perf?.total_cost ? parseFloat(perf.total_cost) : null

  // Filter the real snapshot history to the selected range. Falls back to the
  // full series when the window has too few points (e.g. a young portfolio), so
  // the chart is never blank.
  const visibleHistory = useMemo(() => {
    const hist = perf?.history ?? []
    if (hist.length === 0) return hist
    const days: Record<TimeRange, number> = { '1d': 1, '1w': 7, '1m': 30, '6m': 180, '1y': 365 }
    const cutoff = Date.now() - days[timeRange] * 86_400_000
    const windowed = hist.filter((h) => new Date(h.date).getTime() >= cutoff)
    return windowed.length >= 2 ? windowed : hist
  }, [perf, timeRange])

  /* ── render ── */
  return (
    <div className="flex flex-col gap-6 pb-20 md:pb-6">

      {/* ── Hero ── */}
      <section className="flex flex-col gap-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Portfolio</p>

        {!portfolioReady ? (
          /* loading: show inline skeleton for the value only */
          <Skel className="h-11 w-52 mt-1" />
        ) : portfolio ? (
          <div className="flex flex-col gap-2.5">
            <span className="font-sans text-[13px] text-ink-soft">
              {portfolio.name || `${portfolio.holdings.length} holdings`}
            </span>

            {/* Current Value */}
            <div className="flex flex-col gap-0.5">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Current Value</span>
              <p className="font-display text-[40px] leading-[1] font-semibold text-ink tabular-nums">
                {totalValue !== null ? (
                  <>
                    {formatPkrFull(totalValue)}{' '}
                    <span className="font-mono text-[14px] text-ink-faint font-normal">PKR</span>
                  </>
                ) : (perfReady ? '—' : '…')}
              </p>
            </div>

            {/* Clearly-labelled stat rows */}
            <div className="flex flex-col gap-1.5 max-w-xs">
              {pnlAbs !== null && pnlPct !== null && (
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-sans text-[12px] text-ink-soft">Total Gain / Loss (all-time)</span>
                  <span className={cn('font-mono text-[13px] tabular-nums font-medium', isGain ? 'text-gain' : 'text-loss')}>
                    {isGain ? '▲' : '▼'} {formatPkrFull(Math.abs(pnlAbs))} ({isGain ? '+' : ''}{(pnlPct * 100).toFixed(2)}%)
                  </span>
                </div>
              )}
              {invested !== null && (
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-sans text-[12px] text-ink-soft">Total Invested</span>
                  <span className="font-mono text-[13px] tabular-nums text-ink">{formatPkrFull(invested)}</span>
                </div>
              )}
            </div>
          </div>
        ) : loadError ? (
          <div className="flex flex-col gap-2">
            <p className="font-sans text-[14px] text-loss">
              Couldn't load your portfolio — the server was briefly unreachable. Your portfolio is safe.
            </p>
            <button
              type="button"
              onClick={() => { setLoadError(false); setPortfolioReady(false); setReloadKey((k) => k + 1) }}
              className="self-start font-mono text-[12px] text-jade hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
            >
              ↻ Retry
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="font-sans text-[14px] text-ink-faint">
              No portfolio yet.{' '}
              <button
                type="button"
                onClick={() => navigate('/onboarding')}
                className="text-jade hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
              >
                Build your first portfolio
              </button>
            </p>
          </div>
        )}

        {portfolio && (
          <p className="font-mono text-[11px] text-ink-faint mt-1">
            Valued as of {new Date().toLocaleDateString('en-PK', { month: 'short', day: 'numeric', year: 'numeric' })} (today's prices)
          </p>
        )}
      </section>

      {/* ── 2-column grid ── */}
      <div className="flex flex-col gap-5 lg:grid lg:grid-cols-[1fr_300px] lg:gap-6">

        {/* LEFT */}
        <div className="flex flex-col gap-5">

          {/* Performance chart card — always rendered */}
          <div className="bg-card border border-line rounded-[10px] p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Performance</p>
              <div className="flex gap-1">
                {TIME_RANGES.map((tr) => (
                  <button
                    key={tr}
                    type="button"
                    onClick={() => setTimeRange(tr)}
                    className={cn(
                      'px-2.5 py-1 rounded font-mono text-[10px] uppercase tracking-[0.1em] transition-all duration-150 btn-press',
                      timeRange === tr ? 'bg-jade text-white' : 'text-ink-faint hover:text-ink hover:bg-line-soft',
                    )}
                  >
                    {tr}
                  </button>
                ))}
              </div>
            </div>

            {!perfReady ? (
              <Skel className="h-[260px] w-full" />
            ) : visibleHistory.length > 1 ? (
              <PerformanceLine history={visibleHistory} height={260} lineColor="#0F6E56" />
            ) : (
              <div className="flex items-center justify-center" style={{ height: 260 }}>
                <p className="font-mono text-[12px] text-ink-faint text-center">
                  {perf && perf.history.length > 0
                    ? 'Building history — your portfolio value is snapshotted daily.'
                    : 'No performance data yet'}
                </p>
              </div>
            )}
          </div>

          {/* Stats row — always rendered; values fill in when ready */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCell
              label="Total P&L"
              value={!perfReady ? '—' : pnlAbs !== null ? formatPkr(pnlAbs) : '—'}
              positive={perfReady && pnlAbs !== null ? isGain : undefined}
            />
            <StatCell
              label="Return"
              value={!perfReady ? '—' : pnlPct !== null ? `${pnlPct >= 0 ? '+' : ''}${(pnlPct * 100).toFixed(2)}%` : '—'}
              positive={perfReady && pnlPct !== null ? pnlPct >= 0 : undefined}
            />
            <StatCell
              label="Expected p.a."
              value={!portfolioReady ? '—' : portfolio ? `${(parseFloat(portfolio.expected_return) * 100).toFixed(1)}%` : '—'}
              positive={portfolioReady && portfolio ? parseFloat(portfolio.expected_return) > 0 : undefined}
              sub={portfolio?.risk_free_rate ? `SBP ${(parseFloat(portfolio.risk_free_rate) * 100).toFixed(2)}%` : undefined}
              info={'Expected return per annum (per year). The MPT optimiser estimates this from each holding’s historical returns and its weight in your portfolio. It is a forward-looking estimate, not a guarantee, and is shown against the SBP risk-free rate.'}
            />
            <StatCell
              label="Sharpe"
              value={!portfolioReady ? '—' : portfolio ? parseFloat(portfolio.sharpe).toFixed(2) : '—'}
              positive={portfolioReady && portfolio ? parseFloat(portfolio.sharpe) > 1 : undefined}
              info={'Sharpe ratio: return earned above the SBP risk-free rate per unit of risk (volatility). Higher is better — above 1 is generally considered good.'}
            />
          </div>

          {/* Holdings list */}
          {portfolioReady && portfolio && portfolio.holdings.length > 0 && (
            <div className="bg-card border border-line rounded-[10px] overflow-hidden">
              <div className="px-5 py-3 border-b border-line">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Holdings</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-line text-ink-faint">
                      <th className="text-left  font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-4 py-2">Symbol</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-3 py-2">Qty</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-3 py-2">Price</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-3 py-2">Value</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-3 py-2">Invested</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-3 py-2">P&amp;L</th>
                      <th className="text-right font-mono text-[10px] uppercase tracking-[0.1em] font-medium px-4 py-2">Wt</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line-soft">
                    {portfolio.holdings.slice(0, 8).map((h) => {
                      const hPerf = perf?.holdings_performance?.find((p) => p.symbol === h.symbol)
                      const qty = h.quantity ?? (hPerf?.quantity ? parseFloat(hPerf.quantity) : undefined)
                      const px = hPerf?.current_price ? parseFloat(hPerf.current_price) : undefined
                      const entry = hPerf?.entry_price ? parseFloat(hPerf.entry_price) : (h.entry_price ?? undefined)
                      // Value computed client-side so it never shows "—" when a price exists.
                      const value = qty != null && (px ?? entry) != null ? qty * (px ?? entry)! : undefined
                      const invested = qty != null && entry != null ? qty * entry : undefined
                      const pnl = hPerf && !hPerf.stale ? parseFloat(hPerf.pnl_pct) : undefined
                      const numFmt = (n?: number, d = 2) => n == null ? '—' : n.toLocaleString('en-PK', { maximumFractionDigits: d })
                      // Quantity: 2 dp for whole-unit holdings (stocks, debt),
                      // but keep meaningful digits for fractional crypto/commodity
                      // (e.g. 0.000107 BTC) which 2 dp would collapse to "0".
                      const fmtQty = (n?: number) =>
                        n == null ? '—'
                          : Math.abs(n) >= 1
                            ? n.toLocaleString('en-PK', { maximumFractionDigits: 2 })
                            : n.toLocaleString('en-PK', { maximumFractionDigits: 6 })
                      return (
                        <tr
                          key={h.symbol ?? h.instrument_id}
                          className={cn('text-ink', h.symbol && 'cursor-pointer hover:bg-jade-soft/40 transition-colors')}
                          onClick={() => { if (h.symbol) navigate(`/holdings/${h.symbol}`) }}
                        >
                          <td className="px-4 py-2.5">
                            <div className="flex flex-col">
                              <span className="font-mono text-[13px] font-semibold leading-tight">{h.symbol}</span>
                              <span className="font-sans text-[10px] text-ink-faint truncate max-w-[140px]">{h.name}</span>
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono text-[12px] tabular-nums">{fmtQty(qty)}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-[12px] tabular-nums">{numFmt(px ?? entry)}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-[12px] tabular-nums font-medium">{value == null ? '—' : formatPkr(value)}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-[12px] tabular-nums text-ink-soft">{invested == null ? '—' : formatPkr(invested)}</td>
                          <td className={cn('px-3 py-2.5 text-right font-mono text-[12px] tabular-nums', pnl == null ? 'text-ink-faint' : pnl >= 0 ? 'text-gain' : 'text-loss')}>
                            {pnl == null ? '—' : `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-[12px] tabular-nums">{(h.weight * 100).toFixed(1)}%</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {portfolio.holdings.length > 8 && (
                  <button
                    type="button"
                    className="w-full px-5 py-2.5 text-center font-mono text-[11px] text-jade hover:bg-jade-soft/40 transition-colors"
                    onClick={() => navigate('/portfolio')}
                  >
                    View all {portfolio.holdings.length} holdings →
                  </button>
                )}
              </div>
            </div>
          )}

          {/* My Activity — buy / sell / update holdings */}
          {portfolioReady && portfolio && portfolio.holdings.length > 0 && (
            <MyActivity holdings={portfolio.holdings} onChanged={refresh} />
          )}
        </div>

        {/* RIGHT sidebar — always rendered */}
        <aside className="flex flex-col gap-5">

          {/* Cash wallet — virtual PKR balance */}
          <WalletCard refreshKey={walletRefreshKey} />

          {/* Risk Score */}
          <div className="bg-card border border-line rounded-[10px] p-5">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">Risk Score</p>
            {!portfolioReady ? (
              <Skel className="h-9 w-20 mb-2" />
            ) : (
              <div className="flex items-end gap-3 mb-2">
                <span className="font-display text-[34px] leading-[1] font-semibold text-ink tabular-nums">
                  {portfolio ? Math.round(riskPct) : '—'}
                </span>
                <span className="font-mono text-[11px] text-ink-faint mb-1">/ 100</span>
              </div>
            )}
            <div className="w-full h-2 bg-line-soft rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-jade rounded-full transition-all duration-700"
                style={{ width: portfolioReady ? `${riskPct}%` : '0%' }}
              />
            </div>
            <button
              type="button"
              onClick={() => navigate('/chat', { state: { seedMessage: 'Why is my risk score what it is? Explain the factors.' } })}
              className="font-mono text-[11px] text-jade hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
            >
              Why this score? Ask the agent →
            </button>
          </div>

          {/* Market sentiment (renders only when a snapshot exists) */}
          <MarketSentimentGauge />

          {/* Risk analytics (renders only when enough price history exists) */}
          <RiskPanel />

          {/* Active alerts */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Alerts</p>
              {activeFlags.length > 2 && (
                <a href="/flags" className="font-mono text-[11px] text-jade hover:underline">
                  View all ({activeFlags.length})
                </a>
              )}
            </div>
            {!flagsReady ? (
              <Skel className="h-16 w-full rounded-[10px]" />
            ) : activeFlags.length === 0 ? (
              <div className="bg-card border border-line rounded-[10px] p-4 text-center">
                <p className="font-sans text-[13px] text-ink-soft">All clear</p>
                <p className="font-sans text-[11px] text-ink-faint mt-0.5">No active alerts</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {activeFlags.slice(0, 2).map((flag) => (
                  <FlagCard
                    key={flag.id}
                    flag={flag}
                    onDismiss={(id) => setFlags((prev) => prev.map((f) => f.id === id ? { ...f, dismissed: true } : f))}
                  />
                ))}
              </div>
            )}
          </div>

          {/* News activity feed */}
          {newsReady && news.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">Activity</p>
                {news.length > 3 && (
                  <a href="/news" className="font-mono text-[11px] text-jade hover:underline">View all</a>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {news.slice(0, 3).map((item, i) => {
                  const mat = item.materiality_score != null
                    ? item.materiality_score > 0.7 ? 'material' : item.materiality_score > 0.4 ? 'review' : 'info'
                    : 'info'
                  return (
                    <a
                      key={i}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cn(
                        'px-4 py-3 flex flex-col gap-1.5 rounded-[10px] border transition-colors',
                        mat === 'material' ? 'bg-jade-soft border-jade/20' : 'bg-card border-line hover:bg-line-soft/40',
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint bg-paper px-1.5 py-0.5 rounded">
                          {item.source}
                        </span>
                        <span className={cn(
                          'font-mono text-[10px] uppercase tracking-[0.08em] px-1.5 py-0.5 rounded',
                          item.impact === 'positive' ? 'text-gain bg-jade-soft'
                            : item.impact === 'negative' ? 'text-loss bg-loss-soft'
                              : 'text-info bg-info-soft',
                        )}>
                          {IMPACT_SYMBOL[item.impact]} {item.impact_level}
                        </span>
                        {mat === 'material' && <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-jade font-semibold">Material</span>}
                        {mat === 'review' && <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-gold font-semibold">Review</span>}
                      </div>
                      <p className="font-sans text-[12px] text-ink leading-[1.4] line-clamp-2">{item.headline}</p>
                    </a>
                  )
                })}
              </div>
            </div>
          )}

          {/* Allocation donut */}
          {portfolioReady && portfolio && portfolio.holdings.length > 0 && (
            <div className="bg-card border border-line rounded-[10px] p-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-4">Allocation</p>
              <div className="flex flex-col items-center gap-4">
                <AllocationDonut
                  holdings={portfolio.holdings}
                  size={140}
                  centerLabel="Total"
                  centerValue={totalValue != null ? formatPkr(totalValue) : undefined}
                />
                <ul className="w-full flex flex-col gap-1.5">
                  {portfolio.holdings.slice(0, 5).map((h) => (
                    <li key={h.symbol ?? h.instrument_id} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-jade shrink-0" aria-hidden />
                      <span className="font-sans text-[12px] text-ink-soft truncate flex-1">{h.name}</span>
                      <span className="font-mono text-[12px] text-ink tabular-nums font-medium shrink-0">
                        {(h.weight * 100).toFixed(1)}%
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
