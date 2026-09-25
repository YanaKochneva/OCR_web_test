import { Alert } from './Alert'
import { useBenchmarkStore } from '../store/useBenchmarkStore'

export function ErrorBanner() {
  const error = useBenchmarkStore((state) => state.error)
  const clearError = useBenchmarkStore((state) => state.clearError)

  if (!error) return null

  return (
    <div className="mb-6 animate-fade-rise">
      <Alert tone="error" title="Ошибка" onDismiss={clearError}>
        {error}
      </Alert>
    </div>
  )
}