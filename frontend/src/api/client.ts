// Thin wrapper around the FastAPI endpoints. Everything stays same-origin:
// Vite proxies /api and /static to the backend in dev, and FastAPI serves the
// built SPA in production.

import type {
  DocumentTypeId,
  DocumentTypeListResponse,
  HealthResponse,
  MetricsResponse,
  NormalizationOptions,
  RecognizeResponse,
  ResultsResponse,
  SessionSummary,
  UploadResponse,
} from '../types'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const DEFAULT_OPTIONS: NormalizationOptions = {
  lowercase: true,
  collapse_whitespace: true,
  unify_quotes: true,
  unify_dashes: true,
  remove_punctuation: false,
  strip_diacritics: false,
  label: 'default',
}

export const defaultNormalizationOptions = (): NormalizationOptions => ({
  ...DEFAULT_OPTIONS,
})

async function parseError(response: Response): Promise<never> {
  let detail = `HTTP ${response.status}`
  let code: string | undefined
  try {
    const body = (await response.json()) as { detail?: unknown; code?: string }
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail)) {
      // FastAPI validation error shape
      detail = body.detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string }
          const where = Array.isArray(entry.loc) ? entry.loc.join('.') : ''
          return where ? `${where}: ${entry.msg ?? 'ошибка'}` : entry.msg ?? 'ошибка'
        })
        .join('; ')
    }
    code = body.code
  } catch {
    // response had no JSON body - keep the generic message
  }
  throw new ApiError(detail, response.status, code)
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    throw new ApiError(
      'Не удалось связаться с сервером. Проверьте, что backend запущен на порту 8000.',
      0,
      'network_error',
    )
  }
  if (!response.ok) {
    await parseError(response)
  }
  return (await response.json()) as T
}

export const api = {
  health(): Promise<HealthResponse> {
    return requestJson<HealthResponse>('/api/health')
  },

  documentTypes(): Promise<DocumentTypeListResponse> {
    return requestJson<DocumentTypeListResponse>('/api/document-types')
  },

  upload(
    documentType: DocumentTypeId,
    reference: File,
    recognized: File,
    onProgress?: (percent: number) => void,
  ): Promise<UploadResponse> {
    const body = new FormData()
    body.append('document_type', documentType)
    body.append('reference', reference)
    body.append('recognized', recognized)

    // fetch() cannot report upload progress, so XHR is used here.
    return new Promise<UploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/upload')
      xhr.responseType = 'json'
      xhr.upload.onprogress = (event) => {
        if (onProgress && event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      }
      xhr.onload = () => {
        const payload = xhr.response as (UploadResponse & { detail?: string }) | null
        if (xhr.status >= 200 && xhr.status < 300 && payload) {
          resolve(payload)
          return
        }
        reject(
          new ApiError(
            (payload && typeof payload.detail === 'string'
              ? payload.detail
              : `HTTP ${xhr.status}`),
            xhr.status,
          ),
        )
      }
      xhr.onerror = () =>
        reject(new ApiError('Ошибка сети при загрузке файлов.', 0, 'network_error'))
      xhr.send(body)
    })
  },

  recognize(sessionId: string, options?: { model?: string; force?: boolean }): Promise<RecognizeResponse> {
    return requestJson<RecognizeResponse>('/api/recognize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        model: options?.model ?? null,
        force: options?.force ?? false,
      }),
    })
  },

  metrics(
    sessionId: string,
    normalization: NormalizationOptions,
    includeDiff = true,
  ): Promise<MetricsResponse> {
    return requestJson<MetricsResponse>('/api/metrics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        options: normalization,
        include_diff: includeDiff,
        recompute: true,
      }),
    })
  },

  results(sessionId: string): Promise<ResultsResponse> {
    return requestJson<ResultsResponse>(`/api/results/${encodeURIComponent(sessionId)}`)
  },

  sessions(): Promise<{ sessions: SessionSummary[] }> {
    return requestJson<{ sessions: SessionSummary[] }>('/api/sessions')
  },

  remove(sessionId: string): Promise<{ deleted: string }> {
    return requestJson<{ deleted: string }>(
      `/api/results/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE' },
    )
  },
}
