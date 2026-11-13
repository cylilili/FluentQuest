# Reading Quest

Reading Quest is an English reading game. Play three challenges in *Venus and Adonis* or use Gemini to generate a quest from your own article.

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

Open [Reading Quest](http://127.0.0.1:5173/). The built-in quest works without a Gemini API key and uses standard answer feedback. Set `GEMINI_API_KEY` before starting FastAPI to enable article generation and Tutor tool calls.

## Verify

1. Open [Reading Quest](http://127.0.0.1:5173/). Select an answer and click **Check answer**. A correct answer awards 10 XP. Two wrong answers finish the stage with an explanation and 0 XP.
2. Switch between **Guided Quest** and **Full Article**. Both modes show the same answers, XP, and progress.
3. Finish all three stages and check the XP total on the summary. Use **Play again** to replay the same article from 0 XP.
4. Open **Article Library** to find the built-in article and previously generated articles. Choose **Read article** to view the full text or **Start quiz** to open a fresh session with the saved questions.
5. Open **Learning Summary** to see first-try results and tutor feedback counts by skill across saved sessions. Choose **Back to quest** to return to your current session.

### Verify saved sessions

Answer one stage, then reload in the same browser. The quest should resume at the first unfinished stage with the same XP. Restart FastAPI and reload again to check persistence in `backend/data/reading_quest.sqlite3`.

### Generate a quest

The default model is `gemini-3.5-flash-lite`. Set `GEMINI_MODEL` to choose a Gemini model that supports structured output and function calling.

On the reading page, select **Use my own article**, paste 300–800 English words, and click **Generate quest**. Gemini receives the article text to generate the questions. Complete a stage and reload to check that the generated quest and its progress resume.

### Verify the tutor

With Gemini configured, start a fresh quest and answer the first question incorrectly. In the browser's **Network** panel, open **answers → Response** and look for `agent_trace`.

- `input_state` shows what the tutor received after grading. `nodes` lists the LangGraph nodes that ran.
- `offered_tool` and `requested_tool` show which tool the model could call and which recognized tool it requested. `reason` records the validation result or fallback, such as `invalid_tool_call` or `provider_timeout`.
- `action` shows the graph's decision. If `applied` is false, another submission changed the state while the graph ran. The top-level `agent_action` shows the saved action.

Submit another wrong answer to check the simpler example. The session response also includes saved traces. Answers recorded before tracing show `agent_trace: null`.

When the tutor gives a hint, `hint_level` is `guided` if at least two first attempts for that skill were wrong in other sessions and those misses make up at least half of the first attempts. Otherwise the hint is `standard`. The trace includes the counts in `skill_history`.

### Run backend tests

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

The tests simulate Gemini responses and use a temporary SQLite database.
