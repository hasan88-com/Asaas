/**
 * Resolve a palette CSS variable (stored as "R G B" channels in globals.css)
 * to a concrete `rgb(...)` string. Canvas/SVG charts can't read CSS variables,
 * so charts call this at render time (keyed on the active theme) to pick up the
 * light/dark value. `alpha` returns an `rgba(...)` string when < 1.
 */
export function cssVarRgb(name: string, alpha = 1): string {
  if (typeof document === 'undefined') return '#000'
  const channels = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!channels) return '#000'
  return alpha >= 1 ? `rgb(${channels})` : `rgb(${channels} / ${alpha})`
}
