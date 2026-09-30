export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

// Cost is in SYNTHETIC_UNITS (see data/raw/gtfs/fares.csv) — never a real
// currency symbol, which would misrepresent synthetic development data.
export function formatCost(cost: number): string {
  return `${cost.toFixed(2)} units`
}

export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

// Always 'en-US' grouping (1,234,567) — deliberately NOT the ambient/OS
// locale, which varies by machine (e.g. en-IN groups as 12,34,567) and
// would make the same real number render inconsistently.
export function formatCount(n: number): string {
  return n.toLocaleString('en-US')
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}
