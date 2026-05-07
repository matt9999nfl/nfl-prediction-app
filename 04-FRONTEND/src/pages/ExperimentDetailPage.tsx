/**
 * Experiment detail + run + results — /experiments/:id
 *
 * States:
 *  draft    → shows config, "Run" button enabled
 *  running  → polling every 10s, spinner + fold progress, note about Phase 3
 *  complete → full results: ATS hit rate, gate_passed, per-fold breakdown,
 *             "Save as Framework" button
 *  failed   → error message, "Run again" button
 *
 * Per the build spec: the Cloud Run Job isn't wired until Phase 3, so the
 * experiment will stay 'running' indefinitely. The UI handles this gracefully
 * with a note that experiments typically complete in 5–15 minutes and keeps
 * polling without timing out.
 *
 * The EvaluationBanner in Layout is hidden for this page when gate_passed = true.
 */

import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useExperiment,
  useExperimentStatus,
  useRunExperiment,
  useExperimentPredictions,
  useCreateFramework,
} from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { StatusBadge, GateBadge } from '@/components/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import {
  formatPct,
  formatRelativeDate,
  targetLabel,
  metricLabel,
} from '@/lib/formatters'
import {
  ArrowLeft,
  BookmarkPlus,
  Loader2,
  Play,
  RefreshCw,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { Prediction } from '@/api/types'

// We poll every 10 seconds while running — per spec
const POLL_INTERVAL_MS = 10_000
// Fetch predictions for the last season in the experiment range
const RESULTS_SEASON = 2024

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [isRunning, setIsRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [saveFrameworkError, setSaveFrameworkError] = useState<string | null>(null)

  const {
    data: detail,
    isLoading,
    isError,
    error,
    refetch,
  } = useExperiment(id ?? '')

  const runExperiment = useRunExperiment()
  const createFramework = useCreateFramework()

  const config = detail?.config
  const latestRun = detail?.latest_run

  // Determine if we should poll status
  const shouldPoll =
    isRunning || config?.status === 'running'

  const { data: statusData } = useExperimentStatus(id ?? '', {
    refetchInterval: shouldPoll ? POLL_INTERVAL_MS : false,
    enabled: Boolean(id) && shouldPoll,
  })

  // When status transitions to complete/failed, refresh the experiment
  useEffect(() => {
    if (statusData?.status === 'complete' || statusData?.status === 'failed') {
      setIsRunning(false)
      void qc.invalidateQueries({ queryKey: ['experiments', id] })
    }
  }, [statusData?.status, id, qc])

  // Load predictions for the complete state
  const {
    data: predictionsData,
  } = useExperimentPredictions(
    id ?? '',
    RESULTS_SEASON,
    { enabled: config?.status === 'complete' },
  )

  const predictions = predictionsData?.data ?? []

  // Group predictions by fold for per-fold breakdown
  const foldStats = groupByFold(predictions)

  async function handleRun() {
    if (!id) return
    setRunError(null)
    setIsRunning(true)
    try {
      await runExperiment.mutateAsync(id)
    } catch (err) {
      setIsRunning(false)
      setRunError(err instanceof Error ? err.message : 'Failed to start experiment run.')
    }
  }

  async function handleSaveFramework() {
    if (!id || !config) return
    setSaveFrameworkError(null)
    try {
      const framework = await createFramework.mutateAsync({
        name: `${config.name} — framework`,
        description: `Saved from experiment ${config.name}`,
        base_experiment_id: id,
      })
      navigate(`/frameworks/${framework.framework_id}`)
    } catch (err) {
      setSaveFrameworkError(
        err instanceof Error ? err.message : 'Failed to save framework.',
      )
    }
  }

  if (isLoading) return <LoadingState rows={6} />

  if (isError) {
    return (
      <ErrorState
        error={error}
        context={`experiment ${id ?? ''}`}
        onRetry={() => void refetch()}
      />
    )
  }

  if (!config) return null

  const isComplete = config.status === 'complete'
  const isFailed = config.status === 'failed'
  const isDraft = config.status === 'draft'
  const running = config.status === 'running' || isRunning

  return (
    <div className="space-y-6">
      {/* When this experiment has cleared its gate, show a success note in addition
          to (not instead of) the global evaluation banner in the Layout. */}
      {config.gate_passed === true && (
        <Alert variant="success">
          <AlertDescription>
            This experiment cleared its gate (
            {metricLabel(config.evaluation.metric)} ≥{' '}
            {formatPct(config.evaluation.success_threshold)} over{' '}
            {config.evaluation.min_sample}+ games).
          </AlertDescription>
        </Alert>
      )}

      <Link to="/model">
        <Button variant="ghost" size="sm" className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          All experiments
        </Button>
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight">{config.name}</h1>
            <StatusBadge status={config.status} />
            <GateBadge gatePassed={config.gate_passed} />
          </div>
          {config.description && (
            <p className="text-muted-foreground text-sm">{config.description}</p>
          )}
          <p className="text-xs text-muted-foreground">
            Created {formatRelativeDate(config.created_at)}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          {(isDraft || isFailed) && (
            <Button
              onClick={() => void handleRun()}
              disabled={runExperiment.isPending || isRunning}
            >
              {runExperiment.isPending || isRunning ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {isFailed ? 'Run again' : 'Run experiment'}
            </Button>
          )}
          {running && (
            <Button variant="outline" disabled>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Running…
            </Button>
          )}
          {isComplete && (
            <Button
              variant="outline"
              onClick={() => void handleSaveFramework()}
              disabled={createFramework.isPending}
            >
              {createFramework.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <BookmarkPlus className="mr-2 h-4 w-4" />
              )}
              Save as framework
            </Button>
          )}
        </div>
      </div>

      {runError && (
        <Alert variant="destructive">
          <AlertDescription>{runError}</AlertDescription>
        </Alert>
      )}
      {saveFrameworkError && (
        <Alert variant="destructive">
          <AlertDescription>{saveFrameworkError}</AlertDescription>
        </Alert>
      )}

      {/* Running state */}
      {running && (
        <Alert variant="info">
          <Loader2 className="h-4 w-4 animate-spin" />
          <AlertTitle>Experiment running</AlertTitle>
          <AlertDescription>
            {statusData?.progress
              ? `Fold ${statusData.progress.folds_complete} of ${statusData.progress.folds_total} complete.`
              : 'Waiting for the runner to start.'}
            {' '}Experiments typically complete in 5–15 minutes.
            {statusData?.progress && (
              <Progress
                value={(statusData.progress.folds_complete / statusData.progress.folds_total) * 100}
                className="mt-2"
              />
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Failed state */}
      {isFailed && latestRun && (
        <Alert variant="destructive">
          <AlertTitle>Run failed</AlertTitle>
          <AlertDescription>
            The last run did not complete successfully.
            {latestRun.notes && ` ${latestRun.notes}`}
          </AlertDescription>
        </Alert>
      )}

      {/* Results (complete) */}
      {isComplete && latestRun && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Results</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <ResultCard
              label="ATS hit rate"
              value={formatPct(latestRun.ats_hit_rate)}
              highlight={
                latestRun.ats_hit_rate !== null &&
                latestRun.ats_hit_rate >= config.evaluation.success_threshold
              }
            />
            <ResultCard
              label="Games evaluated"
              value={latestRun.n_games_evaluated?.toLocaleString() ?? '—'}
            />
            <ResultCard
              label="Threshold"
              value={formatPct(config.evaluation.success_threshold)}
            />
            <ResultCard
              label="Gate"
              value={latestRun.gate_passed === true ? 'Passed ✓' : 'Not passed'}
              highlight={latestRun.gate_passed === true}
            />
          </div>

          {/* Per-fold breakdown */}
          {foldStats.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Per-fold ATS hit rate</CardTitle>
                <CardDescription>
                  Walk-forward test folds — each bar = one test season
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={foldStats} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis
                      dataKey="fold"
                      tick={{ fontSize: 12 }}
                      tickFormatter={(v: unknown) => `F${String(v)}`}
                    />
                    <YAxis
                      domain={[0, 1]}
                      tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                      tick={{ fontSize: 12 }}
                      width={40}
                    />
                    <Tooltip
                      formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'Hit rate']}
                      labelFormatter={(l: unknown) => `Fold ${String(l)}`}
                    />
                    <ReferenceLine
                      y={config.evaluation.success_threshold}
                      stroke="hsl(var(--destructive))"
                      strokeDasharray="4 2"
                      label={{
                        value: 'Threshold',
                        position: 'insideTopRight',
                        fontSize: 11,
                        fill: 'hsl(var(--muted-foreground))',
                      }}
                    />
                    <Bar
                      dataKey="hitRate"
                      fill="hsl(var(--primary))"
                      radius={[3, 3, 0, 0]}
                      name="Hit rate"
                    />
                  </BarChart>
                </ResponsiveContainer>

                {/* Fold table */}
                <div className="overflow-x-auto mt-4">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        <th className="text-left py-2 pr-4">Fold</th>
                        <th className="text-right py-2 px-4">Games</th>
                        <th className="text-right py-2 px-4">Correct</th>
                        <th className="text-right py-2 pl-4">Hit rate</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {foldStats.map((row) => (
                        <tr key={row.fold}>
                          <td className="py-2 pr-4">Fold {row.fold}</td>
                          <td className="py-2 px-4 text-right tabular-nums">{row.total}</td>
                          <td className="py-2 px-4 text-right tabular-nums">{row.correct}</td>
                          <td className="py-2 pl-4 text-right tabular-nums font-medium">
                            {formatPct(row.hitRate)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <Separator />

      {/* Config details */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Configuration</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <ConfigCard title="Target & evaluation">
            <ConfigRow label="Target" value={targetLabel(config.target)} />
            <ConfigRow label="Metric" value={metricLabel(config.evaluation.metric)} />
            <ConfigRow
              label="Success threshold"
              value={formatPct(config.evaluation.success_threshold)}
            />
            <ConfigRow
              label="Min sample"
              value={`${config.evaluation.min_sample} games`}
            />
          </ConfigCard>

          <ConfigCard title="Methodology">
            <ConfigRow
              label="Season range"
              value={`${config.methodology.start_season}–${config.methodology.end_season}`}
            />
            <ConfigRow
              label="Training window"
              value={`${config.methodology.train_seasons} seasons`}
            />
            <ConfigRow label="Method" value="Walk-forward" />
            <ConfigRow label="Model" value={config.model.type} />
          </ConfigCard>
        </div>

        {/* Features */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Features{' '}
              <Badge variant="secondary">{config.features.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {config.features.length === 0 ? (
              <p className="text-sm text-muted-foreground">No features configured.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {config.features.map((f) => (
                  <Badge key={`${f.dataset}.${f.column}`} variant="outline">
                    {f.semantic_name}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Run history */}
        {detail?.run_history && detail.run_history.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Run history</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="text-left py-2 pr-4">Run</th>
                      <th className="text-right py-2 px-4">ATS hit rate</th>
                      <th className="text-right py-2 px-4">Games</th>
                      <th className="text-right py-2 pl-4">Gate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {detail.run_history.map((run) => (
                      <tr key={run.run_id}>
                        <td className="py-2 pr-4">
                          <div className="font-medium">{run.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {formatRelativeDate(run.run_at)}
                          </div>
                        </td>
                        <td className="py-2 px-4 text-right tabular-nums">
                          {formatPct(run.ats_hit_rate)}
                        </td>
                        <td className="py-2 px-4 text-right tabular-nums">
                          {run.n_games_evaluated?.toLocaleString() ?? '—'}
                        </td>
                        <td className="py-2 pl-4 text-right">
                          <GateBadge gatePassed={run.gate_passed} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* "New from this" button */}
        <div className="flex justify-end">
          <Link
            to="/experiments/new"
            state={{ prefill: config }}
          >
            <Button variant="outline" size="sm">
              <RefreshCw className="mr-2 h-4 w-4" />
              New experiment from this config
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function groupByFold(predictions: Prediction[]) {
  const map = new Map<number, { total: number; correct: number }>()
  for (const p of predictions) {
    const foldId = p.fold ?? 0
    const entry = map.get(foldId) ?? { total: 0, correct: 0 }
    entry.total += 1
    if (p.correct === 1) entry.correct += 1
    map.set(foldId, entry)
  }
  return [...map.entries()]
    .sort(([a], [b]) => a - b)
    .map(([fold, { total, correct }]) => ({
      fold,
      total,
      correct,
      hitRate: total > 0 ? correct / total : 0,
    }))
}

function ResultCard({
  label,
  value,
  highlight,
}: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <Card className={highlight ? 'border-green-400' : ''}>
      <CardContent className="px-4 py-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={`text-xl font-bold ${highlight ? 'text-green-700' : ''}`}>{value}</p>
      </CardContent>
    </Card>
  )
}

function ConfigCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">{children}</CardContent>
    </Card>
  )
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm py-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
