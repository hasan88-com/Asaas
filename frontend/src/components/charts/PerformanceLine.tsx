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
import type { TooltipItem, ScriptableContext } from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Filler)

interface DataPoint {
  date: string
  value: string
}

interface PerformanceLineProps {
  history: DataPoint[]
  height?: number
  lineColor?: string
  isPositive?: boolean
}

function fmtPKR(n: number): string {
  if (n >= 1_000_000) return `₨${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `₨${(n / 1_000).toFixed(1)}K`
  return `₨${n.toFixed(0)}`
}

function PerformanceLineImpl({
  history,
  height = 280,
  lineColor = '#10CFAA',
  isPositive = true,
}: PerformanceLineProps) {
  const color = isPositive ? '#10CFAA' : '#FF6B6B'

  const data = useMemo(() => {
    const labels = history.map((d) => {
      const dt = new Date(d.date)
      return dt.toLocaleDateString('en-PK', { month: 'short', day: 'numeric' })
    })
    const values = history.map((d) => parseFloat(d.value))

    return {
      labels,
      datasets: [
        {
          data: values,
          borderColor: color,
          borderWidth: 2,
          tension: 0.42,
          fill: true,
          backgroundColor: (ctx: ScriptableContext<'line'>) => {
            const chart = ctx.chart
            const { ctx: canvasCtx, chartArea } = chart
            if (!chartArea) return 'transparent'
            const gradient = canvasCtx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom)
            gradient.addColorStop(0, `${color}40`)
            gradient.addColorStop(0.5, `${color}18`)
            gradient.addColorStop(1, `${color}00`)
            return gradient
          },
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: color,
          pointHoverBorderColor: '#1A2420',
          pointHoverBorderWidth: 2,
        },
      ],
    }
  }, [history, color])

  const options = useMemo(() => ({
    animation: false as const,
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0E1B17',
        borderColor: `${color}60`,
        borderWidth: 1,
        titleColor: '#6B8A80',
        bodyColor: '#E8F5F1',
        padding: 10,
        titleFont: { family: 'ui-monospace, monospace', size: 11 },
        bodyFont: { family: 'ui-monospace, monospace', size: 13, weight: 600 as const },
        callbacks: {
          label: (item: TooltipItem<'line'>) => ` ${fmtPKR(item.parsed?.y ?? 0)}`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: {
          color: '#4A6B60',
          font: { family: 'ui-monospace, monospace', size: 10 },
          maxTicksLimit: 7,
          maxRotation: 0,
        },
      },
      y: {
        position: 'right' as const,
        grid: {
          color: 'rgba(255,255,255,0.04)',
          lineWidth: 1,
        },
        border: { display: false },
        ticks: {
          color: '#4A6B60',
          font: { family: 'ui-monospace, monospace', size: 10 },
          callback: (v: number | string) => fmtPKR(Number(v)),
          maxTicksLimit: 5,
        },
      },
    },
  }), [color])

  if (history.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2"
        style={{ height }}
      >
        <div className="w-8 h-8 rounded-full border border-dashed border-white/10 flex items-center justify-center">
          <span className="text-white/20 text-lg">~</span>
        </div>
        <p className="text-[11px] text-white/25 font-mono">No history yet — snapshotted daily</p>
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
