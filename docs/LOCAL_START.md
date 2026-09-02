# LOCAL START (Windows) — Phase 8

> Scripts: `backend/scripts/start-local.ps1`, `backend/scripts/stop-local.ps1`
> (extend, do not replace, any existing dev scripts). **Never resets the DB.**

## start-local.ps1

1. Check Docker is running (Postgres :5433, Redis :6379) — start `docker compose up -d db redis` if compose is present.
2. Check Ollama (`GET http://localhost:11434/api/tags`); warn (do not fail) if down.
3. Check `gemma3:4b` is pulled; **do not auto-pull** — print `ollama pull gemma3:4b` and continue.
4. `alembic upgrade head` (additive migrations only).
5. Start the API (`uvicorn app.main:app`), a worker (`celery -A app.celery_app worker --pool=solo`), and the frontend (`npm run dev`).
6. Wait for `/health/ready`, then open `http://localhost:3000` in the browser.

## stop-local.ps1

Stops the frontend, worker and API processes it started. Leaves Docker
containers and all data untouched.

## System status

`/system` (and `/api/ops/status` + `/api/local-ai/status`) show Backend /
Database / Redis / Workers / Ollama / Cloud Providers / Storage / Publishers as
정상 / 문제 / 확인 불가.
