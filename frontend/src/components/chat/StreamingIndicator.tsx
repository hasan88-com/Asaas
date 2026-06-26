import { useReducedMotion } from '@/hooks/useReducedMotion'
import { cn } from '@/lib/utils'

export function StreamingIndicator() {
  const reduced = useReducedMotion()

  return (
    <span className="inline-flex items-center gap-1 h-4" aria-label="Typing…">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            'w-1.5 h-1.5 rounded-full bg-ink-faint',
            !reduced && [
              i === 0 && 'animate-dot-pulse',
              i === 1 && 'animate-dot-pulse-2',
              i === 2 && 'animate-dot-pulse-3',
            ],
          )}
        />
      ))}
    </span>
  )
}
