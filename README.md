# AI CONTENT FACTORY

Automated content pipeline. **Phase 1-A** (current): a topic goes in, and the
system runs Research → Fact Check → Strategy → Hook → Master Script (with a
Natural Writing pass), persisting every step to PostgreSQL and showing it on a
web dashboard.

> Phases 1-B … 10 (media, publishing, analytics, autopilot, …) are planned but
> **not** built. See `docs/PROJECT_STATE.md` and `docs/DECISIONS.md`.

## Stack
FastAPI · LangGraph (Postgres checkpointer) · PostgreSQL + pgvector · Redis + Celery ·
Next.js + Tailwind · Alembic · pytest. Provider Adapter pattern with an offline
**MOCK MODE** default (no paid API needed to run or test).

## Quick start (Windows, one command)
```powershell
cd C:\AI-Content-Factory
.\scripts\start-local.ps1        # checks Docker Desktop + Ollama, builds, waits for health, opens the dashboard
```
`.\scripts\stop-local.ps1` stops the stack (never deletes a volume; `pgdata` is kept, Ollama is untouched).
`.\scripts\status-local.ps1` prints a read-only health snapshot. No script prints an API key.

## Quick start (Docker, any OS)
```bash
cp .env.example .env          # defaults work for local; keys optional
docker compose up --build     # postgres:5433  redis:6379  backend:8000  worker  frontend:3000
```
Open http://localhost:3000 , type a topic, pick platforms + a goal, hit **자동 제작 시작**.

`.env` is the single source of truth for runtime config. `docker-compose.yml` reads it via
`env_file:` and only pins infra URLs (service-name DB/Redis) + `${VAR:-default}` fallbacks in
`environment:`. Set `MOCK_MODE=false` in `.env` to enable paid providers; nothing is hard-coded
to override it. Secrets stay in the backend/worker containers — the frontend gets no secret env.
Containers reach a Windows-host Ollama at `http://host.docker.internal:11434` (Linux: `host-gateway`).

## Local dev (no Docker for the app)
```bash
docker compose up -d postgres redis

cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows; use bin/activate on POSIX
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
celery -A app.celery_app.celery_app worker --loglevel=info   # add --pool=solo on Windows

cd ../frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

## Tests
```bash
cd backend
docker compose up -d postgres           # integration + checkpoint-resume tests need it
pytest                                   # 28 tests
```

## Layout
```
backend/app/
  agents/      LangGraph state, nodes, graph, runner (+ resume)
  providers/   LLM/Search adapters: mock (default) + anthropic/tavily; retry; fault-injection
  naturalness/ AI_SLOP_SCORE, Natural Writing Pass, VoiceProfile, CTA library   (Design Amendment)
  services/    budget guard, cost + agent logging, prompt loader/versioning
  opensource/  open-source component registry (+ docs/OPEN_SOURCE_COMPONENTS.md)
  api/         FastAPI routes
backend/prompts/<agent>/v1.md            versioned prompts (no long literals in code)
backend/brands/<brand>/                  voice_profile.json + writing_samples/
frontend/app/                            dashboard + campaign view
docs/                                    PROJECT_STATE.md · DECISIONS.md · OPEN_SOURCE_COMPONENTS.md
```

## Security
No key is committed. `.env` is git-ignored; only `.env.example` is tracked. Keys
are never logged. `MOCK_MODE` is used only when a key is absent, and is always
labelled as mock — never reported as a production run.
