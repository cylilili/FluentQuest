import { useEffect, useRef, useState } from 'react'
import { getLearningProgress, type LearningProgress } from './questApi'

type SummaryState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; progress: LearningProgress }

export function LearningSummary({ onBack }: { onBack: () => void }) {
  const [state, setState] = useState<SummaryState>({ status: 'loading' })
  const [requestAttempt, setRequestAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    heading.current?.focus()
  }, [])

  useEffect(() => {
    let active = true
    void getLearningProgress().then(
      (progress) => { if (active) setState({ status: 'ready', progress }) },
      () => { if (active) setState({ status: 'error' }) },
    )
    return () => { active = false }
  }, [requestAttempt])

  return (
    <main className="quest-content">
      <h1 ref={heading} tabIndex={-1}>Learning Summary</h1>
      <div className="stage-actions article-back">
        <button type="button" onClick={onBack}>Back to quest</button>
      </div>
      {state.status === 'loading' && <p role="status">Loading your learning summary…</p>}
      {state.status === 'error' && (
        <>
          <p role="alert">Could not load your learning summary.</p>
          <div className="stage-actions">
            <button type="button" onClick={() => {
              setState({ status: 'loading' })
              setRequestAttempt((attempt) => attempt + 1)
            }}>Try again</button>
          </div>
        </>
      )}
      {state.status === 'ready' && (
        state.progress.skills.length === 0 ? (
          <p>Answer a question to see your progress by skill.</p>
        ) : (
          <ul className="learning-skills">
            {state.progress.skills.map((skill) => (
              <li key={skill.skill_tag} className="guided-stage">
                <h2>{skill.skill_tag}</h2>
                <dl className="skill-stats">
                  <dt>Correct on first try</dt>
                  <dd>{skill.correct_first_attempts} / {skill.first_attempts}</dd>
                  <dt>Hints shown</dt>
                  <dd>{skill.hints_shown}</dd>
                  <dt>Correct retries after a hint</dt>
                  <dd>
                    {skill.retries_after_hint > 0
                      ? `${skill.correct_retries_after_hint} / ${skill.retries_after_hint}`
                      : 'No retries yet'}
                  </dd>
                  <dt>Simpler examples shown</dt>
                  <dd>{skill.simpler_examples_shown}</dd>
                </dl>
              </li>
            ))}
          </ul>
        )
      )}
    </main>
  )
}
