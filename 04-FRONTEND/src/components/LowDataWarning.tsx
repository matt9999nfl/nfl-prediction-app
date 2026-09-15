import { AlertTriangle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface LowDataWarningProps {
  week: number
}

/**
 * True for weeks where a team's season-to-date features rest on little or no
 * current-season data (week 1: zero 2026 games; week 2: one game per team).
 *
 * This is a stopgap for the current-season-only feature pipeline. Once
 * blended prior-season features are live, this should be updated to say what
 * the picks are actually built on, or removed.
 */
export function isLowDataWeek(week: number): boolean {
  return week <= 2
}

export function LowDataWarning({ week }: LowDataWarningProps) {
  if (!isLowDataWeek(week)) return null

  const detail =
    week === 1
      ? "last season's data only — no 2026 games have been played yet"
      : 'one game of 2026 data per team'

  return (
    <Alert variant="warning" className="mb-4">
      <AlertTriangle className="h-4 w-4" />
      <AlertDescription>
        <strong>Low-information picks</strong> — these predictions are built on {detail}.
        Treat them as low-information.
      </AlertDescription>
    </Alert>
  )
}
