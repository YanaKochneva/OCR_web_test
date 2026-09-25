import { useState } from 'react'

import { Alert, WarningList } from './Alert'
import { Button } from './Button'
import { DiffViewer } from './DiffViewer'
import { DocumentPreview } from './DocumentPreview'
import { MetricCards } from './MetricCards'
import { PerPageTable } from './PerPageTable'
import { useBenchmarkStore } from '../store/useBenchmarkStore'
import type { NormalizationOptions } from '../types'

type TabId = 'pages' | 'diff' | 'reference' | 'recognized'

const TABS: { id: TabId; label: string }[] = [
  { id: 'pages', label: 'Постранично' },
  { id: 'diff', label: 'Diff' },
  { id: 'reference', label: 'Эталон' },
  { id: 'recognized', label: 'Распознанный' },
]

type BoolKey =
  | 'lowercase'
  | 'collapse_whitespace'
  | 'unify_quotes'
  | 'unify_dashes'
  | 'remove_punctuation'
  | 'strip_diacritics'

const TOGGLES: { key: BoolKey; label: string; hint: string }[] = [
  { key: 'lowercase', label: 'Нижний регистр', hint: 'aA → aa' },
  { key: 'collapse_whitespace', label: 'Схлопнуть пробелы', hint: '«  » → « »' },
  { key: 'unify_quotes', label: 'Единые кавычки', hint: '“”„" → «»' },
  { key: 'unify_dashes', label: 'Единые тире', hint: '–—− → -' },
  { key: 'remove_punctuation', label: 'Без пунктуации', hint: ',.!?;: → пусто' },
  { key: 'strip_diacritics', label: 'Без диакритики', hint: 'é → e' },
]

const ENTITY_LABELS: Record<string, string> = {
  text: 'Текст',
  tables: 'Таблицы',
  images: 'Изображения',
}

export function MetricsPanel() {
  const metrics = useBenchmarkStore((state) => state.metrics)
  const metricsComputing = useBenchmarkStore((state) => state.metricsComputing)
  const computeMetrics = useBenchmarkStore((state) => state.computeMetrics)
  const normalization = useBenchmarkStore((state) => state.normalization)
  const setNormalization = useBenchmarkStore((state) => state.setNormalization)
  const sessionId = useBenchmarkStore((state) => state.sessionId)
  const sessionWarnings = useBenchmarkStore((state) => state.sessionWarnings)
  const referenceDocument = useBenchmarkStore((state) => state.referenceDocument)
  const recognizedDocument = useBenchmarkStore((state) => state.recognizedDocument)
  const recognition = useBenchmarkStore((state) => state.recognition)
  const [tab, setTab] = useState<TabId>('pages')

  if (!metrics) return null

  const toggle = (key: BoolKey, checked: boolean) => {
    const patch = { [key]: checked } as Record<string, boolean>
    setNormalization(patch as unknown as Partial<NormalizationOptions>)
  }

  const warnings = sessionWarnings

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Результаты бенчмарка</h2>
          <p className="muted mt-1">
            Сессия <span className="font-mono text-xs">{sessionId ?? '—'}</span>
            {' · '}нормализация: {metrics.options.label}
            {' · '}{new Date(metrics.generated_at).toLocaleString('ru-RU')}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {metrics.accounted_entities.map((entity) => (
            <span
              key={entity}
              className="rounded-full border border-line bg-canvas px-2.5 py-1 text-xs text-ink-500"
            >
              {ENTITY_LABELS[entity] ?? entity}
            </span>
          ))}
        </div>
      </div>

      <MetricCards report={metrics} />

      {warnings.length > 0 ? (
        <Alert tone="warn" title="Предупреждения">
          <WarningList warnings={warnings} />
        </Alert>
      ) : null}
      {metrics.notes.length > 0 ? (
        <Alert tone="info" title="Примечания к расчёту">
          <WarningList warnings={metrics.notes} tone="info" />
        </Alert>
      ) : null}

      <div className="card card-pad">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Нормализация текста</h3>
            <p className="muted mt-0.5">
              Настройки применяются при расчёте. Текущий набор:{' '}
              <span className="font-medium text-ink-700">{normalization.label}</span>
            </p>
          </div>
          <Button
            loading={metricsComputing}
            onClick={() => void computeMetrics()}
            hint="Пересчитать CER/WER/Exact с текущими настройками"
          >
            Пересчитать метрики
          </Button>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {TOGGLES.map((toggleItem) => (
            <label
              key={toggleItem.key}
              className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-canvas px-3 py-2 transition hover:border-ink-400/30 hover:bg-surface"
              title={toggleItem.hint}
            >
              <input
                type="checkbox"
                checked={normalization[toggleItem.key]}
                onChange={(event) => toggle(toggleItem.key, event.target.checked)}
                className="h-4 w-4 rounded border-line text-accent-500 focus:ring-accent-400"
              />
              <span className="text-sm text-ink-700">{toggleItem.label}</span>
              <span className="ml-auto font-mono text-xs text-ink-400">
                {toggleItem.hint}
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="segmented" role="tablist" aria-label="Разделы результатов">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={[
              'segmented-item',
              tab === item.id ? 'segmented-item-active' : '',
            ].join(' ')}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'pages' ? (
        <div className="space-y-4">
          <PerPageTable rows={metrics.per_page} />
          {metrics.tables ? (
            <div className="card card-pad grid gap-4 sm:grid-cols-4">
              <MiniStat label="Таблиц эталон" value={String(metrics.tables.reference_tables)} />
              <MiniStat label="Таблиц распознано" value={String(metrics.tables.recognized_tables)} />
              <MiniStat
                label="Точность ячеек"
                value={`${(metrics.tables.cell_accuracy * 100).toFixed(1)}%`}
              />
              <MiniStat
                label="Δ строк"
                value={
                  metrics.tables.row_count_delta > 0
                    ? `+${metrics.tables.row_count_delta}`
                    : String(metrics.tables.row_count_delta)
                }
              />
            </div>
          ) : null}
          <div className="card card-pad grid gap-4 sm:grid-cols-4">
            <MiniStat label="Модель" value={metrics.performance.model ?? '—'} />
            <MiniStat
              label="Сек./стр."
              value={
                metrics.performance.per_page_seconds.length > 0
                  ? (
                      metrics.performance.per_page_seconds.reduce((a, b) => a + b, 0) /
                      metrics.performance.per_page_seconds.length
                    ).toFixed(2)
                  : '—'
              }
            />
            <MiniStat label="Кэш/рассужд." value={`${metrics.performance.cached_tokens}/${metrics.performance.reasoning_tokens}`} />
            <MiniStat
              label="Fallback"
              value={
                metrics.performance.fallback_models.length > 0
                  ? metrics.performance.fallback_models.join(', ')
                  : 'нет'
              }
            />
          </div>
        </div>
      ) : null}

      {tab === 'diff' ? (
        <DiffViewer segments={metrics.diff} truncated={metrics.diff_truncated} />
      ) : null}

      {tab === 'reference' ? (
        <DocumentPreview
          title="Эталон (файл А)"
          subtitle="JSON, построенный из исходного документа."
          document={referenceDocument}
        />
      ) : null}

      {tab === 'recognized' ? (
        <DocumentPreview
          title="Распознанный (файл Б)"
          subtitle={
            recognition
              ? `Модель: ${recognition.model} · prompt v${recognition.prompt_version}`
              : 'JSON, полученный из GLM.'
          }
          document={recognizedDocument}
        />
      ) : null}
    </section>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-ink-700" title={value}>
        {value}
      </p>
    </div>
  )
}