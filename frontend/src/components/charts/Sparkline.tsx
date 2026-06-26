interface SparklineProps {
  data: number[]
  positive?: boolean
  width?: number
  height?: number
}

export function Sparkline({ data, positive = true, width = 64, height = 24 }: SparklineProps) {
  if (data.length < 2) return <span style={{ width, height, display: 'inline-block' }} />

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / range) * height
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const color = positive ? '#0F6E56' : '#A8401F'

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      style={{ display: 'block' }}
    >
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
