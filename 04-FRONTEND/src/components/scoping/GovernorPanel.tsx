/**
 * The governor's read on whether this experiment is worth running.
 *
 * ADR-012 and S4: this is ADVISORY. `advisory_only` is true, `dispatch` never
 * calls it, and nothing in this component is wired to a disabled state on the
 * approve or dispatch buttons. A `reconsider` verdict is shown loudly and Matt
 * proceeds anyway if he wants to — a governor that can block becomes a thing to
 * route around, and the honest signal goes with the veto.
 *
 * It also degrades: `review` 409s before the required slots are answered, which
 * is a not-yet, not an error.
 */

import { AlertTriangle, CheckCircle2, ShieldQuestion } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiRequestError } from '@/api/client'
import type { Concern, Review } from '@/api/scoping'

const VERDICTS: Record<
  Review['verdict'],
  { label: string; badge: 'success' | 'warning' | 'destructive'; icon: typeof CheckCircle2; line: string }
> = {
  proceed: {
    label: 'Proceed',
    badge: 'success',
    icon: CheckCircle2,
    line: 'Nothing in the deterministic checks argues against running this.',
  },
  proceed_with_caution: {
    label: 'Proceed with caution',
    badge: 'warning',
    icon: AlertTriangle,
    line: 'Worth reading before you approve. None of it stops the run.',
  },
  reconsider: {
    label: 'Reconsider',
    badge: 'destructive',
    icon: AlertTriangle,
    line: 'The checks think this run is unlikely to teach you much. It is still yours to run.',
  },
}

const SEVERITY: Record<Concern['severity'], 'destructive' | 'warning' | 'muted'> = {
  high: 'destructive',
  medium: 'warning',
  low: 'muted',
}

interface GovernorPanelProps {
  review?: Review
  isLoading: boolean
  error: unknown
}

export function GovernorPanel({ review, isLoading, error }: GovernorPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Governor</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (error || !review) {
    const incomplete = error instanceof ApiRequestError && error.code === 'incomplete_scoping'
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldQuestion className="h-4 w-4" />
            Governor
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {incomplete
              ? 'Not available until every required question is answered — it reviews the assembled config, not a partial one.'
              : 'The review could not be fetched. It is advisory, so this does not block approving or running.'}
          </p>
        </CardContent>
      </Card>
    )
  }

  const v = VERDICTS[review.verdict]
  const Icon = v.icon

  return (
    <Card data-testid="governor-panel" data-verdict={review.verdict}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Icon className="h-4 w-4" />
            Governor
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={v.badge}>{v.label}</Badge>
            {review.advisory_only && <Badge variant="muted">Advisory only</Badge>}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{v.line}</p>
      </CardHeader>

      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Evaluated games</dt>
            <dd className="font-medium">
              {review.evaluated_games ?? <span className="text-muted-foreground">—</span>}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Slice fraction</dt>
            <dd className="font-medium">
              {typeof review.slice_fraction === 'number' ? (
                `${(review.slice_fraction * 100).toFixed(1)}% of games`
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Concerns</dt>
            <dd className="font-medium">{review.concerns?.length ?? 0}</dd>
          </div>
        </dl>

        {review.concerns && review.concerns.length > 0 ? (
          <ul className="space-y-2">
            {review.concerns.map((c, i) => (
              <li
                key={`${c.kind}-${i}`}
                className="flex flex-wrap items-start gap-2 rounded-md border p-3 text-sm"
              >
                <Badge variant={SEVERITY[c.severity]}>{c.severity}</Badge>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {c.kind}
                </Badge>
                <span className="w-full sm:w-auto sm:flex-1">{c.message}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No concerns raised.</p>
        )}

        <p className="text-xs text-muted-foreground">
          Every check behind this is arithmetic — sample size, duplication, cold start, threshold
          plausibility. It advises; it cannot stop a run, and it is not consulted at dispatch.
        </p>
      </CardContent>
    </Card>
  )
}
