/**
 * Dataset detail + schema mapping — /datasets/:datasetId
 *
 * Polling behaviour:
 *  - If status = 'uploading', polls every 3s until it changes.
 *  - If status = 'mapping', shows the schema mapping form.
 *  - If status = 'ready' or 'error', shows the dataset summary.
 *
 * AI inference:
 *  - "Use AI to suggest mapping" calls POST /infer-schema.
 *  - 503 → fall back silently to manual form (no error banner, form is already there).
 *  - 200 → pre-fill form fields with suggestions + show "Review AI suggestions" header.
 *  - User must confirm by submitting the form.
 */

import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useDataset, useUpdateDatasetSchema, useInferSchema } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { formatRelativeDate } from '@/lib/formatters'
import { ArrowLeft, Bot, Loader2, RefreshCw } from 'lucide-react'
import type { DataType, JoinKeyType, DatasetColumn, SchemaMappingPayload } from '@/api/types'

interface ColumnFormState {
  column_name: string
  semantic_name: string
  description: string
  data_type: DataType
  is_join_key: boolean
}

export function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const navigate = useNavigate()

  const [refetchInterval, setRefetchInterval] = useState<number | false>(false)
  const [aiSuggested, setAiSuggested] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [joinKeyType, setJoinKeyType] = useState<JoinKeyType>('game_id')
  const [joinKeyColumns, setJoinKeyColumns] = useState<Record<string, string>>({
    game_id: '',
  })
  const [columnForms, setColumnForms] = useState<ColumnFormState[]>([])
  const [formInitialised, setFormInitialised] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const { data: dataset, isLoading, isError, error, refetch } = useDataset(datasetId ?? '', {
    refetchInterval,
  })

  const updateSchema = useUpdateDatasetSchema()
  const inferSchema = useInferSchema()

  // Start polling if status is 'uploading'
  useEffect(() => {
    if (dataset?.status === 'uploading') {
      setRefetchInterval(3_000)
    } else {
      setRefetchInterval(false)
    }
  }, [dataset?.status])

  // Initialise form from columns when we first get mapping-state data
  useEffect(() => {
    if (!formInitialised && dataset?.status === 'mapping' && dataset.columns.length > 0) {
      setColumnForms(
        dataset.columns.map((col) => ({
          column_name: col.column_name,
          semantic_name: col.semantic_name || col.column_name,
          description: col.description || '',
          data_type: col.data_type || 'numeric',
          is_join_key: col.is_join_key || false,
        })),
      )
      if (dataset.join_key_type) setJoinKeyType(dataset.join_key_type)
      setFormInitialised(true)
    }
  }, [dataset, formInitialised])

  // Update join key columns when type changes
  useEffect(() => {
    const templates: Record<JoinKeyType, Record<string, string>> = {
      game_id: { game_id: '' },
      player_season_week: { player_id: '', season: '', week: '' },
      team_season_week: { team: '', season: '', week: '' },
    }
    setJoinKeyColumns(templates[joinKeyType])
  }, [joinKeyType])

  async function handleAIInfer() {
    if (!datasetId) return
    setAiError(null)
    try {
      const result = await inferSchema.mutateAsync(datasetId)
      // Pre-fill form with suggestions
      setJoinKeyType(result.suggested_join_key_type)
      setJoinKeyColumns(result.suggested_join_key_columns)
      setColumnForms(
        result.suggested_columns.map((col: DatasetColumn) => ({
          column_name: col.column_name,
          semantic_name: col.semantic_name,
          description: col.description,
          data_type: col.data_type,
          is_join_key: col.is_join_key,
        })),
      )
      setAiSuggested(true)
    } catch (err) {
      // 503 = AI unavailable → fall back silently (form already visible)
      if (err instanceof Error && 'status' in err && (err as { status: number }).status === 503) {
        return
      }
      setAiError(err instanceof Error ? err.message : 'AI inference failed.')
    }
  }

  async function handleSubmitSchema(e: React.FormEvent) {
    e.preventDefault()
    if (!datasetId) return
    setSubmitError(null)

    const payload: SchemaMappingPayload = {
      join_key_type: joinKeyType,
      join_key_columns: joinKeyColumns,
      columns: columnForms.map((col) => ({
        column_name: col.column_name,
        semantic_name: col.semantic_name,
        description: col.description,
        data_type: col.data_type,
      })),
    }

    try {
      await updateSchema.mutateAsync({ datasetId, payload })
      // Navigate back to datasets list on success
      navigate('/datasets')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to save schema mapping.')
    }
  }

  function updateColumn(index: number, field: keyof ColumnFormState, value: string | boolean) {
    setColumnForms((prev) =>
      prev.map((col, i) => (i === index ? { ...col, [field]: value } : col)),
    )
  }

  if (isLoading) return <LoadingState rows={6} />

  if (isError) {
    return (
      <ErrorState
        error={error}
        context={`dataset ${datasetId ?? ''}`}
        onRetry={() => void refetch()}
      />
    )
  }

  if (!dataset) return null

  return (
    <div className="space-y-6">
      <Link to="/datasets">
        <Button variant="ghost" size="sm" className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          All datasets
        </Button>
      </Link>

      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{dataset.name}</h1>
          <StatusBadge status={dataset.status} />
        </div>
        <p className="text-muted-foreground text-sm">
          {formatRelativeDate(dataset.upload_date)} ·{' '}
          {dataset.row_count.toLocaleString()} rows · {dataset.column_count} columns
        </p>
      </div>

      {/* Uploading state */}
      {dataset.status === 'uploading' && (
        <Alert variant="info">
          <Loader2 className="h-4 w-4 animate-spin" />
          <AlertTitle>Processing upload</AlertTitle>
          <AlertDescription>
            The file is being parsed and loaded into BigQuery. This page will
            update automatically when it's ready for schema mapping.
          </AlertDescription>
        </Alert>
      )}

      {/* Error state */}
      {dataset.status === 'error' && (
        <Alert variant="destructive">
          <AlertTitle>Upload failed</AlertTitle>
          <AlertDescription>
            There was a problem processing this dataset. Delete it and try
            uploading again with a valid CSV, Excel, or JSON file.
          </AlertDescription>
        </Alert>
      )}

      {/* Ready state */}
      {dataset.status === 'ready' && (
        <Alert variant="success">
          <AlertTitle>Dataset ready</AlertTitle>
          <AlertDescription>
            This dataset is mapped and available in the experiment feature selector.
            Schema source:{' '}
            <strong>{dataset.schema_source === 'ai_assisted' ? 'AI-assisted' : 'Manual form'}</strong>
          </AlertDescription>
        </Alert>
      )}

      {/* Schema mapping form (status = 'mapping') */}
      {dataset.status === 'mapping' && (
        <form onSubmit={(e) => void handleSubmitSchema(e)} className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>
                    {aiSuggested ? '🤖 Review AI suggestions' : 'Map schema'}
                  </CardTitle>
                  <CardDescription>
                    {aiSuggested
                      ? 'AI has pre-filled the fields below. Review and confirm before saving.'
                      : 'Tell the platform what each column means so it can be used in experiments.'}
                  </CardDescription>
                </div>
                {!aiSuggested && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={inferSchema.isPending}
                    onClick={() => void handleAIInfer()}
                  >
                    {inferSchema.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Bot className="mr-2 h-4 w-4" />
                    )}
                    Use AI to suggest mapping
                  </Button>
                )}
                {aiSuggested && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setAiSuggested(false)}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Reset
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {aiError && (
                <Alert variant="destructive">
                  <AlertDescription>{aiError}</AlertDescription>
                </Alert>
              )}

              {/* Join key type */}
              <div className="space-y-3">
                <h3 className="font-medium text-sm">Join key type</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="join-key-type">How rows link to games</Label>
                    <Select
                      id="join-key-type"
                      value={joinKeyType}
                      onChange={(e) => setJoinKeyType(e.target.value as JoinKeyType)}
                    >
                      <option value="game_id">Game ID</option>
                      <option value="player_season_week">Player + Season + Week</option>
                      <option value="team_season_week">Team + Season + Week</option>
                    </Select>
                  </div>
                </div>

                {/* Join key column mapping */}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.keys(joinKeyColumns).map((keyField) => (
                    <div key={keyField} className="space-y-2">
                      <Label htmlFor={`jk-${keyField}`}>
                        Column for <code className="text-xs bg-muted px-1 rounded">{keyField}</code>
                      </Label>
                      <Input
                        id={`jk-${keyField}`}
                        value={joinKeyColumns[keyField]}
                        onChange={(e) =>
                          setJoinKeyColumns((prev) => ({
                            ...prev,
                            [keyField]: e.target.value,
                          }))
                        }
                        placeholder="column_name_in_file"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Column mappings */}
              <div className="space-y-3">
                <h3 className="font-medium text-sm">
                  Column mappings{' '}
                  <Badge variant="secondary">{columnForms.length} columns</Badge>
                </h3>

                {columnForms.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    No columns detected. Ensure the upload processed correctly.
                  </p>
                )}

                <div className="space-y-4">
                  {columnForms.map((col, i) => (
                    <div key={col.column_name} className="rounded-md border p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <code className="text-sm bg-muted px-2 py-0.5 rounded font-mono">
                          {col.column_name}
                        </code>
                        <div className="flex items-center gap-2">
                          <Checkbox
                            id={`jk-check-${i}`}
                            checked={col.is_join_key}
                            onCheckedChange={(v) => updateColumn(i, 'is_join_key', Boolean(v))}
                          />
                          <Label htmlFor={`jk-check-${i}`} className="text-xs cursor-pointer">
                            Join key
                          </Label>
                        </div>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="space-y-1">
                          <Label htmlFor={`sem-${i}`} className="text-xs">
                            Feature name
                          </Label>
                          <Input
                            id={`sem-${i}`}
                            value={col.semantic_name}
                            onChange={(e) => updateColumn(i, 'semantic_name', e.target.value)}
                            placeholder="home_receiver_separation_avg"
                            className="text-sm"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`desc-${i}`} className="text-xs">
                            Description
                          </Label>
                          <Input
                            id={`desc-${i}`}
                            value={col.description}
                            onChange={(e) => updateColumn(i, 'description', e.target.value)}
                            placeholder="What this column measures"
                            className="text-sm"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`dtype-${i}`} className="text-xs">
                            Data type
                          </Label>
                          <Select
                            id={`dtype-${i}`}
                            value={col.data_type}
                            onChange={(e) =>
                              updateColumn(i, 'data_type', e.target.value as DataType)
                            }
                          >
                            <option value="numeric">Numeric</option>
                            <option value="categorical">Categorical</option>
                            <option value="boolean">Boolean</option>
                          </Select>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {submitError && (
            <Alert variant="destructive">
              <AlertDescription>{submitError}</AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end gap-3">
            <Link to="/datasets">
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </Link>
            <Button type="submit" disabled={updateSchema.isPending}>
              {updateSchema.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Save schema mapping
            </Button>
          </div>
        </form>
      )}

      {/* Column table (ready/error state) */}
      {(dataset.status === 'ready' || dataset.status === 'error') &&
        dataset.columns.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Columns</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="text-left py-2 pr-4">Raw column</th>
                      <th className="text-left py-2 px-4">Feature name</th>
                      <th className="text-left py-2 px-4">Type</th>
                      <th className="text-right py-2 pl-4">Null %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {dataset.columns.map((col) => (
                      <tr key={col.column_name}>
                        <td className="py-2 pr-4 font-mono text-xs">{col.column_name}</td>
                        <td className="py-2 px-4">{col.semantic_name}</td>
                        <td className="py-2 px-4 text-muted-foreground">{col.data_type}</td>
                        <td className="py-2 pl-4 text-right tabular-nums">
                          {(col.null_rate * 100).toFixed(1)}%
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
  )
}
