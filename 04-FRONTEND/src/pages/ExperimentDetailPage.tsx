/**
 * Experiment detail + run + results — /experiments/:id
 *
 * States:
 *  draft    → shows config, "Run" button enabled
 *  running  → polling every 10s, spinner + fold progress, note about Phase 3
 *  complete → full results: ATS hit rate, gate_passed, per-fold breakdown,
 *             feature importance panel, "Save as Framework" button
 *  failed   → error message, "Run again" button
 *
 * Per-fold chart (3.3): consumes `per_fold` array from GET /api/v1/experiments/:id.
 * Feature importance (3.4): fetches GET /api/v1/experiments/:id/feature-importance.
 * Both endpoints may not be deployed yet — mock data is used with clear TODO comments.
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useExperiment,
  useExperimentStatus,
  useRunExperiment,
  useFeatureImportance,
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
  AlertTriangle,
  ArrowLeft,
  BookmarkPlus,
  Loader2,
  Play,
  RefreshCw,
  X,
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
  Cell,
} from 'recharts'
import type { FoldResult } from '@/api/types'

// We poll every 10 seconds while running — per spec
const POLL_INTERVAL_MS = 10_000

// ── Reference lines ───────────────────────────────────────────────────────────

const BREAK_EVEN_RATE = 0.5238  // 52.38% at -110 odds
const GATE_RATE = 0.54          // 54% gate threshold

export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [isRunning, setIsRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [saveFrameworkError, setSaveFrameworkError] = useState<string | null>(null)
  // BUG-002 (F2-A): session-dismissable deprecated features banner
  const [deprecatedBannerDismissed, setDeprecatedBannerDismissed] = useState(false)
  const dismissDeprecatedBanner = useCallback(() => setDeprecatedBannerDismissed(true), [])

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

  const isComplete = config?.status === 'complete'

  // Feature importance — fetch when experiment is complete
  const {
    data: featureImportanceData,
    isLoading: fiLoading,
  } = useFeatureImportance(id ?? '', { enabled: isComplete && Boolean(id) })

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

  const isFailed = config.status === 'failed'
  const isDraft = config.status === 'draft'
  const running = config.status === 'running' || isRunning

  // Per-fold data: prefer the new `per_fold` field from the API.
  // TODO: wire to live endpoint once deployed (BACKEND-API 3.1)
  const perFoldData: FoldResult[] = detail?.per_fold ?? []

  // Feature importance: top 15 (API returns sorted descending — preserve order)
  const topFeatures = (featureImportanceData?.features ?? []).slice(0, 15)

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

      {/* BUG-002 (F2-A): amber warning banner for deprecated features — session-dismissable */}
      {!deprecatedBannerDismissed && (detail?.deprecated_features?.length ?? 0) > 0 && (
        <Alert variant="warning" className="flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <AlertTitle>Deprecated features</AlertTitle>
            <AlertDescription>
              {detail!.deprecated_features!.length} feature{detail!.deprecated_features!.length === 1 ? '' : 's'} in this experiment {detail!.deprecated_features!.length === 1 ? 'is' : 'are'} no longer available:{' '}
              {detail!.deprecated_features!.map((d) => d.name).join(', ')}.
              Results from this run remain valid, but these features cannot be selected in new experiments.
            </AlertDescription>
          </div>
          <button
            type="button"
            onClick={dismissDeprecatedBanner}
            className="shrink-0 rounded-md p-0.5 hover:bg-yellow-200 transition-colors"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
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

          {/* ── 3.3: Per-fold hit rate chart ──────────────────────────────── */}
          <PerFoldChart
            data={perFoldData}
            successThreshold={config.evaluation.success_threshold}
          />

          {/* ── 3.4: Feature importance panel ────────────────────────────── */}
          <FeatureImportancePanel
            features={topFeatures}
            isLoading={fiLoading}
            runId={featureImportanceData?.run_id ?? null}
          />
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
            state={{
              prefill: config,
              // BUG-002 (F2-C): pass deprecated features so the wizard can exclude them
              // from the pre-populated selection and show the user a named alert
              cloneDeprecatedFeatures: detail?.deprecated_features ?? [],
            }}
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

// ── 3.3: Per-fold hit rate chart ──────────────────────────────────────────────

interface FoldTooltipPayload {
  wins: number
  losses: number
  pushes: number
  n_games: number
  hit_rate: number
}

function FoldTooltipContent({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ payload: FoldTooltipPayload }>
  label?: string | number
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded border bg-background px-3 py-2 text-xs shadow-md">
      <p className="font-semibold mb-1">Season {String(label)}</p>
      <p>Hit rate: <span className="font-medium">{(d.hit_rate * 100).toFixed(1)}%</span></p>
      <p>Record: {d.wins}–{d.losses}{d.pushes > 0 ? `–${d.pushes}` : ''}</p>
      <p>Games: {d.n_games}</p>
    </div>
  )
}

function PerFoldChart({
  data,
  successThreshold,
}: {
  data: FoldResult[]
  successThreshold: number
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Per-season ATS hit rate</CardTitle>
        <CardDescription>
          Walk-forward test folds — each bar = one test season. Reference lines: break-even (52.4%) and gate threshold (54%).
        </CardDescription>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            No fold data yet — run this experiment to see per-season results.
          </p>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data} margin={{ top: 12, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="season"
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  domain={[0.4, 0.65]}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 12 }}
                  width={44}
                />
                <Tooltip content={<FoldTooltipContent />} />
                {/* Break-even line */}
                <ReferenceLine
                  y={BREAK_EVEN_RATE}
                  stroke="hsl(var(--muted-foreground))"
                  strokeDasharray="4 2"
                  label={{
                    value: 'Break-even 52.4%',
                    position: 'insideTopLeft',
                    fontSize: 10,
                    fill: 'hsl(var(--muted-foreground))',
                  }}
                />
                {/* Gate threshold line */}
                <ReferenceLine
                  y={GATE_RATE}
                  stroke="hsl(var(--destructive))"
                  strokeDasharray="4 2"
                  label={{
                    value: `Gate ${(GATE_RATE * 100).toFixed(0)}%`,
                    position: 'insideTopRight',
                    fontSize: 10,
                    fill: 'hsl(var(--destructive))',
                  }}
                />
                {/* Success threshold line (may differ from gate) */}
                {successThreshold !== GATE_RATE && (
                  <ReferenceLine
                    y={successThreshold}
                    stroke="hsl(var(--primary))"
                    strokeDasharray="4 2"
                    label={{
                      value: `Threshold ${formatPct(successThreshold)}`,
                      position: 'insideBottomRight',
                      fontSize: 10,
                      fill: 'hsl(var(--primary))',
                    }}
                  />
                )}
                <Bar
                  dataKey="hit_rate"
                  name="Hit rate"
                  radius={[3, 3, 0, 0]}
                >
                  {data.map((entry) => (
                    <Cell
                      key={`cell-${entry.season}`}
                      fill={
                        entry.hit_rate >= GATE_RATE
                          ? 'hsl(var(--primary))'
                          : entry.hit_rate >= BREAK_EVEN_RATE
                            ? 'hsl(var(--muted-foreground))'
                            : 'hsl(var(--destructive))'
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {/* Fold table */}
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="text-left py-2 pr-4">Season</th>
                    <th className="text-right py-2 px-4">W–L–P</th>
                    <th className="text-right py-2 px-4">Games</th>
                    <th className="text-right py-2 pl-4">Hit rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.map((row) => (
                    <tr key={row.season}>
                      <td className="py-2 pr-4">{row.season}</td>
                      <td className="py-2 px-4 text-right tabular-nums">
                        {row.wins}–{row.losses}{row.pushes > 0 ? `–${row.pushes}` : ''}
                      </td>
                      <td className="py-2 px-4 text-right tabular-nums">{row.n_games}</td>
                      <td className="py-2 pl-4 text-right tabular-nums font-medium">
                        {formatPct(row.hit_rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ── 3.4: Feature importance panel ────────────────────────────────────────────

/** Strip home_/away_ prefix and replace underscores with spaces. */
function cleanFeatureLabel(raw: string): string {
  return raw
    .replace(/^(home_|away_)/, '')
    .replace(/_/g, ' ')
}

interface FeatureImportanceItem {
  feature: string
  importance: number
}

function FeatureTooltipContent({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: FeatureImportanceItem }>
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded border bg-background px-3 py-2 text-xs shadow-md max-w-[240px]">
      <p className="font-mono break-all">{d.feature}</p>
      <p className="mt-1">Importance: <span className="font-medium">{d.importance.toFixed(4)}</span></p>
    </div>
  )
}

function FeatureImportancePanel({
  features,
  isLoading,
  runId,
}: {
  features: FeatureImportanceItem[]
  isLoading: boolean
  runId: string | null
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Feature importance</CardTitle>
        <CardDescription>
          Top 15 features by XGBoost importance score
          {runId ? ` — run ${runId}` : ''}.
          Hover a bar to see the full feature name.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading feature importance…
          </div>
        ) : features.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            Feature importance will appear after the experiment runs.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(240, features.length * 26)}>
            <BarChart
              data={features}
              layout="vertical"
              margin={{ top: 4, right: 16, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
              <XAxis
                type="number"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => v.toFixed(3)}
              />
              <YAxis
                type="category"
                dataKey="feature"
                tickFormatter={cleanFeatureLabel}
                width={160}
                tick={{ fontSize: 11 }}
              />
              <Tooltip content={<FeatureTooltipContent />} />
              <Bar
                dataKey="importance"
                fill="hsl(var(--primary))"
                radius={[0, 3, 3, 0]}
                name="Importance"
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}

// ── Shared helpers ────────────────────────────────────────────────────────────

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
