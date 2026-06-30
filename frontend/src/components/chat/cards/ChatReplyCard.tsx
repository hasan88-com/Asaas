import { CardShell } from './CardShell'

const ACCENT = '#0F6E56'

interface ChatReplyCardProps {
  text: string
}

export function ChatReplyCard({ text }: ChatReplyCardProps) {
  return (
    <CardShell eyebrow="Asaasa" accentColor={ACCENT}>
      <p className="text-[16px] leading-[1.6] text-ink whitespace-pre-wrap">{text}</p>
    </CardShell>
  )
}
