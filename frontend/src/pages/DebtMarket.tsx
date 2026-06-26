import { useEffect, useState } from 'react'
import { getDebtMarket } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { DebtInstrument } from '@/types/api'

const CATEGORY_META: Record<string, { label: string; icon: string; order: number }> = {
  govt_debt: { label: 'Government Securities (PIBs & T-Bills)', icon: '🏛️', order: 1 },
  gop_sukuk: { label: 'GoP Ijarah Sukuk (Islamic)', icon: '🌙', order: 2 },
  public_debt: { label: 'Public Debt Securities (Corporate Sukuk/TFCs)', icon: '🏢', order: 3 },
  private_debt: { label: 'Privately Placed Debt Securities', icon: '📋', order: 4 },
}

function formatCoupon(rate: number | null): string {
  if (rate === null) return '—'
  return `${(rate * 100).toFixed(2)}%`
}

function formatRemaining(years: number | null): string {
  if (years === null) return '—'
  if (years < 0) return 'Matured'
  if (years < 1) return `${Math.round(years * 12)} months`
  return `${years.toFixed(1)} years`
}

function formatDate(dateStr: string): string {
  if (!dateStr || dateStr === '') return '—'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    return d.toLocaleDateString('en-PK', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return dateStr
  }
}

export default function DebtMarket() {
  const [items, setItems] = useState<DebtInstrument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<string>('govt_debt')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    getDebtMarket()
      .then((data) => {
        setItems(data.items || [])
      })
      .catch(() => {
        setError('Failed to load PSX debt market data')
      })
      .finally(() => setLoading(false))
  }, [])

  const categories = Object.entries(CATEGORY_META)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([key, meta]) => ({
      key,
      ...meta,
      count: items.filter((i) => i.category === key).length,
    }))

  const filtered = items
    .filter((i) => i.category === activeCategory)
    .filter((i) => {
      if (!searchQuery.trim()) return true
      const q = searchQuery.toLowerCase()
      return (
        i.security_code.toLowerCase().includes(q) ||
        i.security_name.toLowerCase().includes(q)
      )
    })
    .sort((a, b) => (b.remaining_years ?? 0) - (a.remaining_years ?? 0))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-[28px] font-semibold text-ink">Debt Market</h1>
          <p className="font-sans text-[14px] text-ink-soft mt-1">
            Live data scraped from PSX Debt Market — {items.length} instruments across {categories.length} categories.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center gap-3 py-16">
          <span className="w-6 h-6 rounded-full border-2 border-jade border-t-transparent animate-spin" />
          <p className="font-sans text-[13px] text-ink-faint">Scraping PSX debt market…</p>
        </div>
      ) : error ? (
        <div className="bg-card border border-line rounded-[10px] p-6 text-center">
          <p className="font-sans text-[14px] text-loss">{error}</p>
          <Button variant="ghost" onClick={() => window.location.reload()} className="mt-3">
            Retry
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-card border border-line rounded-[10px] p-8 text-center">
          <p className="font-sans text-[16px] text-ink-soft">No debt market data found</p>
          <p className="font-sans text-[13px] text-ink-faint mt-1">
            PSX debt market page may be temporarily unavailable.
          </p>
        </div>
      ) : (
        <>
          {/* Category tabs */}
          <div className="flex gap-2 flex-wrap">
            {categories.map((cat) => (
              <button
                key={cat.key}
                type="button"
                onClick={() => setActiveCategory(cat.key)}
                className={cn(
                  'px-4 py-2 rounded-[8px] font-sans text-[13px] border transition-colors btn-press',
                  activeCategory === cat.key
                    ? 'bg-jade text-white border-jade'
                    : 'bg-card text-ink border-line hover:border-jade-soft',
                )}
              >
                {cat.icon} {cat.label} ({cat.count})
              </button>
            ))}
          </div>

          {/* Search */}
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by code or name…"
            className="bg-card border border-line rounded-[8px] px-3 py-2.5 text-[14px] text-ink placeholder:text-ink-faint focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2"
          />

          {/* Table */}
          <div className="bg-card border border-line rounded-[10px] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-line">
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint">Code</th>
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint">Security Name</th>
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint text-right">Coupon</th>
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint text-right">Maturity</th>
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint text-right">Remaining</th>
                    <th className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint text-right">Face Value</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center font-sans text-[13px] text-ink-faint">
                        No instruments match your search
                      </td>
                    </tr>
                  ) : (
                    filtered.map((inst) => (
                      <tr
                        key={inst.security_code}
                        className="border-b border-line-soft last:border-b-0 hover:bg-jade-soft/30 transition-colors"
                      >
                        <td className="px-4 py-3 font-mono text-[13px] font-semibold text-jade">
                          {inst.security_code}
                        </td>
                        <td className="px-4 py-3 font-sans text-[13px] text-ink max-w-[300px] truncate">
                          {inst.security_name}
                        </td>
                        <td className={cn(
                          'px-4 py-3 font-mono text-[14px] font-semibold tabular-nums text-right',
                          inst.coupon_rate && inst.coupon_rate > 0.12 ? 'text-gain' :
                          inst.coupon_rate && inst.coupon_rate < 0.10 ? 'text-info' : 'text-ink'
                        )}>
                          {formatCoupon(inst.coupon_rate)}
                        </td>
                        <td className="px-4 py-3 font-mono text-[12px] text-ink-faint text-right">
                          {formatDate(inst.maturity_date)}
                        </td>
                        <td className="px-4 py-3 font-mono text-[13px] text-ink text-right tabular-nums">
                          {formatRemaining(inst.remaining_years)}
                        </td>
                        <td className="px-4 py-3 font-mono text-[12px] text-ink-faint text-right">
                          {inst.face_value ? `₨${inst.face_value.toLocaleString()}` : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {filtered.length > 0 && (
              <div className="px-4 py-2 border-t border-line">
                <p className="font-mono text-[10px] text-ink-faint">
                  Showing {filtered.length} of {items.filter((i) => i.category === activeCategory).length} instruments
                </p>
              </div>
            )}
          </div>

          {/* Summary stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {categories.map((cat) => {
              const catItems = items.filter((i) => i.category === cat.key)
              const avgCoupon = catItems.length > 0
                ? catItems.reduce((sum, i) => sum + (i.coupon_rate ?? 0), 0) / catItems.length
                : 0
              return (
                <div
                  key={cat.key}
                  className="bg-card border border-line rounded-[10px] p-4 cursor-pointer hover:border-jade-soft transition-colors"
                  onClick={() => setActiveCategory(cat.key)}
                >
                  <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-ink-faint">{cat.label}</p>
                  <p className="font-mono text-[20px] font-semibold text-ink mt-1">{catItems.length}</p>
                  <p className="font-mono text-[11px] text-ink-faint mt-0.5">
                    Avg coupon: {avgCoupon > 0 ? `${(avgCoupon * 100).toFixed(2)}%` : 'N/A'}
                  </p>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
