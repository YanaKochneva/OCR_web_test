import type { Step } from '../store/useBenchmarkStore'

const STEPS: { id: Step; label: string }[] = [
  { id: 'type', label: 'Тип документа' },
  { id: 'upload', label: 'Загрузка' },
  { id: 'recognize', label: 'Распознавание' },
  { id: 'results', label: 'Метрики' },
]

interface StepperProps {
  current: Step
}

export function Stepper({ current }: StepperProps) {
  const activeIndex = STEPS.findIndex((step) => step.id === current)

  return (
    <nav aria-label="Ход теста" className="animate-fade-rise">
      <ol className="flex flex-wrap items-center gap-y-3">
        {STEPS.map((step, index) => {
          const state =
            index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'todo'
          return (
            <li
              key={step.id}
              aria-current={state === 'active' ? 'step' : undefined}
              className="flex items-center"
            >
              <div className="flex items-center gap-2.5">
                <span
                  className={[
                    'grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-semibold transition',
                    state === 'done'
                      ? 'bg-good-500 text-white'
                      : state === 'active'
                        ? 'bg-accent-500 text-white shadow-soft ring-4 ring-accent-100'
                        : 'border border-line bg-surface text-ink-400',
                  ].join(' ')}
                >
                  {state === 'done' ? '✓' : index + 1}
                </span>
                <span
                  className={[
                    'text-sm',
                    state === 'active'
                      ? 'font-semibold text-ink-900'
                      : state === 'done'
                        ? 'text-ink-700'
                        : 'text-ink-400',
                  ].join(' ')}
                >
                  {step.label}
                </span>
              </div>
              {index < STEPS.length - 1 ? (
                <span
                  aria-hidden="true"
                  className={[
                    'mx-3 h-px w-6 sm:w-10',
                    index < activeIndex ? 'bg-good-500' : 'bg-line',
                  ].join(' ')}
                />
              ) : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}