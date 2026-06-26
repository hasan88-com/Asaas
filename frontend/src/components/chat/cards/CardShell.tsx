import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface CardShellProps {
  eyebrow: string
  accentColor: string
  children: ReactNode
  actions?: ReactNode
  delayMs?: number
  className?: string
}

export function CardShell({ eyebrow, accentColor, children, actions, delayMs = 0, className }: CardShellProps) {
  return (
    <div
      className={cn(
        'bg-card border border-line rounded-[12px] overflow-hidden shadow-sm mt-2 animate-slide-up',
        className,
      )}
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* Accent bar */}
      <div style={{ height: 3, backgroundColor: accentColor }} aria-hidden="true" />

      <div className="p-4">
        {/* Eyebrow */}
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-faint mb-3">
          {eyebrow}
        </p>

        {children}

        {actions && (
          <div className="flex gap-2 mt-4 pt-4 border-t border-line-soft">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
