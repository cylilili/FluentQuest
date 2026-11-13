import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

type HealthState = 'loading' | 'ok' | 'error'

const healthMessages: Record<HealthState, string> = {
  loading: 'Checking backend connection…',
  ok: 'Backend status: ok',
  error: 'Could not connect to the backend. Check that it is running, then reload this page.',
}

function App() {
  const [health, setHealth] = useState<HealthState>('loading')

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch('/health', {
          cache: 'no-store',
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`Health check returned HTTP ${response.status}`)
        }

        const data: unknown = await response.json()
        if (
          data === null ||
          typeof data !== 'object' ||
          !('status' in data) ||
          data.status !== 'ok'
        ) {
          throw new Error('Unexpected health response')
        }

        setHealth(data.status)
      } catch {
        if (!controller.signal.aborted) {
          setHealth('error')
        }
      }
    }

    void checkHealth()
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Reading Quest</h1>
      <p role="status">{healthMessages[health]}</p>
    </main>
  )
}

const container = document.getElementById('root')

if (!container) {
  throw new Error('Reading Quest root element is missing')
}

createRoot(container).render(<App />)
