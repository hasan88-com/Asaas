import { useEffect, useRef } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface RSIGaugeProps {
  value: number
  size?: number
}

const R = 44
const CX = 60
const CY = 56
const STROKE = 10

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const toRad = (d: number) => ((d - 90) * Math.PI) / 180
  const x1 = cx + r * Math.cos(toRad(startDeg))
  const y1 = cy + r * Math.sin(toRad(startDeg))
  const x2 = cx + r * Math.cos(toRad(endDeg))
  const y2 = cy + r * Math.sin(toRad(endDeg))
  const large = endDeg - startDeg > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
}

// RSI 0–100 maps to 180 degrees (9 o'clock → 3 o'clock via bottom)
function rsiToDeg(rsi: number): number {
  return (rsi / 100) * 180 - 90 // -90 → 90 degrees offset from 12 o'clock
}

export function RSIGauge({ value, size = 120 }: RSIGaugeProps) {
  const reduced = useReducedMotion()
  const needleRef = useRef<SVGLineElement>(null)

  const scale = size / 120
  const viewW = 120
  const viewH = 70

  const clampedRSI = Math.max(0, Math.min(100, value))

  // Semicircle from 180° to 360° (left to right)
  // We split into 3 colored zones: 0–30 (jade-soft), 30–70 (line), 70–100 (loss-soft)
  // Each maps to 0–54°, 54°–126°, 126°–180° of the semicircle
  const zones = [
    { from: 180, to: 234, fill: '#E1F1EA' }, // 0–30 oversold (jade-soft)
    { from: 234, to: 306, fill: '#DCD8CC' }, // 30–70 neutral (line)
    { from: 306, to: 360, fill: '#F6E3DA' }, // 70–100 overbought (loss-soft)
  ]

  // Needle angle: RSI 0 → 180°, RSI 100 → 360°
  const needleAngleDeg = 180 + (clampedRSI / 100) * 180
  const needleRad = (needleAngleDeg * Math.PI) / 180
  const needleLen = R - STROKE / 2 - 2
  const nx = CX + needleLen * Math.cos(needleRad)
  const ny = CY + needleLen * Math.sin(needleRad)

  useEffect(() => {
    if (reduced || !needleRef.current) return
    const el = needleRef.current

    // Start at RSI=0 angle (left = 180°)
    const startAngle = 180
    const endAngle = needleAngleDeg
    const startRad = (startAngle * Math.PI) / 180
    const snx = CX + needleLen * Math.cos(startRad)
    const sny = CY + needleLen * Math.sin(startRad)
    el.setAttribute('x2', String(snx))
    el.setAttribute('y2', String(sny))

    requestAnimationFrame(() => {
      el.style.transition = 'x2 200ms cubic-bezier(0.23,1,0.32,1), y2 200ms cubic-bezier(0.23,1,0.32,1)'
      el.setAttribute('x2', String(nx))
      el.setAttribute('y2', String(ny))
      // CSS transitions don't apply to SVG attributes natively; use SMIL or transform
      // Fallback: set directly (no animation in older browsers)
      void endAngle
    })
  }, [reduced, needleAngleDeg, nx, ny, needleLen])

  const label =
    clampedRSI < 30 ? 'Oversold' : clampedRSI > 70 ? 'Overbought' : 'Neutral'
  const labelColor =
    clampedRSI < 30 ? '#0F6E56' : clampedRSI > 70 ? '#A8401F' : '#7C867F'

  return (
    <figure aria-label={`RSI ${clampedRSI.toFixed(1)} — ${label}`} style={{ margin: 0 }}>
      <svg
        width={size}
        height={size * (viewH / viewW)}
        viewBox={`0 0 ${viewW} ${viewH}`}
        overflow="visible"
      >
        {/* Zone arcs */}
        {zones.map((z) => (
          <path
            key={z.from}
            d={arcPath(CX, CY, R, z.from, z.to)}
            fill="none"
            stroke={z.fill}
            strokeWidth={STROKE}
            strokeLinecap="butt"
          />
        ))}

        {/* Needle */}
        <line
          ref={needleRef}
          x1={CX}
          y1={CY}
          x2={nx}
          y2={ny}
          stroke="#16201C"
          strokeWidth={2}
          strokeLinecap="round"
        />

        {/* Center dot */}
        <circle cx={CX} cy={CY} r={3} fill="#16201C" />

        {/* RSI value */}
        <text
          x={CX}
          y={CY - 10}
          textAnchor="middle"
          fontSize={13}
          fontWeight={500}
          fill="#16201C"
          fontFamily="IBM Plex Mono, monospace"
        >
          {clampedRSI.toFixed(1)}
        </text>

        {/* Label */}
        <text
          x={CX}
          y={CY + 14}
          textAnchor="middle"
          fontSize={9}
          fill={labelColor}
          fontFamily="IBM Plex Mono, monospace"
          fontWeight={600}
          letterSpacing="0.08em"
        >
          {label.toUpperCase()}
        </text>
      </svg>
      <figcaption className="sr-only">
        RSI {clampedRSI.toFixed(1)} — {label}
      </figcaption>
    </figure>
  )
}
