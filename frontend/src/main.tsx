import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { sampleQuest } from './sampleQuest'
import './styles.css'

type HealthState = 'loading' | 'ok' | 'error'
type ReadingMode = 'guided' | 'full'
type Stage = (typeof sampleQuest.stages)[number]

const healthMessages: Record<HealthState, string> = {
  loading: 'Checking backend connection…',
  ok: 'Backend status: ok',
  error: 'Could not connect to the backend. Check that it is running, then reload this page.',
}

function Question({
  stage,
  selected,
  onSelect,
}: {
  stage: Stage
  selected: string | undefined
  onSelect: (option: string) => void
}) {
  return (
    <fieldset className="challenge">
      <legend>
        <span className="challenge-type">{stage.question.title}</span>
        <span className="challenge-prompt">{stage.question.prompt}</span>
      </legend>
      {stage.question.options.map((option) => (
        <label key={option} className="challenge-option">
          <input
            type="radio"
            name={stage.id}
            value={option}
            checked={selected === option}
            onChange={() => onSelect(option)}
          />
          <span>{option}</span>
        </label>
      ))}
    </fieldset>
  )
}

function App() {
  const [health, setHealth] = useState<HealthState>('loading')
  const [mode, setMode] = useState<ReadingMode>('guided')
  const [stageIndex, setStageIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const stageHeading = useRef<HTMLHeadingElement>(null)
  const focusStage = useRef(false)

  const { stages } = sampleQuest
  const currentStage = stages[stageIndex]
  const isLastStage = stageIndex === stages.length - 1

  function goToStage(index: number) {
    focusStage.current = true
    setStageIndex(index)
  }

  function selectAnswer(stageId: string, option: string) {
    setAnswers((previous) => ({ ...previous, [stageId]: option }))
  }

  useEffect(() => {
    if (focusStage.current) {
      stageHeading.current?.focus()
      focusStage.current = false
    }
  }, [stageIndex])

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
    <div className="page">
      <header className="site-header">
        <span>Reading Quest</span>
        <label className="mode-picker">
          Reading mode
          <select
            value={mode}
            onChange={(event) => setMode(event.currentTarget.value === 'full' ? 'full' : 'guided')}
          >
            <option value="guided">Guided Quest</option>
            <option value="full">Full Article</option>
          </select>
        </label>
      </header>
      <main className="quest-content">
        <h1>{sampleQuest.title}</h1>
        {mode === 'full' ? (
          <>
            <article className="story">
              {stages.map((stage) => <p key={stage.id}>{stage.passage}</p>)}
            </article>
            <section className="full-challenges" aria-labelledby="challenges-title">
              <h2 id="challenges-title">Reading Challenges</h2>
              {stages.map((stage) => (
                <Question
                  key={stage.id}
                  stage={stage}
                  selected={answers[stage.id]}
                  onSelect={(option) => selectAnswer(stage.id, option)}
                />
              ))}
            </section>
          </>
        ) : currentStage ? (
          <section className="guided-stage" aria-labelledby="stage-title">
            <p className="stage-position">Stage {stageIndex + 1} of {stages.length}</p>
            <h2 id="stage-title" ref={stageHeading} tabIndex={-1}>{currentStage.title}</h2>
            <article className="story">
              <p>{currentStage.passage}</p>
            </article>
            <Question
              key={currentStage.id}
              stage={currentStage}
              selected={answers[currentStage.id]}
              onSelect={(option) => selectAnswer(currentStage.id, option)}
            />
            <div className="stage-actions">
              {stageIndex > 0 && (
                <button type="button" onClick={() => goToStage(stageIndex - 1)}>Back</button>
              )}
              <button
                className="primary-button"
                type="button"
                disabled={answers[currentStage.id] === undefined}
                onClick={() => goToStage(stageIndex + 1)}
              >
                {isLastStage ? 'Finish quest' : 'Continue'}
              </button>
            </div>
          </section>
        ) : (
          <section className="guided-stage" aria-labelledby="stage-title">
            <h2 id="stage-title" ref={stageHeading} tabIndex={-1}>Story complete</h2>
            <p>You reached the end of all {stages.length} stages.</p>
            <div className="stage-actions">
              <button type="button" onClick={() => goToStage(stages.length - 1)}>Review last stage</button>
            </div>
          </section>
        )}
      </main>
      <footer className="site-footer">
        <p>Adapted from <a href={sampleQuest.source.url}>{sampleQuest.source.label}</a>.</p>
        <p role="status">{healthMessages[health]}</p>
      </footer>
    </div>
  )
}

const container = document.getElementById('root')

if (!container) {
  throw new Error('Reading Quest root element is missing')
}

createRoot(container).render(<App />)
