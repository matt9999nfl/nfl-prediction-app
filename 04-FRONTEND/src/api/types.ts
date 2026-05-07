/**
 * NFL Prediction Platform — API types
 *
 * These types are hand-authored from docs/API_CONTRACTS.md.
 * Once the API is running locally, regenerate with:
 *
 *   npm run types:generate
 *
 * That writes src/api/openapi.gen.ts from the live OpenAPI schema,
 * which is the authoritative source. Until then, this file is the contract.
 */

// ── Common ────────────────────────────────────────────────────────────────────

export interface Pagination {
  next_cursor: string | null
  has_more: boolean
}

export interface PaginatedResponse<T> {
  data: T[]
  pagination: Pagination
}

export interface ApiError {
  error: string
  code: string
  request_id: string
}

// ── Health ────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
  commit: string
}

// ── Games ─────────────────────────────────────────────────────────────────────

export interface Game {
  game_id: string
  season: number
  week: number
  game_date: string
  home_team: string
  away_team: string
  home_score: number | null
  away_score: number | null
  status: 'scheduled' | 'final'
  home_spread_close: number | null
  total_close: number | null
  home_covered: boolean | null
  div_game: boolean | null
  roof: string | null
  temp: number | null
  wind: number | null
}

export interface TeamSideStats {
  score: number | null
  pass_yards: number | null
  rush_yards: number | null
  total_yards: number | null
  pass_attempts: number | null
  rush_attempts: number | null
}

export interface GameDetail extends Game {
  play_count: number
  team_stats: {
    home: TeamSideStats
    away: TeamSideStats
  }
}

// ── Datasets ──────────────────────────────────────────────────────────────────

export type JoinKeyType = 'game_id' | 'player_season_week' | 'team_season_week'
export type LicenseTag = 'open' | 'licensed_commercial' | 'personal_use_only'
export type DatasetStatus = 'uploading' | 'mapping' | 'ready' | 'error'
export type DataType = 'numeric' | 'categorical' | 'boolean'

export interface Dataset {
  dataset_id: string
  name: string
  description: string
  upload_date: string
  join_key_type: JoinKeyType
  row_count: number
  column_count: number
  license_tag: LicenseTag
  status: DatasetStatus
  schema_source: 'form' | 'ai_assisted'
}

export interface DatasetColumn {
  dataset_id: string
  column_name: string
  semantic_name: string
  description: string
  data_type: DataType
  is_join_key: boolean
  null_rate: number
}

export interface DatasetDetail extends Dataset {
  columns: DatasetColumn[]
}

export interface DatasetUploadResponse {
  dataset_id: string
  status: DatasetStatus
  schema_job_id: string
}

export interface SchemaMappingPayload {
  join_key_type: JoinKeyType
  join_key_columns: Record<string, string>
  columns: Array<{
    column_name: string
    semantic_name: string
    description: string
    data_type: DataType
  }>
}

export interface DataQualityFlag {
  column: string
  issue: string
  severity: 'warning' | 'error'
}

export interface InferSchemaResponse {
  suggested_join_key_type: JoinKeyType
  suggested_join_key_columns: Record<string, string>
  suggested_columns: DatasetColumn[]
  data_quality_flags: DataQualityFlag[]
  confidence: number
}

// ── Experiments ───────────────────────────────────────────────────────────────

export type ExperimentTarget =
  | 'ats_cover'
  | 'outright_winner'
  | 'total_over'
  | 'team_total_yards'

export type EvaluationMetric =
  | 'ats_hit_rate'
  | 'accuracy'
  | 'log_loss'
  | 'rmse'

export type ModelType =
  | 'xgboost'
  | 'logistic_regression'
  | 'random_forest'

export type ExperimentStatus = 'draft' | 'running' | 'complete' | 'failed'

export interface ExperimentFeature {
  dataset: string
  column: string
  semantic_name: string
}

export interface ExperimentConfig {
  experiment_id: string
  name: string
  description?: string
  created_at: string
  target: ExperimentTarget
  features: ExperimentFeature[]
  evaluation: {
    metric: EvaluationMetric
    success_threshold: number
    min_sample: number
  }
  methodology: {
    type: 'walk_forward'
    train_seasons: number
    test_seasons: number
    start_season: number
    end_season: number
  }
  model: {
    type: ModelType
    hyperparams: Record<string, unknown>
  }
  status: ExperimentStatus
  gate_passed: boolean | null
}

export interface BacktestRun {
  run_id: string
  experiment_id: string
  name: string
  run_at: string
  model_type: string
  features: string[]
  ats_hit_rate: number | null
  n_games_evaluated: number | null
  gate_passed: boolean | null
  notes: string | null
}

export interface ExperimentDetail {
  config: ExperimentConfig
  latest_run: BacktestRun | null
  run_history: BacktestRun[]
}

export interface RunExperimentResponse {
  run_id: string
  status: 'running'
  estimated_duration_seconds: number
}

export interface ExperimentRunStatus {
  experiment_id: string
  run_id: string
  status: 'running' | 'complete' | 'failed'
  progress: {
    folds_complete: number
    folds_total: number
  }
  started_at: string
  completed_at: string | null
  error: string | null
}

export interface Prediction {
  game_id: string
  season: number
  week: number
  /** Walk-forward fold index. Null for non-walk-forward runs. Added 2026-05-06. */
  fold: number | null
  home_team: string
  away_team: string
  predicted_home_cover_prob: number
  predicted_side: 'home' | 'away'
  actual_home_covered: boolean | null
  correct: number | null
  confidence_tier: 'high' | 'medium' | 'low'
}

export type CreateExperimentPayload = Omit<
  ExperimentConfig,
  'experiment_id' | 'created_at' | 'status' | 'gate_passed'
>

// ── Frameworks ────────────────────────────────────────────────────────────────

export interface Framework {
  framework_id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  base_experiment_id: string | null
  config: ExperimentConfig
}

export interface CreateFrameworkPayload {
  name: string
  description: string
  base_experiment_id?: string
}

// ── Features ──────────────────────────────────────────────────────────────────

export interface Feature {
  feature_id: string
  semantic_name: string
  description: string
  dataset: string
  data_type: DataType
  join_key_type: JoinKeyType
  license_tag: LicenseTag
}
