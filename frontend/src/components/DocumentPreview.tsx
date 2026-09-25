import { Alert } from './Alert'
import type { DocumentBlock, DocumentJSON } from '../types'

interface DocumentPreviewProps {
  title: string
  subtitle?: string
  document: DocumentJSON | null
}

export function DocumentPreview({ title, subtitle, document }: DocumentPreviewProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle ? <p className="muted mt-0.5">{subtitle}</p> : null}
      </div>

      {!document ? (
        <Alert tone="info">Документ ещё не сформирован.</Alert>
      ) : document.pages.length === 0 ? (
        <Alert tone="info">Документ пуст — блоки не найдены.</Alert>
      ) : (
        document.pages.map((page) => (
          <article key={page.page_number} className="card card-pad">
            <header className="mb-3 flex items-center justify-between">
              <span className="label">Страница {page.page_number}</span>
              <span className="text-xs text-ink-400">
                {page.blocks.length} блоков · {page.width ?? '?'}×{page.height ?? '?'}
              </span>
            </header>
            <div className="space-y-3">
              {page.blocks.map((block) => (
                <BlockView key={block.id} block={block} />
              ))}
            </div>
          </article>
        ))
      )}
    </div>
  )
}

function BlockView({ block }: { block: DocumentBlock }) {
  if (block.type === 'text') {
    return (
      <p className="whitespace-pre-wrap text-sm leading-6 text-ink-700">
        {block.content ?? '—'}
      </p>
    )
  }

  if (block.type === 'table') {
    const rows = block.rows ?? []
    if (rows.length === 0) {
      return <p className="muted">Пустая таблица.</p>
    }
    const [head, ...body] = rows
    return (
      <div className="thin-scroll overflow-x-auto rounded-xl border border-line">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-canvas">
              {head.map((cell, index) => (
                <th
                  key={index}
                  className="border-b border-line px-2 py-1.5 text-left font-medium text-ink-700"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line last:border-0">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-2 py-1.5 text-ink-700">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // image
  return (
    <figure className="rounded-xl border border-line bg-canvas p-3">
      {block.url ? (
        <img
          src={block.url}
          alt={block.caption ?? 'Изображение страницы'}
          loading="lazy"
          className="max-h-64 rounded-lg object-contain"
        />
      ) : (
        <div className="grid h-24 place-items-center rounded-lg bg-surface text-xs text-ink-400">
          Изображение недоступно
        </div>
      )}
      <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-400">
        <span>{block.caption ?? 'без подписи'}</span>
        {block.bbox ? (
          <span className="font-mono">
            bbox [{block.bbox.map((value) => Math.round(value)).join(', ')}]
          </span>
        ) : null}
      </figcaption>
    </figure>
  )
}