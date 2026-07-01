import { memo, useMemo } from 'react'
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Filler,
} from 'chart.js'
import type { TooltipItem } from 'chart.js'
import { Line } from 'react-chartjs-2'
import { useTheme } from '@/context/ThemeContext'
import { cssVarRgb } from '@/lib/themeColor'

ChartJS.register(LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Filler)

interface DataPoint {
  date: string
  value: string
}

interface PerformanceLineProps {
  history: DataPoint[]
  height?: number
  lineColor?: string
}

function fmtPKR(n: number): string {
  if (n >= 1_000_000) return `₨${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `₨${(n / 1_000).toFixed(0)}K`
  return `₨${n.toFixed(0)}`
}

function PerformanceLineImpl({ history, height = 240, lineColor }: PerformanceLineProps) {
  const { theme } = useTheme()
  const line = lineColor ?? cssVarRgb('--jade')
  const data = useMemo(() => {
    const labels = history.map((d) => {
      const dt = new Date(d.date)
      return dt.toLocaleDateString('en-PK', { month: 'short', day: 'numeric' })
    })
    const values = history.map((d) => parseFloat(d.value))
    const fillColor = cssVarRgb('--jade', 0.1)

    return {
      labels,
      datasets: [
        {
          data: values,
          borderColor: line,
          borderWidth: 2.5,
          tension: 0.35,
          fill: true,
          backgroundColor: fillColor,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: line,
          pointHoverBorderColor: cssVarRgb('--card'),
          pointHoverBorderWidth: 2,
        },
      ],
    }
  }, [history, line, theme])

  const options = useMemo(() => ({
    // Disabled so the chart never re-animates on a parent re-render (no flicker).
    animation: false as const,
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: cssVarRgb('--ink'),
        borderColor: cssVarRgb('--line'),
        borderWidth: 1,
        titleColor: cssVarRgb('--ink-faint'),
        bodyColor: cssVarRgb('--paper'),
        titleFont: { family: '"IBM Plex Mono"', size: 11 },
        bodyFont: { family: '"IBM Plex Mono"', size: 13, weight: 500 as const },
        callbacks: {
          label: (tooltipItem: TooltipItem<'line'>) => fmtPKR(tooltipItem.parsed?.y ?? 0),
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: {
          color: cssVarRgb('--ink-faint'),
          font: { family: '"IBM Plex Mono"', size: 11 },
          maxTicksLimit: 6,
        },
      },
      y: {
        position: 'left' as const,
        grid: { color: cssVarRgb('--line'), lineWidth: 1 },
        border: { display: false, dash: [3, 3] },
        ticks: {
          color: cssVarRgb('--ink-faint'),
          font: { family: '"IBM Plex Mono"', size: 11 },
          callback: (v: number | string) => fmtPKR(Number(v)),
        },
      },
    },
  }), [theme])

  if (history.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-card rounded-[10px] border border-line"
        style={{ height }}
      >
        <p className="font-mono text-[12px] text-ink-faint">No performance data yet</p>
      </div>
    )
  }

  return (
    <div style={{ height }}>
      <Line data={data} options={options} />
    </div>
  )
}

export const PerformanceLine = memo(PerformanceLineImpl)
