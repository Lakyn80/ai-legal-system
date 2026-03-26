# AI Legal System

Modular monorepo foundation for an AI legal system focused on court files, statutes, case law and litigation strategy across two isolated jurisdiction branches: `russia` and `czechia`.

## Current Checkpoint

This section is the resume point after restart. It summarizes what is already implemented, what was verified live, what runtime state is currently in use, and what should happen next.

### Implemented So Far

- Modular FastAPI backend and Next.js frontend foundation are in place.
- Qdrant lifecycle is production-safe:
  - active alias
  - versioned physical collections
  - embedding compatibility guard
  - explicit reindex flow
- Embedding layer supports:
  - `hash`
  - `sentence_transformer`
- Runtime fallback between embedding spaces is disabled to avoid mixed-vector retrieval.
- New shared query pipeline was added:
  - query normalization
  - low-cost query classification
  - domain hints
  - confidence routing
- Retrieval was upgraded from dense-only behavior to a modular hybrid path:
  - dense retrieval
  - lexical signals
  - fused scoring
  - retrieval feature bundle for downstream routing
- New strict response layer was added for structured search answers.
- `POST /api/search/answer` was added as the new retrieval-to-answer pipeline.
- `POST /api/search` remains backward-compatible and still returns chunk results.
- Redis exact cache was added as an optional optimization.
- Redis Stack semantic cache was added as an optional optimization.
- Exact cache runs first, semantic cache runs second, retrieval runs only when both miss.
- Strategy requests still use the existing strategy engine and LangGraph path.
- Cache observability was added:
  - in-memory cache counters
  - runtime cache status
  - health output enrichment
  - admin metrics endpoint
- Structured JSON logging was added around:
  - exact cache hits/misses/writes
  - semantic cache hits/misses/writes
  - search routing decisions
- Cache admin operations were added:
  - `POST /api/admin/cache/reset`
  - `POST /api/admin/cache/metrics/reset`
- Route-level API tests were added for:
  - `GET /api/health`
  - `GET /api/admin/cache/metrics`
  - `POST /api/search/answer`
  - cache reset admin endpoints

### Modules Added or Extended Recently

- Shared query layer:
  - `backend/app/modules/common/querying/*`
- Shared confidence / reasoning layer:
  - `backend/app/modules/common/reasoning/*`
- Shared response contracts:
  - `backend/app/modules/common/responses/*`
- Shared orchestration:
  - `backend/app/modules/common/orchestration/search_pipeline.py`
- Shared cache layer:
  - `backend/app/modules/common/cache/client.py`
  - `backend/app/modules/common/cache/exact_cache.py`
  - `backend/app/modules/common/cache/identity.py`
  - `backend/app/modules/common/cache/schemas.py`
  - `backend/app/modules/common/cache/semantic_cache.py`
- Shared observability:
  - `backend/app/modules/common/observability/*`
- Shared logging config:
  - `backend/app/core/logging.py`
- Shared cache admin control:
  - `backend/app/modules/common/cache/admin_service.py`
- Extended retrieval modules:
  - `backend/app/modules/common/qdrant/retrieval_service.py`
  - `backend/app/modules/common/qdrant/lexical_reranker.py`
  - `backend/app/modules/common/qdrant/schemas.py`
- Extended API / DI / config:
  - `backend/app/api/routes/search.py`
  - `backend/app/api/routes/health.py`
  - `backend/app/api/routes/admin.py`
  - `backend/app/core/dependencies.py`
  - `backend/app/core/config.py`

### Live Verified State

Live verification was completed against the currently running stack:

- Backend: `http://localhost:8030`
- Frontend: `http://localhost:3010`
- Qdrant: `http://localhost:6335`
- Redis Stack: `localhost:6381`

Verified live:

- `GET /api/health`
- `GET /api/admin/cache/metrics`
- `POST /api/admin/cache/reset`
- `POST /api/admin/cache/metrics/reset`
- exact cache hit path
- semantic cache hit path
- retrieval fallback path
- structured JSON logs from backend container

Verified live scenario:

1. Query: `§ 3080 občanský zákoník`
2. Query: `občanský zákoník § 3080`
3. Query: `§ 3080 občanský zákoník`

Observed result:

- first request: retrieval path
- second request: semantic cache hit
- third request: exact cache hit

Observed cache metrics after that sequence:

- `exact_cache.hits = 1`
- `exact_cache.misses = 2`
- `exact_cache.writes = 1`
- `semantic_cache.hits = 1`
- `semantic_cache.misses = 1`
- `semantic_cache.writes = 1`
- `pipeline.requests_total = 3`
- `pipeline.retrieval_executions = 1`
- `pipeline.llm_executions = 0`
- `pipeline.strategy_executions = 0`

### Runtime Nuance

Current live backend on `8030` is functionally correct, but it is important to note the exact runtime state:

- the running backend was updated from the current codebase and verified live
- however, the active backend container is not yet a fully fresh compose-rebuilt image after the latest Redis/cache additions
- Redis itself is currently running and reachable on `6381`

This means:

- the code state is current
- the verified behavior is current
- runtime has now been rebuilt into a clean compose-managed state after restart
- backend, frontend, Qdrant and Redis are currently running through compose again

### Latest Test Status

Verified recently:

- `python -m compileall backend/app backend/tests`
- `pytest backend/tests/test_cache_metrics.py backend/tests/test_api_routes.py backend/tests/test_search_answer_service.py`
- `pytest backend/tests/test_api_routes.py backend/tests/test_search_answer_service.py backend/tests/test_exact_cache_service.py backend/tests/test_semantic_cache_service.py backend/tests/test_redis_cache_client.py`

Latest known recent results:

- full local backend suite: `48 passed`
- targeted local/backend tests: `12 passed`
- expanded cache + API subset: `16 passed`
- earlier full backend suite result before restart: `42 passed`

### Resume Plan After Restart

When continuing work, start from these steps:

1. Confirm containers and ports:
   - backend `8030`
   - frontend `3010`
   - Qdrant `6335`
   - Redis `6381`
2. Re-run smoke checks:
   - `GET /api/health`
   - `GET /api/admin/cache/metrics`
   - `POST /api/admin/cache/reset`
   - `POST /api/admin/cache/metrics/reset`
   - one exact-cache / semantic-cache test query pair
3. Continue with the next engineering phase below.

### Planned Next Steps

These are the agreed next tasks after the current cache pipeline work:

1. Clean runtime consolidation
   - completed after restart cleanup
2. Observability hardening
   - structured logging around cache hits/misses and routing decisions completed
   - next optional step: Prometheus-style export or OpenTelemetry integration
3. Cache operations
   - cache clear/reset and metrics reset endpoints completed
   - next optional step: scoped invalidation by jurisdiction/domain
4. Semantic cache policy refinement
   - different thresholds by query type
   - optional stricter reuse rules for law vs courts
5. Integration tests
   - route-level tests for `/api/health`, `/api/admin/cache/metrics`, `/api/search/answer` completed
   - next step: add end-to-end compose-backed API smoke into CI
6. Strategy pipeline refinement
   - reuse more of the shared query/retrieval primitives inside strategy orchestration
   - keep jurisdiction isolation intact

### Operational Reminder

The checkpoint goal is:

- do not rewrite working ingestion/Qdrant/jurisdiction modules
- continue incrementally from the new shared query/cache/retrieval/observability layers
- preserve no-mixed-embedding-space guarantees
- preserve active alias and versioned collection lifecycle
- keep Redis optional and non-breaking

## Stack

- Backend: FastAPI
- Frontend: Next.js + React + Tailwind CSS
- Vector database: Qdrant
- Orchestration: LangChain + LangGraph
- Configuration: `.env`
- Runtime: Docker + docker-compose
- Testing: pytest
- CI: GitHub Actions
- Cache: Redis / Redis Stack (optional exact + semantic cache)

## Project Tree

```text
.
├── .dockerignore
├── .env.example
├── .github
│   └── workflows
│       └── ci.yml
├── .gitignore
├── README.md
├── docker-compose.yml
├── backend
│   ├── .dockerignore
│   ├── .env.example
│   ├── Dockerfile
│   ├── requirements-dev.txt
│   ├── requirements.txt
│   ├── app
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   └── routes
│   │   │       ├── __init__.py
│   │   │       ├── admin.py
│   │   │       ├── documents.py
│   │   │       ├── health.py
│   │   │       ├── jurisdictions.py
│   │   │       ├── search.py
│   │   │       └── strategy.py
│   │   ├── cli
│   │   │   ├── __init__.py
│   │   │   └── import_local_document.py
│   │   │   └── reindex_documents.py
│   │   ├── core
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── dependencies.py
│   │   │   ├── enums.py
│   │   │   └── exceptions.py
│   │   ├── db
│   │   │   └── __init__.py
│   │   └── modules
│   │       ├── __init__.py
│   │       ├── contracts.py
│   │       ├── registry.py
│   │       ├── common
│   │       │   ├── __init__.py
│   │       │   ├── auth
│   │       │   │   └── __init__.py
│   │       │   ├── chunking
│   │       │   │   ├── __init__.py
│   │       │   │   └── service.py
│   │       │   ├── documents
│   │       │   │   ├── __init__.py
│   │       │   │   ├── ingestion_service.py
│   │       │   │   ├── repository.py
│   │       │   │   ├── schemas.py
│   │       │   │   └── service.py
│   │       │   ├── embeddings
│   │       │   │   ├── __init__.py
│   │       │   │   ├── base.py
│   │       │   │   ├── hash_provider.py
│   │       │   │   ├── profile.py
│   │       │   │   ├── provider.py
│   │       │   │   └── sentence_transformer_provider.py
│   │       │   ├── graph
│   │       │   │   ├── __init__.py
│   │       │   │   ├── builder.py
│   │       │   │   ├── schemas.py
│   │       │   │   └── strategy_engine.py
│   │       │   ├── llm
│   │       │   │   ├── __init__.py
│   │       │   │   └── provider.py
│   │       │   ├── parsing
│   │       │   │   ├── __init__.py
│   │       │   │   ├── legal_collection.py
│   │       │   │   ├── service.py
│   │       │   │   └── xhtml.py
│   │       │   ├── prompts
│   │       │   │   ├── __init__.py
│   │       │   │   └── base.py
│   │       │   ├── qdrant
│   │       │   │   ├── __init__.py
│   │       │   │   ├── client.py
│   │       │   │   ├── lexical_reranker.py
│   │       │   │   ├── reindex_service.py
│   │       │   │   ├── retrieval_service.py
│   │       │   │   └── schemas.py
│   │       │   └── storage
│   │       │       ├── __init__.py
│   │       │       └── file_storage.py
│   │       ├── czechia
│   │       │   ├── __init__.py
│   │       │   ├── courts
│   │       │   │   └── __init__.py
│   │       │   ├── graph
│   │       │   │   ├── __init__.py
│   │       │   │   └── workflow.py
│   │       │   ├── ingestion
│   │       │   │   └── __init__.py
│   │       │   ├── law
│   │       │   │   └── __init__.py
│   │       │   ├── prompts
│   │       │   │   ├── __init__.py
│   │       │   │   └── strategy_prompts.py
│   │       │   ├── retrieval
│   │       │   │   └── __init__.py
│   │       │   ├── schemas
│   │       │   │   ├── __init__.py
│   │       │   │   └── profile.py
│   │       │   ├── services
│   │       │   │   ├── __init__.py
│   │       │   │   └── strategy.py
│   │       │   └── strategy
│   │       │       └── __init__.py
│   │       └── russia
│   │           ├── __init__.py
│   │           ├── courts
│   │           │   └── __init__.py
│   │           ├── graph
│   │           │   ├── __init__.py
│   │           │   └── workflow.py
│   │           ├── ingestion
│   │           │   └── __init__.py
│   │           ├── law
│   │           │   └── __init__.py
│   │           ├── prompts
│   │           │   ├── __init__.py
│   │           │   └── strategy_prompts.py
│   │           ├── retrieval
│   │           │   └── __init__.py
│   │           ├── schemas
│   │           │   ├── __init__.py
│   │           │   └── profile.py
│   │           ├── services
│   │           │   ├── __init__.py
│   │           │   └── strategy.py
│   │           └── strategy
│   │               └── __init__.py
│   └── tests
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_chunking.py
│       ├── test_document_service.py
│       ├── test_embedding_provider.py
│       ├── test_ingestion_service.py
│       ├── test_legal_collection_parser.py
│       ├── test_qdrant_vector_store.py
│       ├── test_reindex_service.py
│       └── test_retrieval_service.py
└── frontend
    ├── .dockerignore
    ├── .env.example
    ├── Dockerfile
    ├── next-env.d.ts
    ├── next.config.js
    ├── package-lock.json
    ├── package.json
    ├── postcss.config.js
    ├── tailwind.config.js
    ├── tsconfig.json
    ├── app
    │   ├── documents
    │   │   └── page.tsx
    │   ├── search
    │   │   └── page.tsx
    │   ├── strategy
    │   │   └── page.tsx
    │   ├── upload
    │   │   └── page.tsx
    │   ├── globals.css
    │   ├── layout.tsx
    │   └── page.tsx
    ├── components
    │   ├── chunk-results.tsx
    │   ├── navigation.tsx
    │   ├── page-header.tsx
    │   ├── section-card.tsx
    │   └── strategy-view.tsx
    ├── features
    │   ├── documents
    │   │   └── documents-list.tsx
    │   ├── jurisdiction
    │   │   └── jurisdiction-selector.tsx
    │   ├── search
    │   │   └── search-panel.tsx
    │   ├── strategy
    │   │   └── strategy-panel.tsx
    │   └── upload
    │       └── upload-form.tsx
    ├── lib
    │   ├── config.ts
    │   └── utils.ts
    ├── public
    │   └── .gitkeep
    ├── services
    │   └── backend-api.ts
    └── types
        └── index.ts
```

## Architecture Summary

- `backend/app/modules/common`: shared parsing, chunking, embeddings, Qdrant, LLM and strategy orchestration.
- `backend/app/modules/russia` and `backend/app/modules/czechia`: isolated jurisdiction branches with separate prompts, schema profiles and graph workflow entrypoints.
- `backend/app/modules/contracts.py` and `backend/app/modules/registry.py`: plug-in style jurisdiction descriptors and routing.
- `backend/app/modules/common/embeddings`: provider-based embedding layer with swappable providers.
- `backend/app/modules/common/parsing/legal_collection.py`: legal collection parser for structured Czech statute exports in `JSON` or `ZIP`.
- `backend/app/modules/common/qdrant/client.py`: active-alias lifecycle, embedding metadata guard and versioned physical collections.
- `backend/app/modules/common/qdrant/reindex_service.py`: safe reindex into a new collection version followed by alias switch.
- `backend/app/modules/common/qdrant/lexical_reranker.py`: retrieval post-processing layer that improves ordering of candidate chunks.
- `frontend/features/*`: UI logic separated by functional area.
- `frontend/services/backend-api.ts`: isolated API client.

## Backend Features

- `POST /api/documents/upload`
- `POST /api/documents/ingest`
- `GET /api/documents`
- `POST /api/admin/reindex`
- `GET /api/admin/cache/metrics`
- `POST /api/search`
- `POST /api/search/answer`
- `POST /api/strategy/generate`
- `GET /api/health`
- `GET /api/jurisdictions`

### Upload and Ingestion

- Supports `PDF`, `DOCX`, `TXT`, `JSON`, `ZIP`
- Stores metadata locally in `STORAGE_PATH`
- Parses text, chunks with overlap, builds embeddings and upserts to Qdrant
- Supports local archive import through the CLI for large legal collections
- Uses a stable active alias in Qdrant and stores embedding metadata on the physical collection
- Qdrant payload contains:
  - `chunk_id`
  - `document_id`
  - `filename`
  - `country`
  - `domain`
  - `jurisdiction_module`
  - `text`
  - `chunk_index`
  - `source_type`
  - `tags`

### Embedding Providers

- `hash`: offline-safe deterministic provider for local bootstrap and CI
- `sentence_transformer`: semantic provider for higher-quality retrieval when model download or local cache is available
- provider aliases `sentence_transformer` and `sentence_transformers` are both accepted in config
- runtime fallback between embedding spaces is intentionally disabled to avoid mixed-vector retrieval

### Strategy Engine

LangGraph workflow runs these steps:

1. Intake query
2. Determine jurisdiction
3. Retrieve relevant law chunks
4. Retrieve relevant court chunks
5. Analyze legal norms
6. Analyze court positions
7. Synthesize arguments
8. Assess risks and missing materials
9. Return structured JSON strategy

If no real provider is configured, the system falls back to a `mock` LLM provider so the project remains runnable as a functional base. For production use, switch `LLM_PROVIDER=openai` and provide `LLM_API_KEY`.

### Search Answer Pipeline

- `POST /api/search` keeps the original retrieval-only behavior and returns ranked chunks
- `POST /api/search/answer` runs the new query pipeline:
  - query normalization and classification
  - optional exact cache short-circuit in Redis
  - optional semantic cache short-circuit in Redis Stack / RediSearch
  - hybrid retrieval with lexical signals
  - confidence gate
  - deterministic citation answer for high-confidence exact matches
  - LLM-grounded semantic explanation only when needed

## Environment Setup

1. Copy root env:

```powershell
Copy-Item .env.example .env
```

2. Optional:

- copy `backend/.env.example` to `backend/.env` for local backend-only runs
- copy `frontend/.env.example` to `frontend/.env.local` for local frontend-only runs

Important env variables:

- `BACKEND_PORT=8030`
- `FRONTEND_PORT=3010`
- `QDRANT_HOST_PORT=6335`
- `QDRANT_COLLECTION=legal_documents`
- `QDRANT_COLLECTION_ALIAS=legal_documents_active`
- `REDIS_ENABLED=false`
- `REDIS_URL=redis://redis:6379/0`
- `EXACT_CACHE_ENABLED=false`
- `EXACT_CACHE_TTL_SECONDS=3600`
- `SEMANTIC_CACHE_ENABLED=false`
- `SEMANTIC_CACHE_TTL_SECONDS=7200`
- `SEMANTIC_CACHE_SIMILARITY_THRESHOLD=0.93`
- `SEMANTIC_CACHE_TOP_K=3`
- `RESPONSE_SCHEMA_VERSION=v1`
- `STRATEGY_PROMPT_VERSION=v1`
- `EMBEDDING_PROVIDER=hash`
- `EMBEDDING_MODEL_NAME=Alibaba-NLP/gte-multilingual-base`

## Run With Docker

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:3010`
- Backend API: `http://localhost:8030`
- Backend docs: `http://localhost:8030/docs`
- Qdrant: `http://localhost:6335`
- Redis: `localhost:6381`

## Local Development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8030
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Import Local Legal Collection

Large legal archives can be kept outside git and imported through the backend CLI after extraction.

Example:

```powershell
docker exec ai-legal-backend python -m app.cli.import_local_document `
  /tmp/legal-imports/Sb_2012_89_2026-01-01_IZ.json `
  --country czechia `
  --domain law `
  --document-type legal_collection_json `
  --source "Sb_2012_89_2026-01-01_IZ" `
  --tags sbirka,zakony,czechia
```

## Reindex Qdrant

Reindex creates a new physical collection version, re-embeds all stored documents and atomically switches the active alias after success.

API example:

```powershell
Invoke-RestMethod -Uri "http://localhost:8030/api/admin/reindex" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"delete_previous_collection": false}'
```

CLI example:

```powershell
docker compose run --rm backend python -m app.cli.reindex_documents
```

## Tests and CI

Run backend tests:

```powershell
docker run --rm -v "${PWD}\backend:/workspace" -w /workspace ai-legal-system-backend sh -lc "pip install --no-cache-dir -r requirements-dev.txt && pytest tests"
```

GitHub Actions workflow:

- installs CPU-only torch
- installs backend and frontend dependencies
- compiles backend modules
- runs `pytest backend/tests`
- runs `npm run build` for frontend

## Notes

- Backend validates embedding compatibility on startup and fails fast on mismatch.
- Qdrant writes and reads go through an active alias, while physical collections are versioned.
- Redis exact cache is optional and does not block startup or request handling when disabled or unavailable.
- Semantic cache is also optional and only activates when Redis Stack / RediSearch features are available.
- `GET /api/health` now includes cache runtime state and in-memory request/cache counters.
- `GET /api/admin/cache/metrics` exposes detailed exact/semantic cache counters and runtime status for observability.
- Storage is file-backed to keep the foundation simple and replaceable.
- The archive `Sb_2012_89_2026-01-01_IZ.zip` and extracted workspace data are ignored by git and docker context.
- Jurisdictions can be extended by adding a new module branch and registering a new descriptor.
- For better legal retrieval quality in production, switch the embedding provider from `hash` to `sentence_transformer` and preload or cache the model.
