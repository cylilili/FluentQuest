import { useEffect, useRef, useState } from 'react'
import { getArticle, listArticles, type ArticleListItem, type QuestArticle } from './questApi'

export function ArticleLibrary({ starting, startError, onStart }: {
  starting: boolean
  startError: string | null
  onStart: (articleId: string) => void
}) {
  const [articles, setArticles] = useState<ArticleListItem[] | null>(null)
  const [listError, setListError] = useState(false)
  const [listAttempt, setListAttempt] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [article, setArticle] = useState<QuestArticle | null>(null)
  const [articleError, setArticleError] = useState(false)
  const [articleAttempt, setArticleAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    let active = true
    void listArticles().then(
      (items) => { if (active) setArticles(items) },
      () => { if (active) setListError(true) },
    )
    return () => { active = false }
  }, [listAttempt])

  useEffect(() => {
    if (selectedId === null) return
    let active = true
    void getArticle(selectedId).then(
      (item) => { if (active) setArticle(item) },
      () => { if (active) setArticleError(true) },
    )
    return () => { active = false }
  }, [selectedId, articleAttempt])

  useEffect(() => {
    heading.current?.focus()
  }, [selectedId, article])

  function readArticle(articleId: string | null) {
    setArticle(null)
    setArticleError(false)
    setSelectedId(articleId)
  }

  return (
    <main className="quest-content">
      {selectedId === null ? (
        <>
          <h1 ref={heading} tabIndex={-1}>Article Library</h1>
          {listError ? (
            <>
              <p role="alert">Could not load the articles.</p>
              <div className="stage-actions">
                <button type="button" onClick={() => {
                  setListError(false)
                  setListAttempt((attempt) => attempt + 1)
                }}>Try again</button>
              </div>
            </>
          ) : articles === null ? (
            <p role="status">Loading articles…</p>
          ) : articles.length === 0 ? (
            <p>No articles have been saved yet.</p>
          ) : (
            <ul className="article-list">
              {articles.map((item) => (
                <li className="article-list-item" key={item.id}>
                  <div>
                    {item.built_in && <p className="stage-position">Built-in article</p>}
                    <h2>{item.title}</h2>
                  </div>
                  <div className="stage-actions">
                    <button type="button" disabled={starting} onClick={() => readArticle(item.id)}>
                      Read article
                    </button>
                    <button type="button" className="primary-button" disabled={starting}
                      onClick={() => onStart(item.id)}>
                      Start quiz
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <>
          <div className="stage-actions article-back">
            <button type="button" disabled={starting} onClick={() => readArticle(null)}>
              Back to articles
            </button>
          </div>
          <h1 ref={heading} tabIndex={-1}>{article?.title ?? 'Article'}</h1>
          {articleError ? (
            <>
              <p role="alert">Could not load this article.</p>
              <div className="stage-actions">
                <button type="button" onClick={() => {
                  setArticleError(false)
                  setArticleAttempt((attempt) => attempt + 1)
                }}>Try again</button>
              </div>
            </>
          ) : article === null ? (
            <p role="status">Loading article…</p>
          ) : (
            <>
              <article className="story">
                {article.stages.map((stage) => <p key={stage.id}>{stage.passage}</p>)}
              </article>
              {article.source && (
                <p>Adapted from <a href={article.source.url}>{article.source.label}</a>.</p>
              )}
              <div className="stage-actions">
                <button type="button" className="primary-button" disabled={starting}
                  onClick={() => onStart(article.id)}>
                  Start quiz
                </button>
              </div>
            </>
          )}
        </>
      )}
      {starting && <p role="status">Opening your quest…</p>}
      {startError && <p role="alert">{startError}</p>}
    </main>
  )
}
