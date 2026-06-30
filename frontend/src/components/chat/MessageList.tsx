import { useEffect, useRef } from 'react'
import { UserMessage } from './UserMessage'
import { AgentMessage } from './AgentMessage'
import type { Message } from '@/types/chat'

const EXAMPLE_CHIPS = [
  'Suggest a portfolio for me',
  'Value HBL for me',
  'Show RSI for OGDC',
  'How does the SBP rate affect my T-bills?',
]

interface MessageListProps {
  messages: Message[]
  activeTool?: string
  onChipClick?: (text: string) => void
  /** Portfolio-aware suggestion chips; falls back to generic examples. */
  chips?: string[]
}

export function MessageList({ messages, activeTool, onChipClick, chips }: MessageListProps) {
  const exampleChips = chips && chips.length > 0 ? chips : EXAMPLE_CHIPS
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-8 p-6 text-center">
        <div className="flex flex-col items-center gap-3">
          <p className="font-display text-[36px] font-semibold text-ink leading-[1.1]">
            اثاثہ
          </p>
          <div className="flex items-center gap-2">
            <span className="h-px w-6 bg-jade/30" />
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-jade/60">Asaasa</span>
            <span className="h-px w-6 bg-jade/30" />
          </div>
          <p className="font-sans text-[15px] text-ink-soft mt-1 max-w-xs">
            Your Pakistan-focused wealth advisor. Ask about portfolios, stocks, or market events.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2.5 max-w-sm w-full">
          {exampleChips.map((chip) => (
            <button
              key={chip}
              onClick={() => onChipClick?.(chip)}
              className="px-4 py-3 rounded-[10px] border border-line bg-card text-[13px] text-ink-soft text-left hover:border-jade hover:text-ink hover:bg-jade-soft/30 transition-all duration-150 active:scale-[0.97] min-h-[44px] focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2"
            >
              {chip}
            </button>
          ))}
        </div>

        <p className="font-mono text-[10px] text-ink-faint uppercase tracking-[0.12em]">
          Or type your own question below
        </p>
      </div>
    )
  }

  // Determine which assistant messages are the first in each agent turn
  // (to show the role label once per turn)
  const firstAssistantIds = new Set<string>()
  let lastRole: string | null = null
  for (const m of messages) {
    if (m.role === 'user') {
      lastRole = null
    } else if (m.role === 'assistant') {
      if (lastRole !== m.agentRole) {
        firstAssistantIds.add(m.id)
        lastRole = m.agentRole
      }
    }
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
      {messages.map((m) => {
        if (m.role === 'user') {
          return <UserMessage key={m.id} text={m.text} />
        }
        return (
          <AgentMessage
            key={m.id}
            message={m}
            showRoleLabel={firstAssistantIds.has(m.id)}
            activeTool={m.isStreaming ? activeTool : undefined}
          />
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
