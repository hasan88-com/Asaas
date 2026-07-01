import { memo, useMemo } from 'react'
import { Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
} from 'chart.js'
import type { HoldingResponse } from '@/types/api'
import { useTheme } from '@/context/ThemeContext'
import { cssVarRgb } from '@/lib/themeColor'

ChartJS.register(ArcElement, Tooltip)

/**
 * Canonical per-asset-class colour palette.
 * equity = jade green, crypto = purple, tbill/bond = amber, commodity = coral.
 */
export const ASSET_CLASS_COLORS: Record<string, string> = {
  equity: '#1D9E75',
  stock: '#1D9E75',
  psx_stock: '#1D9E75',
  crypto: '#7F77DD',
  tbill: '#BA7517',
  bond: '#BA7517',
  commodity: '#D85A30',
  fund: '#3E7C8C',
}

const FALLBACK_COLOR = '#A0ADB8'

/** Human-readable asset-class label used in donut labels and legends. */
export function assetClassLabel(ac?: string): string {
  switch ((ac ?? '').toLowerCase()) {
    case 'equity':
    case 'stock':
    case 'psx_stock': return 'Equity'
    case 'crypto': return 'Crypto'
    case 'tbill': return 'T-Bill'
    case 'bond': return 'Bond'
    case 'commodity': return 'Commodity'
    case 'fund': return 'Fund'
    default: return ac ? ac.charAt(0).toUpperCase() + ac.slice(1) : 'Other'
  }
}

export function assetClassColor(ac?: string): string {
  return ASSET_CLASS_COLORS[(ac ?? '').toLowerCase()] ?? FALLBACK_COLOR
}

/** Build the "SYMBOL (Asset)" label for a holding. */
export function holdingLabel(h: Pick<HoldingResponse, 'symbol' | 'name' | 'asset_class'>): string {
  const sym = h.symbol || h.name || '—'
  return `${sym} (${assetClassLabel(h.asset_class)})`
}

interface AllocationDonutProps {
  /** Holdings-driven mode (default). Labels/colours derived from each holding. */
  holdings?: HoldingResponse[]
  /** Explicit mode — caller supplies parallel arrays. Overrides `holdings`. */
  labels?: string[]
  data?: number[]
  colors?: string[]
  size?: number
  /** Center label override — defaults to "Allocation" */
  centerLabel?: string
  /** Optional value shown under the center label (e.g. total portfolio value). */
  centerValue?: string
}

function AllocationDonutImpl({
  holdings,
  labels,
  data,
  colors,
  size = 180,
  centerLabel = 'Allocation',
  centerValue,
}: AllocationDonutProps) {
  const { theme } = useTheme()
  const chartData = useMemo(() => {
    // Explicit arrays win; otherwise derive from holdings.
    const finalLabels = labels ?? (holdings ?? []).map((h) => holdingLabel(h))
    const finalData = data ?? (holdings ?? []).map((h) => h.weight * 100)
    const finalColors = colors ?? (holdings ?? []).map((h) => assetClassColor(h.asset_class))
    return {
      labels: finalLabels,
      datasets: [
        {
          data: finalData,
          backgroundColor: finalColors,
          // Segment separators match the card surface so they read as gaps in
          // both light and dark themes (not white slivers on a dark card).
          borderColor: cssVarRgb('--card'),
          borderWidth: 2,
          hoverOffset: 4,
        },
      ],
    }
  }, [holdings, labels, data, colors, theme])

  const options = useMemo(() => ({
    cutout: '68%',
    // Disabled so the donut never re-animates on a parent re-render (no flicker).
    animation: false as const,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: { label: string; raw: unknown }) =>
            `${ctx.label}: ${(ctx.raw as number).toFixed(1)}%`,
        },
      },
    },
  }), [])

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <Doughnut data={chartData} options={options} />
      {/* Center overlay */}
      <div
        className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
        aria-hidden="true"
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-faint">
          {centerLabel}
        </span>
        {centerValue && (
          <span className="font-display font-semibold text-ink leading-tight tabular-nums"
            style={{ fontSize: Math.max(13, Math.round(size * 0.13)) }}>
            {centerValue}
          </span>
        )}
      </div>
    </div>
  )
}

export const AllocationDonut = memo(AllocationDonutImpl)
