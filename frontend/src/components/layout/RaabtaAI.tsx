import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/utils'
import {
  streamChat,
  getConversations,
  createConversation,
  getConversationMessages,
  deleteConversation,
} from '@/lib/api'
import type { Conversation, ConversationMessage } from '@/types/api'

type Msg = { role: 'user' | 'assistant'; content: string }

const STARTERS = [
  'Optimise my portfolio',
  "What's my risk score?",
  'Explain diversification',
  'Value my top holding',
]

/**
 * Raabta AI — the in-app assistant for Asaasa. A floating, animated bot button
 * (every page, palette colours, mobile-friendly) that opens a ChatGPT-style
 * panel with saved conversations. Scoped on the backend to the user's portfolio,
 * investing/education, and the Asaasa platform.
 */
export function RaabtaAI() {
  const [open, setOpen] = useState(false)
  const [showList, setShowList] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (open) refreshConversations()
  }, [open])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function refreshConversations() {
    try {
      setConversations(await getConversations())
    } catch {
      /* fail-open: empty list */
    }
  }

  async function openConversation(id: string) {
    setActiveId(id)
    setShowList(false)
    setMessages([])
    try {
      const msgs: ConversationMessage[] = await getConversationMessages(id)
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })))
    } catch {
      /* leave empty */
    }
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
    setShowList(false)
    setInput('')
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    await deleteConversation(id).catch(() => {})
    if (id === activeId) newChat()
    refreshConversations()
  }

  async function send(text: string) {
    const msg = text.trim()
    if (!msg || sending) return
    setInput('')
    setSending(true)
    setMessages((m) => [...m, { role: 'user', content: msg }, { role: 'assistant', content: '' }])

    try {
      // Ensure a conversation thread exists so the message is saved + titled.
      let convId = activeId
      if (!convId) {
        const conv = await createConversation()
        convId = conv.id
        setActiveId(conv.id)
      }
      const ctrl = new AbortController()
      abortRef.current = ctrl
      await streamChat(
        msg,
        {
          onContent: (delta) =>
            setMessages((m) => {
              const next = [...m]
              next[next.length - 1] = {
                role: 'assistant',
                content: next[next.length - 1].content + delta,
              }
              return next
            }),
        },
        ctrl.signal,
        convId,
      )
      refreshConversations() // pick up the auto-generated title
    } catch {
      setMessages((m) => {
        const next = [...m]
        next[next.length - 1] = { role: 'assistant', content: 'Something went wrong — please try again.' }
        return next
      })
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }

  // Let any page open Raabta AI (optionally with a seeded question) by dispatching
  // window CustomEvent('raabta:ask', { detail: { message } }). Used by the News
  // page's "Affect on my portfolio?" action.
  const sendRef = useRef(send)
  sendRef.current = send
  useEffect(() => {
    const handler = (e: Event) => {
      setOpen(true)
      const msg = (e as CustomEvent).detail?.message as string | undefined
      if (msg) {
        setActiveId(null)
        setMessages([])
        setShowList(false)
        setTimeout(() => sendRef.current(msg), 60)
      }
    }
    window.addEventListener('raabta:ask', handler)
    return () => window.removeEventListener('raabta:ask', handler)
  }, [])

  return (
    <>
      {/* keyframes for the bot button */}
      <style>{`
        @keyframes raabta-float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }
        @keyframes raabta-blink { 0%,90%,100%{opacity:1} 95%{opacity:.2} }
        @keyframes raabta-ring { 0%{transform:scale(1);opacity:.45} 100%{transform:scale(1.8);opacity:0} }
        @keyframes raabta-typing { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-4px);opacity:1} }
        @keyframes raabta-shimmer { 0%,100%{opacity:.4} 50%{opacity:1} }
        @keyframes raabta-spin { to{transform:rotate(360deg)} }
        .raabta-dot { width:6px;height:6px;border-radius:9999px;background:#0F6E56;display:inline-block; }
        .raabta-shimmer { animation: raabta-shimmer 1.3s ease-in-out infinite; }
        /* Compact, aligned markdown inside the chat bubble */
        .raabta-md { font-size:13px; line-height:1.5; }
        .raabta-md > *:first-child { margin-top:0; }
        .raabta-md > *:last-child { margin-bottom:0; }
        .raabta-md h1,.raabta-md h2,.raabta-md h3 { font-size:12px; font-weight:600; margin:10px 0 4px; color:#16201C; text-transform:uppercase; letter-spacing:.04em; }
        .raabta-md p { margin:4px 0; }
        .raabta-md ul { margin:4px 0; padding-left:16px; list-style:disc; }
        .raabta-md li { margin:2px 0; }
        .raabta-md strong { font-weight:600; }
        .raabta-md hr { display:none; }
      `}</style>

      {/* Floating launcher */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open Raabta AI"
          className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-white shadow-lg flex items-center justify-center border border-line hover:shadow-xl transition-shadow focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2"
          style={{ animation: 'raabta-float 3s ease-in-out infinite' }}
        >
          <span
            className="absolute inset-0 rounded-full bg-jade/40"
            style={{ animation: 'raabta-ring 2.4s ease-out infinite' }}
            aria-hidden
          />
          <img src="/logo.png" alt="Raabta AI" className="relative w-9 h-9 object-contain" />
        </button>
      )}

      {/* Click-outside backdrop — dismisses the panel back to the floating icon */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-ink/10"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}

      {/* Panel */}
      {open && (
        <div
          className={cn(
            'fixed z-50 bg-card border border-line shadow-xl flex flex-col overflow-hidden',
            'inset-0 rounded-none', // mobile: full-screen
            'sm:inset-auto sm:bottom-5 sm:right-5 sm:w-[400px] sm:h-[620px] sm:max-h-[85vh] sm:rounded-[14px]',
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 h-14 border-b border-line bg-ink text-paper shrink-0">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowList((s) => !s)}
                className="p-1 -ml-1 rounded hover:bg-white/10"
                aria-label="Conversations"
              >
                <MenuIcon />
              </button>
              <span className="w-6 h-6 rounded-full bg-white flex items-center justify-center shrink-0">
                <img src="/logo.png" alt="" className="w-5 h-5 object-contain" />
              </span>
              <span className="font-display text-[15px] font-semibold">Raabta AI</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={newChat}
                className="px-2 py-1 rounded text-[12px] font-mono hover:bg-white/10"
              >
                + New
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1 rounded hover:bg-white/10"
                aria-label="Close"
              >
                <CloseIcon />
              </button>
            </div>
          </div>

          {/* Conversation list overlay */}
          {showList && (
            <div className="flex-1 overflow-y-auto p-2">
              <button
                type="button"
                onClick={newChat}
                className="w-full text-left px-3 py-2.5 rounded-[8px] text-jade font-sans text-[13px] hover:bg-jade-soft"
              >
                + New chat
              </button>
              {conversations.length === 0 ? (
                <p className="px-3 py-4 text-[13px] text-ink-faint font-sans">No conversations yet.</p>
              ) : (
                conversations.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => openConversation(c.id)}
                    className={cn(
                      'group flex items-center justify-between gap-2 px-3 py-2.5 rounded-[8px] cursor-pointer',
                      c.id === activeId ? 'bg-jade-soft' : 'hover:bg-paper',
                    )}
                  >
                    <span className="font-sans text-[13px] text-ink truncate">{c.title}</span>
                    <button
                      type="button"
                      onClick={(e) => handleDelete(c.id, e)}
                      className="opacity-0 group-hover:opacity-100 text-ink-faint hover:text-loss text-[15px] leading-none px-1"
                      aria-label="Delete conversation"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Messages */}
          {!showList && (
            <>
              <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
                {messages.length === 0 ? (
                  <div className="flex flex-col gap-3 mt-2">
                    <p className="font-sans text-[14px] text-ink-soft">
                      Hi — I'm Raabta AI. Ask me about your portfolio, investing, or how to use Asaasa.
                    </p>
                    <div className="flex flex-col gap-2">
                      {STARTERS.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => send(s)}
                          className="text-left px-3 py-2 rounded-[8px] border border-line text-[13px] font-sans text-ink hover:border-jade hover:bg-jade-soft transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((m, i) => {
                    const empty = !m.content && sending && i === messages.length - 1
                    return (
                      <div
                        key={i}
                        className={cn(
                          'max-w-[88%] px-3 py-2 rounded-[10px] text-[13px] leading-[1.5]',
                          m.role === 'user'
                            ? 'self-end bg-jade text-white font-sans whitespace-pre-wrap'
                            : 'self-start bg-paper border border-line text-ink',
                        )}
                      >
                        {empty ? (
                          <ThinkingIndicator />
                        ) : m.role === 'assistant' ? (
                          <div className="raabta-md">
                            <ReactMarkdown>{m.content}</ReactMarkdown>
                          </div>
                        ) : (
                          m.content
                        )}
                      </div>
                    )
                  })
                )}
              </div>

              {/* Composer */}
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  send(input)
                }}
                className="border-t border-line p-3 flex items-end gap-2 shrink-0"
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      send(input)
                    }
                  }}
                  rows={1}
                  placeholder="Ask Raabta AI…"
                  className="flex-1 resize-none bg-paper border border-line rounded-[10px] px-3 py-2 font-sans text-[13px] text-ink max-h-28 focus:outline-none focus:border-jade"
                />
                <button
                  type="submit"
                  disabled={sending || !input.trim()}
                  className="w-9 h-9 rounded-full bg-jade text-white flex items-center justify-center disabled:opacity-40 hover:bg-[#0d5e49] transition-colors shrink-0"
                  aria-label="Send"
                >
                  <SendIcon />
                </button>
              </form>
              <p className="text-center text-[10px] font-mono text-ink-faint pb-2">
                Suggestions, not financial advice
              </p>
            </>
          )}
        </div>
      )}
    </>
  )
}

/* ---- inline icons (palette-coloured, no extra deps) ---------------------- */

function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-0.5" aria-label="typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="raabta-dot"
          style={{ animation: `raabta-typing 1.2s ease-in-out ${i * 0.15}s infinite` }}
        />
      ))}
    </span>
  )
}

function ThinkingIndicator() {
  return (
    <span className="flex items-center gap-2" aria-label="Raabta AI is thinking">
      <span className="relative w-5 h-5 shrink-0 flex items-center justify-center">
        <span
          className="absolute inset-0 rounded-full bg-jade/30"
          style={{ animation: 'raabta-ring 1.6s ease-out infinite' }}
          aria-hidden
        />
        <img
          src="/logo.png"
          alt=""
          className="relative w-5 h-5 object-contain"
          style={{ animation: 'raabta-float 2s ease-in-out infinite' }}
        />
      </span>
      <span className="raabta-shimmer font-sans text-[12px] text-ink-soft">Thinking</span>
      <TypingDots />
    </span>
  )
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function MenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
