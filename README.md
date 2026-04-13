# AI Legal System

Modular monorepo for an AI legal system focused on Czech statutes, case law and litigation strategy. Core jurisdiction: `czechia`. Secondary (scaffold only): `russia`.

---

## Current Checkpoint

This section is the authoritative resume point. It describes what is implemented, what is live-verified, what the current runtime state is, and what comes next.

---

### Implemented So Far

#### Foundation (earlier phase)

- Modular FastAPI backend and Next.js frontend.
- Qdrant lifecycle is production-safe:
  - active alias
  - versioned physical collections
  - embedding compatibility guard
  - explicit reindex flow
- Embedding layer supports `hash` and `sentence_transformer`.
- Runtime fallback between embedding spaces is disabled (no mixed-vector retrieval).
- Shared query pipeline: normalization, classification, domain hints, confidence routing.
- Hybrid retrieval: dense + lexical signals + fused scoring.
- `POST /api/search/answer` — retrieval-to-answer pipeline.
- `POST /api/search` — backward-compatible chunk retrieval.
- Redis exact cache (optional).
- Redis Stack semantic cache (optional).
- Structured JSON logging, cache observability, admin endpoints.

#### Czech Law Hybrid Retrieval Pipeline (current phase)

A fully custom retrieval stack was built for Czech statutes on top of Qdrant `czech_laws_v2`, a hybrid collection with named dense (`"dense"`) and sparse (`"sparse"`) vectors.

**Collection**

- `czech_laws_v2` — Qdrant hybrid collection, named vectors
- Dense vector: `Alibaba-NLP/gte-multilingual-base` (384 dim)
- Sparse vector: Czech BM25 (Robertson IDF + Robertson TF), IDF checkpoint at `storage/idf_czech_laws_v2.json`

**Key modules**

| File | Purpose |
|------|---------|
| `backend/app/modules/czechia/retrieval/query_analyzer.py` | Deterministic Czech query understanding: law ref detection, paragraph extraction, domain scoring (phrase + stem signals), query mode routing |
| `backend/app/modules/czechia/retrieval/retrieval_planner.py` | Builds `RetrievalPlan` per query mode: `exact`, `constrained`, `domain`, `broad` — with per-mode boost factors and hard law filters |
| `backend/app/modules/czechia/retrieval/dense_retriever.py` | Qdrant dense search on `czech_laws_v2` using `using="dense"` |
| `backend/app/modules/czechia/retrieval/sparse_retriever.py` | Qdrant sparse search on `czech_laws_v2` using `models.SparseVector` + lazy BM25 IDF load |
| `backend/app/modules/czechia/retrieval/fusion.py` | RRF fusion of dense + sparse candidates |
| `backend/app/modules/czechia/retrieval/reranker.py` | Score-based reranker with law match, paragraph match, preferred law, exact match, structural neighbor and text overlap boosts |
| `backend/app/modules/czechia/retrieval/evidence_validator.py` | Validates result set, triggers broadening if below threshold — does NOT broaden on exact mode with hits |
| `backend/app/modules/czechia/retrieval/service.py` | Orchestrates the full pipeline: ambiguity check → analyze → plan → execute → validate → keyword boost → dedup → confidence gate → relevance filter |
| `backend/app/modules/czechia/retrieval/ambiguity_handler.py` | Returns clarification suggestions for bare paragraph queries without a law name |
| `backend/app/modules/czechia/retrieval/adapter.py` | Wraps `CzechLawRetrievalService` into the generic `RetrievalService` interface |
| `backend/app/modules/czechia/ingestion/` | Full ingestion pipeline: fragment filter, chunk builder (deterministic uuid5 IDs), BM25 embedder, Qdrant writer, relation index, CLI |

**Domain detection**

Scores domains (`employment`, `civil`, `criminal`, `tax`, `administrative`, `constitutional`, `corporate`) using:
- phrase signals (e.g. `"výpověď z pracovního poměru"` → 6.0)
- stem signals (e.g. `"zamestnan"` → 3.0, `"dovolen"` → 3.0, `"zavaz"` → 3.0)
- detected law refs (+5.0 per matched law)

Threshold 2.5 — below this → `"unknown"`.

**Query modes**

| Mode | Trigger | Behavior |
|------|---------|----------|
| `exact_lookup` | law ref + paragraph detected | exact Qdrant payload filter, no broadening |
| `law_constrained_search` | law ref only | dense+sparse within law filter |
| `domain_search` | known domain, no ref | hard law filter when confidence ≥ 0.9 |
| `broad_search` | no signal | unconstrained dense+sparse + confidence gate |

**Confidence gate**

Fires only on `broad_search` with `unknown` domain and no law/paragraph refs. Uses `overlap_ratio(query_tokens, result_text) ≥ 0.5` — returns `irrelevant_query` system response if no result reaches threshold.

**Clarification flow**

Bare paragraph queries like `§52` without a law name return a structured clarification response with suggestions for the top 3 laws. Bypassed if the full query analyzer detects a law ref (e.g. `§1 zákon o daních z příjmů`).

**Dedup**

- Query-time: `_dedup_by_text()` in retrieval service strips identical text before returning results.
- Ingestion-time: `sha1(text)` per `law_iri` during streaming — same text in different fragments of the same law is stored only once.

**Fixes applied this phase**

- `"pracovn"` stem → `"prac"` (covers `práci`, `práce`, inflections)
- `zamestnan`/`zamestnav` weights raised to 3.0 (cross threshold alone)
- `dovolen` raised to 3.0, `zkusebn` added to employment
- `zavaz` added to civil at 3.0
- Evidence validator: early return for exact mode with hits (no spurious broadening)
- `is_paragraph_only` check: run full analyzer first so law names like `zákon o daních z příjmů` bypass clarification
- Confidence gate: token overlap ratio instead of any-token-in-text (blocks proper noun false positives)
- High-confidence domain search: hard `law_filter = preferred_law_iris` when `domain_confidence ≥ 0.9`
- Removed `"narok"`/`"naroku"` from `_STRATEGY_KEYWORDS` — "nárok" is a basic Czech legal term, not a strategy indicator; queries like "zaměstnanec nárok na odstupné" now correctly route to law retrieval
- Index-line structural penalty: numbered derogation-schedule entries (`"1. zákon č. ..."`, `"16. nařízení vlády č. ..."`) get −0.55 penalty in `CzechLawReranker` — runs unconditionally, covers all laws with preamble derogation lists; extended regex also catches `"N. Část první zákona č. Y/Z Sb."` entries
- **Exact lookup sort fix**: `paragraph=N` payload in Qdrant is a context inheritance tag (set by sequential scan), not an ownership tag — all fragments between §(N-1) and §N get `paragraph=N`. Fixed in `dense_retriever.py`: collect up to `_OVERSCAN=1024` candidates before sorting (heading chunk was at scroll position ~30, missed by the old `limit=15` early break); use `fragment_id` numeric suffix to detect pre-heading inherited chunks and relegate them; heading chunk is always position 0
- **LLM grounding fix**: `is_substantive()` min-length 55→30 chars so clause sub-items like `"a) ruší-li se zaměstnavatel..."` (43 chars) are included in the LLM context; added `-li` verb suffix detection; `max_chunks` 3→5 in `build_search_explanation_prompt`

#### Topic Query Improvements

Queries without an explicit paragraph number (e.g. `"výpověď zákoník práce"`, `"kupní smlouva občanský zákoník"`) now retrieve substantive sections instead of derogation index lines.

**Query expansion**

`query_analyzer.py` contains `_TOPIC_KEYWORD_EXPANSIONS` — 50 entries mapping normalized trigger phrases to a string of paragraph hints appended to the BM25 query. Examples:

| Trigger | Appended hint |
|---------|--------------|
| `výpověď zákoník práce` | `výpověď § 50 § 52 § 53` |
| `odstupné zákoník práce` | `odstupné § 67 § 68 § 73a` |
| `dovolená zákoník práce` | `dovolená § 211 § 212 § 213 § 214 § 215` |
| `kupní smlouva občanský zákoník` | `kupní smlouva § 2079 § 2080 § 2085 § 2099` |
| `vražda trestní zákoník` | `vražda § 140 trest odnětí svobody` |

`QueryUnderstanding` carries an `expanded_query` field. The service passes `expanded_query` to the sparse retriever only (BM25 benefits from paragraph hints; dense embedding quality degrades with appended noise).

**Reranker improvements**

- `_topic_heading_boost` (+0.18): boosts named legal-institute headings (`"Dovolená"`, `"Odstupné"`) that overlap with query tokens — only in `law_constrained_search` / `domain_search` modes and only when the chunk belongs to the target law
- `_PURE_REFERENCE_PENALTY` (−0.25): penalises fragments consisting only of cross-references (`"§ 52 odst. 2 a § 54"`) with no normative content
- `diversify_by_paragraph()`: caps 2 chunks per `(law_iri, paragraph)` group, ensuring results span multiple sections rather than all coming from a single paragraph

**Retrieval planner — topic mode**

When `law_constrained_search` fires without an explicit paragraph (`is_topic=True`):
- `candidate_k=120` (wider pre-rerank pool)
- `structural_window=2` (more neighboring chunks collected)
- `text_overlap_weight=0.32` (query keywords in chunk text weighted more heavily)

**Additional overlap gate for domain_search**

Filters out results where `mode=constrained`, domain is known, no paragraph filter, and no result reaches `overlap_ratio ≥ 0.3` — prevents keyword-matched but content-empty derogation lines from reaching the LLM.

#### Cross-Encoder Reranker

A modular cross-encoder reranker stack was added as a common abstraction under `modules/common/reranker/`.

**Architecture**

| File | Purpose |
|------|---------|
| `backend/app/modules/common/reranker/provider.py` | `BaseRerankerProvider` ABC — `score(query, documents) → list[float]` |
| `backend/app/modules/common/reranker/providers/bge.py` | `BGERerankerProvider` — `BAAI/bge-reranker-base` (~280 MB), lazy singleton, thread-safe, `_init_failed` guard |
| `backend/app/modules/common/reranker/service.py` | `rerank()` — reorder results by cross-encoder score, fail-open, 1200 ms timeout via `ThreadPoolExecutor`; `score_with_fallback()` — returns raw scores for domain-specific post-processing |
| `backend/app/modules/common/relevance/reranker.py` | `warmup_reranker()` — fires background thread at startup to pre-load BGE model; called from `app.main` `startup` event |
| `backend/app/modules/czechia/retrieval/cross_encoder_reranker.py` | Czech-law shim: delegates to `common.reranker.service.score_with_fallback()`, applies Czech heading penalty (−0.40) and index-line penalty (−0.55) before final sort |

**Design decisions**

- Text truncated to 768 chars before scoring (keeps latency predictable on CPU)
- Original `result.score` is NOT overwritten — cross-encoder only reorders
- Timeout fail-open: if BGE model exceeds 1200 ms (raised from 300 ms), original RRF order is preserved
- BGE pre-loaded at startup in a background thread (`warmup_reranker()`) — eliminates ~5-second cold-start timeout on first topic query
- BGE not applied on `exact` mode (paragraph lookup) — order there is structurally determined
- Index-line penalty also lives in `CzechLawReranker` (runs unconditionally) so it fires even when BGE has not yet finished loading

#### Batch Search Endpoint

`POST /api/search/answer` now accepts both single and batch requests:

```json
// single (unchanged)
{"query": "...", "country": "czechia", "domain": "law"}

// batch
{"queries": [{"query": "...", "country": "czechia", "domain": "law"}, ...]}
```

Batch runs queries concurrently via `ThreadPoolExecutor` (max 8 workers). Empty list returns `{"results": []}`.

New models:
- `BatchSearchRequest` — `queries: list[SearchRequest]`
- `BatchSearchAnswerResponse` — `results: list[SearchAnswerResponse]`

#### Russia Retrieval Hardening (deterministic anchors)

Russian taxonomy-first retrieval now has a deterministic safety layer for supported procedural/alimony issue clusters.

**What is guaranteed**

- If a supported issue is detected (`interpreter_issue`, `language_issue`, `notice_issue`, `service_address_issue`, `foreign_party_issue`, `alimony_issue`, `alimony_debt_issue`, `alimony_enforcement_issue`), response must never be empty.
- If retrieval candidates are empty/insufficient, backend injects canonical legal anchors directly (not another best-effort search attempt).
- Fallback is index-independent: when no chunk is available, API returns canonical reference rows with:
  - `law_id`
  - `law_short`
  - `article_num`
  - `article_heading` (if available in taxonomy)
  - `source = deterministic_anchor_fallback`
- Fallback metadata is explicit and consistent:
  - `fallback_applied`
  - `fallback_reason` (`no_taxonomy_candidates`, `retrieval_empty`, `retrieval_below_threshold`, `deterministic_anchor_injection`)
- Result dedup is enforced by `(law_id, article_num)` to avoid duplicate chunks dominating top output.

**Anchor guarantees**

- `interpreter_issue` → `ГПК 9`, `ГПК 162`
- `language_issue` → `ГПК 9`
- `notice_issue` → `ГПК 113`
- `service_address_issue` → notice/service cluster (`ГПК 113` minimum)
- `foreign_party_issue` → `ГПК 9`, `ГПК 162`
- `alimony_issue` → `СК 80`, `СК 81`
- `alimony_debt_issue` → canonical debt anchors (`СК 113` minimum)
- `alimony_enforcement_issue` → canonical enforcement anchors (`СК 113` minimum)

**Live verification**

- Real endpoint smoke run (`POST /api/russia/search`) across 9 production-like Russian formulations: **PASS 9 / FAIL 0**.
- Response payload now includes per-result `source` and top-level fallback metadata for auditability.

#### LLM Provider — DeepSeek

`BaseLLMProvider` now has three implementations:

| Class | `LLM_PROVIDER` value | Notes |
|-------|---------------------|-------|
| `MockLLMProvider` | `mock` | Default, no API key needed |
| `OpenAIProvider` | `openai` | OpenAI API |
| `DeepSeekProvider` | `deepseek` | OpenAI-compatible, `base_url=https://api.deepseek.com/v1`, no new packages |

Active config (in root `.env`):
```
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=<key>
```

---

### Live Verified State

Current ports:

| Service | Host port |
|---------|-----------|
| Backend API | `http://localhost:8032` |
| Backend docs (Swagger) | `http://localhost:8032/docs` |
| Frontend | `http://localhost:3010` |
| Qdrant | `http://localhost:6337` |
| Redis | `localhost:6382` |

Live-verified:

- 60/60 queries in `backend/run_tests.py` pass — exact lookups, domain search, broad search, clarification, irrelevant/nonsense detection
- 49/49 queries in `test_queries.ps1` pass — live HTTP test against `POST /api/search/answer`
- DeepSeek `deepseek-chat` returns real Czech legal explanations (not mock)
- Batch endpoint processes multiple queries in parallel correctly
- Redis cache working: exact cache hit on repeat queries
- `pytest backend/tests` — 48 passed
- Strategy routing: "nárok" queries correctly go to law retrieval, not strategy engine
- Index-line chunks no longer rank above substantive paragraphs

Sample verified query results:

| Query | Result |
|-------|--------|
| `§ 52 zákoník práce` | exact hit → 262/2006 Sb., heading at pos 0, clause list at pos 1-4 |
| `§ 209 trestní zákoník` | exact hit → 40/2009 Sb. |
| `§ 2910 občanský zákoník` | exact hit → 89/2012 Sb. |
| `výpovědní doba zákoník práce` | constrained → 262/2006 Sb. |
| `výpověď zákoník práce` | constrained + expanded → §52 heading + reasons returned |
| `dovolená zákoník práce délka` | constrained + expanded → §211-215 returned |
| `kupní smlouva občanský zákoník` | constrained + expanded → §2079-2099 returned |
| `trestní zákoník vražda trest` | constrained + expanded → "Vražda" heading + §140 returned |
| `odstupné zákoník práce podmínky` | constrained + expanded → §67-68 returned |
| `jak se počítá dovolená` | domain search → 262/2006 Sb. |
| `zkušební doba délka` | domain search → 262/2006 Sb. |
| `§ 52` | clarification response |
| `počasí Praha zítra` | irrelevant_query response |
| `python programming tutorial` | irrelevant_query response |

---

### Resume Plan After Restart

```powershell
# 1. Start stack
docker compose up -d

# 2. Rebuild backend image after code changes
docker compose up -d --build backend

# 3. Clear Redis cache (required after code changes that affect responses)
Invoke-RestMethod -Uri "http://localhost:8032/api/admin/cache/reset" -Method POST

# 4. Run end-to-end retrieval tests
docker exec ai-legal-backend python run_tests.py

# 5. Run unit test suite
docker exec ai-legal-backend pytest tests -q
```

After `docker compose up -d --build`, `run_tests.py` is not baked into the image — copy it first:
```powershell
docker cp backend/run_tests.py ai-legal-backend:/app/run_tests.py
```

---

### Planned Next Steps

1. **Re-ingest with full BM25 sparse vectors** — run `FORCE_REINGEST=1` to rebuild `czech_laws_v2` with proper sparse vectors (currently ingested with hash provider, sparse vectors empty for most points). This will significantly improve keyword-based retrieval.

2. **Score summary fix** — `decision.score_summary` always shows zeros for Czech path (Czech retrieval bypasses the `RetrievalFeatureSet` pipeline). Needs a bridge in `CzechLawRetrievalAdapter`.

3. **Prometheus / OpenTelemetry** — export cache and retrieval metrics in machine-readable format.

4. **Scoped cache invalidation** — invalidate by `jurisdiction + domain` without clearing everything.

5. **End-to-end CI test** — compose-backed smoke test in GitHub Actions hitting the live API.

6. **Russia jurisdiction** — deterministic taxonomy-first procedural/alimony anchor guarantees are implemented; next steps are broader corpus/topic expansion and additional end-to-end CI smoke coverage.

---

### Operational Constraints

- Do not rewrite ingestion or Qdrant lifecycle modules.
- Preserve no-mixed-embedding-space guarantee.
- Preserve active alias and versioned collection lifecycle.
- Keep Redis optional and non-blocking.
- Czech retrieval is fully isolated — `CzechLawRetrievalService` / `CzechLawRetrievalAdapter` — does not affect the generic retrieval path.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn |
| Frontend | Next.js + React + Tailwind CSS |
| Vector DB | Qdrant 1.17 (hybrid named vectors) |
| Orchestration | LangChain + LangGraph |
| LLM | DeepSeek Chat (configurable: also OpenAI or mock) |
| Embeddings | `Alibaba-NLP/gte-multilingual-base` via sentence-transformers |
| Sparse | Czech BM25 (custom Robertson IDF/TF) |
| Cache | Redis (exact) + Redis Stack (semantic, optional) |
| Config | `.env` via pydantic-settings |
| Runtime | Docker + docker-compose |
| Testing | pytest |
| CI | GitHub Actions |

---

## Project Tree

```text
.
├── .env                         ← active config (not in git)
├── .env.example
├── docker-compose.yml
├── test_queries.ps1             ← 50-query PowerShell live test (POST /api/search/answer)
├── test_topic_smoke.py          ← diagnostic: expansion check + sparse with expansion + penalty check
├── backend
│   ├── .env.example
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run_tests.py             ← 60-query end-to-end retrieval test
│   ├── storage/
│   │   └── idf_czech_laws_v2.json  ← BM25 IDF checkpoint
│   ├── app
│   │   ├── api/routes/
│   │   │   ├── search.py        ← single + batch search/answer endpoints
│   │   │   ├── health.py
│   │   │   └── admin.py
│   │   ├── core/
│   │   │   ├── config.py        ← Settings (LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, ...)
│   │   │   └── dependencies.py  ← DI wiring
│   │   └── modules/
│   │       ├── common/
│   │       │   ├── llm/provider.py          ← MockLLMProvider, OpenAIProvider, DeepSeekProvider
│   │       │   ├── orchestration/search_pipeline.py
│   │       │   ├── querying/                ← query normalization + classification
│   │       │   │   └── classifier.py        ← QueryType routing (_STRATEGY_KEYWORDS tuned)
│   │       │   ├── reranker/                ← cross-encoder abstraction
│   │       │   │   ├── provider.py          ← BaseRerankerProvider ABC
│   │       │   │   ├── service.py           ← rerank() + score_with_fallback(), 1200 ms timeout
│   │       │   │   └── providers/bge.py     ← BAAI/bge-reranker-base lazy singleton
│   │       │   ├── reasoning/               ← confidence gate
│   │       │   ├── responses/               ← SearchAnswerResponse, BatchSearchAnswerResponse
│   │       │   ├── cache/                   ← exact + semantic Redis cache
│   │       │   ├── observability/           ← metrics, logging
│   │       │   ├── relevance/               ← filter.py (score + system tag passthrough)
│   │       │   │   └── reranker.py          ← warmup_reranker() — pre-loads BGE at startup
│   │       │   └── qdrant/                  ← generic retrieval service
│   │       └── czechia/
│   │           ├── retrieval/
│   │           │   ├── query_analyzer.py        ← law ref + domain + paragraph detection
│   │           │   ├── retrieval_planner.py      ← RetrievalPlan per query mode
│   │           │   ├── dense_retriever.py        ← czech_laws_v2, using="dense"
│   │           │   ├── sparse_retriever.py       ← czech_laws_v2, BM25 SparseVector
│   │           │   ├── fusion.py                 ← RRF
│   │           │   ├── reranker.py               ← multi-factor score reranker + structural penalties
│   │           │   ├── cross_encoder_reranker.py ← BGE shim: heading + index-line penalties
│   │           │   ├── evidence_validator.py
│   │           │   ├── service.py                ← pipeline orchestrator
│   │           │   ├── ambiguity_handler.py      ← clarification for bare §N queries
│   │           │   ├── adapter.py                ← bridges to generic RetrievalService
│   │           │   └── schemas.py
│   │           └── ingestion/
│   │               ├── service.py           ← streaming ingest + sha1 dedup
│   │               ├── chunk_builder.py     ← deterministic uuid5 chunk IDs
│   │               ├── embedder.py
│   │               ├── sparse_retriever.py  ← BM25 encoder
│   │               ├── fragment_filter.py
│   │               ├── loader.py
│   │               ├── qdrant_writer.py     ← upsert to czech_laws_v2
│   │               ├── relation_index.py
│   │               └── schemas.py
│   └── tests/                   ← 48 pytest tests
└── frontend/
    └── ...                      ← Next.js UI
```

---

## API Reference

### Search

```
POST /api/search
```
Returns ranked chunks. Backward-compatible.

```
POST /api/search/answer
```
Single query → `SearchAnswerResponse`
Batch query → `BatchSearchAnswerResponse`

Single input:
```json
{"query": "§ 52 zákoník práce", "country": "czechia", "domain": "law", "top_k": 5}
```

Batch input:
```json
{
  "queries": [
    {"query": "§ 52 zákoník práce", "country": "czechia", "domain": "law"},
    {"query": "výpovědní doba", "country": "czechia", "domain": "law"}
  ]
}
```

### Admin

```
GET  /api/health
GET  /api/admin/cache/metrics
POST /api/admin/cache/reset
POST /api/admin/cache/metrics/reset
```

---

## Environment Setup

Copy root env and fill in secrets:

```powershell
Copy-Item .env.example .env
```

Key variables:

```env
# Ports
BACKEND_PORT=8032
FRONTEND_PORT=3010
QDRANT_HOST_PORT=6337
REDIS_HOST_PORT=6382

# LLM — set to deepseek for production
LLM_PROVIDER=deepseek          # deepseek | openai | mock
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-...

# Cache (optional)
REDIS_ENABLED=true
EXACT_CACHE_ENABLED=true
SEMANTIC_CACHE_ENABLED=true

# Embeddings
EMBEDDING_PROVIDER=hash        # hash | sentence_transformer
EMBEDDING_MODEL_NAME=Alibaba-NLP/gte-multilingual-base
```

> `backend/.env` is NOT used — docker-compose reads root `.env` and passes variables directly into the backend container environment.

---

## Run With Docker

```powershell
docker compose up -d --build
```

After first build, for code-only changes:

```powershell
docker compose up -d --build backend
docker cp backend/run_tests.py ai-legal-backend:/app/run_tests.py
Invoke-RestMethod -Uri "http://localhost:8032/api/admin/cache/reset" -Method POST
docker exec ai-legal-backend python run_tests.py
```

---

## Tests

```powershell
# Unit tests (inside container)
docker exec ai-legal-backend pytest tests -q

# End-to-end retrieval tests (60 queries, requires running stack)
docker exec ai-legal-backend python run_tests.py

# Live HTTP test — 50 queries against POST /api/search/answer (requires running stack)
.\test_queries.ps1

# CI (GitHub Actions)
# installs deps, compiles, runs pytest backend/tests, builds frontend
```

---

## Notes

- Czech retrieval is isolated in `modules/czechia/retrieval/` — does not touch the generic retrieval path.
- `czech_laws_v2` is a separate Qdrant collection from `legal_documents` — the two collections do not interact.
- BM25 IDF checkpoint is lazy-loaded on first sparse retrieval call and cached for the process lifetime.
- Redis cache must be cleared after backend code changes that affect response format (`POST /api/admin/cache/reset`).
- `run_tests.py` is not baked into the Docker image — copy it with `docker cp` after `--build`.
- DeepSeek uses the OpenAI-compatible API — no new packages required, `langchain-openai` handles it via `base_url`.
- Qdrant writes use deterministic `uuid5(chunk_id)` point IDs — re-ingestion is idempotent.
