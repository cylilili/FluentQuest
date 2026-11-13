import type { AnswerSubmission } from './questApi'

const storageKey = 'reading-quest.session'

export type SavedSession = {
  sessionId: string
  pending: AnswerSubmission | null
}

export function readSavedSession(): SavedSession | null {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null')
    if (typeof saved?.sessionId !== 'string' || !saved.sessionId) return null

    const pending = saved.pending
    const validPending = typeof pending?.challenge_id === 'string'
      && ['A', 'B', 'C'].includes(pending.selected_option_id)
      && typeof pending.request_id === 'string'
      && pending.request_id.length > 0

    return { sessionId: saved.sessionId, pending: validPending ? pending : null }
  } catch {
    return null
  }
}

export function saveSession(saved: SavedSession | null) {
  try {
    if (saved) {
      localStorage.setItem(storageKey, JSON.stringify(saved))
    } else {
      localStorage.removeItem(storageKey)
    }
  } catch {
    // The current quest can still run when browser storage is unavailable.
  }
}
