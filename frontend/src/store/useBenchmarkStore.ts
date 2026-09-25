// Single Zustand store for the whole benchmark flow:
//   тип документа -> загрузка пары -> распознавание -> метрики
//
// The two readiness flags (`referenceJsonReady`, `recognizedJsonReady`) are what
// gate the "Рассчитать метрики" button; they are kept in sync with the backend.

import { create } from 'zustand'

import { ApiError, api, defaultNormalizationOptions } from '../api/client'
import type {
  DocumentJSON,
  DocumentTypeId,
  DocumentTypeInfo,
  HealthResponse,
  MetricsReport,
  NormalizationOptions,
  RecognitionMeta,
  ResultsResponse,
  SessionSummary,
  UploadResponse,
} from '../types'

export type Step = 'type' | 'upload' | 'recognize' | 'results'

interface BenchmarkState {
  // --- navigation -------------------------------------------------------
  step: Step
  setStep: (step: Step) => void

  // --- backend info -----------------------------------------------------
  health: HealthResponse | null
  documentTypes: DocumentTypeInfo[]
  loadBackendInfo: () => Promise<void>

  // --- step 1: document type --------------------------------------------
  documentType: DocumentTypeId | null
  selectDocumentType: (id: DocumentTypeId) => void

  // --- step 2: files ----------------------------------------------------
  referenceFile: File | null
  recognizedFile: File | null
  uploadProgress: number | null
  setFile: (role: 'reference' | 'recognized', file: File | null) => void
  upload: () => Promise<boolean>
  sessionId: string | null
  uploadResult: UploadResponse | null

  // --- extracted documents & warnings (previews / banners) ----------------
  referenceDocument: DocumentJSON | null
  recognizedDocument: DocumentJSON | null
  sessionWarnings: string[]

  // --- step 3: recognition ---------------------------------------------
  recognizing: boolean
  recognition: RecognitionMeta | null
  recognizedReady: boolean
  referenceJsonReady: boolean
  recognize: (options?: { model?: string; force?: boolean }) => Promise<boolean>

  // --- step 4: metrics --------------------------------------------------
  metricsComputing: boolean
  metrics: MetricsReport | null
  metricsReady: boolean
  normalization: NormalizationOptions
  setNormalization: (patch: Partial<NormalizationOptions>) => void
  computeMetrics: () => Promise<boolean>

  // --- session history / restore ---------------------------------------
  sessions: SessionSummary[]
  loadSessions: () => Promise<void>
  restoreSession: (sessionId: string) => Promise<boolean>
  reset: () => void

  // --- errors -----------------------------------------------------------
  error: string | null
  clearError: () => void
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Непредвиденная ошибка'
}

const initialState = {
  step: 'type' as Step,
  health: null,
  documentTypes: [],
  documentType: null,
  referenceFile: null,
  recognizedFile: null,
  uploadProgress: null,
  sessionId: null,
  uploadResult: null,
  referenceDocument: null,
  recognizedDocument: null,
  sessionWarnings: [],
  recognizing: false,
  recognition: null,
  recognizedReady: false,
  referenceJsonReady: false,
  metricsComputing: false,
  metrics: null,
  metricsReady: false,
  normalization: defaultNormalizationOptions(),
  error: null,
  sessions: [],
}

export const useBenchmarkStore = create<BenchmarkState>((set, get) => ({
  ...initialState,

  setStep: (step) => set({ step }),

  async loadBackendInfo() {
    try {
      const [health, types] = await Promise.all([api.health(), api.documentTypes()])
      set({ health, documentTypes: types.document_types })
    } catch (error) {
      set({ error: messageOf(error) })
    }
  },

  selectDocumentType(id) {
    const { documentType } = get()
    // Changing the type invalidates the pair: entities differ per type.
    if (documentType !== null && documentType !== id) {
      set({
        referenceFile: null,
        recognizedFile: null,
        referenceDocument: null,
        recognizedDocument: null,
        sessionWarnings: [],
        sessionId: null,
        uploadResult: null,
        recognizedReady: false,
        referenceJsonReady: false,
        metrics: null,
        metricsReady: false,
        recognition: null,
        error: null,
      })
    }
    set({ documentType: id, step: 'upload' })
  },

  setFile(role, file) {
    // Any file change invalidates the previous upload (and its session).
    const patch: Partial<BenchmarkState> = {
      sessionId: null,
      uploadResult: null,
      recognizedReady: false,
      referenceJsonReady: false,
      recognition: null,
      metrics: null,
      metricsReady: false,
      error: null,
    }
    if (role === 'reference') {
      patch.referenceFile = file
      patch.referenceDocument = null
    } else {
      patch.recognizedFile = file
      patch.recognizedDocument = null
    }
    patch.sessionWarnings = []
    set(patch)
  },

  async upload() {
    const { documentType, referenceFile, recognizedFile } = get()
    if (!documentType || !referenceFile || !recognizedFile) {
      set({ error: 'Выберите тип документа и загрузите оба файла.' })
      return false
    }
    set({ uploadProgress: 0, error: null })
    try {
      const result = await api.upload(
        documentType,
        referenceFile,
        recognizedFile,
        (percent) => set({ uploadProgress: percent }),
      )
      set({
        uploadResult: result,
        sessionId: result.session_id,
        referenceJsonReady: result.reference.ready,
        recognizedReady: result.recognized.ready,
        referenceDocument: result.reference.document,
        recognizedDocument: result.recognized.document,
        sessionWarnings: [
          ...new Set([...result.reference.warnings, ...result.recognized.warnings, ...result.warnings]),
        ],
        uploadProgress: null,
        step: 'recognize',
      })
      void get().loadSessions()
      return true
    } catch (error) {
      set({ error: messageOf(error), uploadProgress: null })
      return false
    }
  },

  async recognize(options) {
    const { sessionId } = get()
    if (!sessionId) {
      set({ error: 'Сначала загрузите пару файлов.' })
      return false
    }
    set({ recognizing: true, error: null })
    try {
      const result = await api.recognize(sessionId, options)
      set({
        recognizing: false,
        recognition: result.meta,
        recognizedReady: true,
        recognizedDocument: result.document,
        sessionWarnings: [
          ...new Set([...get().sessionWarnings, ...result.meta.warnings, ...result.warnings]),
        ],
        // a re-run invalidates previously computed metrics
        metrics: null,
        metricsReady: false,
        step: 'results',
      })
      void get().loadSessions()
      return true
    } catch (error) {
      set({ recognizing: false, error: messageOf(error) })
      return false
    }
  },

  setNormalization(patch) {
    set({ normalization: { ...get().normalization, ...patch } })
  },

  async computeMetrics() {
    const { sessionId, normalization } = get()
    if (!sessionId) {
      set({ error: 'Нет активной сессии.' })
      return false
    }
    set({ metricsComputing: true, error: null })
    try {
      const result = await api.metrics(sessionId, normalization)
      set({ metricsComputing: false, metrics: result.report, metricsReady: true })
      return true
    } catch (error) {
      set({ metricsComputing: false, error: messageOf(error) })
      return false
    }
  },

  async loadSessions() {
    try {
      const { sessions } = await api.sessions()
      set({ sessions })
    } catch {
      // history is a convenience feature - it never blocks the main flow
    }
  },

  async restoreSession(sessionId) {
    const previous = get().sessionId
    set({
      error: null,
      referenceJsonReady: false,
      recognizedReady: false,
      metricsReady: false,
    })
    try {
      const result: ResultsResponse = await api.results(sessionId)
      set({
        sessionId: result.session.session_id,
        documentType: result.session.document_type,
        referenceJsonReady: result.reference_json_ready,
        recognizedReady: result.recognized_json_ready,
        metricsReady: result.metrics_ready,
        metrics: result.metrics,
        recognition: result.recognition,
        referenceDocument: result.reference,
        recognizedDocument: result.recognized,
        sessionWarnings: [...result.warnings],
        step:
          result.metrics_ready || result.recognized_json_ready ? 'results' : 'upload',
      })
      return true
    } catch (error) {
      set({ sessionId: previous, error: messageOf(error) })
      return false
    }
  },

  reset() {
    set({ ...initialState })
  },

  clearError: () => set({ error: null }),
}))

// ---------------------------------------------------------------------------
//  selectors
// ---------------------------------------------------------------------------

export const selectCanUpload = (state: BenchmarkState): boolean =>
  Boolean(state.documentType && state.referenceFile && state.recognizedFile)

export const selectCanRecognize = (state: BenchmarkState): boolean =>
  Boolean(state.sessionId) && state.referenceJsonReady && !state.recognizing

/** The "Рассчитать метрики" button is enabled only with BOTH JSONs ready. */
export const selectCanComputeMetrics = (state: BenchmarkState): boolean =>
  state.referenceJsonReady && state.recognizedReady && !state.metricsComputing

export const selectMetricsGateHint = (state: BenchmarkState): string | null => {
  if (selectCanComputeMetrics(state)) return null
  if (!state.sessionId) return 'Сначала загрузите пару файлов и запустите распознавание.'
  if (!state.referenceJsonReady) return 'Эталонный JSON ещё не сформирован.'
  if (!state.recognizedReady) {
    return 'Распознанный JSON ещё не сформирован — нажмите «Распознать».'
  }
  if (state.metricsComputing) return 'Расчёт метрик выполняется…'
  return null
}
