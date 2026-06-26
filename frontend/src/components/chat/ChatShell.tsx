import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { cn } from '@/lib/utils'
import type { Message } from '@/types/chat'

interface ChatShellProps {
  messages: Message[]
  isStreaming: boolean
  activeTool?: string
  onSend: (text: string) => void
  className?: string
  chips?: string[]
}

export function ChatShell({ messages, isStreaming, activeTool, onSend, className, chips }: ChatShellProps) {
  return (
    <div className={cn('flex flex-col h-full overflow-hidden', className)}>
      <MessageList
        messages={messages}
        activeTool={isStreaming ? activeTool : undefined}
        onChipClick={onSend}
        chips={chips}
      />
      <Composer onSend={onSend} disabled={isStreaming} />
    </div>
  )
}
