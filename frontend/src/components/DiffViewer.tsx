import { useState } from 'react'
import type { ReactNode } from 'react'

import type { DiffOp, DiffSegment } from '../types'

interface DiffViewerProps {
  segments: DiffSegment[]
  truncated: boolean
}

function renderSegment(segment: DiffSegment, index: number) {
  const key = `${index}-${segment.op}`
  switch (segment.op) {
    case 'equal':
      return (
        <span key={key} className="diff-equal">
          {segment.reference}{' '}
        </span>
      )
    case 'insert':
      return (
        <span key={key} className="diff-insert">
          {segment.recognized}{' '}
        </span>
      )
    case 'delete':
      return (
        <span key={key} className="diff-delete">
          {segment.reference}{' '}
        </span>
      )
    case 'replace':
      return (
        <span key={key} className="diff-replace">
          {segment.reference} → {segment.recognized}{' '}
        </span>
      )
  }
}

export function DiffViewer({ segments, truncated }: DiffViewerProps) {
  const [onlyDiffs, setOnlyDiffs] = useState(false)

  const counts = segments.reduce(
    (acc, segment) => {
      acc[segment.op] += 1
      return acc
    },
    { equal: 0, insert: 0, delete: 0, replace: 0 } as Record<DiffOp, number>,
  )

  const visible = onlyDiffs
    ? segments.filter((segment) => segment.op !== 'equal')
    : segments

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-3 text-xs text-ink-500">
          <Legend className="bg-good-50 text-good-700">вставки: {counts.insert}</Legend>
          <Legend className="bg-bad-50 text-bad-700 line-through">
            пропуски: {counts.delete}
          </Legend>
          <Legend className="bg-warn-50 text-warn-700">замены: {counts.replace}</Legend>
          <Legend className="text-ink-400">совпадения: {counts.equal}</Legend>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-700">
          <input
            type="checkbox"
            checked={onlyDiffs}
            onChange={(event) => setOnlyDiffs(event.target.checked)}
            className="h-4 w-4 rounded border-line text-accent-500 focus:ring-accent-400"
          />
          Только различия
        </label>
      </div>

      <div className="thin-scroll card card-pad max-h-[520px] overflow-y-auto whitespace-pre-wrap font-mono text-sm leading-6">
        {visible.length === 0 ? (
          <p className="muted">Различий нет.</p>
        ) : (
          visible.map((segment, index) => renderSegment(segment, index))
        )}
      </div>

      {truncated ? (
        <p className="text-xs text-warn-700">
          Diff усечён по лимиту сегментов — полный текст доступен во вкладках
          «Эталон» и «Распознанный».
        </p>
      ) : null}
    </div>
  )
}

function Legend({
  children,
  className,
}: {
  children: ReactNode
  className: string
}) {
  return <span className={`rounded px-1.5 py-0.5 ${className}`}>{children}</span>
}