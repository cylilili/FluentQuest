# Reading Quest

Reading Quest is an English reading game in development. Read *Venus and Adonis* one passage at a time, with a question after each passage. Use the **Reading mode** menu to switch to the full article.

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
3. Finish all three stages and check the XP total on the summary. Use **Start a new quest** to reset progress.

### Verify saved sessions

Answer one stage, then reload in the same browser. The quest should resume at the first unfinished stage with the same XP. Restart FastAPI and reload again to check persistence in `backend/data/reading_quest.sqlite3`.
