import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { streamChat } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function NewsChat() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Hello! I\'m your Pakistan market news analyst. Ask me anything about PSX stocks, SBP rates, T-bills, commodities, crypto, or how current events affect your portfolio.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const q = input.trim()
    if (!q || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      await streamChat(q, {
        onContent: (delta) => {
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant') {
              return [...prev.slice(0, -1), { role: 'assistant', content: last.content + delta }]
            }
            return [...prev, { role: 'assistant', content: delta }]
          })
        },
        onDone: () => setLoading(false),
      })
    } catch {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: 'Connection error. Make sure you\'re logged in and the server is running.',
      }])
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-48px)]">
      <header className="flex items-center justify-between px-4 h-12 border-b border-line bg-card shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-display text-[16px] font-semibold text-ink">News Analyst</span>
          <span className="font-mono text-[10px] text-ink-faint bg-jade-soft px-1.5 py-0.5 rounded">AI</span>
        </div>
        <Button variant="ghost" onClick={() => navigate('/news')} className="text-[12px]">
          ← Back to News
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              'max-w-[85%] px-4 py-3 rounded-[12px] font-sans text-[14px] leading-[1.5]',
              msg.role === 'user'
                ? 'bg-jade text-white ml-auto rounded-br-[4px]'
                : 'bg-card border border-line text-ink rounded-bl-[4px]',
            )}
          >
            {msg.content}
          </div>
        ))}
        {loading && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="bg-card border border-line rounded-[12px] rounded-bl-[4px] px-4 py-3 max-w-[85%]">
            <span className="w-2 h-2 rounded-full bg-jade animate-pulse inline-block" />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="px-4 py-3 border-t border-line bg-card">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about market news, rates, or portfolio impact…"
            className="flex-1 bg-paper border border-line rounded-[8px] px-3 py-2.5 text-[14px] text-ink placeholder:text-ink-faint focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2"
            disabled={loading}
          />
          <Button variant="primary" onClick={handleSend} disabled={loading || !input.trim()} className="btn-press">
            {loading ? '…' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  )
}
