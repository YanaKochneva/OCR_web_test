import type { ReactNode } from 'react'

interface AlertProps {
  tone?: 'info' | 'warn' | 'error' | 'success'
  title?: string
  children: ReactNode
  className?: string
  onDismiss?: () => void
}

const TONES = {
  info: 'border-line bg-canvas text-ink-700',
  warn: 'border-warn-200 bg-warn-50 text-warn-700',
  error: 'border-bad-200 bg-bad-50 text-bad-700',
  success: 'border-good-200 bg-good-50 text-good-700',
} as const

export function Alert({
  tone = 'info',
  title,
  children,
  className = '',
  onDismiss,
}: AlertProps) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={[
        'flex items-start gap-3 rounded-xl border px-4 py-3 text-sm',
        TONES[tone],
        className,
      ].join(' ')}
    >
      <div className="min-w-0 flex-1">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className={title ? 'mt-1' : ''}>{children}</div>
      </div>
      {onDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Скрыть"
          className="focus-ring -mr-1 rounded p-1 text-current/70 transition hover:bg-black/5"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
            <path d="M6.3 5.3 5 6.6 8.4 10 5 13.4l1.3 1.3L10 11.3l3.4 3.4 1.3-1.3L11.3 10 14.7 6.6 13.4 5.3 10 8.7z" />
          </svg>
        </button>
      ) : null}
    </div>
  )
}

export function WarningList({
  warnings,
  tone = 'warn',
}: {
  warnings: string[]
  tone?: 'warn' | 'info'
}) {
  if (warnings.length === 0) return null
  return (
    <ul className="space-y-1.5">
      {warnings.map((warning, index) => (
        <li key={`${index}-${warning.slice(0, 16)}`} className="flex gap-2">
          <span
            className={
              tone === 'warn'
                ? 'mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn-500'
                : 'mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-400'
            }
          />
          <span>{warning}</span>
        </li>
      ))}
    </ul>
  )
}
