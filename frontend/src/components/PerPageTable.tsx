import type { ReactNode } from 'react'

import type { PageComparison, PageStatus } from '../types'

const STATUS: Record<PageStatus, { label: string; className: string }> = {
  matched: { label: 'в обеих', className: 'bg-good-50 text-good-700' },
  missing_in_recognized: {
    label: 'нет в распознанном',
    className: 'bg-bad-50 text-bad-700',
  },
  extra_in_recognized: {
    label: 'лишняя страница',
    className: 'bg-warn-50 text-warn-700',
  },
}

const pct = (value: number): string => `${(value * 100).toFixed(2)}%`

export function PerPageTable({ rows }: { rows: PageComparison[] }) {
  if (rows.length === 0) {
    return <p className="muted">Постраничные данные отсутствуют.</p>
  }

  return (
    <div className="card overflow-hidden">
      <div className="thin-scroll overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line bg-canvas text-left">
              <Th>Стр.</Th>
              <Th>Статус</Th>
              <Th right>CER</Th>
              <Th right>WER</Th>
              <Th right>Exact</Th>
              <Th right>Блоки А/Б</Th>
              <Th right>Табл. А/Б</Th>
              <Th right>Изобр. А/Б</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const status = STATUS[row.status]
              return (
                <tr key={row.page_number} className="border-b border-line last:border-0">
                  <Td>{row.page_number}</Td>
                  <Td>
                    <span className={`rounded px-1.5 py-0.5 text-xs ${status.className}`}>
                      {status.label}
                    </span>
                  </Td>
                  <Td right>{pct(row.metrics.cer)}</Td>
                  <Td right>{pct(row.metrics.wer)}</Td>
                  <Td right>{row.metrics.exact_match ? 'Да' : 'Нет'}</Td>
                  <Td right>
                    {row.reference_blocks}/{row.recognized_blocks}
                  </Td>
                  <Td right>
                    {row.reference_tables}/{row.recognized_tables}
                  </Td>
                  <Td right>
                    {row.reference_images}/{row.recognized_images}
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Th({
  children,
  right = false,
}: {
  children: ReactNode
  right?: boolean
}) {
  return (
    <th
      className={`px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-400 ${
        right ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  )
}

function Td({
  children,
  right = false,
}: {
  children: ReactNode
  right?: boolean
}) {
  return (
    <td
      className={`px-3 py-2 text-ink-700 tabular-nums ${right ? 'text-right' : 'text-left'}`}
    >
      {children}
    </td>
  )
}