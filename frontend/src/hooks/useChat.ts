import { useCallback, useRef, useState } from 'react'
import { streamChat, getChatHistory } from '@/lib/api'
import type { Message, AssistantMessage, AgentRole } from '@/types/chat'
import type { ChatHistoryItem } from '@/types/api'

function historyToMessages(items: ChatHistoryItem[]): Message[] {
  return items.map((item) => {
    if (item.role === 'user') {
      return { id: item.id, role: 'user', text: item.content, createdAt: item.created_at }
    }
    return {
      id: item.id,
      role: 'assistant',
      agentRole: (item.agent_role ?? 'chat') as AgentRole,
      text: item.content,
      isStreaming: false,
      createdAt: item.created_at,
    }
  })
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeTool, setActiveTool] = useState<string | undefined>()
  const abortRef = useRef<AbortController | null>(null)

  const loadHistory = useCallback(async () => {
    try {
      const items = await getChatHistory()
      setMessages(historyToMessages(items))
    } catch {
      // History load is best-effort; start fresh on failure
    }
  }, [])

  const send = useCallback(async (text: string) => {
    if (isStreaming) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      text,
      createdAt: new Date().toISOString(),
    }

    const assistantId = crypto.randomUUID()
    const assistantMsg: AssistantMessage = {
      id: assistantId,
      role: 'assistant',
      agentRole: 'chat',
      text: '',
      isStreaming: true,
      createdAt: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    // Timeout: abort if stream hangs for 60s
    const timeout = setTimeout(() => ctrl.abort(), 60_000)

    try {
      await streamChat(
        text,
        {
          onTool: (tool, status) => {
            setActiveTool(status === 'running' ? tool : undefined)
          },
          onContent: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId && m.role === 'assistant'
                  ? { ...m, text: m.text + delta }
                  : m,
              ),
            )
          },
          onDone: (agentRole) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId && m.role === 'assistant'
                  ? { ...m, isStreaming: false, agentRole: agentRole as AgentRole }
                  : m,
              ),
            )
          },
        },
        ctrl.signal,
      )
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        if (ctrl.signal.aborted) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.role === 'assistant'
                ? { ...m, isStreaming: false, text: m.text || 'Request timed out. Please try again.' }
                : m,
            ),
          )
        }
        return
      }
      const errText = err instanceof Error && err.message
        ? err.message
        : 'Something went wrong. Please try again.'
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.role === 'assistant'
            ? { ...m, isStreaming: false, text: m.text || errText }
            : m,
        ),
      )
    } finally {
      clearTimeout(timeout)
      setIsStreaming(false)
      setActiveTool(undefined)
      abortRef.current = null
    }
  }, [isStreaming])

  return { messages, isStreaming, activeTool, send, loadHistory }
}
