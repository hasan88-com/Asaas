import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { getWallet, depositCash, withdrawCash, getCashTransactions } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { CashTransaction } from '@/types/api'

type Panel = 'deposit' | 'withdraw' | null

const inputCls = cn(
  'bg-card border border-line rounded-[6px] px-2 py-2 text-[13px] font-mono tabular-nums text-ink w-full',
  'min-h-[40px] focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
)
const labelCls = 'font-sans text-[11px] font-medium text-ink mb-1 block'

const fmtPkr = (v: string | number) => {
  const n = typeof v === 'string' ? parseFloat(v) : v
  return `₨${n.toLocaleString('en-PK', { maximumFractionDigits: 2 })}`
}

// deposit / sell add cash; withdrawal / buy remove it
const CREDIT_TYPES = new Set(['deposit', 'sell'])

const TXN_LABEL: Record<string, string> = {
  deposit: 'Deposit',
  withdrawal: 'Withdraw',
  buy: 'Buy',
  sell: 'Sell',
}

export function WalletCard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [balance, setBalance] = useState<string | null>(null)
  const [txns, setTxns] = useState<CashTransaction[]>([])
  const [panel, setPanel] = useState<Panel>(null)
  const [amount, setAmount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [w, t] = await Promise.allSettled([getWallet(), getCashTransactions(10)])
    if (w.status === 'fulfilled') setBalance(w.value.balance)
    if (t.status === 'fulfilled') setTxns(t.value.items)
  }, [])

  useEffect(() => { void load() }, [load, refreshKey])

  const openPanel = (p: Panel) => {
    setError(null)
    setAmount('')
    setPanel(panel === p ? null : p)
  }

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      const fn = panel === 'deposit' ? depositCash : withdrawCash
      const w = await fn(amount)
      setBalance(w.balance)
      setPanel(null)
      setAmount('')
      await load()
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  const amountValid = parseFloat(amount) > 0

  return (
    <div className="bg-card border border-line rounded-[10px] p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint mb-3">Cash Wallet</p>

      <div className="flex items-end gap-2 mb-3">
        <span className="font-display text-[26px] leading-[1] font-semibold text-ink tabular-nums">
          {balance === null ? '—' : fmtPkr(balance)}
        </span>
        <span className="font-mono text-[11px] text-ink-faint mb-0.5">PKR</span>
      </div>

      <div className="flex gap-2 mb-3">
        <Button variant={panel === 'deposit' ? 'primary' : 'outline'} size="sm" onClick={() => openPanel('deposit')}>
          Deposit
        </Button>
        <Button variant={panel === 'withdraw' ? 'primary' : 'outline'} size="sm" onClick={() => openPanel('withdraw')}>
          Withdraw
        </Button>
      </div>

      {panel && (
        <div className="border border-line rounded-[10px] p-3 flex flex-col gap-2 mb-3">
          <div>
            <label className={labelCls}>Amount (₨)</label>
            <input
              className={inputCls}
              type="number"
              inputMode="decimal"
              placeholder="0.00"
              value={amount}
              onChange={(e) => { setAmount(e.target.value); setError(null) }}
            />
          </div>
          {error && <p className="font-sans text-[12px] text-loss" role="alert">{error}</p>}
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setPanel(null)} disabled={submitting}>Cancel</Button>
            <Button variant="primary" size="sm" onClick={submit} disabled={!amountValid || submitting}>
              {submitting ? 'Saving…' : panel === 'deposit' ? 'Deposit' : 'Withdraw'}
            </Button>
          </div>
        </div>
      )}

      {txns.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {txns.map((t) => {
            const credit = CREDIT_TYPES.has(t.type)
            return (
              <div key={t.id} className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-ink-soft truncate">
                  {TXN_LABEL[t.type] ?? t.type}
                  {t.symbol ? ` · ${t.symbol}` : ''}
                </span>
                <span className={cn('font-mono text-[11px] tabular-nums shrink-0', credit ? 'text-jade' : 'text-loss')}>
                  {credit ? '+' : '−'}{fmtPkr(t.amount)}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
