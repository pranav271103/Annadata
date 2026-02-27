Annadata Dockerization & Scaling Plan

Summary
- Monorepo with multiple Python FastAPI backends and Node frontends, shared datasets and model artifacts. Goal: make the repo developer-friendly via Docker Compose for laptops, provide templates to scale to 10+ idea services, and outline production migration.

Actionable Steps (top-level)
1. Audit repo and confirm service entrypoints.
2. Define a service layout: `services/`, `libs/`, `infra/`.
3. Add Dockerfile templates and per-service `Dockerfile`s.
4. Create root `docker-compose.yml`, `.env.example`, and per-service env templates.
5. Scaffold repeatable service template to add 10+ ideas.
6. Add dev ergonomics (Traefik, profiles, hot-reload) and CI/K8s path.

Detailed Plan

1) Audit & Inventory
- Action: Finalize service list and entrypoints.
- Files to review: `protein_engineering/backend/app.py`, `src/api/app.py`, `msp_mitra/backend/main.py`, `requirements.txt`, `src/models/saved_models`.
- Output: canonical `services.json` mapping directory → entrypoint → port → deps.

2) Define Repo Layout
- Adopt layout: `services/<name>/backend`, `services/<name>/frontend`, `libs/` for shared code, `infra/` for compose & templates.
- Create: `infra/docker-templates/Dockerfile.python`, `infra/docker-templates/Dockerfile.node`, `infra/.dockerignore`.

3) Dockerfile Templates
- Use `python:3.11-slim` and `node:18-alpine`.
- Backends default to port 8000 (uvicorn); `src/api` 8002; `msp_mitra` 8001. Frontends use dev ports (5173/3000).
- Bind-mount code and model artifacts during dev.

Example Dockerfile (Python FastAPI)

```Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/
RUN apt-get update && apt-get install -y build-essential gcc && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt && rm -rf /var/lib/apt/lists/*
COPY . /app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

Example Dockerfile (Node frontend)

```Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

4) Compose Orchestrator (dev)
- Components: `postgres:15`, `redis:7`, `traefik:v2`, representative services: `protein_engineering_backend`, `src_api`, and a frontend.
- Mount `./data` and `./src/models/saved_models` read-only into services.
- Use Compose profiles to opt-in heavy ML services.

Minimal `docker-compose.yml` (proposal)

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    restart: unless-stopped
    environment:
      POSTGRES_USER: "${POSTGRES_USER:-postgres}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-postgres}"
      POSTGRES_DB: "${POSTGRES_DB:-annadata}"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./data:/data:ro
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    restart: unless-stopped
    ports:
      - "6379:6379"

  traefik:
    image: traefik:v2.10
    command:
      - --api.insecure=true
      - --providers.docker=true
      - --entryPoints.web.address=:80
    ports:
      - "80:80"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

  api_service:
    build:
      context: .
      dockerfile: ./infra/docker-templates/Dockerfile.python
    command: uvicorn src.api.app:app --host 0.0.0.0 --port 8002 --reload
    volumes:
      - ./:/app:cached
      - ./src/models/saved_models:/app/src/models/saved_models:cached
      - ./data:/app/data:ro
    ports:
      - "8002:8002"
    depends_on:
      - postgres
      - redis

  protein_engineering_backend:
    build:
      context: ./protein_engineering/backend
    command: uvicorn protein_engineering.backend.app:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./protein_engineering/backend:/app:cached
      - ./protein_engineering/backend/data:/app/data:ro
      - ./src/models/saved_models:/app/src/models/saved_models:cached
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  frontend_vite:
    build:
      context: ./msp_mitra/frontend
      dockerfile: ./infra/docker-templates/Dockerfile.node
    command: npm run dev
    volumes:
      - ./msp_mitra/frontend:/app:cached
    ports:
      - "5173:5173"
    depends_on:
      - api_service

volumes:
  pgdata:
```

5) Service Scaffold + Templates for 10 new ideas
- Create `services/_template` with:
  - `backend/app.py` (FastAPI stub with health endpoint)
  - `backend/requirements.txt`
  - `backend/Dockerfile` (FROM infra template)
  - `README.md`, `openapi.yaml`, `tests/test_basic.py`
- Duplicate and rename to create each idea service; register in `docker-compose.yml` via profile.

6) Data & Model Handling
- Mount `data/processed` and `src/models/saved_models` into containers; avoid copying large artifacts into images.
- Consider `minio` service in compose for S3-compatible storage if needed.

7) Async & Heavy-Job Pattern
- Use `redis` + `celery`/`rq` for long-running jobs. Provide `worker` service template to process queued tasks.

8) Dev Ergonomics & Observability
- Use Traefik for routing via Docker labels, Compose profiles for optional services, `docker-compose.override.yml` for per-developer overrides.
- Add healthchecks and basic logging config.

9) CI → Production Path
- For production, migrate to Kubernetes with Helm charts.
- Add GitHub Actions to build images and run tests; use model serving (BentoML/Seldon) for scalable inference.

Verification & Smoke Tests
- `docker compose up -d --build`
- `docker compose logs -f protein_engineering_backend`
- `curl http://localhost:8000/health`
- `curl http://localhost:8002/docs`
- Ensure model loads from `/app/src/models/saved_models` in containers.

Decisions (recommended)
- Python base: `python:3.11-slim`.
- Node base: `node:18-alpine`.
- DB: `postgres:15`.
- Broker: `redis:7`.
- Reverse proxy: `traefik:v2.10`.
- Models: prefer ONNX/TorchScript in prod; keep pickles for dev only.

Critical Files to Review
- `protein_engineering/backend/app.py`
- `protein_engineering/backend/requirements.txt`
- `src/api/app.py`
- `src/config/settings.py`
- `src/models/saved_models/model_registry.json`
- `msp_mitra/backend/main.py`
- `msp_mitra/frontend/package.json`
- `requirements.txt`
- `data/processed`

Open Questions / Blockers
- Do you want to refactor to `services/<name>/` now or map compose to current paths? (recommend mapping first)
- Should model artifacts move to MinIO or stay under `src/models/saved_models`?
- Any laptop constraints (RAM/disk) to set resource caps in Compose?

Next steps (pick one)
A) Generate `infra/docker-templates` and a working `docker-compose.yml` plus `.env.example`.
B) Scaffold `services/_template` and create 3 example idea services to demonstrate pattern.

Choose A or B or request edits to this plan.
