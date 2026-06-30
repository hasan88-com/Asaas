import { useRef, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface ComposerProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const resize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const lineHeight = 24
    const maxRows = 5
    const maxHeight = lineHeight * maxRows + 24 // padding
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    resize()
  }

  const submit = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, disabled, onSend])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 p-3 border-t border-line bg-paper">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Ask Asaasa…"
        disabled={disabled}
        aria-label="Message"
        className={cn(
          'flex-1 resize-none bg-card border border-line rounded-[10px] px-3.5 py-2.5',
          'text-[16px] leading-[1.6] text-ink placeholder:text-ink-faint',
          'focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2',
          'disabled:opacity-40 disabled:cursor-not-allowed',
          'overflow-y-auto min-h-[44px]',
        )}
        style={{ height: 'auto' }}
      />
      <Button
        onClick={submit}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="shrink-0 self-end mb-0"
      >
        Send
      </Button>
    </div>
  )
}
