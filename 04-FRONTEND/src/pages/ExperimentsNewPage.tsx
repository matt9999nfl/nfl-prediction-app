/**
 * Experiment builder — /experiments/new
 *
 * 6-step wizard:
 *  1. Name + description
 *  2. Target variable
 *  3. Feature selection (searchable checklist grouped by dataset)
 *  4. Evaluation criteria
 *  5. Methodology + model type
 *  6. Review + save
 *
 * On save, POSTs to /api/v1/experiments and redirects to the detail page.
 * If a frameworkConfig prop is provided (from "New from framework"), the form
 * is pre-filled.
 */

import { useState, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useFeatures, useCreateExperiment } from '@/api/queries'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { targetLabel, metricLabel } from '@/lib/formatters'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import type {
  CreateExperimentPayload,
  ExperimentTarget,
  EvaluationMetric,
  Feature,
} from '@/api/types'

const STEPS = [
  'Name',
  'Target',
  'Features',
  'Evaluation',
  'Methodology',
  'Review',
]

const TARGETS: ExperimentTarget[] = [
  'ats_cover',
  'outright_winner',
  'total_over',
  'team_total_yards',
]

const METRICS: EvaluationMetric[] = ['ats_hit_rate', 'accuracy', 'log_loss', 'rmse']

interface ExperimentsNewPageProps {
  /** Pre-fill the form from a saved framework */
  prefill?: Partial<CreateExperimentPayload>
}

export function ExperimentsNewPage({ prefill: prefillProp }: ExperimentsNewPageProps = {}) {
  const navigate = useNavigate()
  const location = useLocation()
  // Support pre-fill from either a prop (future use) or React Router state
  // (passed via <Link state={{ prefill: config }}>)
  const routerPrefill = (location.state as { prefill?: Partial<CreateExperimentPayload> } | null)?.prefill
  const prefill = prefillProp ?? routerPrefill
  const [step, setStep] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [featureSearch, setFeatureSearch] = useState('')

  // Form state
  const [name, setName] = useState(prefill?.name ?? '')
  const [description, setDescription] = useState(prefill?.description ?? '')
  const [target, setTarget] = useState<ExperimentTarget>(prefill?.target ?? 'ats_cover')
  const [selectedFeatureIds, setSelectedFeatureIds] = useState<Set<string>>(
    new Set(prefill?.features?.map((f) => `${f.dataset}.${f.column}`) ?? []),
  )
  const [metric, setMetric] = useState<EvaluationMetric>(
    prefill?.evaluation?.metric ?? 'ats_hit_rate',
  )
  const [successThreshold, setSuccessThreshold] = useState(
    prefill?.evaluation?.success_threshold ?? 0.54,
  )
  const [minSample, setMinSample] = useState(prefill?.evaluation?.min_sample ?? 250)
  const [startSeason, setStartSeason] = useState(prefill?.methodology?.start_season ?? 2015)
  const [endSeason, setEndSeason] = useState(prefill?.methodology?.end_season ?? 2024)
  const [trainSeasons, setTrainSeasons] = useState(prefill?.methodology?.train_seasons ?? 4)

  const { data: featuresData, isLoading: featuresLoading, isError: featuresError } = useFeatures()
  const createExperiment = useCreateExperiment()

  const allFeatures = featuresData?.data ?? []

  // Group features by dataset
  const featuresByDataset = useMemo(() => {
    const filtered = featureSearch
      ? allFeatures.filter(
          (f) =>
            f.semantic_name.toLowerCase().includes(featureSearch.toLowerCase()) ||
            f.description.toLowerCase().includes(featureSearch.toLowerCase()),
        )
      : allFeatures
    const map = new Map<string, Feature[]>()
    for (const f of filtered) {
      const bucket = map.get(f.dataset) ?? []
      bucket.push(f)
      map.set(f.dataset, bucket)
    }
    return [...map.entries()].sort(([a], [b]) => {
      // curated first
      if (a === 'curated') return -1
      if (b === 'curated') return 1
      return a.localeCompare(b)
    })
  }, [allFeatures, featureSearch])

  function toggleFeature(featureId: string) {
    setSelectedFeatureIds((prev) => {
      const next = new Set(prev)
      if (next.has(featureId)) {
        next.delete(featureId)
      } else {
        next.add(featureId)
      }
      return next
    })
  }

  function buildPayload(): CreateExperimentPayload {
    const selectedFeatures = allFeatures
      .filter((f) => selectedFeatureIds.has(f.feature_id))
      .map((f) => ({
        dataset: f.dataset,
        // feature_id = "{dataset}.{column}" — strip the dataset prefix to get the column name
        column: f.feature_id.startsWith(`${f.dataset}.`)
          ? f.feature_id.slice(f.dataset.length + 1)
          : f.semantic_name,
        semantic_name: f.semantic_name,
      }))

    return {
      name: name.trim(),
      description: description.trim(),
      target,
      features: selectedFeatures,
      evaluation: {
        metric,
        success_threshold: successThreshold,
        min_sample: minSample,
      },
      methodology: {
        type: 'walk_forward',
        train_seasons: trainSeasons,
        test_seasons: 1,
        start_season: startSeason,
        end_season: endSeason,
      },
      model: {
        type: 'xgboost',
        hyperparams: {},
      },
    }
  }

  async function handleSave() {
    setSubmitError(null)
    try {
      const result = await createExperiment.mutateAsync(buildPayload())
      navigate(`/experiments/${result.experiment_id}`)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create experiment.')
    }
  }

  // Step validity checks
  function canProceed(): boolean {
    if (step === 0) return name.trim().length > 0
    if (step === 2) return selectedFeatureIds.size > 0
    if (step === 4)
      return startSeason < endSeason && endSeason - startSeason >= trainSeasons
    return true
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New experiment</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Configure a backtest experiment in {STEPS.length} steps
        </p>
      </div>

      {/* Step indicators */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => i < step && setStep(i)}
              className={`flex items-center justify-center rounded-full w-7 h-7 text-xs font-medium transition-colors ${
                i === step
                  ? 'bg-primary text-primary-foreground'
                  : i < step
                  ? 'bg-muted text-muted-foreground hover:bg-accent cursor-pointer'
                  : 'bg-muted text-muted-foreground cursor-default opacity-50'
              }`}
            >
              {i + 1}
            </button>
            {i < STEPS.length - 1 && (
              <div className={`h-[1px] w-6 ${i < step ? 'bg-primary' : 'bg-border'}`} />
            )}
          </div>
        ))}
        <span className="ml-2 text-sm text-muted-foreground">{STEPS[step]}</span>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          {/* Step 0: Name */}
          {step === 0 && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="exp-name">Experiment name *</Label>
                <Input
                  id="exp-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. OL mismatch ATS v3"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="exp-desc">Description</Label>
                <Textarea
                  id="exp-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What's the hypothesis? What's different about this experiment?"
                  rows={3}
                />
              </div>
            </div>
          )}

          {/* Step 1: Target */}
          {step === 1 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                What outcome is this model trying to predict?
              </p>
              <div className="grid gap-2">
                {TARGETS.map((t) => (
                  <label
                    key={t}
                    className={`flex items-center gap-3 rounded-lg border p-4 cursor-pointer transition-colors ${
                      target === t ? 'border-primary bg-accent' : 'hover:bg-accent/50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="target"
                      value={t}
                      checked={target === t}
                      onChange={() => setTarget(t)}
                      className="accent-primary"
                    />
                    <div>
                      <div className="font-medium">{targetLabel(t)}</div>
                      <div className="text-xs text-muted-foreground">
                        {targetDescription(t)}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Features */}
          {step === 2 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  Select features to include. Curated features come from the platform's
                  nflfastR data. User datasets appear below.
                </p>
                <Badge variant="secondary">{selectedFeatureIds.size} selected</Badge>
              </div>

              <Input
                placeholder="Search features…"
                value={featureSearch}
                onChange={(e) => setFeatureSearch(e.target.value)}
              />

              {featuresLoading && <LoadingState rows={3} />}
              {featuresError && (
                <ErrorState error={featuresError} context="features" />
              )}

              {!featuresLoading && !featuresError && (
                <div className="max-h-80 overflow-y-auto space-y-4 border rounded-md p-3">
                  {featuresByDataset.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      {featureSearch ? 'No features match your search.' : 'No features available.'}
                    </p>
                  )}
                  {featuresByDataset.map(([dataset, features]) => (
                    <div key={dataset}>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                        {dataset}
                      </p>
                      <div className="space-y-2">
                        {features.map((f) => (
                          <div
                            key={f.feature_id}
                            className="flex items-start gap-3 py-1"
                          >
                            <Checkbox
                              id={`feat-${f.feature_id}`}
                              checked={selectedFeatureIds.has(f.feature_id)}
                              onCheckedChange={() => toggleFeature(f.feature_id)}
                              className="mt-0.5"
                            />
                            <Label
                              htmlFor={`feat-${f.feature_id}`}
                              className="cursor-pointer space-y-0.5"
                            >
                              <span className="font-medium text-sm">{f.semantic_name}</span>
                              <span className="block text-xs text-muted-foreground">
                                {f.description}
                              </span>
                            </Label>
                          </div>
                        ))}
                      </div>
                      <Separator className="mt-3" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Evaluation */}
          {step === 3 && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Define the success criteria. The model must exceed the threshold over
                at least the minimum sample to clear the gate.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="eval-metric">Primary metric</Label>
                  <Select
                    id="eval-metric"
                    value={metric}
                    onChange={(e) => setMetric(e.target.value as EvaluationMetric)}
                  >
                    {METRICS.map((m) => (
                      <option key={m} value={m}>
                        {metricLabel(m)}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eval-threshold">
                    Success threshold{' '}
                    <span className="text-xs text-muted-foreground">(0–1)</span>
                  </Label>
                  <Input
                    id="eval-threshold"
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={successThreshold}
                    onChange={(e) => setSuccessThreshold(parseFloat(e.target.value))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="eval-minsample">Minimum sample (games)</Label>
                  <Input
                    id="eval-minsample"
                    type="number"
                    min={50}
                    step={25}
                    value={minSample}
                    onChange={(e) => setMinSample(parseInt(e.target.value, 10))}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Methodology */}
          {step === 4 && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Walk-forward evaluation: train on{' '}
                <strong>{trainSeasons} seasons</strong>, test on 1 season,
                rolling forward.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="start-season">Start season</Label>
                  <Input
                    id="start-season"
                    type="number"
                    min={2010}
                    max={2030}
                    value={startSeason}
                    onChange={(e) => setStartSeason(parseInt(e.target.value, 10))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="end-season">End season</Label>
                  <Input
                    id="end-season"
                    type="number"
                    min={2010}
                    max={2030}
                    value={endSeason}
                    onChange={(e) => setEndSeason(parseInt(e.target.value, 10))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="train-seasons">Training window (seasons)</Label>
                  <Input
                    id="train-seasons"
                    type="number"
                    min={1}
                    max={10}
                    value={trainSeasons}
                    onChange={(e) => setTrainSeasons(parseInt(e.target.value, 10))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="model-type">Model type</Label>
                  <Select id="model-type" value="xgboost" disabled>
                    <option value="xgboost">XGBoost</option>
                    <option value="logistic_regression" disabled>
                      Logistic regression (coming soon)
                    </option>
                    <option value="random_forest" disabled>
                      Random forest (coming soon)
                    </option>
                  </Select>
                </div>
              </div>

              {endSeason - startSeason < trainSeasons && (
                <Alert variant="warning">
                  <AlertDescription>
                    The season range ({endSeason - startSeason} seasons) is smaller
                    than the training window ({trainSeasons}). Increase the range or
                    reduce the training window.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {/* Step 5: Review */}
          {step === 5 && (
            <div className="space-y-4">
              <ReviewRow label="Name" value={name} />
              {description && <ReviewRow label="Description" value={description} />}
              <ReviewRow label="Target" value={targetLabel(target)} />
              <ReviewRow
                label="Features"
                value={`${selectedFeatureIds.size} selected`}
              />
              <ReviewRow label="Metric" value={metricLabel(metric)} />
              <ReviewRow
                label="Success threshold"
                value={`${(successThreshold * 100).toFixed(1)}%`}
              />
              <ReviewRow
                label="Min sample"
                value={`${minSample} games`}
              />
              <ReviewRow
                label="Season range"
                value={`${startSeason}–${endSeason}`}
              />
              <ReviewRow
                label="Training window"
                value={`${trainSeasons} seasons`}
              />
              <ReviewRow label="Model" value="XGBoost" />

              {submitError && (
                <Alert variant="destructive">
                  <AlertDescription>{submitError}</AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          disabled={step === 0}
          onClick={() => setStep((s) => s - 1)}
        >
          <ChevronLeft className="mr-2 h-4 w-4" />
          Back
        </Button>

        {step < STEPS.length - 1 ? (
          <Button
            onClick={() => setStep((s) => s + 1)}
            disabled={!canProceed()}
          >
            Next
            <ChevronRight className="ml-2 h-4 w-4" />
          </Button>
        ) : (
          <Button
            onClick={() => void handleSave()}
            disabled={createExperiment.isPending}
          >
            {createExperiment.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save experiment
          </Button>
        )}
      </div>
    </div>
  )
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1 border-b last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-right">{value}</span>
    </div>
  )
}

function targetDescription(t: ExperimentTarget): string {
  const d: Record<ExperimentTarget, string> = {
    ats_cover: 'Did the home team cover the closing spread?',
    outright_winner: 'Did the home team win?',
    total_over: 'Did the game go over the closing total?',
    team_total_yards: 'Team total offensive yards over/under a threshold',
  }
  return d[t]
}
