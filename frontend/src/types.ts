// TypeScript mirror of the FastAPI/pydantic schemas (backend/app/schemas/*).
// Keep this file in sync when the backend contract changes.

export type DocumentTypeId = 'text_only' | 'text_tables' | 'text_tables_images'

export type DocumentSource = 'reference' | 'recognized'

export type BlockType = 'text' | 'table' | 'image'

export interface EntitySet {
  text: boolean
  tables: boolean
  images: boolean
}

export interface DocumentTypeInfo {
  id: DocumentTypeId
  label: string
  description: string
  entities: EntitySet
  accepted_hint: string
}

export interface DocumentTypeListResponse {
  document_types: DocumentTypeInfo[]
  default: DocumentTypeId
}

/** One content block. `bbox` is [x, y, w, h] in page pixels. */
export interface DocumentBlock {
  id: string
  type: BlockType
  content: string | null
  rows: string[][] | null
  url: string | null
  caption: string | null
  bbox: number[] | null
  page_size: number[] | null
  confidence: number | null
  source: string | null
}

export interface DocumentPage {
  page_number: number
  width: number | null
  height: number | null
  blocks: DocumentBlock[]
}

export interface DocumentJSON {
  document_type: DocumentTypeId
  source: DocumentSource
  session_id: string
  pages: DocumentPage[]
  model: string | null
  parser: string | null
  created_at: string
}

export interface FileInfo {
  filename: string
  stored_path: string
  size_bytes: number
  extension: string
  mime_type: string
  sha256: string
  page_count: number | null
  has_text_layer: boolean | null
  text_layer_chars: number | null
  render_backend: string | null
}

export interface UploadedSide {
  role: string
  file: FileInfo
  document: DocumentJSON | null
  ready: boolean
  warnings: string[]
}

export interface UploadResponse {
  session_id: string
  document_type: DocumentTypeId
  reference: UploadedSide
  recognized: UploadedSide
  warnings: string[]
  next_step: string
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cached_tokens: number
  reasoning_tokens: number
}

export interface PageRecognitionMeta {
  page_number: number
  model: string
  request_seconds: number
  usage: TokenUsage
  text_blocks: number
  table_blocks: number
  image_blocks: number
  raw_response_chars: number
  attempts: number
  error: string | null
}

export interface RecognitionMeta {
  session_id: string
  model: string
  requested_models: string[]
  fallback_models: string[]
  request_seconds: number
  usage: TokenUsage
  pages: PageRecognitionMeta[]
  render_dpi: number
  prompt_version: string
  started_at: string
  finished_at: string
  warnings: string[]
}

export interface RecognizeResponse {
  session_id: string
  document_type: DocumentTypeId
  model: string
  document: DocumentJSON
  meta: RecognitionMeta
  warnings: string[]
  next_step: string
}

export interface NormalizationOptions {
  lowercase: boolean
  collapse_whitespace: boolean
  unify_quotes: boolean
  unify_dashes: boolean
  remove_punctuation: boolean
  strip_diacritics: boolean
  label: string
}

export interface PairMetrics {
  cer: number
  wer: number
  exact_match: boolean
  similarity: number
  char_edit_distance: number
  word_edit_distance: number
  reference_chars: number
  recognized_chars: number
  reference_words: number
  recognized_words: number
}

export type PageStatus = 'matched' | 'missing_in_recognized' | 'extra_in_recognized'

export interface PageComparison {
  page_number: number
  status: PageStatus
  metrics: PairMetrics
  reference_blocks: number
  recognized_blocks: number
  reference_tables: number
  recognized_tables: number
  reference_images: number
  recognized_images: number
}

export interface TableMetrics {
  reference_tables: number
  recognized_tables: number
  matched_rows: number
  cell_accuracy: number
  row_count_delta: number
}

export interface PerformanceMetrics {
  model: string | null
  request_seconds: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cached_tokens: number
  reasoning_tokens: number
  pages_processed: number
  per_page_seconds: number[]
  retries: number
  fallback_models: string[]
}

export type DiffOp = 'equal' | 'insert' | 'delete' | 'replace'

export interface DiffSegment {
  op: DiffOp
  reference: string
  recognized: string
}

export interface MetricsReport {
  session_id: string
  document_type: string
  generated_at: string
  options: NormalizationOptions
  accounted_entities: string[]
  overall: PairMetrics
  per_page: PageComparison[]
  tables: TableMetrics | null
  performance: PerformanceMetrics
  reference_text_preview: string
  recognized_text_preview: string
  diff: DiffSegment[]
  diff_truncated: boolean
  notes: string[]
}

export interface MetricsResponse {
  session_id: string
  document_type: DocumentTypeId
  report: MetricsReport
  next_step: string
}

export interface SessionSummary {
  session_id: string
  document_type: DocumentTypeId
  created_at: string
  updated_at: string | null
  reference_filename: string | null
  recognized_filename: string | null
  recognized_status: 'pending' | 'ready' | 'failed'
  metrics_status: 'pending' | 'ready'
  model: string | null
  cer: number | null
  wer: number | null
  exact_match: boolean | null
  request_seconds: number | null
  total_tokens: number | null
}

export interface ResultsResponse {
  session: SessionSummary
  reference_file: FileInfo | null
  recognized_file: FileInfo | null
  reference: DocumentJSON | null
  recognized: DocumentJSON | null
  recognition: RecognitionMeta | null
  metrics: MetricsReport | null
  warnings: string[]
  reference_json_ready: boolean
  recognized_json_ready: boolean
  metrics_ready: boolean
}

export interface HealthResponse {
  status: string
  app: string
  model: string
  model_chain: string[]
  base_url: string
  api_key_configured: boolean
  mock_mode: boolean
  render_dpi: number
  max_upload_mb: number
}
