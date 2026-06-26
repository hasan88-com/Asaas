import { useEffect, useRef } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface UserMessageProps {
  text: string
}

export function UserMessage({ text }: UserMessageProps) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    if (reduced || !ref.current) return
    const el = ref.current
    el.style.opacity = '0'
    el.style.transform = 'translateY(6px)'
    // Use rAF so styles are applied before transition starts
    requestAnimationFrame(() => {
      el.style.transition = 'opacity 200ms cubic-bezier(0.23,1,0.32,1), transform 200ms cubic-bezier(0.23,1,0.32,1)'
      el.style.opacity = '1'
      el.style.transform = 'translateY(0)'
    })
  }, [reduced])

  return (
    <div ref={ref} className="flex justify-end">
      <div
        className="max-w-[80%] bg-jade-soft text-ink px-4 py-2.5 rounded-[14px] rounded-br-[4px] text-[16px] leading-[1.6] whitespace-pre-wrap break-words"
      >
        {text}
      </div>
    </div>
  )
}
