import { useEffect, useRef } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface MonteCarloRangeProps {
  p10: number
  p50: number
  p90: number
  current?: number
  width?: number
  height?: number
}

const PAD = { left: 36, right: 36, top: 16, bottom: 28 }

function fmt(n: number): string {
  return n >= 1000
    ? `₨${(n / 1000).toFixed(0)}k`
    : `₨${n.toFixed(0)}`
}

export function MonteCarloRange({
  p10,
  p50,
  p90,
  current,
  width = 320,
  height = 80,
}: MonteCarloRangeProps) {
  const reduced = useReducedMotion()
  const lineRef = useRef<SVGLineElement>(null)

  const innerW = width - PAD.left - PAD.right
  const innerH = height - PAD.top - PAD.bottom

  const low = Math.min(p10, current ?? p10) * 0.97
  const high = Math.max(p90, current ?? p90) * 1.03

  const xScale = (v: number) => ((v - low) / (high - low)) * innerW

  const xP10 = xScale(p10)
  const xP50 = xScale(p50)
  const xP90 = xScale(p90)
  const xCurrent = current !== undefined ? xScale(current) : undefined

  const midY = innerH / 2
  const bandH = Math.max(innerH * 0.4, 8)

  // Animate current price marker on mount
  useEffect(() => {
    if (reduced || !lineRef.current || xCurrent === undefined) return
    const el = lineRef.current
    el.style.transform = `translateX(${-(xCurrent ?? 0)}px)`
    el.style.transition = 'none'
    requestAnimationFrame(() => {
      el.style.transition = 'transform 200ms cubic-bezier(0.23,1,0.32,1)'
      el.style.transform = 'translateX(0)'
    })
  }, [reduced, xCurrent])

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-label={`Monte Carlo range: p10 ${fmt(p10)}, p50 ${fmt(p50)}, p90 ${fmt(p90)}${current ? `, current ${fmt(current)}` : ''}`}
      role="img"
    >
      <g transform={`translate(${PAD.left},${PAD.top})`}>
        {/* P10–P90 band */}
        <rect
          x={xP10}
          y={midY - bandH / 2}
          width={xP90 - xP10}
          height={bandH}
          rx={4}
          fill="#E2E9EE"
        />

        {/* P50 tick */}
        <line
          x1={xP50}
          y1={midY - bandH / 2 - 4}
          x2={xP50}
          y2={midY + bandH / 2 + 4}
          stroke="#7C867F"
          strokeWidth={1}
          strokeDasharray="3 2"
        />

        {/* Current price marker */}
        {xCurrent !== undefined && (
          <g ref={lineRef as React.Ref<SVGGElement>}>
            <line
              x1={xCurrent}
              y1={midY - bandH / 2 - 6}
              x2={xCurrent}
              y2={midY + bandH / 2 + 6}
              stroke="#0F6E56"
              strokeWidth={2}
              strokeLinecap="round"
            />
          </g>
        )}

        {/* Labels */}
        <text x={xP10} y={innerH + 14} textAnchor="middle" fontSize={10} fill="#7C867F" fontFamily="IBM Plex Mono, monospace">
          {fmt(p10)}
        </text>
        <text x={xP90} y={innerH + 14} textAnchor="middle" fontSize={10} fill="#7C867F" fontFamily="IBM Plex Mono, monospace">
          {fmt(p90)}
        </text>
        {xCurrent !== undefined && current !== undefined && (
          <text x={xCurrent} y={PAD.top - 20} textAnchor="middle" fontSize={10} fill="#0F6E56" fontFamily="IBM Plex Mono, monospace">
            {fmt(current)}
          </text>
        )}
      </g>
    </svg>
  )
}
