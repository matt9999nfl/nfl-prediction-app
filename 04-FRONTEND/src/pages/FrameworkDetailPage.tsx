/**
 * Framework detail — /frameworks/:id
 *
 * Shows saved config and provides "New experiment from this framework" which
 * pre-fills the experiment builder with the framework's config.
 */

import { useParams, Link, useNavigate } from 'react-router-dom'
import { useFramework, useDeleteFramework } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import {
  formatRelativeDate,
  targetLabel,
  metricLabel,
  formatPct,
} from '@/lib/formatters'
import { ArrowLeft, FlaskConical, Loader2, Trash2 } from 'lucide-react'
import { useState } from 'react'

export function FrameworkDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const {
    data: framework,
    isLoading,
    isError,
    error,
    refetch,
  } = useFramework(id ?? '')

  const deleteFramework = useDeleteFramework()

  async function handleDelete() {
    if (!id) return
    setDeleteError(null)
    try {
      await deleteFramework.mutateAsync(id)
      navigate('/frameworks')
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : 'Failed to delete framework.',
      )
    }
  }

  if (isLoading) return <LoadingState rows={5} />

  if (isError) {
    return (
      <ErrorState
        error={error}
        context={`framework ${id ?? ''}`}
        onRetry={() => void refetch()}
      />
    )
  }

  if (!framework) return null

  const config = framework.config

  return (
    <div className="space-y-6 max-w-2xl">
      <Link to="/frameworks">
        <Button variant="ghost" size="sm" className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          All frameworks
        </Button>
      </Link>

      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{framework.name}</h1>
        {framework.description && (
          <p className="text-muted-foreground">{framework.description}</p>
        )}
        <p className="text-xs text-muted-foreground">
          Created {formatRelativeDate(framework.created_at)} · Updated{' '}
          {formatRelativeDate(framework.updated_at)}
        </p>
        {framework.base_experiment_id && (
          <p className="text-xs text-muted-foreground">
            Based on{' '}
            <Link
              to={`/experiments/${framework.base_experiment_id}`}
              className="text-primary underline underline-offset-4"
            >
              experiment
            </Link>
          </p>
        )}
      </div>

      {/* Primary action */}
      <Link
        to="/experiments/new"
        state={{ prefill: config }}
      >
        <Button className="w-full sm:w-auto">
          <FlaskConical className="mr-2 h-4 w-4" />
          New experiment from this framework
        </Button>
      </Link>

      <Separator />

      {/* Config summary */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Target & evaluation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <Row label="Target" value={targetLabel(config.target)} />
            <Row label="Metric" value={metricLabel(config.evaluation.metric)} />
            <Row
              label="Threshold"
              value={formatPct(config.evaluation.success_threshold)}
            />
            <Row
              label="Min sample"
              value={`${config.evaluation.min_sample} games`}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Methodology</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <Row
              label="Season range"
              value={`${config.methodology.start_season}–${config.methodology.end_season}`}
            />
            <Row
              label="Training window"
              value={`${config.methodology.train_seasons} seasons`}
            />
            <Row label="Method" value="Walk-forward" />
            <Row label="Model" value={config.model.type} />
          </CardContent>
        </Card>
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

      {/* Delete */}
      <div className="border rounded-md p-4 space-y-3">
        <h3 className="text-sm font-medium text-destructive">Danger zone</h3>
        {deleteError && (
          <Alert variant="destructive">
            <AlertDescription>{deleteError}</AlertDescription>
          </Alert>
        )}
        {!confirmDelete ? (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete framework
          </Button>
        ) : (
          <div className="flex items-center gap-3">
            <p className="text-sm text-muted-foreground">
              This cannot be undone. Confirm?
            </p>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleteFramework.isPending}
              onClick={() => void handleDelete()}
            >
              {deleteFramework.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Yes, delete
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
