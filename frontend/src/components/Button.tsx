import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'success'
type Size = 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  hint?: string
  loading?: boolean
  icon?: ReactNode
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent-500 text-white shadow-soft hover:bg-accent-600 disabled:bg-accent-200 disabled:text-white/80 disabled:shadow-none',
  secondary:
    'border border-line bg-surface text-ink-900 shadow-sm hover:border-ink-400/40 hover:bg-canvas disabled:text-ink-400 disabled:shadow-none',
  ghost: 'text-ink-700 hover:bg-canvas hover:text-ink-900 disabled:text-ink-400',
  success:
    'bg-good-500 text-white shadow-soft hover:bg-good-700 disabled:bg-good-200 disabled:text-white/80 disabled:shadow-none',
}

const SIZES: Record<Size, string> = {
  md: 'px-4 py-2 text-sm',
  lg: 'px-5 py-2.5 text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  hint,
  loading = false,
  icon,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading
  return (
    <button
      {...rest}
      disabled={isDisabled}
      title={hint ?? rest.title}
      className={[
        'focus-ring inline-flex items-center justify-center gap-2 rounded-xl font-medium transition',
        'disabled:cursor-not-allowed',
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(' ')}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  )
}

function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="3"
        className="opacity-25"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export { Spinner }
