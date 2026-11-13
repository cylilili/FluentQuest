from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, status

from .db import initialize_database
from .quest import (
    AnswerResult,
    AnswerSubmission,
    SessionProgress,
    SessionSnapshot,
    create_session,
    get_session,
    submit_answer,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Reading Quest", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def start_session() -> SessionProgress:
    return create_session()


@app.get("/api/sessions/{session_id}")
def restore_session(session_id: UUID) -> SessionSnapshot:
    return get_session(session_id)


@app.post("/api/sessions/{session_id}/answers")
def answer_challenge(session_id: UUID, submission: AnswerSubmission) -> AnswerResult:
    return submit_answer(session_id, submission)
