from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from .db import SAMPLE_ARTICLE_ID, initialize_database
from .generation import ArticleSubmission, generate_article
from .llm import (
    LLMProvider,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
    get_llm_provider,
)
from .quest import (
    AnswerResult,
    AnswerSubmission,
    ArticleListItem,
    QuestArticle,
    SessionProgress,
    SessionSnapshot,
    create_session,
    get_article,
    get_session,
    list_articles,
    submit_answer,
)


class ArticleCreated(BaseModel):
    article_id: str


class SessionStart(BaseModel):
    article_id: str = SAMPLE_ARTICLE_ID


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Reading Quest", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def start_session(submission: SessionStart | None = None) -> SessionProgress:
    return create_session(submission.article_id if submission else SAMPLE_ARTICLE_ID)


@app.get("/api/articles")
def article_list() -> list[ArticleListItem]:
    return list_articles()


@app.get("/api/articles/{article_id}")
def article_detail(article_id: str) -> QuestArticle:
    return get_article(article_id)


@app.post("/api/articles", status_code=status.HTTP_201_CREATED)
def create_article(
    submission: ArticleSubmission,
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ArticleCreated:
    try:
        article_id = generate_article(submission, provider)
    except ProviderTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ArticleCreated(article_id=article_id)


@app.get("/api/sessions/{session_id}")
def restore_session(session_id: UUID) -> SessionSnapshot:
    return get_session(session_id)


@app.post("/api/sessions/{session_id}/answers")
def answer_challenge(
    session_id: UUID,
    submission: AnswerSubmission,
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AnswerResult:
    return submit_answer(session_id, submission, provider)
