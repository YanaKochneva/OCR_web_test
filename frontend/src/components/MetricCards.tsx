import type { MetricsReport } from '../types'

const pct = (value: number): string => `${(value * 100).toFixed(2)}%`

interface MetricCardsProps {
  report: MetricsReport
}

export function MetricCards({ report }: MetricCardsProps) {
  const { overall, performance: perf } = report

  const cards: {
    key: string
    label: string
    value: string
    hint: string
    tone?: 'good' | 'bad'
  }[] = [
    {
      key: 'cer',
      label: 'CER (ошибки символов)',
      value: pct(overall.cer),
      hint: `редакт. расст. ${overall.char_edit_distance} из ${overall.reference_chars} симв.`,
      tone: overall.cer === 0 ? 'good' : undefined,
    },
    {
      key: 'wer',
      label: 'WER (ошибки слов)',
      value: pct(overall.wer),
      hint: `редакт. расст. ${overall.word_edit_distance} из ${overall.reference_words} слов`,
      tone: overall.wer === 0 ? 'good' : undefined,
    },
    {
      key: 'exact',
      label: 'Exact Success',
      value: overall.exact_match ? 'Да' : 'Нет',
      hint: 'полное совпадение после нормализации',
      tone: overall.exact_match ? 'good' : 'bad',
    },
    {
      key: 'time',
      label: 'Время запроса',
      value: `${perf.request_seconds.toFixed(2)} с`,
      hint: `${perf.pages_processed} стр.${perf.retries > 0 ? ` · повторов: ${perf.retries}` : ''}`,
    },
    {
      key: 'tokens',
      label: 'Токены',
      value: String(perf.total_tokens),
      hint: `prompt ${perf.prompt_tokens} + completion ${perf.completion_tokens}`,
    },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => (
        <div key={card.key} className="card card-pad">
          <p className="label">{card.label}</p>
          <p
            className={[
              'mt-2 text-2xl font-semibold leading-none tracking-tight tabular-nums',
              card.tone === 'good'
                ? 'text-good-700'
                : card.tone === 'bad'
                  ? 'text-bad-700'
                  : 'text-ink-900',
            ].join(' ')}
          >
            {card.value}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-ink-400">{card.hint}</p>
        </div>
      ))}
    </div>
  )
}