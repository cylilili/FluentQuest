import { useRef, useState, type FormEvent } from 'react'
import {
  createArticle,
  QuestApiError,
  restoreSession,
  startSession,
  type SessionSnapshot,
} from './questApi'

export function ArticleForm({ onReady, onCancel }: {
  onReady: (snapshot: SessionSnapshot) => void
  onCancel: () => void
}) {
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [status, setStatus] = useState<'idle' | 'generating' | 'starting'>('idle')
  const [error, setError] = useState<string | null>(null)
  const createdArticle = useRef<string | null>(null)
  const createdSession = useRef<string | null>(null)
  const inFlight = useRef(false)
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length
  const busy = status !== 'idle'

  function resetRequest() {
    createdArticle.current = null
    createdSession.current = null
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    if (wordCount < 300 || wordCount > 800) {
      setError('Enter an article between 300 and 800 words.')
      return
    }

    inFlight.current = true
    setError(null)
    try {
      if (!createdArticle.current) {
        setStatus('generating')
        const { article_id } = await createArticle(text.trim(), title.trim())
        createdArticle.current = article_id
      }

      setStatus('starting')
      if (!createdSession.current) {
        const session = await startSession(createdArticle.current)
        createdSession.current = session.session_id
      }
      const snapshot = await restoreSession(createdSession.current)
      onReady(snapshot)
    } catch (cause) {
      if (cause instanceof QuestApiError && cause.status === 404) {
        if (!createdSession.current) createdArticle.current = null
        createdSession.current = null
      }
      setError(
        cause instanceof QuestApiError
          ? cause.message
          : 'Could not load your quest. Check the backend connection and try again.',
      )
    } finally {
      inFlight.current = false
      setStatus('idle')
    }
  }

  return (
    <form className="guided-stage article-form" onSubmit={(event) => void handleSubmit(event)}>
      <label htmlFor="article-title">Title (optional)</label>
      <input
        id="article-title"
        value={title}
        maxLength={120}
        disabled={busy}
        onChange={(event) => {
          setTitle(event.currentTarget.value)
          resetRequest()
        }}
      />
      <label htmlFor="article-text">English article</label>
      <textarea
        id="article-text"
        value={text}
        rows={10}
        maxLength={12_000}
        disabled={busy}
        required
        aria-describedby="article-word-count"
        onChange={(event) => {
          setText(event.currentTarget.value)
          resetRequest()
        }}
      />
      <p id="article-word-count">{wordCount} words · 300–800 required</p>
      <p>Your article is sent to Gemini to generate questions.</p>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">{status === 'generating' ? 'Generating questions with Gemini…' : 'Opening your quest…'}</p>}
      <div className="stage-actions">
        <button type="submit" className="primary-button" disabled={busy}>Generate quest</button>
        <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
