# Reading Quest

Reading Quest is an English reading game in development. The current page checks the connection between React and FastAPI.

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

1. Open [Reading Quest](http://127.0.0.1:5173/) and check for `Backend status: ok`.
2. Reload with DevTools open. In **Network**, `/health` should return HTTP `200` and `{"status":"ok"}`.
3. Stop FastAPI and reload to see the connection error. Restart FastAPI and reload to confirm recovery.
