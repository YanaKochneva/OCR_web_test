import { useState } from 'react'

import { Button } from './Button'
import { Dropzone } from './Dropzone'
import {
  selectCanUpload,
  useBenchmarkStore,
} from '../store/useBenchmarkStore'

export function UploadScreen() {
  const documentType = useBenchmarkStore((state) => state.documentType)
  const documentTypes = useBenchmarkStore((state) => state.documentTypes)
  const referenceFile = useBenchmarkStore((state) => state.referenceFile)
  const recognizedFile = useBenchmarkStore((state) => state.recognizedFile)
  const setFile = useBenchmarkStore((state) => state.setFile)
  const upload = useBenchmarkStore((state) => state.upload)
  const recognize = useBenchmarkStore((state) => state.recognize)
  const uploadProgress = useBenchmarkStore((state) => state.uploadProgress)
  const recognizing = useBenchmarkStore((state) => state.recognizing)
  const health = useBenchmarkStore((state) => state.health)
  const canUpload = useBenchmarkStore(selectCanUpload)
  const [starting, setStarting] = useState(false)

  const busy = uploadProgress !== null || recognizing || starting
  const maxMb = health?.max_upload_mb ?? 50
  const typeLabel =
    documentTypes.find((type) => type.id === documentType)?.label ?? '—'

  const start = async () => {
    setStarting(true)
    const uploaded = await upload()
    if (uploaded) await recognize()
    setStarting(false)
  }

  const hint = !documentType
    ? 'Сначала выберите тип документа.'
    : !referenceFile || !recognizedFile
      ? 'Загрузите оба файла, чтобы запустить распознавание.'
      : null

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Шаг 2. Загрузите пару файлов</h2>
          <p className="muted mt-1">
            Эталон — исходный документ, распознаваемый — его скан. Тип:{' '}
            <span className="font-medium text-ink-700">{typeLabel}</span>
          </p>
        </div>
        <Button variant="secondary" onClick={() => useBenchmarkStore.getState().setStep('type')}>
          Изменить тип
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Dropzone
          title="Эталон (файл А)"
          subtitle="Исходный документ с текстовым слоем: PDF или DOCX."
          note="Из него строится эталонный JSON для расчёта CER/WER."
          file={referenceFile}
          onFile={(file) => setFile('reference', file)}
          maxUploadMb={maxMb}
          disabled={busy}
        />
        <Dropzone
          title="Распознаваемый (файл Б)"
          subtitle="Скан без текстового слоя: PDF, напечатанная копия файла А."
          note="Наличие текстового слоя проверяется после загрузки."
          file={recognizedFile}
          onFile={(file) => setFile('recognized', file)}
          maxUploadMb={maxMb}
          disabled={busy}
        />
      </div>

      {uploadProgress !== null ? (
        <div className="card card-pad mt-4">
          <div className="flex items-center justify-between text-xs text-ink-500">
            <span>Загрузка файлов…</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-canvas">
            <div
              className="h-2 rounded-full bg-accent-500 transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      ) : null}

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Button size="lg" disabled={!canUpload} loading={busy} onClick={() => void start()}>
          {recognizing ? 'Распознавание…' : 'Распознать'}
        </Button>
        {busy ? (
          <span className="muted">
            {uploadProgress !== null ? 'Отправка файлов на сервер…' : 'Запуск распознавания…'}
          </span>
        ) : hint ? (
          <span className="muted">{hint}</span>
        ) : (
          <span className="muted">
            Будет выполнен OCR страниц скана моделью GLM и построен распознанный JSON.
          </span>
        )}
      </div>
    </section>
  )
}