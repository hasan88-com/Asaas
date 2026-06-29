import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { declareHoldings, searchMarket, getDebtInstrument, getPortfolio } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AssetComboBox } from '@/components/ui/combobox'
import { cn } from '@/lib/utils'
import { ASSET_UNIVERSE } from '@/data/assetUniverse'
import type { DeclareHoldingInput } from '@/types/api'

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

// ---- Helpers ---------------------------------------------------------------

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

/** Resolve a universe symbol (e.g. "HBL.KA", "BTC") to a tracked DB instrument id. */
async function resolveInstrumentId(symbol: string): Promise<string | null> {
  try {
    const results = await searchMarket(symbol)
    const exact = results.find((r) => r.symbol.toUpperCase() === symbol.toUpperCase())
    return exact?.id ?? null
  } catch {
    return null
  }
}

// ---- Main component --------------------------------------------------------

interface LocationState {
  fromAdjust?: boolean
}

function holdingResponseToRow(h: import('@/types/api').HoldingResponse): HoldingRow {
  const ac = (h.asset_class ?? 'equity').toLowerCase() as AssetClass
  const isBond = ac === 'tbill' || ac === 'bond'
  return {
    id: crypto.randomUUID(),
    assetClass: ac,
    symbol: h.symbol ?? '',
    qty: h.quantity != null ? String(h.quantity) : '',
    units: isBond && h.quantity != null ? String(Math.round(h.quantity)) : '',
    entry_price: h.entry_price != null ? String(h.entry_price) : '',
    interest_rate: '',
    buy_date: h.entry_date ?? '',
    errors: {},
  }
}

export default function DeclareHoldings() {
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = location.state as LocationState | null
  const fromAdjust = locationState?.fromAdjust === true

  const [mode, setMode] = useState<'choose' | 'form'>(fromAdjust ? 'form' : 'choose')
  const [holdings, setHoldings] = useState<HoldingRow[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loadingExisting, setLoadingExisting] = useState(fromAdjust)
  const [error, setError] = useState<string | null>(null)

  // When coming from Adjust, pre-load existing holdings
  useEffect(() => {
    if (!fromAdjust) return
    getPortfolio()
      .then((p) => {
        if (p.holdings.length > 0) {
          setHoldings(p.holdings.map(holdingResponseToRow))
        }
      })
      .catch(() => { /* leave empty — user can add manually */ })
      .finally(() => setLoadingExisting(false))
  }, [])

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

  // T-bill / bond: auto-detect face value (and coupon, if any) from live PSX
  // debt data when a symbol is picked. The user can still override.
  const autofillBond = async (rowId: string, sym: string) => {
    if (!sym) return
    try {
      const d = await getDebtInstrument(sym)
      const patch: Partial<HoldingRow> = {}
      if (d.face_value != null) patch.qty = String(d.face_value)
      if (d.coupon_rate != null && d.coupon_rate > 0) patch.interest_rate = (d.coupon_rate * 100).toFixed(2)
      if (Object.keys(patch).length) updateRow(rowId, patch)
    } catch {
      /* no live match — leave the field for manual entry */
    }
  }

  const addHolding = (ac: AssetClass) => {
    setHoldings((prev) => [...prev, newHolding(ac)])
    setPickerOpen(false)
    setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 50)
  }

  // ---- Validation ----------------------------------------------------------

  const validate = (): boolean => {
    const next = holdings.map((r) => {
      const errs: HoldingRow['errors'] = {}
      if (!r.symbol.trim()) errs.symbol = 'Symbol is required'
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
      } else {
        const qty = parseFloat(r.qty)
        if (!r.qty || isNaN(qty) || qty <= 0) errs.qty = 'Enter a positive number'
      }
      return { ...r, errors: errs }
    })
    setHoldings(next)
    return next.every((r) => Object.keys(r.errors).length === 0)
  }

  // ---- Submit --------------------------------------------------------------

  const handleStartFresh = () => {
    navigate('/onboarding/suggest', { replace: true, state: { portfolio: null } })
  }

  const handleDeclare = async () => {
    if (!validate()) return
    setError(null)
    setSubmitting(true)
    try {
      const resolved = await Promise.all(
        holdings.map(async (r) => ({ row: r, id: await resolveInstrumentId(r.symbol.trim()) })),
      )
      const unresolved = resolved.filter((x) => !x.id).map((x) => x.row.symbol.trim())
      if (unresolved.length > 0) {
        setError(`Couldn't match these to tracked instruments: ${unresolved.join(', ')}. Pick from the suggestions list.`)
        setSubmitting(false)
        return
      }
      const payload: DeclareHoldingInput[] = resolved.map(({ row, id }) => {
        const isBond = row.assetClass === 'tbill' || row.assetClass === 'bond'
        return {
          instrument_id: id as string,
          quantity: isBond ? String(parseInt(row.units, 10)) : String(parseFloat(row.qty)),
          entry_price: String(parseFloat(row.entry_price)),
          ...(isBond && row.buy_date ? { entry_date: row.buy_date } : {}),
        }
      })
      await declareHoldings(payload)
      navigate('/onboarding/suggest', { replace: true, state: { portfolio: null, hadHoldings: true } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Declaration failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const anyErrors = holdings.some((r) => Object.values(r.errors).some(Boolean))
  const declareDisabled = holdings.length === 0 || anyErrors || submitting

  // ---- Shared field styles -------------------------------------------------

  const inputCls = cn(
    'bg-card border border-line rounded-[6px] px-2 py-2 text-[13px] font-mono tabular-nums text-ink w-full',
    'min-h-[40px] focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 transition-colors',
  )
  const labelCls = 'font-sans text-[11px] font-medium text-ink'
  const errorCls = 'font-sans text-[11px] text-loss mt-0.5'

  // ---- Loading screen (fetching existing holdings for adjust flow) ----------

  if (loadingExisting) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <span className="w-6 h-6 rounded-full border-2 border-jade border-t-transparent animate-spin" />
      </div>
    )
  }

  // ---- Choose screen (unchanged "Start fresh" path) ------------------------

  if (mode === 'choose') {
    return (
      <div className="min-h-screen bg-paper flex flex-col items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <span className="font-display text-[28px] font-semibold text-ink block mb-2">اثاثہ</span>
          <h1 className="font-display text-[22px] font-semibold text-ink mb-2">Your existing portfolio</h1>
          <p className="font-sans text-[15px] text-ink-soft mb-8">
            Do you already own investments you'd like to track?
          </p>
          <div className="flex flex-col gap-3">
            <Button variant="primary" onClick={() => setMode('form')} className="w-full">
              Yes, I already own investments
            </Button>
            <Button variant="outline" onClick={handleStartFresh} className="w-full">
              Start fresh — suggest an allocation
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // ---- Form screen (asset-class-first, mirrors /try) -----------------------

  return (
    <div className="min-h-screen bg-paper px-4 py-8">
      <div className="max-w-2xl mx-auto flex flex-col gap-6">

        {/* Header */}
        <div className="text-center">
          <span className="font-display text-[28px] font-semibold text-ink block mb-1">اثاثہ</span>
          <h1 className="font-display text-[20px] font-semibold text-ink">
            {fromAdjust ? 'Adjust your holdings' : 'Declare your holdings'}
          </h1>
          <p className="font-sans text-[14px] text-ink-soft mt-1">
            {fromAdjust
              ? 'Add, remove, or update your holdings. We\'ll regenerate your portfolio suggestion.'
              : 'Add each investment you currently hold. Entry price is used for P&L tracking.'}
          </p>
        </div>

        {/* Empty state */}
        {holdings.length === 0 && (
          <div className="flex flex-col items-center gap-4 py-8">
            <p className="font-sans text-[14px] text-ink-soft text-center">
              Add your holdings to get started.
            </p>
            <Button variant="primary" onClick={() => setPickerOpen(true)} className="btn-press">
              Add holding
            </Button>
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
                          placeholder="Search bonds / T-bills…"
                          assetClass={BOND_FILTER}
                          onChange={(sym) => { updateRow(row.id, { symbol: sym, errors: { ...row.errors, symbol: undefined } }); autofillBond(row.id, sym) }}
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
                        <p className="font-sans text-[10px] text-ink-faint">Auto-detected from PSX when you pick a symbol — editable.</p>
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
          </div>
        )}

        {error && (
          <div className="bg-loss-soft border border-loss/20 rounded-[8px] px-3 py-2.5">
            <p className="font-sans text-[13px] text-loss" role="alert">{error}</p>
          </div>
        )}

        {/* Footer actions */}
        <div className="flex gap-3">
          <Button
            variant="ghost"
            onClick={() => fromAdjust ? navigate('/onboarding/suggest', { replace: true, state: { portfolio: null } }) : setMode('choose')}
            className="flex-1 btn-press"
          >
            Back
          </Button>
          <Button
            variant="primary"
            onClick={handleDeclare}
            disabled={declareDisabled}
            className="flex-1 btn-press"
          >
            {submitting ? 'Saving…' : 'Declare holdings'}
          </Button>
        </div>
      </div>
    </div>
  )
}
