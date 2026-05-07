/**
 * Thin API client.
 *
 * - Reads base URL and API key from env vars.
 * - In dev, the Vite proxy forwards /api and /health to localhost:8000,
 *   so VITE_API_BASE_URL can be left empty.
 * - In production, set VITE_API_BASE_URL to the full backend origin.
 * - Throws ApiRequestError on non-2xx responses, with structured error info.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? ''

// ── Error type ────────────────────────────────────────────────────────────────

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId: string,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

// ── Core request ──────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`

  const extraHeaders: Record<string, string> = {
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
  }

  // Don't force Content-Type for FormData; browser sets it with the boundary.
  const isFormData = init?.body instanceof FormData
  if (!isFormData && init?.method !== 'GET' && init?.method !== undefined) {
    extraHeaders['Content-Type'] = 'application/json'
  }

  const response = await fetch(url, {
    ...init,
    headers: {
      ...extraHeaders,
      ...(init?.headers as Record<string, string> | undefined),
    },
  })

  if (response.status === 204) {
    return undefined as T
  }

  if (!response.ok) {
    let errorData: { error?: string; code?: string; request_id?: string }
    try {
      errorData = (await response.json()) as typeof errorData
    } catch {
      errorData = {}
    }
    throw new ApiRequestError(
      response.status,
      errorData.code ?? 'internal_error',
      errorData.error ?? `HTTP ${response.status}`,
      errorData.request_id ?? response.headers.get('X-Request-ID') ?? 'unknown',
    )
  }

  return response.json() as Promise<T>
}

// ── Public API surface ────────────────────────────────────────────────────────

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>) => {
    const url = params
      ? `${path}?${new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)]),
        )}`
      : path
    return request<T>(url)
  },

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body != null ? JSON.stringify(body) : undefined,
    }),

  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),

  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),

  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
