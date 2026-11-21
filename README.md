# SmartCampus AI

Agentic university-orientation platform for IIT and ISB. Prospective students will talk to an
assistant in French, Tunisian dialect or Arabizi (text and voice), receive justified program
recommendations, pre-register, take a targeted quiz and be followed up until their enrolment
interview.

## Status

The repository currently contains the **technical foundation**; the product features are planned.

| Implemented | Planned |
| --- | --- |
| FastAPI backend: health check, catalogue API: public reads of published, valid data (programs, specialties, subjects, fees, admission requirements, eligibility) and management routes reserved to academic managers and administrators | Conversation, orientation and pre-registration services |
| Authentication and role-based access (SA-28): login, JWT in HttpOnly cookies, refresh, logout, CSRF protection, five roles | LangGraph agents with human validation |
| Next.js frontend: home page, login page for every actor, role-protected pages and public Qwen-backed chat | RAG over official IIT/ISB documents |
| Same-origin proxy from the frontend to the API | Speech-to-text, LoRA language adaptation |
| PostgreSQL + pgvector: 27-table data model, least-privilege roles, migrations | Production deployment |
| Replayable demonstration data | |
| Local services: PostgreSQL, Mailpit, Ollama | |
| Tests, linters, CI and a local verification script | |

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS 4, shadcn/ui |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, uv |
| Database | PostgreSQL 16 with pgvector |
| AI (planned) | LangGraph, Qwen3 served by Ollama (development) or vLLM, bge-m3 embeddings, faster-whisper |
| Tooling | Docker Compose, pytest, Ruff, ESLint, Prettier, GitHub Actions |

## Repository structure

```
apps/
  backend/     FastAPI application, models, migrations, tests, seed script
  frontend/    Next.js application
docs/          Reference documents (PDF) and developer guides
infra/         Docker Compose services and PostgreSQL role initialisation
scripts/       verify.ps1, local verification
.github/       CI workflow
```

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20.9 or later, with npm
- Docker Desktop (Compose v2)

## Getting started

All commands start from the repository root.

**1. Create the local configuration** from the tracked examples.

PowerShell:

```powershell
Copy-Item infra/.env.example infra/.env
Copy-Item apps/backend/.env.example apps/backend/.env
Copy-Item apps/backend/migrations/.env.example apps/backend/migrations/.env
Copy-Item apps/frontend/.env.example apps/frontend/.env.local
```

Git Bash:

```bash
cp infra/.env.example infra/.env
cp apps/backend/.env.example apps/backend/.env
cp apps/backend/migrations/.env.example apps/backend/migrations/.env
cp apps/frontend/.env.example apps/frontend/.env.local
```

Replace the `change_me_*` placeholders with your own local passwords, using the same value for a
role in `infra/.env` and in the backend URLs. See [docs/development.md](docs/development.md#configuration-files).

**2. Start the local services** (PostgreSQL, Mailpit, Ollama):

```bash
docker compose -f infra/docker-compose.yml up -d
```

Pull the configured Qwen model once (the Ollama volume keeps it across restarts):

```bash
docker compose -f infra/docker-compose.yml exec llm ollama pull qwen3:4b
```

The backend calls Ollama at `http://localhost:11434` by default using `qwen3:4b`. Override
`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, or `OLLAMA_TEMPERATURE` in
`apps/backend/.env` if needed.

**3. Prepare the database and start the backend** in a terminal:

```bash
cd apps/backend
uv sync
uv run alembic upgrade head
uv run fastapi dev
```

The API runs on <http://localhost:8000> (interactive docs at `/docs`).

**4. Start the frontend** in a second terminal:

```bash
cd apps/frontend
npm install
npm run dev
```

Open <http://localhost:3000> and choose Chat to try the Qwen-backed assistant. Its first reply may
take longer while Ollama loads the model. <http://localhost:3000/api/v1/health> checks the full chain
(frontend proxy, API and database).

**Optional:** load demonstration data with `uv run python -m app.seed` (from `apps/backend`; set
`DEMO_PASSWORD` in `apps/backend/.env` first if you want to log in with the demonstration accounts),
create a real account with `uv run python -m app.create_user --email … --role admin` (see
[docs/authentication.md](docs/authentication.md)), and
download the language model with
`docker compose -f infra/docker-compose.yml exec llm ollama pull qwen3:4b`.

## Testing

| Scope | Commands (from the application folder) |
| --- | --- |
| Backend (`apps/backend`) | `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest` |
| Frontend (`apps/frontend`) | `npm run lint` · `npm run typecheck` · `npm run build` |

Backend tests use the isolated `smartcampus_test` database and need the `db` container running.

To run every check at once (Windows PowerShell, from the repository root):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

CI runs the linters, the backend tests and the frontend build on every push and pull request.

## Documentation

- [Development guide](docs/development.md): services, configuration files, request flow, verification script
- [Database](docs/database.md): roles, migrations, tests, demonstration data
- Reference documents: [SA-3 actors and processes](docs/SA-3_Acteurs_et_processus_metier.pdf),
  [SA-4 architecture](docs/SA-4_Architecture_technique_du_systeme.pdf),
  [SA-5 API and access rules](docs/SA-5_API_et_regles_d_acces.pdf),
  [SA-11 data model](docs/SA-11_Modele_relationnel_metier.pdf),
  [SA-12](docs/SA-12_Tables_du_catalogue_academique.pdf),
  [SA-13](docs/SA-13_Tables_utilisateurs_et_candidatures.pdf),
  [SA-14](docs/SA-14_Tables_documents_et_synchronisation.pdf) tables
