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

1. Open [Reading Quest](http://127.0.0.1:5173/). In **Guided Quest**, select one answer per stage and continue until the story ends.
2. Switch to **Full Article** to see the complete story and all three questions. Switch back to check that your place and selections are still there.
3. With FastAPI running, the footer should show `Backend status: ok` and `/health` should return HTTP `200` in DevTools.
