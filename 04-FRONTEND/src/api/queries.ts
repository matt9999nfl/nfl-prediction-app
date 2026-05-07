/**
 * TanStack Query hooks — one per API resource.
 *
 * Query keys follow the pattern:
 *   ['resource']                  — list
 *   ['resource', id]              — detail
 *   ['resource', id, 'sub']       — sub-resource
 *
 * Mutations don't use query keys; callers invalidate the relevant list/detail
 * after success.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import { api } from './client'
import type {
  HealthResponse,
  Game,
  GameDetail,
  PaginatedResponse,
  Dataset,
  DatasetDetail,
  DatasetUploadResponse,
  SchemaMappingPayload,
  InferSchemaResponse,
  ExperimentConfig,
  ExperimentDetail,
  RunExperimentResponse,
  ExperimentRunStatus,
  Prediction,
  CreateExperimentPayload,
  Framework,
  CreateFrameworkPayload,
  Feature,
} from './types'

// ── Health ────────────────────────────────────────────────────────────────────

export function useHealth(
  options?: Partial<UseQueryOptions<HealthResponse>>,
) {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: () => api.get<HealthResponse>('/health'),
    staleTime: 30_000,
    retry: 1,
    ...options,
  })
}

// ── Games ─────────────────────────────────────────────────────────────────────

export interface GamesFilters {
  season?: number
  week?: number
  team?: string
  status?: 'scheduled' | 'final'
  limit?: number
  cursor?: string
}

export function useGames(filters: GamesFilters = {}) {
  return useQuery<PaginatedResponse<Game>>({
    queryKey: ['games', filters],
    queryFn: () =>
      api.get<PaginatedResponse<Game>>('/api/v1/games', {
        ...(filters as Record<string, string | number | boolean | undefined>),
      }),
    staleTime: 60_000,
  })
}

export function useGame(gameId: string) {
  return useQuery<GameDetail>({
    queryKey: ['games', gameId],
    queryFn: () => api.get<GameDetail>(`/api/v1/games/${gameId}`),
    staleTime: 60_000,
    enabled: Boolean(gameId),
  })
}

// ── Datasets ──────────────────────────────────────────────────────────────────

export function useDatasets(filters: { status?: string; limit?: number } = {}) {
  return useQuery<PaginatedResponse<Dataset>>({
    queryKey: ['datasets', filters],
    queryFn: () =>
      api.get<PaginatedResponse<Dataset>>('/api/v1/datasets', {
        ...(filters as Record<string, string | number | undefined>),
      }),
    staleTime: 30_000,
  })
}

export function useDataset(datasetId: string, options?: { refetchInterval?: number | false }) {
  return useQuery<DatasetDetail>({
    queryKey: ['datasets', datasetId],
    queryFn: () => api.get<DatasetDetail>(`/api/v1/datasets/${datasetId}`),
    enabled: Boolean(datasetId),
    staleTime: 15_000,
    ...options,
  })
}

export function useUploadDataset() {
  const qc = useQueryClient()
  return useMutation<DatasetUploadResponse, Error, FormData>({
    mutationFn: (form) =>
      api.postForm<DatasetUploadResponse>('/api/v1/datasets/upload', form),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useUpdateDatasetSchema() {
  const qc = useQueryClient()
  return useMutation<DatasetDetail, Error, { datasetId: string; payload: SchemaMappingPayload }>({
    mutationFn: ({ datasetId, payload }) =>
      api.put<DatasetDetail>(`/api/v1/datasets/${datasetId}/schema`, payload),
    onSuccess: (_data, { datasetId }) => {
      void qc.invalidateQueries({ queryKey: ['datasets', datasetId] })
      void qc.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useInferSchema() {
  return useMutation<InferSchemaResponse, Error, string>({
    mutationFn: (datasetId) =>
      api.post<InferSchemaResponse>(`/api/v1/datasets/${datasetId}/infer-schema`),
  })
}

export function useDeleteDataset() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (datasetId) => api.delete(`/api/v1/datasets/${datasetId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

// ── Experiments ───────────────────────────────────────────────────────────────

export function useExperiments(
  filters: { status?: string; gate_passed?: boolean; limit?: number } = {},
) {
  return useQuery<PaginatedResponse<ExperimentConfig>>({
    queryKey: ['experiments', filters],
    queryFn: () =>
      api.get<PaginatedResponse<ExperimentConfig>>('/api/v1/experiments', {
        ...(filters as Record<string, string | number | boolean | undefined>),
      }),
    staleTime: 30_000,
  })
}

export function useExperiment(experimentId: string) {
  return useQuery<ExperimentDetail>({
    queryKey: ['experiments', experimentId],
    queryFn: () =>
      api.get<ExperimentDetail>(`/api/v1/experiments/${experimentId}`),
    enabled: Boolean(experimentId),
    staleTime: 15_000,
  })
}

export function useExperimentStatus(
  experimentId: string,
  options?: { refetchInterval?: number | false; enabled?: boolean },
) {
  return useQuery<ExperimentRunStatus>({
    queryKey: ['experiments', experimentId, 'status'],
    queryFn: () =>
      api.get<ExperimentRunStatus>(`/api/v1/experiments/${experimentId}/status`),
    enabled: Boolean(experimentId) && (options?.enabled ?? true),
    refetchInterval: options?.refetchInterval,
    staleTime: 0,
  })
}

export function useExperimentPredictions(
  experimentId: string,
  season: number,
  options?: { fold?: number; limit?: number; enabled?: boolean },
) {
  return useQuery<PaginatedResponse<Prediction>>({
    queryKey: ['experiments', experimentId, 'predictions', season, options?.fold],
    queryFn: () =>
      api.get<PaginatedResponse<Prediction>>(
        `/api/v1/experiments/${experimentId}/predictions`,
        {
          season,
          ...(options?.fold !== undefined ? { fold: options.fold } : {}),
          limit: options?.limit ?? 500,
        },
      ),
    enabled: (options?.enabled ?? true) && Boolean(experimentId),
    staleTime: 60_000,
  })
}

export function useCreateExperiment() {
  const qc = useQueryClient()
  return useMutation<{ experiment_id: string; status: string }, Error, CreateExperimentPayload>({
    mutationFn: (payload) =>
      api.post<{ experiment_id: string; status: string }>('/api/v1/experiments', payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}

export function useRunExperiment() {
  const qc = useQueryClient()
  return useMutation<RunExperimentResponse, Error, string>({
    mutationFn: (experimentId) =>
      api.post<RunExperimentResponse>(`/api/v1/experiments/${experimentId}/run`),
    onSuccess: (_data, experimentId) => {
      void qc.invalidateQueries({ queryKey: ['experiments', experimentId] })
      void qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}

// ── Frameworks ────────────────────────────────────────────────────────────────

export function useFrameworks() {
  return useQuery<PaginatedResponse<Framework>>({
    queryKey: ['frameworks'],
    queryFn: () => api.get<PaginatedResponse<Framework>>('/api/v1/frameworks'),
    staleTime: 30_000,
  })
}

export function useFramework(frameworkId: string) {
  return useQuery<Framework>({
    queryKey: ['frameworks', frameworkId],
    queryFn: () => api.get<Framework>(`/api/v1/frameworks/${frameworkId}`),
    enabled: Boolean(frameworkId),
    staleTime: 30_000,
  })
}

export function useCreateFramework() {
  const qc = useQueryClient()
  return useMutation<Framework, Error, CreateFrameworkPayload>({
    mutationFn: (payload) =>
      api.post<Framework>('/api/v1/frameworks', payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['frameworks'] })
    },
  })
}

export function useDeleteFramework() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (frameworkId) => api.delete(`/api/v1/frameworks/${frameworkId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['frameworks'] })
    },
  })
}

// ── Features ──────────────────────────────────────────────────────────────────

export function useFeatures(
  filters: { dataset?: string; data_type?: string; join_key_type?: string } = {},
) {
  return useQuery<{ data: Feature[] }>({
    queryKey: ['features', filters],
    queryFn: () =>
      api.get<{ data: Feature[] }>('/api/v1/features', {
        ...(filters as Record<string, string | undefined>),
      }),
    staleTime: 300_000, // features don't change often
  })
}
