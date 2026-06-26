import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send } from 'lucide-react'
import { useChat } from '@/hooks/useChat'
import { cn } from '@/lib/utils'

const EXAMPLE_CHIPS = [
  'Optimise my portfolio',
  'What is my risk score?',
  'Value my top holding',
  'Explain recent flags',
]

export function DashboardChatComposer() {
  const navigate = useNavigate()
  const { messages, isStreaming, send } = useChat()
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = () => {
    const text = input.trim()
    if (!text || isStreaming) return
    send(text)
    setInput('')
    // Navigate to full chat page to see the conversation
    navigate('/chat', { state: { seedMessage: text } })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleChipClick = (chip: string) => {
    setInput(chip)
    textareaRef.current?.focus()
  }

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [input])

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 md:static md:z-auto">
      <div className="bg-ink border-t border-line-soft">
        <div className="max-w-5xl mx-auto px-4 py-3">
          {/* Example chips */}
          <div className="flex flex-wrap gap-1.5 mb-2">
            {EXAMPLE_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => handleChipClick(chip)}
                className="font-mono text-[10px] px-2.5 py-1 rounded-full bg-ink-soft text-paper border border-line-soft hover:bg-line-soft transition-colors btn-press"
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Input row */}
          <div className="flex items-end gap-2">
            <span className="font-mono text-[10px] text-ink-faint uppercase tracking-[0.1em] shrink-0 pb-2 hidden sm:block">
              Asaas agent
            </span>
            <div className="flex-1 flex items-end gap-2 bg-ink-soft rounded-[10px] px-3 py-2 border border-line-soft">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your portfolio…"
                rows={1}
                className="flex-1 bg-transparent text-paper text-[13px] font-sans placeholder:text-ink-faint resize-none outline-none min-h-[24px] max-h-[120px]"
                aria-label="Chat message"
              />
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!input.trim() || isStreaming}
                className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-all duration-120',
                  input.trim() && !isStreaming
                    ? 'bg-jade text-white hover:bg-jade-dark active:scale-[0.95]'
                    : 'bg-line text-ink-faint cursor-not-allowed',
                )}
                aria-label="Send message"
              >
                <Send size={14} />
              </button>
            </div>
          </div>

          {/* Disclaimer */}
          <p className="font-mono text-[9px] text-ink-faint/60 mt-2 text-center">
            Suggestions, not financial advice
          </p>
        </div>
      </div>
    </div>
  )
}
