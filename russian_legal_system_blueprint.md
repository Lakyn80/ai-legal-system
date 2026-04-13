# Barevná vizualizace: produkční plán pro Russian Legal System

## Legenda

- 🟦 **Core platforma** — sdílená infrastruktura a orchestrátor
- 🟩 **Stabilní produkční vrstva** — ingest, chunking, indexing, retrieval
- 🟨 **Kontrolní a validační vrstva** — testy, quality gates, audit, confidence
- 🟧 **Asynchronní processing** — Celery joby, fronty, background pipelines
- 🟥 **Incident / risk / stop gate** — co nesmí projít dál
- 🟪 **Observability a monitoring** — Prometheus, Flower, logs, tracing
- ⬜ **Výstup pro uživatele** — API, strategie, case analysis

---

# 1. Cílový obrázek systému

```text
                           ┌─────────────────────────────────────┐
                           │ ⬜ API / Frontend / Case UI         │
                           │ search | answer | strategy         │
                           └────────────────┬────────────────────┘
                                            │
                                            ▼
                   ┌────────────────────────────────────────────────────┐
                   │ 🟦 AI-Legal-System Orchestration Layer            │
                   │ Router | Query Understanding | Strategy Engine    │
                   │ Validation | Response Builder                     │
                   └───────┬───────────────────────┬───────────────────┘
                           │                       │
                           │                       │
                           ▼                       ▼
        ┌──────────────────────────────┐   ┌──────────────────────────────┐
        │ 🟩 Law Retrieval (RU laws)   │   │ 🟩 Case Retrieval            │
        │ parser | chunking | qdrant   │   │ client docs | facts         │
        │ exact lookup | topic search  │   │ timeline | evidence         │
        └──────────────┬───────────────┘   └──────────────┬───────────────┘
                       │                                  │
                       ▼                                  ▼
             ┌──────────────────────┐           ┌──────────────────────┐
             │ 🟩 Judicature Layer  │           │ 🟨 Validation Gates  │
             │ court decisions      │           │ evidence | schema    │
             │ case law retrieval   │           │ confidence | audit   │
             └──────────┬───────────┘           └──────────┬───────────┘
                        │                                  │
                        └────────────────┬─────────────────┘
                                         ▼
                        ┌────────────────────────────────────┐
                        │ ⬜ Final response / strategy       │
                        │ facts | laws | judgments | risks   │
                        │ recommendations | citations        │
                        └────────────────────────────────────┘
```

---

# 2. Produkční vrstvy odspodu nahoru

## 🟦 Vrstva A — Shared platform foundation

Tohle **znovupoužiješ** z aktuálního systému.

### Moduly
- `backend/app/core/config.py`
- `backend/app/core/dependencies.py`
- `modules/common/cache/`
- `modules/common/responses/`
- `modules/common/reasoning/`
- `modules/common/orchestration/`
- `modules/common/llm/`
- `modules/common/observability/`
- `modules/common/reranker/`
- `modules/common/qdrant/` pouze infrastrukturně

### Co musí zůstat zachované
- versioned collections
- alias lifecycle
- no mixed embedding spaces
- Redis optional / fail-open
- strict response schemas
- structured logs

### Kontrolní bod A1
**Smoke gate:** backend naběhne bez RU retrieval logiky.

### Testy
- config load test
- dependency wiring test
- Redis off test
- Qdrant unavailable graceful failure test
- health endpoint test

---

## 🟩 Vrstva B — Russian law corpus ingest

Tady začne nová větev.

## Cíl
Vzít ruské zákony v Unicode textu a převést je do přesně strukturovaného korpusu pro retrieval.

### Pipeline
```text
raw unicode law files
  -> law loader
  -> structure parser
  -> metadata extractor
  -> legal chunk builder
  -> embedding
  -> sparse indexing
  -> qdrant write
  -> ingest validation
```

### Nové moduly
- `modules/russia/ingestion/loader.py`
- `modules/russia/ingestion/parser.py`
- `modules/russia/ingestion/metadata_extractor.py`
- `modules/russia/ingestion/chunk_builder.py`
- `modules/russia/ingestion/embedder.py`
- `modules/russia/ingestion/qdrant_writer.py`
- `modules/russia/ingestion/schemas.py`

### Parser musí vytáhnout
- law code / identifier
- plný název zákona
- zkratky / aliasy
- chapter / section / article / part / point
- headings
- body text
- cross references
- source filename
- source version / ingest timestamp

### Kontrolní bod B1 — raw parse gate
Každý soubor musí projít přes parser a uložit:
- `law_id`
- `law_title`
- `article_count`
- `structure_depth`
- `parse_errors[]`

### Kontrolní bod B2 — chunk integrity gate
Každý chunk musí mít:
- deterministic ID
- law_id
- article / part metadata
- heading context
- body text
- non-empty text

### Kontrolní bod B3 — indexing gate
Před zápisem do Qdrantu:
- embedding dim valid
- sparse vector present
- payload valid
- chunk count sedí proti parser outputu

### Testy krok za krokem
1. parser unit tests na 3 malé zákony
2. article extraction tests
3. heading extraction tests
4. cross-reference extraction tests
5. chunk builder tests
6. deterministic idempotent ingest test
7. qdrant write test
8. re-ingest overwrite/idempotency test

### Stop conditions 🟥
- chybí article numbering
- text je prázdný / rozbitý
- chunk bez law_id
- embedding mismatch
- index se zapisuje do špatné collection

---

## 🟩 Vrstva C — Russian retrieval engine

## Cíl
Postavit retrieval, který funguje bez LLM jako právní základ.

### Pipeline
```text
query
  -> normalizace
  -> jurisdiction check
  -> query analyzer
  -> exact / topic / domain routing
  -> dense retrieval
  -> sparse retrieval
  -> fusion
  -> rerank
  -> evidence validation
  -> deterministic answer OR LLM fallback
```

### Nové moduly
- `modules/russia/retrieval/query_analyzer.py`
- `modules/russia/retrieval/retrieval_planner.py`
- `modules/russia/retrieval/dense_retriever.py`
- `modules/russia/retrieval/sparse_retriever.py`
- `modules/russia/retrieval/fusion.py`
- `modules/russia/retrieval/reranker.py`
- `modules/russia/retrieval/evidence_validator.py`
- `modules/russia/retrieval/ambiguity_handler.py`
- `modules/russia/retrieval/adapter.py`
- `modules/russia/retrieval/schemas.py`

### Query typy
- `exact_lookup`
- `law_constrained_search`
- `domain_search`
- `broad_search`
- později `case_strategy_search`

### Exact lookup musí umět
- `статья X`
- `ст. X`
- `ч. Y ст. X`
- `п. Z ч. Y ст. X`
- zákon + článek

### Topic mode musí umět
- rodinné právo
- styk rodiče s dítětem
- rodičovská práva
- výkon rozhodnutí
- procesní vady
- opatrovnické řízení

### Kontrolní bod C1 — query classification gate
U každé test query musí být správně:
- non-legal
- legal-out-of-scope
- ambiguous
- in-domain legal

### Kontrolní bod C2 — exact hit gate
Pokud je exact hit true:
- LLM se nesmí pustit
- top1 musí být obsahový chunk
- heading chunk může být jen jako kontext, ne jediný důkaz

### Kontrolní bod C3 — topic retrieval gate
U topic query musí top výsledky pokrývat relevantní article pack, ne jen structural headings.

### Kontrolní bod C4 — weak evidence gate
Pokud:
- anchor_hits == 0
- supporting_chunks == 0
- top1 off-topic

pak:
- stop
- deterministic fallback
- žádné LLM

### Testy krok za krokem
1. query analyzer unit tests
2. exact article parsing tests
3. topic mapping tests
4. ambiguity tests
5. dense retrieval tests
6. sparse retrieval tests
7. fusion ordering tests
8. reranker penalty tests
9. evidence validator tests
10. end-to-end retrieval smoke tests

### Stop conditions 🟥
- exact hit přesto jde do LLM
- top1 je heading bez obsahu
- domain unknown query přesto pustí retrieval
- unrelated law contamination

---

## 🟩 Vrstva D — Case understanding system

## Cíl
Po nahrání klientského spisu vznikne spolehlivá factual layer.

### Pipeline
```text
uploaded case files
  -> document boundary cleanup
  -> attachment split
  -> OCR/noise normalization (jen pokud potřeba)
  -> document typing
  -> metadata extraction
  -> facts extraction
  -> timeline extraction
  -> case artifact persistence
  -> case retrieval index
```

### Artifacty
- `document_boundaries.v1`
- `document_splits.v1`
- `normalized_text.v1`
- `case_assembly.v1`
- `timeline.v1`
- `facts.v1`
- `missing_evidence.v1`

### Kontrolní bod D1 — segmentation gate
Každá stránka musí patřit do správného dokumentového segmentu.

### Kontrolní bod D2 — document typing gate
Dokument musí být označen typem:
- court_decision
- appeal
- petition
- protocol
- evidence
- postal_tracking
- receipt
- translation
- attachment

### Kontrolní bod D3 — fact integrity gate
Extrahovaná fakta musí mít:
- source refs
- confidence
- no hallucinated fields

### Testy krok za krokem
1. boundary detection tests
2. attachment split tests
3. document type classifier tests
4. timeline extraction tests
5. fact extraction tests
6. case retrieval tests

---

## 🟩 Vrstva E — Judicature / court decisions layer

## Cíl
Přidat retrieval nad rozhodnutími soudů.

### Pipeline
```text
court decisions
  -> parser
  -> metadata extraction
  -> passage chunking
  -> embeddings
  -> qdrant / search index
  -> case-law retrieval
```

### Metadata minimum
- court
- case number
- date
- decision type
- chamber/panel if available
- procedural stage
- key issue tags

### Kontrolní bod E1
Rozhodnutí musí být citovatelná a dohledatelná po spisové značce i tématu.

### Testy
- case number extraction tests
- court metadata tests
- chunk quality tests
- case law retrieval tests

---

## 🟦 Vrstva F — Strategy orchestration

## Cíl
AI-Legal-System skládá strategii nad:
- case evidence
- laws
- judicature

### LangGraph role
Pouze orchestrace:
- Router Agent
- Law Retrieval Agent
- Judicature Retrieval Agent
- Case Evidence Agent
- Strategy Synthesis Agent
- Validation Agent

### Strategy flow
```text
user query + case_id
  -> router
  -> parallel retrieval:
       law
       judicature
       case evidence
  -> fusion/context builder
  -> strategy synthesis
  -> citation validation
  -> response schema validation
  -> final strategy response
```

### Kontrolní bod F1
Každé zásadní tvrzení musí mít source support.

### Kontrolní bod F2
Confidence nesmí být vysoká, pokud chybí zákon nebo case evidence.

### Testy
- strategy schema tests
- evidence coverage tests
- unsupported claim rejection tests
- mixed-source fusion tests

---

# 3. Celery: kde přesně dává smysl

## 🟧 Celery použij pro dlouhé a opakovatelné joby

Ne pro jednoduchý sync search request.

### Celery joby
- RU law ingest batch
- reindex collection
- sparse vector recomputation
- IDF rebuild
- court decisions ingest
- case file processing
- timeline rebuild
- cached answer precomputation
- nightly validation jobs
- dead-letter reprocessing

### Doporučené queue rozdělení
- `ingest_high`
- `ingest_bulk`
- `reindex`
- `case_processing`
- `cache_build`
- `monitoring_checks`

### Worker role separation
- CPU worker — parsing, chunking, embeddings prep
- IO worker — file reads, writes, uploads
- low-priority batch worker — reindex, rebuild, backfills

### Celery kontrolní body
- task retries bounded
- idempotent tasks only
- task result metadata persisted
- failure reason saved
- poison task quarantine

### Flower role
Flower používej jako:
- live queue dashboard
- failed task inspection
- retry visibility
- worker status panel

Flower **není observability systém**, jen operační UI pro Celery.

### Celery testy
1. single ingest task test
2. batch chain test
3. retry-on-failure test
4. idempotent rerun test
5. dead-letter scenario test
6. queue saturation test

---

# 4. Prometheus, metrics, health, alerts

## 🟪 Prometheus musí být od začátku

### Co měřit

## Backend / API
- request count
- latency p50/p95/p99
- error rate
- endpoint-specific latency
- batch query size

## Retrieval
- dense retrieval latency
- sparse retrieval latency
- fusion latency
- reranker latency
- evidence gate reject count
- exact_hit count
- LLM fallback rate
- irrelevant_query rate
- clarification rate

## Qdrant
- collection size
- search latency
- write latency
- failed writes

## Redis
- hit rate exact cache
- hit rate semantic cache
- miss rate
- cache reset count
- invalidation count

## Celery
- queued tasks
- running tasks
- failed tasks
- retry count
- time in queue
- task runtime by task type

## Case pipeline
- pages processed
- segmentation confidence distribution
- fact extraction success rate
- timeline extraction success rate

### Alerty
- high error rate > threshold
- reranker timeout spike
- LLM fallback spike
- exact_hit regression
- Qdrant unavailable
- Redis unavailable
- Celery queue backlog high
- repeated ingest failures

### Health endpoints
- `/api/health`
- `/api/health/dependencies`
- `/api/health/retrieval`
- `/api/health/cache`
- `/api/health/celery`

---

# 5. Flower + Prometheus + logs + tracing: jak to spojit

```text
API / workers / ingestion / retrieval
   -> structured logs (JSON)
   -> Prometheus metrics
   -> traces (OpenTelemetry)
   -> Grafana dashboards
   -> Flower only for Celery task UI
```

## Doporučená sada
- **Prometheus** — sběr metrik
- **Grafana** — dashboardy
- **Flower** — Celery UI
- **OpenTelemetry** — tracing requestu přes retrieval pipeline
- **Loki / ELK** — log storage

### Co má jít trasovat end-to-end
Jedna request trace musí ukázat:
- query received
- query classified
- retrieval mode selected
- dense done
- sparse done
- fusion done
- rerank done
- evidence gate decision
- LLM called yes/no
- cache hit yes/no
- response returned

---

# 6. Kontrolní systém krok za krokem

## 🟨 Stage-gate model

## Stage 0 — Foundation gate
Musí projít:
- backend boot
- config valid
- env valid
- health endpoints alive
- logs valid JSON

## Stage 1 — RU ingest gate
Musí projít:
- parser correctness
- chunk integrity
- embedding valid
- Qdrant write valid
- re-ingest idempotent

## Stage 2 — RU retrieval gate
Musí projít:
- exact lookup tests
- topic tests
- ambiguity tests
- irrelevant query tests
- no false-positive LLM tests

## Stage 3 — Case understanding gate
Musí projít:
- segmentation tests
- typing tests
- timeline tests
- facts with source refs

## Stage 4 — Judicature gate
Musí projít:
- case number lookup
- topic retrieval
- metadata integrity

## Stage 5 — Strategy gate
Musí projít:
- mixed-source strategy response
- unsupported claim blocking
- source-backed outputs only

## Stage 6 — Ops gate
Musí projít:
- Prometheus scrape
- Grafana dashboards
- Flower workers visible
- Celery retries working
- alerts fire in simulated failure

## Stage 7 — Production readiness gate
Musí projít:
- soak test
- queue backlog test
- cache resilience test
- Qdrant restart recovery
- Redis down fail-open
- worker restart recovery

---

# 7. Nejlepší pořadí implementace

## Fáze 1 — RU law ingest foundation
- parser
- metadata extractor
- chunk builder
- qdrant write
- ingest tests

## Fáze 2 — RU exact lookup
- article parser
- exact retrieval
- exact rerank
- exact no-LLM gate
- exact smoke tests

## Fáze 3 — RU topic retrieval
- topic taxonomy
- query analyzer
- planner
- dense+sparse fusion
- evidence validator
- topic smoke tests

## Fáze 4 — observability minimum
- Prometheus metrics
- Grafana dashboard v1
- structured logs
- basic alerts

## Fáze 5 — Celery background jobs
- ingest queue
- reindex queue
- case processing queue
- Flower
- retry policy

## Fáze 6 — case understanding
- boundary cleanup
- artifact schemas
- facts and timeline
- case retrieval

## Fáze 7 — judicature
- ingest decisions
- metadata
- retrieval

## Fáze 8 — strategy engine
- parallel retrieval
- fusion
- synthesis
- validation

## Fáze 9 — production hardening
- soak tests
- chaos tests
- recovery drills
- scoped cache invalidation

---

# 8. Definition of Done pro každou velkou oblast

## RU laws ingest je hotový když:
- zákony jsou strukturovaně parseované
- chunky jsou auditovatelné
- index je idempotentní
- exact lookup vrací správné články

## RU retrieval je hotový když:
- in-domain query najde správný právní základ
- weak evidence neprojde
- exact hit nikdy neuteče do LLM
- topic query vrací obsah, ne headings

## Case understanding je hotový když:
- spis je rozdělen na dokumenty
- timeline sedí
- facts mají source refs
- typické case dotazy jdou rychle přes cache

## Operations jsou hotové když:
- máš dashboardy
- máš alerty
- vidíš worker backlog
- umíš dohledat request trace
- pád Redis neshodí službu
- pád jednoho workeru nezastaví ingest

---

# 9. Jedna doporučená výsledná infra topologie

```text
[Frontend / API]
      |
      v
[FastAPI backend]
      |
      +-------------------+
      |                   |
      v                   v
 [Redis]              [Qdrant]
      |
      v
[Celery broker/backend]
      |
      +------------------+------------------+
      |                  |                  |
      v                  v                  v
[worker-ingest]   [worker-case]     [worker-reindex]
      |
      v
   [Flower]

Monitoring side:
[Prometheus] -> [Grafana]
[OpenTelemetry] -> [Trace backend]
[Logs JSON] -> [Loki/ELK]
```

---

# 10. Finální doporučení

## Co ano hned
- nová RU branch
- parser + structure-first ingest
- exact lookup jako první produkční milestone
- Prometheus od začátku
- Celery jen na dlouhé joby
- Flower jako operátorské UI

## Co ne hned
- neřešit Temporal teď
- nedávat agentiku dřív než stabilní retrieval
- nedávat LLM do ingest parseru jako hlavní logiku
- nepouštět strategy engine bez factual case layer

---

# 11. Jedna věta jako hlavní princip

**Nejdřív postav spolehlivý, měřitelný a auditovatelný retrieval + processing engine; teprve potom nad něj vrstvi právní reasoning, strategii a agentní orchestrace.**

