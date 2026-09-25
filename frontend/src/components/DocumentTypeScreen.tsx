import { Alert } from './Alert'
import { useBenchmarkStore } from '../store/useBenchmarkStore'
import type { DocumentTypeInfo } from '../types'

function EntityChips({ info }: { info: DocumentTypeInfo }) {
  const chips = [
    { on: info.entities.text, label: 'Текст' },
    { on: info.entities.tables, label: 'Таблицы' },
    { on: info.entities.images, label: 'Изображения' },
  ].filter((chip) => chip.on)

  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="rounded-full border border-line bg-canvas px-2 py-0.5 text-xs text-ink-500"
        >
          {chip.label}
        </span>
      ))}
    </div>
  )
}

export function DocumentTypeScreen() {
  const documentTypes = useBenchmarkStore((state) => state.documentTypes)
  const selectDocumentType = useBenchmarkStore((state) => state.selectDocumentType)

  return (
    <section>
      <div className="mb-6 max-w-2xl">
        <h2 className="text-lg font-semibold">Шаг 1. Выберите тип документа</h2>
        <p className="muted mt-1">
          Тип определяет, какие сущности участвуют в извлечении и метриках:
          текст, таблицы, растровые изображения.
        </p>
      </div>

      {documentTypes.length === 0 ? (
        <Alert tone="warn" title="Справочник типов недоступен">
          Не удалось получить список типов документов с сервера. Проверьте, что
          backend запущен, и обновите страницу.
        </Alert>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {documentTypes.map((info) => (
            <button
              key={info.id}
              type="button"
              onClick={() => selectDocumentType(info.id)}
              className="focus-ring card card-pad group flex flex-col items-start gap-3 text-left transition hover:-translate-y-0.5 hover:border-ink-400/30 hover:shadow-lift"
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-50 text-accent-600 transition group-hover:bg-accent-500 group-hover:text-white">
                <svg
                  viewBox="0 0 24 24"
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  aria-hidden="true"
                >
                  <path
                    d="M7 3h7l4 4v14H7z"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  <path d="M14 3v4h4M10 12h5M10 16h5" strokeLinecap="round" />
                </svg>
              </span>
              <div>
                <p className="font-semibold">{info.label}</p>
                <p className="muted mt-1">{info.description}</p>
              </div>
              <div className="mt-auto pt-1">
                <EntityChips info={info} />
              </div>
              <p className="text-xs text-ink-400">{info.accepted_hint}</p>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}