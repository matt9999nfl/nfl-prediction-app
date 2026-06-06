/**
 * Experiments list — /model
 *
 * Shows all experiments with status, ATS hit rate, and gate_passed.
 * Links to individual experiment detail pages.
 */

import { Link } from 'react-router-dom'
import { useExperiments } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { EmptyState } from '@/components/EmptyState'
import { StatusBadge, GateBadge } from '@/components/StatusBadge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { formatRelativeDate, targetLabel } from '@/lib/formatters'
import { AlertTriangle, FlaskConical, Plus } from 'lucide-react'

export function ModelPage() {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useExperiments({ limit: 50 })

  const experiments = data?.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Experiments</h1>
          <p className="text-muted-foreground text-sm mt-1">
            All configured experiments and their backtest results
          </p>
        </div>
        <Link to="/experiments/new">
          <Button size="sm">
            <Plus className="mr-2 h-4 w-4" />
            New experiment
          </Button>
        </Link>
      </div>

      {isLoading && <LoadingState rows={5} />}

      {isError && (
        <ErrorState
          error={error}
          context="experiments"
          onRetry={() => void refetch()}
        />
      )}

      {!isLoading && !isError && experiments.length === 0 && (
        <EmptyState
          icon={FlaskConical}
          title="No experiments yet"
          description="Create your first experiment to start backtesting a model."
          action={
            <Link to="/experiments/new">
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" />
                Create experiment
              </Button>
            </Link>
          }
        />
      )}

      {!isLoading && !isError && experiments.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {experiments.map((exp) => (
            <Link key={exp.experiment_id} to={`/experiments/${exp.experiment_id}`} className="block group">
              <Card className="h-full transition-shadow group-hover:shadow-md">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <CardTitle className="text-base leading-tight truncate">{exp.name}</CardTitle>
                      {/* BUG-002 (F2-B): amber warning badge for experiments with deprecated features */}
                      {exp.has_deprecated_features && (
                        <span
                          title="This experiment references features that are no longer available"
                          aria-label="This experiment references features that are no longer available"
                          className="shrink-0 text-amber-500"
                        >
                          <AlertTriangle className="h-4 w-4" />
                        </span>
                      )}
                    </div>
                    <StatusBadge status={exp.status} />
                  </div>
                  <CardDescription>
                    {targetLabel(exp.target)} · {exp.model.type}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <MetricItem
                      label="ATS hit rate"
                      value="—"
                      note="run to see results"
                      isComplete={exp.status === 'complete'}
                    />
                    <MetricItem
                      label="Features"
                      value={String(exp.features.length)}
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <GateBadge gatePassed={exp.gate_passed} />
                    <span className="text-xs text-muted-foreground">
                      {formatRelativeDate(exp.created_at)}
                    </span>
                  </div>

                  {exp.status !== 'complete' && exp.status !== 'running' && (
                    <p className="text-xs text-muted-foreground">
                      {exp.methodology.start_season}–{exp.methodology.end_season} ·{' '}
                      {exp.methodology.train_seasons} train seasons
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function MetricItem({
  label,
  value,
  note,
  isComplete,
}: {
  label: string
  value: string
  note?: string
  isComplete?: boolean
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-semibold">
        {isComplete === false && note ? (
          <span className="text-xs text-muted-foreground italic">{note}</span>
        ) : (
          value
        )}
      </p>
    </div>
  )
}

