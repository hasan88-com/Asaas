import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { dismissFlag } from '@/lib/api'
import type { FlagResponse } from '@/types/api'
import { cn } from '@/lib/utils'

const SEVERITY_VARIANT: Record<string, 'loss' | 'gold' | 'neutral'> = {
  high: 'loss',
  medium: 'gold',
  low: 'neutral',
}

const SEVERITY_LABEL: Record<string, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const SEVERITY_BORDER: Record<string, string> = {
  high: 'border-l-loss',
  medium: 'border-l-gold',
  low: 'border-l-ink-faint',
}

const SEVERITY_BG: Record<string, string> = {
  high: 'bg-loss-soft/50',
  medium: 'bg-gold-soft/50',
  low: 'bg-info-soft/50',
}

interface FlagCardProps {
  flag: FlagResponse
  onDismiss?: (id: string) => void
  className?: string
}

export function FlagCard({ flag, onDismiss, className }: FlagCardProps) {
  const navigate = useNavigate()
  const [exiting, setExiting] = useState(false)

  const handleDiscuss = () => {
    setExiting(true)
    setTimeout(() => {
      navigate('/chat', { state: { seedMessage: flag.message } })
    }, 200)
  }

  const handleDismiss = async () => {
    setExiting(true)
    await dismissFlag(flag.id)
    setTimeout(() => onDismiss?.(flag.id), 300)
  }

  return (
    <div
      className={cn(
        'bg-card border border-line rounded-[10px] p-4 shadow-sm',
        'border-l-[3px]',
        SEVERITY_BORDER[flag.severity] ?? 'border-l-ink-faint',
        SEVERITY_BG[flag.severity] ?? '',
        'transition-all duration-300',
        exiting && 'opacity-0 translate-x-4',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          {/* Severity — color + text label, never color alone */}
          <Badge variant={SEVERITY_VARIANT[flag.severity] ?? 'neutral'}>
            {SEVERITY_LABEL[flag.severity] ?? flag.severity}
          </Badge>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
            {flag.category}
          </span>
        </div>
        <time
          dateTime={flag.created_at}
          className="font-mono text-[10px] text-ink-faint shrink-0"
        >
          {new Date(flag.created_at).toLocaleDateString('en-PK', {
            day: 'numeric',
            month: 'short',
          })}
        </time>
      </div>

      <p className="font-sans text-[14px] text-ink leading-[1.5] mb-3">{flag.message}</p>

      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={handleDiscuss} className="btn-press">
          Discuss
        </Button>
        <Button variant="outline" size="sm" onClick={handleDismiss} className="btn-press">
          Dismiss
        </Button>
      </div>
    </div>
  )
}
