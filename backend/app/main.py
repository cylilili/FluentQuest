from uuid import UUID

from fastapi import FastAPI, status

from .quest import (
    AnswerResult,
    AnswerSubmission,
    SessionProgress,
    create_session,
    submit_answer,
)

app = FastAPI(title="Reading Quest")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def start_session() -> SessionProgress:
    return create_session()


@app.post("/api/sessions/{session_id}/answers")
def answer_challenge(session_id: UUID, submission: AnswerSubmission) -> AnswerResult:
    return submit_answer(session_id, submission)
