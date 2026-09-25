import { useState } from 'react'

import { api } from '../api/client'
import { Button } from './Button'
import { useBenchmarkStore } from '../store/useBenchmarkStore'
import type { DocumentTypeId, SessionSummary } from '../types'

const TYPE_LABELS: Record<DocumentTypeId, string> = {
  text_only: 'Только текст',
  text_tables: 'Текст + таблицы',
  text_tables_images: 'Текст + таблицы + изображения',
}

const pct = (value: number | null): string =>
  value === null ? '—' : `${(value * 100).toFixed(2)}%`

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })
}

export function SessionsPanel() {
  const sessions = useBenchmarkStore((state) => state.sessions)
  const loadSessions = useBenchmarkStore((state) => state.loadSessions)
  const restoreSession = useBenchmarkStore((state) => state.restoreSession)
  const [busyId, setBusyId] = useState<string | null>(null)

  const open = async (sessionId: string) => {
    setBusyId(sessionId)
    await restoreSession(sessionId)
    setBusyId(null)
  }

  const remove = async (sessionId: string) => {
    setBusyId(sessionId)
    try {
      await api.remove(sessionId)
      await loadSessions()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <div className="mb-4">
        <h2 className="text-base font-semibold">История тестов</h2>
        <p className="muted mt-1">
          Сохранённые сессии: откройте, чтобы посмотреть результаты заново.
        </p>
      </div>

      {sessions.length === 0 ? (
        <div className="card card-pad flex flex-col items-center gap-2.5 py-10 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-canvas text-ink-400">
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p className="text-sm font-medium text-ink-700">
            Здесь появится история тестов
          </p>
          <p className="muted max-w-sm">
            Выберите тип документа и загрузите пару файлов, чтобы получить CER,
            WER и Exact Success.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {sessions.map((session) => (
            <SessionRow
              key={session.session_id}
              session={session}
              busy={busyId === session.session_id}
              onOpen={() => void open(session.session_id)}
              onRemove={() => void remove(session.session_id)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function SessionRow({
  session,
  busy,
  onOpen,
  onRemove,
}: {
  session: SessionSummary
  busy: boolean
  onOpen: () => void
  onRemove: () => void
}) {
  const statusTone =
    session.metrics_status === 'ready'
      ? 'bg-good-50 text-good-700'
      : session.recognized_status === 'ready'
        ? 'bg-accent-50 text-accent-600'
        : 'bg-warn-50 text-warn-700'
  const statusLabel =
    session.metrics_status === 'ready'
      ? 'метрики готовы'
      : session.recognized_status === 'ready'
        ? 'JSON готов'
        : session.recognized_status === 'failed'
          ? 'ошибка'
          : 'ожидание'

  return (
    <li className="card card-pad flex flex-col gap-3 transition hover:border-ink-400/30 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-ink-900">
            {TYPE_LABELS[session.document_type] ?? session.document_type}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-xs ${statusTone}`}>
            {statusLabel}
          </span>
        </div>
        <p className="mt-1 truncate text-xs text-ink-500">
          {session.reference_filename ?? '—'} → {session.recognized_filename ?? '—'}
        </p>
        <p className="text-xs text-ink-400">
          {formatDate(session.created_at)}
          {session.model ? ` · ${session.model}` : ''}
        </p>
      </div>

      <div className="flex items-center justify-between gap-4 sm:justify-end">
        <div className="flex gap-4 text-xs tabular-nums">
          <Metric label="CER" value={pct(session.cer)} />
          <Metric label="WER" value={pct(session.wer)} />
          <Metric
            label="Exact"
            value={
              session.exact_match === null
                ? '—'
                : session.exact_match
                  ? 'Да'
                  : 'Нет'
            }
          />
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="secondary"
            loading={busy}
            onClick={onOpen}
            disabled={session.recognized_status === 'pending'}
          >
            Открыть
          </Button>
          <Button
            variant="ghost"
            onClick={onRemove}
            disabled={busy}
            className="text-bad-500 hover:bg-bad-50"
          >
            Удалить
          </Button>
        </div>
      </div>
    </li>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <p className="text-[10px] uppercase tracking-wide text-ink-400">{label}</p>
      <p className="font-medium text-ink-700">{value}</p>
    </div>
  )
}