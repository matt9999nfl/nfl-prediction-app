/**
 * Formatting helpers.
 * All pure functions; no external dependencies beyond the standard library.
 */

// ── Numbers ───────────────────────────────────────────────────────────────────

export function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(decimals)}%`
}

export function formatPctRaw(value: number | null | undefined, decimals = 1): string {
  if (value == null) return '—'
  return `${value.toFixed(decimals)}%`
}

export function formatSpread(spread: number | null | undefined): string {
  if (spread == null) return 'PK'
  if (spread === 0) return 'PK'
  const sign = spread > 0 ? '+' : ''
  return `${sign}${spread.toFixed(1)}`
}

export function formatTotal(total: number | null | undefined): string {
  if (total == null) return '—'
  return total.toFixed(1)
}

export function formatYards(yards: number | null | undefined): string {
  if (yards == null) return '—'
  return yards.toLocaleString()
}

export function formatConfidence(prob: number): string {
  return `${Math.round(prob * 100)}%`
}

// ── Dates ─────────────────────────────────────────────────────────────────────

export function formatGameDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatDateTime(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatRelativeDate(isoDate: string): string {
  const date = new Date(isoDate)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / 86_400_000)
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return formatGameDate(isoDate)
}

// ── Teams ─────────────────────────────────────────────────────────────────────

/** Return the team's city name when given the nflfastR 2-3 letter code. */
export function teamName(code: string): string {
  const names: Record<string, string> = {
    ARI: 'Arizona', ATL: 'Atlanta', BAL: 'Baltimore', BUF: 'Buffalo',
    CAR: 'Carolina', CHI: 'Chicago', CIN: 'Cincinnati', CLE: 'Cleveland',
    DAL: 'Dallas', DEN: 'Denver', DET: 'Detroit', GB: 'Green Bay',
    HOU: 'Houston', IND: 'Indianapolis', JAX: 'Jacksonville', KC: 'Kansas City',
    LA: 'LA Rams', LAC: 'LA Chargers', LV: 'Las Vegas', MIA: 'Miami',
    MIN: 'Minnesota', NE: 'New England', NO: 'New Orleans', NYG: 'NY Giants',
    NYJ: 'NY Jets', PHI: 'Philadelphia', PIT: 'Pittsburgh', SEA: 'Seattle',
    SF: 'San Francisco', TB: 'Tampa Bay', TEN: 'Tennessee', WAS: 'Washington',
  }
  return names[code] ?? code
}

// ── Experiment targets & metrics ──────────────────────────────────────────────

export function targetLabel(target: string): string {
  const labels: Record<string, string> = {
    ats_cover: 'ATS Cover',
    outright_winner: 'Outright Winner',
    total_over: 'Total — Over',
    team_total_yards: 'Team Total Yards',
  }
  return labels[target] ?? target
}

export function metricLabel(metric: string): string {
  const labels: Record<string, string> = {
    ats_hit_rate: 'ATS Hit Rate',
    accuracy: 'Accuracy',
    log_loss: 'Log Loss',
    rmse: 'RMSE',
  }
  return labels[metric] ?? metric
}

// ── Misc ──────────────────────────────────────────────────────────────────────

export function truncate(s: string, maxLen: number): string {
  return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s
}
