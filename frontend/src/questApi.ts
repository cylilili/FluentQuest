export type OptionId = 'A' | 'B' | 'C'

export type Stage = {
  id: string
  title: string
  passage: string
  question: {
    title: string
    prompt: string
    options: { id: OptionId; text: string }[]
  }
}

export type SessionProgress = {
  session_id: string
  xp: number
  completed_stages: number
  total_stages: number
  session_completed: boolean
}

export type AnswerSubmission = {
  challenge_id: string
  selected_option_id: OptionId
  request_id: string
}

export type AnswerResult = SessionProgress & {
  challenge_id: string
  attempt_number: number
  correct: boolean
  retry_allowed: boolean
  challenge_completed: boolean
  xp_awarded: number
  feedback: string
}

export type SessionSnapshot = SessionProgress & {
  article: {
    id: string
    title: string
    source: { label: string; url: string } | null
    stages: Stage[]
  }
  answers: (AnswerResult & { selected_option_id: OptionId; request_id: string })[]
}

export class QuestApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 10_000): Promise<T> {
  const response = await fetch(path, {
    ...options,
    signal: AbortSignal.timeout(timeoutMs),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = typeof data?.detail === 'string' ? data.detail : 'Request failed'
    throw new QuestApiError(response.status, message)
  }

  return response.json()
}

export function createArticle(text: string, title: string) {
  return request<{ article_id: string }>('/api/articles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, ...(title ? { title } : {}) }),
  }, 60_000)
}

export function startSession(articleId?: string) {
  return request<SessionProgress>('/api/sessions', {
    method: 'POST',
    ...(articleId && {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article_id: articleId }),
    }),
  })
}

export function restoreSession(sessionId: string) {
  return request<SessionSnapshot>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    cache: 'no-store',
  })
}

export function submitAnswer(sessionId: string, submission: AnswerSubmission) {
  return request<AnswerResult>(`/api/sessions/${sessionId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  })
}
