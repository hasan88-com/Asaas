import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CardShell } from './CardShell'
import { putProfile } from '@/lib/api'
import type { ProfileResponse } from '@/types/api'

const ACCENT = '#2F4858'

const HORIZON_LABEL: Record<string, string> = {
  short: 'Short-term',
  medium: 'Medium-term',
  long: 'Long-term',
}

interface ProfilerCardProps {
  data: ProfileResponse
}

export function ProfilerCard({ data }: ProfilerCardProps) {
  const handleConfirm = async () => {
    await putProfile(data)
  }

  return (
    <CardShell
      eyebrow="Investor Profile"
      accentColor={ACCENT}
      actions={
        <Button onClick={handleConfirm} variant="primary" size="sm">
          Confirm profile
        </Button>
      }
    >
      <div className="flex flex-wrap gap-1.5 mb-3">
        <Badge variant="info">{data.risk_tolerance}</Badge>
        <Badge variant="info">{HORIZON_LABEL[data.horizon] ?? data.horizon}</Badge>
        <Badge variant="info">{data.goal}</Badge>
      </div>
    </CardShell>
  )
}
