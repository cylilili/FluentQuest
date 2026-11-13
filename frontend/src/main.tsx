import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  QuestApiError,
  startSession,
  submitAnswer,
  type AnswerResult,
  type AnswerSubmission,
  type OptionId,
  type SessionProgress,
} from './questApi'
import { sampleQuest, type Stage } from './sampleQuest'
import './styles.css'

type HealthState = 'loading' | 'ok' | 'error'
type ReadingMode = 'guided' | 'full'

const healthMessages: Record<HealthState, string> = {
  loading: 'Checking backend connection…',
  ok: 'Backend status: ok',
  error: 'Could not connect to the backend. Check that it is running, then reload this page.',
}

function Question({
  stage,
  selected,
  result,
  error,
  disabled,
  submitting,
  retrying,
  onSelect,
  onSubmit,
}: {
  stage: Stage
  selected: OptionId | undefined
  result: AnswerResult | undefined
  error: string | undefined
  disabled: boolean
  submitting: boolean
  retrying: boolean
  onSelect: (option: OptionId) => void
  onSubmit: () => void
}) {
  const completed = result?.challenge_completed === true

  return (
    <div className="challenge">
      <fieldset className="challenge-options" disabled={disabled || completed || retrying}>
        <legend>
          <span className="challenge-type">{stage.question.title}</span>
          <span className="challenge-prompt">{stage.question.prompt}</span>
        </legend>
        {stage.question.options.map((option) => (
          <label key={option.id} className="challenge-option">
            <input
              type="radio"
              name={stage.id}
              value={option.id}
              checked={selected === option.id}
              onChange={() => onSelect(option.id)}
            />
            <span>{option.text}</span>
          </label>
        ))}
      </fieldset>
      <div role="status">
        {result && (
          <p className="answer-feedback">
            <strong>{result.correct ? `Correct · +${result.xp_awarded} XP` : 'Incorrect'}</strong>{' '}
            {result.feedback}
          </p>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {!completed && (
        <div className="stage-actions">
          <button
            className="primary-button"
            type="button"
            disabled={disabled || selected === undefined}
            onClick={onSubmit}
          >
            {submitting ? 'Checking…' : retrying ? 'Retry submission' : 'Check answer'}
          </button>
        </div>
      )}
    </div>
  )
}

function App() {
  const [health, setHealth] = useState<HealthState>('loading')
  const [mode, setMode] = useState<ReadingMode>('guided')
  const [stageIndex, setStageIndex] = useState(0)
  const [answers, setAnswers] = useState<Partial<Record<string, OptionId>>>({})
  const [results, setResults] = useState<Partial<Record<string, AnswerResult>>>({})
  const [progress, setProgress] = useState<SessionProgress | null>(null)
  const [pending, setPending] = useState<AnswerSubmission | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submissionError, setSubmissionError] = useState<{
    stageId: string
    message: string
  } | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const submissionInFlight = useRef(false)
  const stageHeading = useRef<HTMLHeadingElement>(null)
  const focusStage = useRef(false)

  const { stages } = sampleQuest
  const currentStage = stages[stageIndex]
  const isLastStage = stageIndex === stages.length - 1

  function goToStage(index: number) {
    focusStage.current = true
    setStageIndex(index)
  }

  function selectAnswer(stageId: string, option: OptionId) {
    setAnswers((previous) => ({ ...previous, [stageId]: option }))
  }

  async function checkAnswer(stageId: string) {
    const selected = answers[stageId]
    if (
      submissionInFlight.current ||
      sessionExpired ||
      !selected ||
      results[stageId]?.challenge_completed ||
      (pending && pending.challenge_id !== stageId)
    ) {
      return
    }

    submissionInFlight.current = true
    setIsSubmitting(true)
    setSubmissionError(null)

    try {
      const submission = pending ?? {
        challenge_id: stageId,
        selected_option_id: selected,
        request_id: crypto.randomUUID(),
      }
      setPending(submission)
      const session = progress ?? await startSession()
      setProgress(session)

      const result = await submitAnswer(session.session_id, submission)
      setProgress(result)
      setResults((previous) => ({ ...previous, [stageId]: result }))
      if (result.retry_allowed) {
        setAnswers((previous) => ({ ...previous, [stageId]: undefined }))
      }
      setPending(null)
    } catch (error) {
      if (
        error instanceof QuestApiError &&
        error.status === 404 &&
        error.message === 'Quest session not found'
      ) {
        setSessionExpired(true)
        setPending(null)
      } else if (
        error instanceof QuestApiError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 408
      ) {
        setPending(null)
        setSubmissionError({ stageId, message: error.message })
      } else {
        setSubmissionError({
          stageId,
          message: 'Could not check your answer. Retry the submission when the connection is back.',
        })
      }
    } finally {
      submissionInFlight.current = false
      setIsSubmitting(false)
    }
  }

  function restartQuest() {
    setAnswers({})
    setResults({})
    setProgress(null)
    setPending(null)
    setSubmissionError(null)
    setSessionExpired(false)
    if (stageIndex !== 0) goToStage(0)
  }

  function renderQuestion(stage: Stage) {
    const isPendingStage = pending?.challenge_id === stage.id
    return (
      <Question
        key={stage.id}
        stage={stage}
        selected={answers[stage.id]}
        result={results[stage.id]}
        error={submissionError?.stageId === stage.id ? submissionError.message : undefined}
        disabled={isSubmitting || sessionExpired || (pending !== null && !isPendingStage)}
        submitting={isSubmitting && isPendingStage}
        retrying={isPendingStage}
        onSelect={(option) => selectAnswer(stage.id, option)}
        onSubmit={() => void checkAnswer(stage.id)}
      />
    )
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
            disabled={pending !== null || isSubmitting}
            onChange={(event) => setMode(event.currentTarget.value === 'full' ? 'full' : 'guided')}
          >
            <option value="guided">Guided Quest</option>
            <option value="full">Full Article</option>
          </select>
        </label>
      </header>
      <main className="quest-content">
        <h1>{sampleQuest.title}</h1>
        <div className="quest-progress">
          <label htmlFor="quest-progress">
            {progress?.completed_stages ?? 0} / {progress?.total_stages ?? stages.length} stages complete
          </label>
          <strong>{progress?.xp ?? 0} XP</strong>
          <progress
            id="quest-progress"
            value={progress?.completed_stages ?? 0}
            max={progress?.total_stages ?? stages.length}
          />
        </div>
        {sessionExpired && (
          <div className="quest-restart">
            <p role="alert">This quest session has expired. Start a new quest to continue.</p>
            <div className="stage-actions">
              <button type="button" onClick={restartQuest}>Start a new quest</button>
            </div>
          </div>
        )}
        {mode === 'full' ? (
          <>
            <article className="story">
              {stages.map((stage) => <p key={stage.id}>{stage.passage}</p>)}
            </article>
            <section className="full-challenges" aria-labelledby="challenges-title">
              <h2 id="challenges-title">Reading Challenges</h2>
              {stages.map(renderQuestion)}
            </section>
            {progress?.session_completed && (
              <section className="guided-stage" aria-labelledby="full-summary">
                <h2 id="full-summary">Story complete</h2>
                <p>You earned {progress.xp} XP.</p>
                <div className="stage-actions">
                  <button type="button" onClick={restartQuest}>Start a new quest</button>
                </div>
              </section>
            )}
          </>
        ) : currentStage ? (
          <section className="guided-stage" aria-labelledby="stage-title">
            <p className="stage-position">Stage {stageIndex + 1} of {stages.length}</p>
            <h2 id="stage-title" ref={stageHeading} tabIndex={-1}>{currentStage.title}</h2>
            <article className="story">
              <p>{currentStage.passage}</p>
            </article>
            {renderQuestion(currentStage)}
            <div className="stage-actions">
              {stageIndex > 0 && (
                <button
                  type="button"
                  disabled={pending !== null || isSubmitting}
                  onClick={() => goToStage(stageIndex - 1)}
                >
                  Back
                </button>
              )}
              {results[currentStage.id]?.challenge_completed && (
                <button
                  className="primary-button"
                  type="button"
                  disabled={sessionExpired || (isLastStage && !progress?.session_completed)}
                  onClick={() => goToStage(stageIndex + 1)}
                >
                  {isLastStage ? 'Finish quest' : 'Continue'}
                </button>
              )}
            </div>
          </section>
        ) : (
          <section className="guided-stage" aria-labelledby="stage-title">
            <h2 id="stage-title" ref={stageHeading} tabIndex={-1}>Story complete</h2>
            <p>You finished all {stages.length} stages and earned {progress?.xp ?? 0} XP.</p>
            <div className="stage-actions">
              <button type="button" onClick={() => goToStage(stages.length - 1)}>Review last stage</button>
              <button type="button" onClick={restartQuest}>Start a new quest</button>
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
