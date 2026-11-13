export type OptionId = 'A' | 'B' | 'C'

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
  correct: boolean
  retry_allowed: boolean
  challenge_completed: boolean
  xp_awarded: number
  feedback: string
}

export class QuestApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function post<T>(path: string, body?: AnswerSubmission): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(10_000),
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = typeof data?.detail === 'string' ? data.detail : 'Request failed'
    throw new QuestApiError(response.status, message)
  }

  return response.json()
}

export function startSession() {
  return post<SessionProgress>('/api/sessions')
}

export function submitAnswer(sessionId: string, submission: AnswerSubmission) {
  return post<AnswerResult>(`/api/sessions/${sessionId}/answers`, submission)
}
