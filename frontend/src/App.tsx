import { useEffect } from 'react'

import { ErrorBanner } from './components/ErrorBanner'
import { DocumentTypeScreen } from './components/DocumentTypeScreen'
import { MetricsPanel } from './components/MetricsPanel'
import { RecognizePanel } from './components/RecognizePanel'
import { SessionsPanel } from './components/SessionsPanel'
import { Stepper } from './components/Stepper'
import { UploadScreen } from './components/UploadScreen'
import { useBenchmarkStore } from './store/useBenchmarkStore'

export default function App() {
  const step = useBenchmarkStore((state) => state.step)
  const health = useBenchmarkStore((state) => state.health)
  const metrics = useBenchmarkStore((state) => state.metrics)
  const loadBackendInfo = useBenchmarkStore((state) => state.loadBackendInfo)
  const loadSessions = useBenchmarkStore((state) => state.loadSessions)
  const reset = useBenchmarkStore((state) => state.reset)

  useEffect(() => {
    void loadBackendInfo()
    void loadSessions()
  }, [loadBackendInfo, loadSessions])

  const showResults = step === 'results' && metrics !== null

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-40 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex max-w-content flex-col gap-2.5 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-500 text-[11px] font-semibold tracking-wide text-white shadow-soft">
              GLM
            </span>
            <div>
              <h1 className="text-[15px] font-semibold leading-tight">
                Бенчмарк извлечения документов
              </h1>
              <p className="text-xs text-ink-400">
                Мультимодальный режим GLM 4.6 · CER · WER · Exact Success
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 text-xs">
            {health ? (
              <span
                className="inline-flex items-center gap-2 rounded-full border border-line bg-canvas px-3 py-1.5 text-ink-700"
                title={`Эндпоинт: ${health.base_url}`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    health.api_key_configured ? 'bg-good-500' : 'bg-warn-500'
                  }`}
                />
                <span className="font-medium">{health.model}</span>
                {health.mock_mode ? (
                  <span className="rounded bg-warn-50 px-1.5 py-0.5 text-warn-700">
                    mock
                  </span>
                ) : null}
                {!health.api_key_configured && !health.mock_mode ? (
                  <span className="text-warn-700">нет ключа</span>
                ) : null}
              </span>
            ) : (
              <span className="text-ink-400">проверка соединения…</span>
            )}
            <button
              type="button"
              onClick={reset}
              className="focus-ring rounded-lg border border-line bg-surface px-3 py-1.5 font-medium text-ink-700 transition hover:border-ink-400/40 hover:text-ink-900"
            >
              Новый тест
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-content px-4 py-8 sm:px-6 sm:py-10">
        <ErrorBanner />
        <Stepper current={step} />

        <div className="mt-8 animate-fade-rise">
          {step === 'type' ? <DocumentTypeScreen /> : null}
          {step === 'upload' ? <UploadScreen /> : null}
          {step === 'recognize' ? <RecognizePanel /> : null}
          {step === 'results' && !showResults ? (
            <div className="card card-pad">
              <p className="muted">
                Распознавание выполнено. Нажмите «Рассчитать метрики», чтобы
                увидеть CER, WER, exact success, время и токены.
              </p>
              <div className="mt-4">
                <RecognizePanel compact />
              </div>
            </div>
          ) : null}
          {showResults ? <MetricsPanel /> : null}
        </div>

        {step === 'type' ? (
          <div className="mt-10">
            <SessionsPanel />
          </div>
        ) : null}
      </main>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-content flex-col gap-1.5 px-4 text-xs leading-relaxed text-ink-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>
            Изображения и схемы сохраняются как кропы страницы и никогда не
            распознаются как текст.
          </span>
          <span>Эталон и результат хранятся раздельными JSON.</span>
        </div>
      </footer>
    </div>
  )
}
