import { AlertTriangle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface LowDataWarningProps {
  week: number
}

/**
 * True for weeks where a team's features still lean heavily on last season
 * rather than the current one (week 1: zero 2026 games; week 2: one game per
 * team, blended 8:1 against last season's numbers — see ADR-013).
 *
 * Reworded 2026-09-16 for the prior-season-blend go-live: earlier weeks are
 * no longer a single game or a flat prior-season carryover, they're a blend.
 * Still worth flagging — the blend is not the same thing as validation.
 */
export function isLowDataWeek(week: number): boolean {
  return week <= 2
}

export function LowDataWarning({ week }: LowDataWarningProps) {
  if (!isLowDataWeek(week)) return null

  const detail =
    week === 1
      ? "entirely on last season's numbers — no 2026 games have been played yet"
      : "one game of 2026 data, blended with last season's numbers (weighted about 8:1 toward last season)"

  return (
    <Alert variant="warning" className="mb-4">
      <AlertTriangle className="h-4 w-4" />
      <AlertDescription>
        <strong>Early-season picks</strong> — these predictions are built on {detail}.
        A blend is not the same as validation: no experiment has cleared its success
        threshold, and this early in the season the model has seen very little of 2026.
      </AlertDescription>
    </Alert>
  )
}
