import { useRef, useState } from 'react'

import { Alert } from './Alert'

interface DropzoneProps {
  title: string
  subtitle: string
  note?: string
  file: File | null
  onFile: (file: File | null) => void
  maxUploadMb: number
  disabled?: boolean
}

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx']

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
  return `${Math.max(1, Math.round(bytes / 1024))} КБ`
}

export function Dropzone({
  title,
  subtitle,
  note,
  file,
  onFile,
  maxUploadMb,
  disabled = false,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const acceptFile = (candidate: File | null | undefined) => {
    if (!candidate) return
    const lower = candidate.name.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setError(`Недопустимый формат «${candidate.name}». Нужен PDF или DOCX.`)
      return
    }
    if (candidate.size > maxUploadMb * 1024 * 1024) {
      setError(`Файл больше ${maxUploadMb} МБ. Сожмите документ или разделите его.`)
      return
    }
    setError(null)
    onFile(candidate)
  }

  const openPicker = () => {
    if (!disabled) inputRef.current?.click()
  }

  return (
    <div className="card card-pad">
      <div className="mb-3">
        <p className="text-sm font-semibold">{title}</p>
        <p className="muted mt-1">{subtitle}</p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        className="sr-only"
        disabled={disabled}
        onChange={(event) => {
          acceptFile(event.target.files?.[0])
          // allow picking the same file again after removal
          event.target.value = ''
        }}
      />

      {file ? (
        <div className="flex items-center gap-3 rounded-xl border border-line bg-canvas px-4 py-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-50 text-accent-600">
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path d="M7 3h7l4 4v14H7z" strokeLinejoin="round" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{file.name}</p>
            <p className="text-xs text-ink-400">{formatSize(file.size)}</p>
          </div>
          <div className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={openPicker}
              disabled={disabled}
              className="focus-ring rounded-lg px-2 py-1 text-xs text-ink-700 transition hover:bg-surface disabled:text-ink-400"
            >
              Заменить
            </button>
            <button
              type="button"
              onClick={() => {
                setError(null)
                onFile(null)
              }}
              disabled={disabled}
              className="focus-ring rounded-lg px-2 py-1 text-xs text-bad-500 transition hover:bg-bad-50 disabled:text-ink-400"
            >
              Убрать
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={openPicker}
          disabled={disabled}
          onDragOver={(event) => {
            event.preventDefault()
            if (!disabled) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            if (!disabled) acceptFile(event.dataTransfer.files?.[0])
          }}
          className={[
            'focus-ring flex w-full flex-col items-center justify-center gap-2.5 rounded-xl border-2 border-dashed px-4 py-10 text-center transition',
            dragging
              ? 'border-accent-400 bg-accent-50'
              : 'border-line bg-canvas hover:border-accent-200 hover:bg-accent-50/40',
            disabled ? 'cursor-not-allowed opacity-60' : '',
          ].join(' ')}
        >
          <span className="grid h-11 w-11 place-items-center rounded-xl border border-line bg-surface text-accent-500 shadow-soft">
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path d="M12 16V4m0 0 4 4m-4-4L8 8" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" />
            </svg>
          </span>
          <span className="text-sm font-medium text-ink-700">
            Перетащите файл или нажмите, чтобы выбрать
          </span>
          <span className="text-xs text-ink-400">
            PDF или DOCX · до {maxUploadMb} МБ
          </span>
        </button>
      )}

      {note ? <p className="mt-3 text-xs text-ink-400">{note}</p> : null}
      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
    </div>
  )
}