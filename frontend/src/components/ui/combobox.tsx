import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { cn } from '@/lib/utils'
import type { AssetOption, AssetCategory } from '@/data/assetUniverse'

interface AssetComboBoxProps {
  category: AssetCategory
  options: AssetOption[]
  value: string
  onChange: (symbol: string) => void
  placeholder?: string
  assetClass?: readonly string[]
}

export function AssetComboBox({ category, options, value, onChange, placeholder, assetClass }: AssetComboBoxProps) {
  const [open, setOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightIdx, setHighlightIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const base = assetClass
      ? options.filter((o) => assetClass.includes((o as AssetOption & { assetClass: string }).assetClass))
      : options
    if (!searchQuery.trim()) return base
    const q = searchQuery.toLowerCase()
    return base.filter(
      (o) =>
        o.symbol.toLowerCase().includes(q) ||
        o.name.toLowerCase().includes(q) ||
        (o.sector && o.sector.toLowerCase().includes(q)),
    )
  }, [options, searchQuery, assetClass])

  useEffect(() => {
    setHighlightIdx(0)
  }, [searchQuery])

  const close = useCallback(() => {
    setOpen(false)
    setSearchQuery('')
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (!listRef.current?.contains(target) && !inputRef.current?.contains(target)) {
        close()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, close])

  const select = (sym: string) => {
    onChange(sym)
    close()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setOpen(true)
        e.preventDefault()
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[highlightIdx]) select(filtered[highlightIdx].symbol)
    } else if (e.key === 'Escape') {
      close()
    }
  }

  const dotColor = {
    stock: 'bg-jade',
    bond: 'bg-info',
    crypto: 'bg-plum',
    commodity: 'bg-gold',
  }[category]

  return (
    <div className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          // Always display the parent value — no open/closed dual-mode
          // Typing updates parent directly; searchQuery is only the dropdown filter
          value={value}
          onChange={(e) => {
            const val = e.target.value.toUpperCase()
            onChange(val)
            setSearchQuery(val)
            if (!open) setOpen(true)
          }}
          onFocus={(e) => {
            setSearchQuery('')
            setOpen(true)
            e.target.select()
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            'w-full bg-card border border-line rounded-[6px] px-2 pl-5 py-2 text-[13px] font-mono text-ink uppercase',
            'placeholder:text-ink-faint min-h-[40px]',
            'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 transition-colors',
          )}
          placeholder={placeholder || 'Search or type symbol...'}
          autoCapitalize="characters"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
        />
        <span className={cn('absolute left-2 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full', dotColor)} />
      </div>

      {open && (
        <div
          ref={listRef}
          role="listbox"
          className={cn(
            'absolute z-50 mt-1 w-full max-h-[240px] overflow-y-auto',
            'bg-card border border-line rounded-[8px] shadow-lg',
            'scrollbar-thin scrollbar-thumb-line scrollbar-track-transparent',
          )}
        >
          {filtered.length === 0 && (
            <div className="px-3 py-3 text-center">
              <p className="font-sans text-[12px] text-ink-faint">No matches found</p>
            </div>
          )}
          {filtered.map((opt, i) => (
            <button
              key={opt.symbol}
              type="button"
              role="option"
              aria-selected={opt.symbol === value}
              onClick={() => select(opt.symbol)}
              onMouseEnter={() => setHighlightIdx(i)}
              className={cn(
                'w-full px-3 py-2 text-left flex items-center gap-2.5 transition-colors',
                'hover:bg-line-soft/50 focus-visible:bg-line-soft/50 focus-visible:outline-none',
                i === highlightIdx && 'bg-line-soft/50',
                opt.symbol === value && 'bg-jade-soft/30',
              )}
            >
              <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dotColor)} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[12px] font-semibold text-ink uppercase shrink-0">
                    {opt.symbol}
                  </span>
                  <span className="font-sans text-[11px] text-ink-soft truncate">
                    {opt.name}
                  </span>
                </div>
                {opt.sector && (
                  <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                    {opt.sector}
                  </span>
                )}
              </div>
              {opt.symbol === value && (
                <span className="text-jade text-[14px] shrink-0">✓</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
