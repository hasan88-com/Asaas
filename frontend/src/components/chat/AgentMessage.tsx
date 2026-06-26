import { useEffect, useRef } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { StreamingIndicator } from './StreamingIndicator'
import { ToolRunningPill } from './ToolRunningPill'
import type { AssistantMessage } from '@/types/chat'

const ROLE_LABEL: Record<string, string> = {
  profiler: 'PROFILER',
  optimizer: 'OPTIMIZER',
  news_materiality: 'NEWS',
  rate_impact: 'RATE IMPACT',
  valuation: 'VALUATION',
  technical: 'TECHNICAL',
  chat: 'ASAAS',
}

const ROLE_COLOR: Record<string, string> = {
  profiler: 'var(--info)',
  optimizer: 'var(--jade)',
  news_materiality: 'var(--rose)',
  rate_impact: 'var(--gold)',
  valuation: 'var(--info)',
  technical: 'var(--plum)',
  chat: 'var(--jade)',
}

interface AgentMessageProps {
  message: AssistantMessage
  showRoleLabel?: boolean
  activeTool?: string
}

export function AgentMessage({ message, showRoleLabel, activeTool }: AgentMessageProps) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    if (reduced || !ref.current) return
    const el = ref.current
    el.style.opacity = '0'
    el.style.transform = 'translateY(6px)'
    requestAnimationFrame(() => {
      el.style.transition =
        'opacity 200ms cubic-bezier(0.23,1,0.32,1), transform 200ms cubic-bezier(0.23,1,0.32,1)'
      el.style.opacity = '1'
      el.style.transform = 'translateY(0)'
    })
  }, [reduced])

  const accentColor = ROLE_COLOR[message.agentRole] ?? '#0F6E56'
  const roleLabel = ROLE_LABEL[message.agentRole] ?? 'ASAAS'

  return (
    <div ref={ref} className="flex flex-col gap-1.5 max-w-[80%]">
      {showRoleLabel && (
        <span
          className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] px-0.5"
          style={{ color: accentColor }}
        >
          {roleLabel}
        </span>
      )}

      <div className="bg-card border border-line rounded-[14px] rounded-bl-[4px] px-4 py-3 text-[16px] leading-[1.6] text-ink whitespace-pre-wrap break-words">
        {activeTool && (
          <div className="mb-2">
            <ToolRunningPill label={`Running ${activeTool}…`} />
          </div>
        )}

        {message.isStreaming && !message.text && <StreamingIndicator />}

        {message.text && <span>{message.text}</span>}

        {message.isStreaming && message.text && (
          <span className="ml-1 inline-flex">
            <StreamingIndicator />
          </span>
        )}
      </div>
    </div>
  )
}
