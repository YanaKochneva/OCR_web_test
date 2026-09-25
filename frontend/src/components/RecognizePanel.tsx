import { Alert, WarningList } from './Alert'
import { Button } from './Button'
import {
  selectCanComputeMetrics,
  selectCanRecognize,
  selectMetricsGateHint,
  useBenchmarkStore,
} from '../store/useBenchmarkStore'

interface RecognizePanelProps {
  compact?: boolean
}

export function RecognizePanel({ compact = false }: RecognizePanelProps) {
  const sessionId = useBenchmarkStore((state) => state.sessionId)
  const health = useBenchmarkStore((state) => state.health)
  const documentType = useBenchmarkStore((state) => state.documentType)
  const documentTypes = useBenchmarkStore((state) => state.documentTypes)
  const uploadResult = useBenchmarkStore((state) => state.uploadResult)
  const sessionWarnings = useBenchmarkStore((state) => state.sessionWarnings)
  const recognizing = useBenchmarkStore((state) => state.recognizing)
  const recognition = useBenchmarkStore((state) => state.recognition)
  const recognizedReady = useBenchmarkStore((state) => state.recognizedReady)
  const referenceJsonReady = useBenchmarkStore((state) => state.referenceJsonReady)
  const metricsReady = useBenchmarkStore((state) => state.metricsReady)
  const recognize = useBenchmarkStore((state) => state.recognize)
  const computeMetrics = useBenchmarkStore((state) => state.computeMetrics)
  const metricsComputing = useBenchmarkStore((state) => state.metricsComputing)

  const canRecognize = useBenchmarkStore(selectCanRecognize)
  const canCompute = useBenchmarkStore(selectCanComputeMetrics)
  const gateHint = useBenchmarkStore(selectMetricsGateHint)

  const runRecognize = () => {
    void recognize(recognizedReady ? { force: true } : undefined)
  }

  const typeLabel =
    documentTypes.find((type) => type.id === documentType)?.label ?? '—'

  const recognizeHint = recognizing
    ? null
    : !sessionId
      ? 'Сначала загрузите пару файлов.'
      : !referenceJsonReady
        ? 'Эталонный JSON ещё не сформирован — вернитесь к загрузке.'
        : null

  const stats = recognition ? (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label="Модель" value={recognition.model} />
      <Stat label="Время запроса" value={`${recognition.request_seconds.toFixed(2)} с`} />
      <Stat label="Токены" value={String(recognition.usage.total_tokens)} />
      <Stat label="Страниц" value={String(recognition.pages.length)} />
    </div>
  ) : null

  if (compact) {
    return (
      <div className="space-y-4">
        {stats}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="success"
            size="lg"
            disabled={!canCompute}
            loading={metricsComputing}
            onClick={() => void computeMetrics()}
          >
            Рассчитать метрики
          </Button>
          <Button
            variant="secondary"
            disabled={!canRecognize}
            loading={recognizing}
            onClick={runRecognize}
          >
            Распознать заново
          </Button>
        </div>
        {!canCompute && gateHint ? <p className="muted">{gateHint}</p> : null}
        {sessionWarnings.length > 0 ? (
          <Alert tone="warn" title="Предупреждения">
            <WarningList warnings={sessionWarnings} />
          </Alert>
        ) : null}
      </div>
    )
  }

  return (
    <section>
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Шаг 3. Распознавание</h2>
        <p className="muted mt-1">
          Страницы скана рендерятся в изображения и отправляются в GLM 4.6;
          ответ сохраняется как распознанный JSON.
        </p>
      </div>

      <div className="card card-pad space-y-5">
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <InfoRow label="Сессия" value={sessionId ?? '—'} mono />
          <InfoRow label="Тип документа" value={typeLabel} />
          <InfoRow
            label="Эталон (файл А)"
            value={uploadResult?.reference.file.filename ?? '—'}
          />
          <InfoRow
            label="Скан (файл Б)"
            value={uploadResult?.recognized.file.filename ?? '—'}
          />
          <InfoRow
            label="Цепочка моделей"
            value={health ? health.model_chain.join(' → ') : '—'}
          />
          <InfoRow
            label="Режим"
            value={health?.mock_mode ? 'mock (без API-ключа)' : 'боевой GLM API'}
          />
        </div>

        {sessionWarnings.length > 0 ? (
          <Alert tone="warn" title="Предупреждения при загрузке">
            <WarningList warnings={sessionWarnings} />
          </Alert>
        ) : null}

        {!recognizedReady ? (
          <div className="space-y-3 border-t border-line pt-5">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                disabled={!canRecognize}
                loading={recognizing}
                onClick={runRecognize}
              >
                Распознать
              </Button>
              {recognizing ? (
                <span className="muted">
                  Отправка страниц в GLM — не закрывайте вкладку…
                </span>
              ) : recognizeHint ? (
                <span className="muted">{recognizeHint}</span>
              ) : (
                <span className="muted">
                  Один запрос на страницу; токены и время попадут в отчёт.
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-4 border-t border-line pt-5">
            {stats}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="success"
                size="lg"
                disabled={!canCompute}
                loading={metricsComputing}
                onClick={() => void computeMetrics()}
              >
                Рассчитать метрики
              </Button>
              <Button
                variant="secondary"
                disabled={!canRecognize}
                loading={recognizing}
                onClick={runRecognize}
              >
                Распознать заново
              </Button>
            </div>
            {!canCompute && gateHint ? <p className="muted">{gateHint}</p> : null}
            {metricsReady ? (
              <Alert tone="success">Метрики рассчитаны.</Alert>
            ) : null}
          </div>
        )}
      </div>
    </section>
  )
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className={`mt-0.5 ${mono ? 'font-mono text-xs sm:text-sm' : 'text-ink-700'}`}>
        {value}
      </p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-canvas px-3 py-2">
      <p className="label">{label}</p>
      <p className="mt-0.5 truncate text-sm font-semibold tabular-nums" title={value}>
        {value}
      </p>
    </div>
  )
}