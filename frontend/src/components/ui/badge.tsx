import * as React from 'react'
import { cn } from '@/lib/utils'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'info' | 'gain' | 'loss' | 'gold' | 'neutral' | 'plum' | 'rose'
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] px-2 py-0.5 rounded-sm',
        variant === 'default' && 'bg-paper text-ink-soft border border-line',
        variant === 'info' && 'bg-info-soft text-info',
        variant === 'gain' && 'bg-jade-soft text-gain',
        variant === 'loss' && 'bg-loss-soft text-loss',
        variant === 'gold' && 'bg-gold-soft text-gold',
        variant === 'neutral' && 'bg-paper text-ink-faint border border-line',
        variant === 'plum' && 'bg-plum-soft text-plum',
        variant === 'rose' && 'bg-rose-soft text-rose',
        className,
      )}
      {...props}
    />
  )
}

export { Badge }
