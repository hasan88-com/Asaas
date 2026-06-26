import { Badge } from '@/components/ui/badge'
import { CardShell } from './CardShell'
import { cn } from '@/lib/utils'
import type { NewsItemResponse } from '@/types/api'

const ACCENT = '#993556'

const IMPACT_ICON: Record<string, string> = {
  positive: '↑',
  negative: '↓',
  neutral: '→',
}

const IMPACT_CLASS: Record<string, string> = {
  positive: 'text-gain',
  negative: 'text-loss',
  neutral: 'text-ink-faint',
}

const LEVEL_VARIANT: Record<string, 'default' | 'info' | 'gain' | 'loss' | 'gold' | 'neutral'> = {
  direct: 'info',
  sector: 'gold',
  macro: 'neutral',
}

interface NewsCardProps {
  items: NewsItemResponse[]
}

export function NewsCard({ items }: NewsCardProps) {
  return (
    <CardShell eyebrow="News Materiality" accentColor={ACCENT}>
      <ul className="flex flex-col gap-3">
        {items.map((item, i) => (
          <li
            key={item.url || i}
            className="flex items-start gap-2.5 animate-slide-up"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            {/* Impact icon — color + symbol, never color alone */}
            <span
              className={cn('font-mono text-[14px] font-semibold mt-0.5 shrink-0 w-4', IMPACT_CLASS[item.impact])}
              aria-label={`Impact: ${item.impact}`}
            >
              {IMPACT_ICON[item.impact]}
            </span>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="font-mono text-[10px] uppercase tracking-wide bg-paper border border-line px-1.5 py-0.5 rounded-sm text-ink-faint shrink-0">
                  {item.source}
                </span>
                <Badge variant={LEVEL_VARIANT[item.impact_level] ?? 'neutral'}>
                  {item.impact_level}
                </Badge>
              </div>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[14px] leading-[1.5] text-ink hover:underline focus-visible:outline-2 focus-visible:outline-jade focus-visible:outline-offset-2 block"
              >
                {item.headline}
              </a>
            </div>
          </li>
        ))}
      </ul>
    </CardShell>
  )
}
