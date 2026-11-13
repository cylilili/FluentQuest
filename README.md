# Reading Quest

Reading Quest is an English reading game in development. Try *Venus and Adonis* or generate three challenges from your own article. Use the **Reading mode** menu to switch to the full article.

## Setup

Use Node.js 24 with npm and Python 3.13. Run all commands from the project root.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements.txt
npm --prefix frontend ci --registry=https://registry.npmjs.org
```

## Run locally

```sh
# Terminal 1 · FastAPI
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
```

```sh
# Terminal 2 · Vite
npm --prefix frontend run dev
```

## Verify

1. Open [Reading Quest](http://127.0.0.1:5173/). Select an answer and click **Check answer**. A correct answer awards 10 XP. Two wrong answers finish the stage with an explanation and 0 XP.
2. Switch between **Guided Quest** and **Full Article**. Both modes show the same answers, XP, and progress.
3. Finish all three stages and check the XP total on the summary. Use **Play again** to replay the same article from 0 XP.
4. Open **Article Library** to find the built-in article and previously generated articles. Choose **Read article** to view the full text or **Start quiz** to open a fresh session with the saved questions.

### Verify saved sessions

Answer one stage, then reload in the same browser. The quest should resume at the first unfinished stage with the same XP. Restart FastAPI and reload again to check persistence in `backend/data/reading_quest.sqlite3`.

### Generate a quest

Set `GEMINI_API_KEY` in the backend terminal before starting FastAPI. The default model is `gemini-3.5-flash-lite`. Set `GEMINI_MODEL` to choose a Gemini model that supports structured output and function calling.

On the reading page, select **Use my own article**, paste 300–800 English words, and click **Generate quest**. Gemini receives the article text to generate the questions. Complete a stage and reload to check that the generated quest and its progress resume.

### Verify the tutor

With Gemini configured, start a fresh quest and answer the first question incorrectly. Gemini receives the question's skill and attempt number. In the browser's **Network** panel, open the answer response. `agent_action: "GIVE_HINT"` confirms LangGraph ran the hint tool. `"RETRY"` shows the standard retry prompt. Both actions allow one more attempt.

### Run backend tests

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

The tests simulate Gemini responses and use a temporary SQLite database.
