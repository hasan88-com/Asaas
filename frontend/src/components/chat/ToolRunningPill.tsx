import { useReducedMotion } from '@/hooks/useReducedMotion'
import { cn } from '@/lib/utils'

interface ToolRunningPillProps {
  label: string
}

export function ToolRunningPill({ label }: ToolRunningPillProps) {
  const reduced = useReducedMotion()

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-paper border border-line text-ink-faint font-mono text-[12px]">
      {/* Spinning ring SVG */}
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        className={cn(!reduced && 'tool-ring')}
      >
        <circle cx="8" cy="8" r="6" stroke="#DCD8CC" strokeWidth="1.5" />
        <path
          d="M8 2 A6 6 0 0 1 14 8"
          stroke="#0F6E56"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <span>{label}</span>
    </span>
  )
}
