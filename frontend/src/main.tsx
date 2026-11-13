import { createRoot } from 'react-dom/client'

const container = document.getElementById('root')

if (!container) {
  throw new Error('Reading Quest root element is missing')
}

createRoot(container).render(
  <main>
    <h1>Reading Quest</h1>
  </main>,
)
