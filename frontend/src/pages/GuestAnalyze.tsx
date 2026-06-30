import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyzeGuest } from '@/lib/api'
import { OptimizerCard } from '@/components/chat/cards/OptimizerCard'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AssetComboBox } from '@/components/ui/combobox'
import { cn } from '@/lib/utils'
import { ASSET_UNIVERSE } from '@/data/assetUniverse'
import type { GuestAnalyzeResponse, GuestHoldingPayload, HoldingResponse } from '@/types/api'

// ---- Types -----------------------------------------------------------------

type AssetClass = 'equity' | 'tbill' | 'bond' | 'crypto' | 'commodity'

interface HoldingRow {
  id: string
  assetClass: AssetClass
  symbol: string
  qty: string
  units: string
  entry_price: string
  interest_rate: string
  buy_date: string
  errors: Partial<Record<'symbol' | 'qty' | 'units' | 'entry_price' | 'interest_rate' | 'buy_date', string>>
}

// ---- Stable filter constants ------------------------------------------------

const EQUITY_FILTER = ['equity'] as const
const BOND_FILTER = ['tbill', 'bond'] as const
const CRYPTO_FILTER = ['crypto'] as const
const COMMODITY_FILTER = ['commodity'] as const

// ---- Asset class metadata --------------------------------------------------

const ASSET_CLASS_META: Record<AssetClass, { label: string; dot: string }> = {
  equity:    { label: 'Equity (Stocks)', dot: 'bg-jade' },
  tbill:     { label: 'Bond / T-Bill',   dot: 'bg-info' },
  bond:      { label: 'Bond / T-Bill',   dot: 'bg-info' },
  crypto:    { label: 'Crypto',          dot: 'bg-plum' },
  commodity: { label: 'Commodity',       dot: 'bg-gold' },
}

// ---- Per-row completion check (required fields only, class-specific) -------

function isRowComplete(r: HoldingRow): boolean {
  if (!r.symbol.trim()) return false
  const qty = parseFloat(r.qty)
  if (!r.qty || isNaN(qty) || qty <= 0) return false
  const ep = parseFloat(r.entry_price)
  if (!r.entry_price || isNaN(ep) || ep <= 0) return false
  return true
}

// ---- Helper ----------------------------------------------------------------

function newHolding(ac: AssetClass): HoldingRow {
  return {
    id: crypto.randomUUID(),
    assetClass: ac,
    symbol: '',
    qty: '',
    units: '',
    entry_price: '',
    interest_rate: '',
    buy_date: '',
    errors: {},
  }
}

// ---- Main component --------------------------------------------------------

export default function GuestAnalyze() {
  const navigate = useNavigate()
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GuestAnalyzeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rateLimited, setRateLimited] = useState(false)

  // Close picker on Escape or outside click
  useEffect(() => {
    if (!pickerOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setPickerOpen(false) }
    const onMouse = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onMouse)
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onMouse) }
  }, [pickerOpen])

  const updateRow = (id: string, patch: Partial<HoldingRow>) =>
    setHoldings((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)))

  const removeRow = (id: string) => setHoldings((prev) => prev.filter((r) => r.id !== id))

  const addHolding = (ac: AssetClass) => {
    const row = newHolding(ac)
    setHoldings((prev) => [...prev, row])
    setPickerOpen(false)
    setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 50)
  }

  // ---- Validation ----------------------------------------------------------

  const validate = (): boolean => {
    const next = holdings.map((r) => {
      const errs: HoldingRow['errors'] = {}
      if (!r.symbol.trim()) errs.symbol = 'Symbol is required'
      const qty = parseFloat(r.qty)
      if (!r.qty || isNaN(qty) || qty <= 0) errs.qty = 'Enter a positive number'
      const ep = parseFloat(r.entry_price)
      if (!r.entry_price || isNaN(ep) || ep <= 0) errs.entry_price = 'Enter a positive price'
      if (r.assetClass === 'tbill' || r.assetClass === 'bond') {
        const units = parseInt(r.units, 10)
        if (!r.units || isNaN(units) || units <= 0) errs.units = 'Enter a whole number of units'
        if (r.interest_rate) {
          const ir = parseFloat(r.interest_rate)
          if (isNaN(ir) || ir < 0 || ir > 100) errs.interest_rate = 'Rate must be 0–100'
        }
        if (r.buy_date) {
          const d = new Date(r.buy_date)
          if (isNaN(d.getTime())) errs.buy_date = 'Invalid date'
          else if (d > new Date()) errs.buy_date = 'Buy date cannot be in the future'
        }
      }
      return { ...r, errors: errs }
    })
    setHoldings(next)
    return next.every((r) => Object.keys(r.errors).length === 0)
  }

  // ---- Submit --------------------------------------------------------------

  const handleAnalyze = async () => {
    if (!validate()) return
    setError(null)
    setLoading(true)
    try {
      const payload: GuestHoldingPayload[] = holdings.map((r) => ({
        symbol: r.symbol.trim(),
        qty: (r.assetClass === 'tbill' || r.assetClass === 'bond')
          ? parseInt(r.units, 10)
          : parseFloat(r.qty),
        entry_price: parseFloat(r.entry_price),
        asset_class: r.assetClass,
        ...((r.assetClass === 'tbill' || r.assetClass === 'bond') && r.interest_rate
          ? { interest_rate_at_buy: parseFloat(r.interest_rate) }
          : {}),
        ...((r.assetClass === 'tbill' || r.assetClass === 'bond') && r.buy_date
          ? { buy_date: r.buy_date }
          : {}),
      }))
      const data = await analyzeGuest(payload)
      setResult(data)
    } catch (err) {
      const s = (err as { status?: number }).status
      if (s === 429) setRateLimited(true)
      else setError(err instanceof Error ? err.message : 'Analysis failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const anyErrors = holdings.some((r) => Object.values(r.errors).some(Boolean))
  const analyzeDisabled = holdings.length === 0 || anyErrors || loading

  // ---- Shared field styles -------------------------------------------------

  const inputCls = cn(
    'bg-card border border-line rounded-[6px] px-2 py-2 text-[13px] font-mono tabular-nums text-ink w-full',
    'min-h-[40px] focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 transition-colors',
  )
  const labelCls = 'font-sans text-[11px] font-medium text-ink'
  const errorCls = 'font-sans text-[11px] text-loss mt-0.5'

  // ---- Render --------------------------------------------------------------

  return (
    <div className="min-h-screen bg-paper px-4 py-8">
      <div className="max-w-2xl mx-auto flex flex-col gap-6">

        {/* Header */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <img src="/logo.png" alt="Asaasa" className="h-10 w-auto" />
            <span className="font-display text-[24px] font-semibold text-ink">اثاثہ</span>
          </div>
          <h1 className="font-display text-[22px] font-semibold text-ink">Analyse your portfolio</h1>
          <p className="font-sans text-[14px] text-ink-soft mt-1">
            No sign-up needed. Add your stocks, bonds, crypto, and commodities for instant AI analysis.
          </p>
        </div>

        {!result && (
          <>
            {/* Empty state */}
            {holdings.length === 0 && (
              <div className="flex flex-col items-center gap-4 py-8">
                <p className="font-sans text-[14px] text-ink-soft text-center">
                  Add your holdings to get started.
                </p>
                <div className="flex gap-3">
                  <Button variant="primary" onClick={() => setPickerOpen(true)} className="btn-press">
                    Add holding
                  </Button>
                  <Button
                    variant="ghost"
                    disabled
                    title="Add at least one holding to analyse"
                    className="btn-press"
                  >
                    Analyse portfolio
                  </Button>
                </div>
              </div>
            )}

            {/* Picker panel — inline 2×2 grid */}
            {pickerOpen && (
              <div ref={pickerRef} className="bg-card border border-line rounded-[12px] p-4">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">
                  Choose asset class
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {(
                    [
                      { ac: 'equity',    label: 'Equity (Stocks)', sub: 'PSX-listed shares',   dot: 'bg-jade', bg: 'hover:bg-jade-soft' },
                      { ac: 'tbill',     label: 'Bond / T-Bill',   sub: 'Govt. securities',    dot: 'bg-info', bg: 'hover:bg-info-soft' },
                      { ac: 'crypto',    label: 'Crypto',          sub: 'BTC, ETH, SOL…',      dot: 'bg-plum', bg: 'hover:bg-plum-soft' },
                      { ac: 'commodity', label: 'Commodity',       sub: 'Gold, oil, silver…',  dot: 'bg-gold', bg: 'hover:bg-gold-soft' },
                    ] as { ac: AssetClass; label: string; sub: string; dot: string; bg: string }[]
                  ).map(({ ac, label, sub, dot, bg }) => (
                    <button
                      key={ac}
                      type="button"
                      onClick={() => addHolding(ac)}
                      className={cn(
                        'flex flex-col items-start gap-1 p-3 rounded-[8px] border border-line transition-colors btn-press text-left',
                        bg,
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={cn('w-2 h-2 rounded-full shrink-0', dot)} />
                        <span className="font-mono text-[12px] font-semibold text-ink">{label}</span>
                      </div>
                      <span className="font-sans text-[11px] text-ink-faint">{sub}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Holdings cards */}
            {holdings.length > 0 && (
              <div className="flex flex-col gap-3">
                {holdings.map((row) => {
                  const meta = ASSET_CLASS_META[row.assetClass]
                  const isBond = row.assetClass === 'tbill' || row.assetClass === 'bond'

                  return (
                    <div key={row.id} className="bg-card border border-line rounded-[10px] p-4 flex flex-col gap-3">

                      {/* Card header */}
                      <div className="flex items-center justify-between">
                        <Badge variant="info" className="text-[10px]">
                          <span className={cn('w-1.5 h-1.5 rounded-full mr-1', meta.dot)} />
                          {meta.label}
                        </Badge>
                        <button
                          type="button"
                          onClick={() => removeRow(row.id)}
                          className="font-sans text-[14px] text-loss hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded btn-press"
                        >
                          ×
                        </button>
                      </div>

                      {/* Equity */}
                      {row.assetClass === 'equity' && (
                        <>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Symbol</label>
                            <AssetComboBox
                              category="stock"
                              options={ASSET_UNIVERSE['stock']}
                              value={row.symbol}
                              onChange={(sym) => updateRow(row.id, { symbol: sym, errors: { ...row.errors, symbol: undefined } })}
                              placeholder="Search stocks…"
                              assetClass={EQUITY_FILTER}
                            />
                            {row.errors.symbol && <p className={errorCls}>{row.errors.symbol}</p>}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Shares</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0"
                                value={row.qty}
                                onChange={(e) => updateRow(row.id, { qty: e.target.value, errors: { ...row.errors, qty: undefined } })}
                              />
                              {row.errors.qty && <p className={errorCls}>{row.errors.qty}</p>}
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Entry price (Rs)</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0.00"
                                value={row.entry_price}
                                onChange={(e) => updateRow(row.id, { entry_price: e.target.value, errors: { ...row.errors, entry_price: undefined } })}
                              />
                              {row.errors.entry_price && <p className={errorCls}>{row.errors.entry_price}</p>}
                            </div>
                          </div>
                        </>
                      )}

                      {/* T-Bill / Bond */}
                      {isBond && (
                        <>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Symbol</label>
                            <AssetComboBox
                              category="bond"
                              options={ASSET_UNIVERSE['bond']}
                              value={row.symbol}
                              onChange={(sym) => updateRow(row.id, { symbol: sym, errors: { ...row.errors, symbol: undefined } })}
                              placeholder="Search bonds / T-bills…"
                              assetClass={BOND_FILTER}
                            />
                            {row.errors.symbol && <p className={errorCls}>{row.errors.symbol}</p>}
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Quantity (units)</label>
                            <input
                              type="number" inputMode="numeric" className={inputCls} placeholder="e.g. 5"
                              value={row.units}
                              onChange={(e) => updateRow(row.id, { units: e.target.value, errors: { ...row.errors, units: undefined } })}
                            />
                            <p className="font-sans text-[10px] text-ink-faint">Number of T-bill units you hold</p>
                            {row.errors.units && <p className={errorCls}>{row.errors.units}</p>}
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Face value (Rs)</label>
                            <input
                              type="number" inputMode="decimal" className={inputCls} placeholder="e.g. 100,000"
                              value={row.qty}
                              onChange={(e) => updateRow(row.id, { qty: e.target.value, errors: { ...row.errors, qty: undefined } })}
                            />
                            {row.errors.qty && <p className={errorCls}>{row.errors.qty}</p>}
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Buying price (Rs)</label>
                            <input
                              type="number" inputMode="decimal" className={inputCls} placeholder="e.g. 96,500"
                              value={row.entry_price}
                              onChange={(e) => updateRow(row.id, { entry_price: e.target.value, errors: { ...row.errors, entry_price: undefined } })}
                            />
                            <p className="font-sans text-[10px] text-ink-faint">The actual amount you paid, e.g. Rs 96,500 for a Rs 100,000 T-bill</p>
                            {row.errors.entry_price && <p className={errorCls}>{row.errors.entry_price}</p>}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Interest rate at buy (%)</label>
                              <input
                                type="number" inputMode="decimal" step="0.01" className={inputCls} placeholder="e.g. 21.5"
                                value={row.interest_rate}
                                onChange={(e) => updateRow(row.id, { interest_rate: e.target.value, errors: { ...row.errors, interest_rate: undefined } })}
                              />
                              {row.errors.interest_rate && <p className={errorCls}>{row.errors.interest_rate}</p>}
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Buy date</label>
                              <input
                                type="date" className={inputCls}
                                value={row.buy_date}
                                onChange={(e) => updateRow(row.id, { buy_date: e.target.value, errors: { ...row.errors, buy_date: undefined } })}
                              />
                              {row.errors.buy_date && <p className={errorCls}>{row.errors.buy_date}</p>}
                            </div>
                          </div>
                        </>
                      )}

                      {/* Crypto */}
                      {row.assetClass === 'crypto' && (
                        <>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Symbol</label>
                            <AssetComboBox
                              category="crypto"
                              options={ASSET_UNIVERSE['crypto']}
                              value={row.symbol}
                              onChange={(sym) => updateRow(row.id, { symbol: sym, errors: { ...row.errors, symbol: undefined } })}
                              placeholder="Search crypto…"
                              assetClass={CRYPTO_FILTER}
                            />
                            {row.errors.symbol && <p className={errorCls}>{row.errors.symbol}</p>}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Units</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0"
                                value={row.qty}
                                onChange={(e) => updateRow(row.id, { qty: e.target.value, errors: { ...row.errors, qty: undefined } })}
                              />
                              {row.errors.qty && <p className={errorCls}>{row.errors.qty}</p>}
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Entry price (Rs)</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0.00"
                                value={row.entry_price}
                                onChange={(e) => updateRow(row.id, { entry_price: e.target.value, errors: { ...row.errors, entry_price: undefined } })}
                              />
                              {row.errors.entry_price && <p className={errorCls}>{row.errors.entry_price}</p>}
                            </div>
                          </div>
                        </>
                      )}

                      {/* Commodity */}
                      {row.assetClass === 'commodity' && (
                        <>
                          <div className="flex flex-col gap-1">
                            <label className={labelCls}>Symbol</label>
                            <AssetComboBox
                              category="commodity"
                              options={ASSET_UNIVERSE['commodity']}
                              value={row.symbol}
                              onChange={(sym) => updateRow(row.id, { symbol: sym, errors: { ...row.errors, symbol: undefined } })}
                              placeholder="Search commodities…"
                              assetClass={COMMODITY_FILTER}
                            />
                            {row.errors.symbol && <p className={errorCls}>{row.errors.symbol}</p>}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Quantity (tola)</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0"
                                value={row.qty}
                                onChange={(e) => updateRow(row.id, { qty: e.target.value, errors: { ...row.errors, qty: undefined } })}
                              />
                              <p className="font-sans text-[10px] text-ink-faint">1 tola ≈ 11.66 g</p>
                              {row.errors.qty && <p className={errorCls}>{row.errors.qty}</p>}
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className={labelCls}>Buying price (Rs/tola)</label>
                              <input
                                type="number" inputMode="decimal" className={inputCls} placeholder="0.00"
                                value={row.entry_price}
                                onChange={(e) => updateRow(row.id, { entry_price: e.target.value, errors: { ...row.errors, entry_price: undefined } })}
                              />
                              {row.errors.entry_price && <p className={errorCls}>{row.errors.entry_price}</p>}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}

                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="font-sans text-[14px] text-jade hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded self-start"
                >
                  + Add another holding
                </button>

                {rateLimited ? (
                  <div className="bg-jade-soft border border-jade-soft rounded-[10px] p-5 flex flex-col gap-3 text-center">
                    <p className="font-sans text-[15px] text-ink font-medium">
                      You've used all your free analyses. Sign up to keep analysing.
                    </p>
                    <Button
                      variant="primary"
                      onClick={() => navigate('/register')}
                      className="w-full btn-press"
                    >
                      Sign up free →
                    </Button>
                    <button
                      type="button"
                      onClick={() => navigate('/login')}
                      className="font-sans text-[13px] text-ink-soft hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
                    >
                      Already have an account? Log in
                    </button>
                  </div>
                ) : (
                  <>
                    {error && (
                      <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2.5">
                        <p className="font-sans text-[13px] text-loss" role="alert">{error}</p>
                      </div>
                    )}
                    <Button
                      variant="primary"
                      onClick={handleAnalyze}
                      disabled={analyzeDisabled}
                      className="w-full btn-press"
                    >
                      {loading ? 'Analysing…' : 'Analyse portfolio'}
                    </Button>
                  </>
                )}
              </div>
            )}
          </>
        )}

        {/* Analysis result */}
        {result && (
          <div className="flex flex-col gap-6">
            <div className="bg-card border border-line rounded-[10px] p-5">
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-jade font-semibold mb-3">
                Portfolio Analysis
              </p>

              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="bg-paper border border-line-soft rounded-[8px] p-3 text-center">
                  <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">P&amp;L</p>
                  <p className={cn(
                    'font-mono text-[16px] font-semibold tabular-nums',
                    result.current_metrics.total_pnl_pct != null
                      ? (result.current_metrics.total_pnl_pct as number) >= 0 ? 'text-jade' : 'text-loss'
                      : 'text-ink',
                  )}>
                    {result.current_metrics.total_pnl_pct != null
                      ? `${(result.current_metrics.total_pnl_pct as number) >= 0 ? '+' : ''}${(result.current_metrics.total_pnl_pct as number).toFixed(1)}%`
                      : '—'}
                  </p>
                </div>
                <div className="bg-paper border border-line-soft rounded-[8px] p-3 text-center">
                  <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">Holdings</p>
                  <p className="font-mono text-[16px] font-semibold text-ink tabular-nums">
                    {result.current_metrics.num_holdings ?? '—'}
                  </p>
                </div>
                <div className="bg-paper border border-line-soft rounded-[8px] p-3 text-center">
                  <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">Diversification</p>
                  <p className="font-mono text-[16px] font-semibold text-ink tabular-nums">
                    {result.current_metrics.diversification_score != null
                      ? `${((result.current_metrics.diversification_score as number) * 100).toFixed(0)}%`
                      : '—'}
                  </p>
                </div>
              </div>

              {Array.isArray(result.current_metrics.concentration_warnings) &&
                result.current_metrics.concentration_warnings.length > 0 && (
                <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2 mb-4">
                  {(result.current_metrics.concentration_warnings as string[]).map((w, i) => (
                    <p key={i} className="font-sans text-[12px] text-loss">{w}</p>
                  ))}
                </div>
              )}

              {result.current_metrics.weights && (
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-2">Current Allocation</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(result.current_metrics.weights as Record<string, number>).map(([sym, weight]) => (
                      <span key={sym} className="font-mono text-[11px] px-2 py-1 rounded-full bg-paper border border-line-soft text-ink-faint">
                        {sym} {(weight * 100).toFixed(1)}%
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="[&_.card-shell]:max-w-none">
              <OptimizerCard
                data={result.suggested_portfolio}
                mode="analyze"
                currentHoldings={Object.entries((result.current_metrics.weights ?? {}) as Record<string, number>).map(([sym, weight]) => ({
                  id: sym,
                  portfolio_id: '',
                  instrument_id: '',
                  symbol: sym,
                  name: sym,
                  asset_class: (result.current_metrics.symbol_classes as Record<string, string>)?.[sym] ?? 'equity',
                  weight,
                } as HoldingResponse))}
              />
            </div>

            {result.rationale && (
              <div className="bg-card border border-line rounded-[10px] p-4">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-2">Rationale</p>
                <p className="font-sans text-[14px] text-ink leading-[1.5]">{result.rationale}</p>
              </div>
            )}

            {result.rebalance_actions.length > 0 && (
              <div className="bg-card border border-line rounded-[10px] p-4">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">
                  Suggested rebalancing
                </p>
                <ul className="flex flex-col gap-1.5">
                  {result.rebalance_actions.map((action, i) => (
                    <li key={i} className="flex items-start gap-2 font-sans text-[14px] text-ink leading-[1.4]">
                      <span className="text-jade shrink-0 mt-0.5">→</span>
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="bg-jade-soft border border-jade-soft rounded-[10px] p-5 flex flex-col gap-3 text-center">
              <p className="font-sans text-[15px] text-ink font-medium">
                Like what you see? Track this portfolio and get real-time alerts.
              </p>
              <Button
                variant="primary"
                onClick={() => navigate('/register', { state: { guestData: result } })}
                className="w-full btn-press"
              >
                Save & track it →
              </Button>
              <button
                type="button"
                onClick={() => { setResult(null); setHoldings([]); setRateLimited(false) }}
                className="font-sans text-[13px] text-ink-soft hover:underline focus-visible:outline-2 focus-visible:outline-jade rounded"
              >
                Analyse a different portfolio
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
