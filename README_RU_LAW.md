# Russian Legal System — Implementation Log

This file is the authoritative, continuously updated implementation journal for the Russian jurisdiction branch of the AI Legal System.

All milestones, corpus findings, design decisions, approved specs, and implementation outcomes are recorded here as work progresses.

---

## Project metadata

| Item | Value |
|------|-------|
| Branch | `feature/russia-law-ingestion` (to be created) |
| Working directory | `backend/app/modules/russia/` |
| Corpus directory | `Ruske_zakony/` |
| Primary collection | `russian_laws_v1` (Qdrant) |
| IDF checkpoint | `backend/storage/idf_russian_laws_v1.json` (Milestone 2) |
| Dense dim | 384 (read from `embedding_service.dimension` at runtime) |
| Status | **Milestone 1 — approved with 4 corrections, ready to code** |

---

## Phase 0 — Corpus Inspection (COMPLETED 2026-04-12)

### Files available

**Root directory (`Ruske_zakony/`)**

| File | Law | Code |
|------|-----|------|
| `Гражданский кодекс РФ (часть первая) ...u.txt` | Civil Code Part 1 | ГК РФ ч.1 |
| `Гражданский кодекс РФ (часть вторая) ...u.txt` | Civil Code Part 2 | ГК РФ ч.2 |
| `Гражданский кодекс РФ (часть третья) ...u.txt` | Civil Code Part 3 | ГК РФ ч.3 |
| `Гражданский кодекс РФ (часть четвертая) ...u.txt` | Civil Code Part 4 | ГК РФ ч.4 |
| `Гражданский процессуальный кодекс РФ ...u.txt` | Civil Procedure Code | ГПК РФ |
| `Семейный кодекс РФ ...u.txt` | Family Code | СК РФ |

**Subdirectory (`rest_of_the_codex_russia/`)**

| File | Law | Code |
|------|-----|------|
| `Арбитражный процессуальный кодекс РФ ...u.txt` | Arbitration Procedure Code | АПК РФ |
| `Бюджетный кодекс РФ ...u.txt` | Budget Code | БК РФ |
| `Водный кодекс РФ ...u.txt` | Water Code | ВК РФ |
| `Воздушный кодекс РФ ...u.txt` | Air Code | ВзК РФ |
| `Градостроительный кодекс РФ ...u.txt` | Urban Planning Code | ГрК РФ |
| `Жилищный кодекс РФ ...u.txt` | Housing Code | ЖК РФ |
| `Земельный кодекс РФ ...u.txt` | Land Code | ЗК РФ |
| `Кодекс РФ об административных правонарушениях ...u.txt` | Code of Admin Offences | КоАП РФ |
| `Кодекс административного судопроизводства РФ ...u.txt` | Administrative Procedure Code | КАС РФ |
| `Конституция РФ ...u.txt` | Constitution | Конституция |
| `Налоговый кодекс РФ (часть первая) ...u.txt` | Tax Code Part 1 | НК РФ ч.1 |
| `Налоговый кодекс РФ (часть вторая) ...u.txt` | Tax Code Part 2 | НК РФ ч.2 |
| `Трудовой кодекс РФ ...u.txt` | Labour Code | ТК РФ |
| `Уголовный кодекс РФ ...u.txt` | Criminal Code | УК РФ |
| `Уголовно-процессуальный кодекс РФ ...u.txt` | Criminal Procedure Code | УПК РФ |
| `Уголовно-исполнительный кодекс РФ ...u.txt` | Penal Code | УИК РФ |
| `Таможенный кодекс ЕАЭС ...u.txt` | Customs Code EAEU | ТК ЕАЭС |
| `Федеральный закон от 28.04.2023 N 138-ФЗ ...u.txt` | Federal Law 138-FZ | ФЗ-138 |

**Subdirectory `opeka/`**

- `Федеральный закон от 24.04.2008 N 48-ФЗ` — Guardianship Law
- `Конвенция о защите прав человека` — ECHR

**Subdirectory `cizinec_v_rusku/`**

- `Федеральный закон от 25.07.2002 N 115-ФЗ` — Law on Foreigners

### Encoding

- **Format**: UTF-16 LE with BOM (`FF FE`)
- **Line endings**: CRLF (`0D 00 0A 00` in UTF-16)
- **Python read**: `open(path, encoding='utf-16')` — BOM handled automatically
- **Terminal display**: UTF-16 does not render in PowerShell/cmd — always read via Python

### Structure (verified on СК, ТК, ГК ч.1)

```
[file header — KonsultantPlus metadata, ~40 lines]
Раздел I. НАЗВАНИЕ              ← optional, roman numeral
  Глава N. НАЗВАНИЕ             ← arabic numeral
    Статья N. Название          ← PRIMARY UNIT — exact lookup target
      [unnumbered text]         ← intro paragraph (part_num = None)
      1. Text                   ← numbered part
      2. Text
         1) Text                ← пункт (nested list item)
         2) Text
            а) Text             ← подпункт (letter item, rare)
```

### Article statistics

| Law | Lines | Статьи | Главы | Разделы | КонсультантПлюс notes |
|-----|-------|--------|-------|---------|----------------------|
| СК РФ | 1,488 | 173 | 22 | 8 | 21 |
| ТК РФ | 6,222 | 538 | 69 | 13 | 53 |
| ГК РФ ч.1 | 6,046 | 591 | 32 | 3 | 103 |

### Edge cases confirmed

1. **Decimal article numbers**: `Статья 19.1.`, `Статья 22.1.`, `Статья 22.2.` — common in ТК (20+ occurrences)
2. **Tombstone articles**: `Статья 7. Утратила силу. - Федеральный закон от 30.06.2006 N 90-ФЗ.` — must be indexed as tombstones, not skipped
3. **Short articles**: some статьи have 1–3 lines → stay as single chunk
4. **Long articles**: ст. 81 ТК = ~50 lines → split by numbered parts
5. **Часть as annotation**: `"Часть вторая утратила силу."` — NOT a structural level, just a note within article text

### Noise patterns confirmed

| Pattern | Example | Action |
|---------|---------|--------|
| `(в ред. Федерального закона от ...)` | `(в ред. ... от 30.06.2006 N 90-ФЗ)` | strip |
| `(п. X в ред. ...)` | `(п. 3 в ред. ... N 90-ФЗ)` | strip |
| `(пп. "X" в ред. ...)` | `(пп. "б" в ред. ...)` | strip |
| `(часть N введена ...)` | `(часть вторая введена ...)` | strip |
| `(часть N в ред. ...)` | `(часть шестая в ред. ...)` | strip |
| `КонсультантПлюс: примечание.` | — | strip this line AND next line |
| `Позиции высших судов по ст. N >>>` | — | strip |
| File header (lines until first Раздел/Глава/Статья) | title, date, consultant.ru, amendment list | skip entire header block |
| `(введен Федеральным законом ...)` | `(п. 7.1 введен ...)` | strip |

---

## Milestone 1 — Proposal (2026-04-12)

**Status**: PROPOSED — awaiting coding approval

### Objective

Parse Семейный кодекс, Трудовой кодекс, and Гражданский кодекс ч.1 into structured chunks, write them to `russian_laws_v1` Qdrant collection, and verify that `ст. N ТК РФ` / `статья N СК РФ` exact lookup returns the correct article text as top-1.

This milestone proves:
- parser correctly extracts all articles, handles edge cases, removes noise
- chunks are deterministic and idempotent
- Qdrant collection is isolated from Czech data
- exact article lookup works end-to-end without LLM

### Scope

- Семейный кодекс РФ (`local:ru/sk`)
- Трудовой кодекс РФ (`local:ru/tk`)
- Гражданский кодекс РФ ч.1 (`local:ru/gk/1`)

### Deliverables

#### New files — ingestion

| File | Purpose |
|------|---------|
| `modules/russia/ingestion/schemas.py` | Dataclasses: `RussianArticle`, `RussianArticlePart`, `RussianChunk`, `ParseResult`, `IngestReport` |
| `modules/russia/ingestion/loader.py` | Read UTF-16 file, extract law metadata from header, yield raw text |
| `modules/russia/ingestion/parser.py` | State machine: header skip → статья extraction → noise strip → part split |
| `modules/russia/ingestion/chunk_builder.py` | Build `RussianChunk` with deterministic uuid5 IDs from `RussianArticle` |
| `modules/russia/ingestion/embedder.py` | Dense embedding (gte-multilingual-base) + BM25 sparse encoding, write `idf_russian_laws_v1.json` |
| `modules/russia/ingestion/qdrant_writer.py` | Upsert chunks to `russian_laws_v1`, validate payload before write |
| `modules/russia/ingestion/cli.py` | CLI: `python -m app.modules.russia.ingestion.cli ingest --source СК ТК ГК1` |

#### New files — retrieval (exact lookup only)

| File | Purpose |
|------|---------|
| `modules/russia/retrieval/schemas.py` | `QueryUnderstanding`, `RetrievalPlan`, `EvidencePack` for Russian |
| `modules/russia/retrieval/query_analyzer.py` | Law alias map + `статья N` / `ст. N` / `ч. Y ст. X` regex, exact_lookup mode only |
| `modules/russia/retrieval/dense_retriever.py` | Qdrant scroll on `russian_laws_v1` filtered by `law_id` + `article_num`, sorted by `chunk_index` |
| `modules/russia/retrieval/evidence_validator.py` | Exact hit gate: 0 chunks → deterministic fallback, no LLM |
| `modules/russia/retrieval/adapter.py` | Bridge to generic `RetrievalService` interface |
| `modules/russia/retrieval/service.py` | Pipeline: analyze → plan → retrieve → validate |

#### Test files

| File | Purpose |
|------|---------|
| `tests/russia/test_parser.py` | Parser unit tests |
| `tests/russia/test_chunk_builder.py` | Chunk ID determinism tests |
| `tests/russia/test_qdrant_writer.py` | Collection isolation + write tests |
| `tests/russia/test_exact_lookup.py` | End-to-end exact lookup smoke tests |

#### NOT in Milestone 1

- Sparse retriever (BM25 at query time) — Milestone 2
- Topic/domain retrieval — Milestone 2
- `reranker.py` — Milestone 2
- `fusion.py` — Milestone 2
- `ambiguity_handler.py` — Milestone 2
- Celery jobs — Phase 5
- Strategy engine — Phase 8

---

### Parser Design

#### `loader.py`

```
load_law_file(path: str) -> tuple[LawMetadata, str]

1. Open with encoding='utf-16'
2. Read full text
3. Extract LawMetadata from first ~50 lines:
   - law_title: first quoted title line e.g. "Семейный кодекс Российской Федерации"
   - law_number: regex N NNN-ФЗ from header
   - law_date: regex from NN.NN.NNNN in header
   - source_file: basename(path)
   - ingest_timestamp: datetime.utcnow().isoformat()
4. Return (metadata, full_text)
```

Law ID derivation (static map based on filename pattern):

| Filename contains | law_id |
|-------------------|--------|
| `Семейный кодекс` | `local:ru/sk` |
| `Трудовой кодекс` | `local:ru/tk` |
| `Гражданский кодекс.*часть первая` | `local:ru/gk/1` |
| `Гражданский кодекс.*часть вторая` | `local:ru/gk/2` |
| `Гражданский кодекс.*часть третья` | `local:ru/gk/3` |
| `Гражданский кодекс.*часть четвертая` | `local:ru/gk/4` |
| `Гражданский процессуальный кодекс` | `local:ru/gpk` |
| `Уголовный кодекс` | `local:ru/uk` |
| `Уголовно-процессуальный кодекс` | `local:ru/upk` |
| `Налоговый кодекс.*часть первая` | `local:ru/nk/1` |
| `Налоговый кодекс.*часть вторая` | `local:ru/nk/2` |
| `Арбитражный процессуальный кодекс` | `local:ru/apk` |
| `Жилищный кодекс` | `local:ru/zhk` |
| `Конституция` | `local:ru/konst` |

#### `parser.py` — State Machine

**States**:

```
HEADER      initial state — skip until first structural marker
IN_SECTION  after Раздел marker — record current раздел label
IN_CHAPTER  after Глава marker — record current глава label
IN_ARTICLE  after Статья marker — accumulate article lines
```

**State transitions**:

```
HEADER      → IN_SECTION  : line matches RAZDEL_RE
HEADER      → IN_CHAPTER  : line matches GLAVA_RE
HEADER      → IN_ARTICLE  : line matches STATYA_RE

IN_SECTION  → IN_CHAPTER  : line matches GLAVA_RE
IN_SECTION  → IN_ARTICLE  : line matches STATYA_RE (no chapter)
IN_CHAPTER  → IN_CHAPTER  : new GLAVA_RE (update current_glava)
IN_CHAPTER  → IN_SECTION  : new RAZDEL_RE (update current_razdel, reset current_glava)
IN_CHAPTER  → IN_ARTICLE  : line matches STATYA_RE

IN_ARTICLE  → IN_ARTICLE  : new STATYA_RE → flush current article, start new
IN_ARTICLE  → IN_CHAPTER  : GLAVA_RE → flush current article, update chapter
IN_ARTICLE  → IN_SECTION  : RAZDEL_RE → flush current article, update section
```

**Marker regexes** (compiled at module level):

```python
RAZDEL_RE = re.compile(r'^Раздел\s+[IVXLCDM]+\.', re.UNICODE)
GLAVA_RE  = re.compile(r'^Глава\s+\d+[\d.]*\.', re.UNICODE)
STATYA_RE = re.compile(r'^Статья\s+(\d+(?:\.\d+)?)\.?\s*(.*)', re.UNICODE)
# Group 1: article number (e.g. "81" or "19.1")
# Group 2: article heading (may be empty or "Утратила силу...")
```

**Two-pass line processing — Correction 4 applied**

Lines in article body are processed in strict order:

```
line → PASS 1: noise_filter() → if dropped: discard
              → if kept: PASS 2: tombstone_detector() → set flag if matched
              → accumulate
```

This guarantees that `(в ред. ... утратил силу ...)` inside a parenthetical annotation is dropped in Pass 1 and never reaches the tombstone detector.

**Pass 1 — Editor-only noise: DROP unconditionally**

All КонсультантПлюс editorial annotations. Zero legal content. Safe to remove.

```python
# Category A — editor noise patterns (all parenthetical change-tracking or distributor metadata)
NOISE_PATTERNS = [
    re.compile(r'^\(в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(п\.\s+[\d.]+\s+в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(пп\.\s+"[а-яёА-ЯЁ]"\s+в\s+ред\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(часть\s+\w+\s+(введена|в\s+ред)\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^\(введен\w*\s+Федеральным', re.UNICODE | re.IGNORECASE),
    re.compile(r'^КонсультантПлюс:\s+примечание', re.UNICODE | re.IGNORECASE),
    re.compile(r'^Позиции\s+высших\s+судов\s+по\s+ст\.', re.UNICODE | re.IGNORECASE),
    re.compile(r'^Документ\s+предоставлен\s+КонсультантПлюс', re.UNICODE | re.IGNORECASE),
    re.compile(r'^www\.consultant\.ru', re.UNICODE | re.IGNORECASE),
    re.compile(r'^Дата\s+сохранения:', re.UNICODE | re.IGNORECASE),
]
```

Special case: `КонсультантПлюс: примечание.` is always followed by an editorial note on the NEXT line. Implement with a `_skip_next: bool` flag in the accumulation loop — set to `True` when the `примечание` pattern matches, and clear after the next line is discarded.

**Pass 2 — Legally meaningful status: PRESERVE as tombstone**

These are part of the official text of the law. Applied only to lines that survived Pass 1.

```python
# Category B — legal status content (official text, not editor annotation)
TOMBSTONE_RE = re.compile(r'[Уу]тратил[аи]?\s+силу', re.UNICODE)
```

Applied to:
- article heading (the text extracted from `STATYA_RE` group 2)
- any line accumulated into article body

If matched → `article.is_tombstone = True`. The article is still fully included in parse output and written to Qdrant with `source_type="tombstone"`. Never silently discarded.

#### Part splitting

After noise removal, article raw text is split into parts:

**Part detection**:

```python
NUMBERED_PART_RE = re.compile(r'^(\d+)\.\s+(.+)', re.UNICODE)
# Matches "1. Text", "2. Text" — numbered parts (часть)
# Does NOT match "1) Text" (пункты — stay inside the parent part text)
```

**Splitting rules**:

```
rule 1: If clean_text length <= 700 chars → 1 chunk (no splitting)
rule 2: If article has numbered parts (1. 2. 3.) and clean_text > 700 chars:
         → split at NUMBERED_PART_RE boundaries
         → part 0: all text before first numbered part (intro), may be empty
         → part N: text starting at "N. " up to next "N+1. " or end
rule 3: Tombstone article → always 1 chunk regardless of length
```

Пункты (`1) 2) 3)`) and подпункты (`а) б) в)`) are **not** split boundaries — they stay within their parent part chunk. This keeps related list items together.

---

### Data Schemas

#### `RussianArticlePart`

```python
@dataclass
class RussianArticlePart:
    part_num: int | None       # 1, 2, 3 or None for intro/unnumbered
    text: str                  # clean text of this part (noise removed)
    is_intro: bool             # True if part_num is None and precedes numbered parts
```

#### `RussianArticle`

```python
@dataclass
class RussianArticle:
    law_id: str                # "local:ru/tk"
    article_num: str           # "81" or "19.1" — always string to handle decimals
    heading: str               # "Расторжение трудового договора по инициативе работодателя"
    razdel: str | None         # "I. ОБЩИЕ ПОЛОЖЕНИЯ"
    glava: str                 # "Глава 3. ..." — required, empty string if missing
    parts: list[RussianArticlePart]
    raw_text: str              # full article text after noise removal, before part split
    is_tombstone: bool         # True if article has been repealed
    source_file: str           # basename of source file
    parse_errors: list[str]    # any warnings encountered during parsing
```

#### `ParseResult`

```python
@dataclass
class ParseResult:
    law_id: str
    law_title: str
    law_number: str | None     # "223-ФЗ"
    law_date: str | None       # "29.12.1995"
    source_file: str
    articles: list[RussianArticle]
    article_count: int
    tombstone_count: int
    parse_error_count: int
    parse_errors: list[str]
```

#### `RussianChunk` (Qdrant payload)

```python
@dataclass
class RussianChunk:
    chunk_id: str              # deterministic uuid5
    law_id: str                # "local:ru/tk"
    law_title: str             # "Трудовой кодекс Российской Федерации"
    law_short: str             # "ТК РФ"
    article_num: str           # "81"
    article_heading: str       # "Расторжение трудового договора..."
    part_num: int | None       # 2 or None
    razdel: str | None
    glava: str
    text: str                  # chunk text
    chunk_index: int           # 0-based position within article (== part_position in M1)
    fragment_id: str           # "{law_id}/{article_position:06d}/{chunk_index:04d}" — lexsortable
    source_type: str           # "law_article" or "tombstone"
    source_file: str
    ingest_timestamp: str
    is_tombstone: bool
```

**Chunk ID derivation** (deterministic, Correction 3 applied):

```python
chunk_id = str(uuid.uuid5(
    uuid.NAMESPACE_URL,
    f"{law_id}/{article_num}/{part_num or 0}/{chunk_index}"
))
```

Same strategy as Czech pipeline — deterministic, idempotent on re-ingest.

**fragment_id and chunk_index derivation** (Correction 3 — explicit counter rule):

```
article_position  assigned by parser's _article_seq counter
                  incremented only at flush_article() call, strictly sequential
                  source order = file order = deterministic

part_position     assigned by enumerate() over parts list in _split_parts()
                  parts list is built top-to-bottom as lines appear in file
                  0 = intro/unnumbered text before first "1."
                  1 = first numbered part "1."
                  2 = second numbered part "2.", etc.

chunk_index       == part_position in Milestone 1 (one chunk per part)
                  If future milestones further split a part, chunk_index
                  increments within the part; part_position stays fixed.

fragment_id       = f"{law_id}/{article_position:06d}/{chunk_index:04d}"
                  Example: "local:ru/tk/000080/0000"
                  Zero-padded so lexicographic sort == numeric sort
                  Sorting by fragment_id ASC gives correct display order
```

**Ordering guarantee**: Re-ingest of the same file always produces the same `fragment_id` and `chunk_index` because:
- file is read sequentially (no parallel parsing)
- `_article_seq` is incremented only at explicit flush points
- `_split_parts()` uses `enumerate()` over an ordered list — no dict traversal

#### `IngestReport`

```python
@dataclass
class IngestReport:
    law_id: str
    source_file: str
    articles_parsed: int
    chunks_written: int
    tombstones: int
    errors: list[str]
    duration_seconds: float
    ingest_timestamp: str
```

---

### Qdrant Design

#### Collection: `russian_laws_v1`

```python
# Vector config — Correction 1: dim derived from runtime, not hardcoded
# qdrant_writer receives embedding_service as dependency
dim = embedding_service.dimension  # 384 as of current config; will adapt if provider changes

vectors_config = {
    "dense": VectorParams(size=dim, distance=Distance.COSINE),
    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
    # sparse vectors written as empty lists in M1 — schema ready for M2 BM25
    # no collection rebuild needed when M2 adds sparse population
}
```

**Dense dim — runtime verified**: `embedding_service.dimension = 384`, confirmed by:
- `profile.dimension = 384`
- actual `embed_documents(["test"])` output: `len(vector) = 384`
- `czech_laws_v2` collection: `vector=dense: size=384`

The Qdrant writer must accept `embedding_service: EmbeddingService` as a parameter and read `.dimension` from it. Hard-coding `768` or any other value is not permitted.

**Sparse in M1 — Correction 2**: Collection schema includes the `sparse` vector config so that M2 (BM25) does not require a collection rebuild or re-ingest. Points are upserted with empty sparse vectors in M1. `qdrant_writer.py` must not import or construct any BM25 encoder in M1.

#### Payload index (create at collection init)

```python
# Fields that will be filtered in exact lookup
create_payload_index("law_id",       PayloadSchemaType.KEYWORD)
create_payload_index("article_num",  PayloadSchemaType.KEYWORD)
create_payload_index("is_tombstone", PayloadSchemaType.BOOL)
create_payload_index("source_type",  PayloadSchemaType.KEYWORD)
create_payload_index("chunk_index",  PayloadSchemaType.INTEGER)
```

#### Fields indexed NOW (Milestone 1)

- `law_id`, `article_num`, `chunk_index`, `is_tombstone`, `source_type`

#### Fields NOT indexed yet (wait for Milestone 2)

- `razdel`, `glava`, `article_heading` — needed for topic retrieval but not for exact lookup filtering

#### Write strategy

- `upsert` with deterministic point IDs (uuid5 → uuid as string)
- Validate before write: `chunk.text` must be non-empty; `chunk.law_id` must be set; `chunk.chunk_id` must be valid UUID
- Write in batches of 100
- Assert target collection = `russian_laws_v1` before first write (hard check, raises on mismatch)

---

### Exact Lookup Retrieval Design (Milestone 1 scope only)

#### `query_analyzer.py` — Milestone 1 subset

Handles only `exact_lookup` mode. Topic/domain routing is Milestone 2.

**Law alias map** (static, hardcoded):

```python
_LAW_ALIASES = {
    "тк рф": "local:ru/tk",
    "трудовой кодекс": "local:ru/tk",
    "ск рф": "local:ru/sk",
    "семейный кодекс": "local:ru/sk",
    "гк рф": "local:ru/gk/1",    # default to part 1 if unspecified
    "гражданский кодекс": "local:ru/gk/1",
    # expanded in Milestone 2
}
```

**Article reference regexes**:

```python
# "статья 81", "статья 19.1"
STATYA_RE = re.compile(r'статья\s+(\d+(?:\.\d+)?)', re.IGNORECASE | re.UNICODE)

# "ст. 81", "ст.81"
ST_SHORT_RE = re.compile(r'ст\.\s*(\d+(?:\.\d+)?)', re.IGNORECASE | re.UNICODE)

# "ч. 2 ст. 81" — part + article
CHAST_ST_RE = re.compile(r'ч\.\s*(\d+)\s+ст\.\s*(\d+(?:\.\d+)?)', re.IGNORECASE | re.UNICODE)
```

**Output**: `QueryUnderstanding` with `query_mode="exact_lookup"`, `law_id`, `article_num`, `part_num` (optional).

#### `dense_retriever.py` — exact mode only

```
1. Build Qdrant filter: must(law_id=X, article_num=Y)
2. Optional: if part_num detected, add must(part_num=Z)
3. Scroll all matching points (no vector search — payload filter only)
4. Sort by chunk_index ascending
5. Return list of payload dicts
```

No vector similarity search for exact lookup. Pure payload filter + sort. Same approach as Czech `dense_retriever.py` exact mode.

#### `evidence_validator.py` — exact gate

```
if len(chunks) == 0:
    return EvidencePack(items=[], fallback_reason="no_exact_hit")
    # caller must NOT invoke LLM
if all(chunk.is_tombstone for chunk in chunks):
    return EvidencePack(items=chunks, fallback_reason="tombstone_only")
    # return tombstone info, no LLM
return EvidencePack(items=chunks, fallback_reason=None)
```

---

### Test Plan

#### Step 1 — Parser unit tests (`test_parser.py`)

| Test | Input | Expected |
|------|-------|---------|
| `test_article_count_sk` | СК РФ file | articles == 173 |
| `test_article_count_tk` | ТК РФ file | articles == 538 |
| `test_article_count_gk1` | ГК РФ ч.1 file | articles == 591 |
| `test_article_81_heading` | ТК РФ | article_num="81", heading="Расторжение трудового договора по инициативе работодателя" |
| `test_article_1_sk` | СК РФ | article_num="1", heading="Основные начала семейного законодательства" |
| `test_decimal_article_191` | ТК РФ | article_num="19.1" is present |
| `test_tombstone_article_7` | ТК РФ | article_num="7", is_tombstone=True |
| `test_no_noise_in_text` | any file | no article text contains "(в ред." |
| `test_no_consultantplus_in_text` | any file | no article text contains "КонсультантПлюс" |
| `test_article_parts_split` | ТК ст.81 | len(parts) > 1 (has numbered parts) |
| `test_short_article_no_split` | СК ст.1 | len(parts) == 1 |

#### Step 2 — Chunk builder tests (`test_chunk_builder.py`)

| Test | Expected |
|------|---------|
| `test_chunk_id_is_valid_uuid` | all chunk_ids parse as UUID |
| `test_chunk_id_deterministic` | same input → same chunk_id on repeat call |
| `test_chunk_id_unique_within_article` | no duplicate chunk_ids within one article |
| `test_chunk_index_sequential` | chunk_index values are 0, 1, 2, ... |
| `test_tombstone_chunk_source_type` | is_tombstone=True → source_type="tombstone" |
| `test_text_not_empty` | all chunks have len(text) > 0 |
| `test_law_id_present` | all chunks have non-empty law_id |

#### Step 3 — Qdrant write tests (`test_qdrant_writer.py`)

| Test | Expected |
|------|---------|
| `test_collection_created` | `russian_laws_v1` collection exists after init |
| `test_collection_isolation` | `czech_laws_v2` unchanged after Russia ingest |
| `test_chunk_count_sk` | point count ≥ 173 (one chunk per article minimum) |
| `test_reingest_idempotent` | second ingest of same law → same point count, same IDs |
| `test_payload_fields_present` | every point has: chunk_id, law_id, article_num, text, chunk_index |
| `test_dense_vector_dim` | all dense vectors have dim=768 |
| `test_no_empty_text_in_qdrant` | no point has empty text field |

#### Step 4 — Exact lookup smoke tests (`test_exact_lookup.py`)

| Query | Expected |
|-------|---------|
| `статья 81 ТК РФ` | top-1 law_id="local:ru/tk", article_num="81", contains "расторжение" |
| `ст. 81 тк рф` | same result |
| `статья 1 СК РФ` | top-1 law_id="local:ru/sk", article_num="1" |
| `ст. 169 ГК РФ` | top-1 law_id="local:ru/gk/1", article_num="169" |
| `статья 7 ТК РФ` | result has is_tombstone=True, no LLM triggered |
| `статья 99999 ТК РФ` | empty result, fallback_reason="no_exact_hit", no LLM |
| `статья 22 СК РФ` | top-1 article_num="22", multiple parts returned in order |

---

### Failure Gates

These conditions **block** moving to Milestone 2. All must pass.

| Gate | Condition | Action if failed |
|------|-----------|-----------------|
| **Parse completeness** | article_count matches expected (±2%) for each law | Fix parser, rerun |
| **No noise in text** | Zero chunks contain `(в ред.` or `КонсультантПлюс` | Fix noise filter |
| **No empty text** | Zero chunks have `len(text) == 0` | Fix part splitter |
| **law_id always set** | Zero chunks have empty or None `law_id` | Fix chunk_builder |
| **ID determinism** | Re-ingest produces identical chunk IDs | Fix uuid5 inputs |
| **Collection isolation** | `czech_laws_v2` point count unchanged after Russia ingest | Fix collection name assertion |
| **Tombstone indexed** | `статья 7 ТК РФ` returns tombstone chunk, not 404 | Fix tombstone handling |
| **Exact lookup top-1 correct** | All 7 smoke queries return expected article | Fix query_analyzer or retriever |
| **LLM never invoked on exact hit** | No LLM calls in logs for any exact lookup query | Fix evidence_validator gate |

---

### Implementation Boundary

#### Milestone 1 scope

- `ingestion/schemas.py`
- `ingestion/loader.py`
- `ingestion/parser.py`
- `ingestion/chunk_builder.py`
- `ingestion/embedder.py`
- `ingestion/qdrant_writer.py`
- `ingestion/cli.py`
- `retrieval/schemas.py` (exact_lookup only)
- `retrieval/query_analyzer.py` (law aliases + article regex only)
- `retrieval/dense_retriever.py` (payload filter + sort, no vector search)
- `retrieval/evidence_validator.py` (exact gate only)
- `retrieval/adapter.py`
- `retrieval/service.py` (exact mode only)
- All tests above

#### Explicitly deferred to Milestone 2

- `retrieval/sparse_retriever.py` (BM25 at query time)
- `retrieval/fusion.py` (RRF)
- `retrieval/reranker.py`
- `retrieval/ambiguity_handler.py`
- `retrieval/retrieval_planner.py` (topic/domain modes)
- Topic keyword expansion map
- Domain taxonomy (семейное право, трудовое право, ...)
- Cross-encoder reranker integration
- Celery ingestion jobs
- Prometheus metrics for Russia path

---

## Milestone 2 — Placeholder (not yet designed)

Topic and domain retrieval. Will be designed after Milestone 1 gates pass.

Planned scope:
- Sparse retriever + RRF fusion
- Domain taxonomy (family law, employment, criminal, civil, procedural)
- Query expansion map for Russian legal terms
- Topic heading boost
- Reranker integration
- Ambiguity handler (bare `статья 81` without law name)

---

## Milestone 3 — Placeholder (not yet designed)

Judicature layer — court decisions ingestion and retrieval.

---

## Milestone 4 — Placeholder (not yet designed)

Case understanding system — client case file processing.

---

## Milestone 5 — Placeholder (not yet designed)

Strategy orchestration — LangGraph parallel retrieval + synthesis.

---

## Step Log

---

## Step 0 — Corpus inspection and Milestone 1 design

**Status:** VERIFIED

### Objective

Inspect the actual Russian law files before writing any code to confirm encoding, structure consistency, edge cases, and noise patterns. Produce a concrete, corrected Milestone 1 design that can go directly into implementation.

### Scope

**In scope:**
- Byte-level inspection of file encoding
- Structure analysis: hierarchy levels, article numbering, part patterns
- Edge case enumeration: decimal article numbers, tombstones, noise types
- Statistical summary across СК, ТК, ГК ч.1
- Full Milestone 1 design: schemas, parser state machine, chunk strategy, Qdrant setup, test plan, failure gates
- 4 design corrections requested and applied before approval

**Out of scope:**
- No code written
- No branch created
- No Qdrant collection created
- No embedding tested against Russian text

### Files changed

| File | Change |
|------|--------|
| `README_RU_LAW.md` | Created — full corpus inspection findings + Milestone 1 design + 4 corrections |

### Implementation details

**Encoding confirmed**: UTF-16 LE with BOM (`FF FE`). Python `open(path, encoding='utf-16')` handles BOM automatically. Files are not valid UTF-8. PowerShell cannot display Cyrillic from these files — all reading must go through Python.

**Structure confirmed** (consistent across all 3 inspected files):

```
Раздел → Глава → Статья → numbered parts (1. 2. 3.) → пункты (1) 2)) → подпункты (а) б))
```

**Статья is the correct primary chunk unit.** Users query by article (`ст. 81 ТК РФ`), not by глава or раздел.

**Edge cases confirmed by direct inspection:**
- Decimal article numbers (`Статья 19.1.`, `Статья 22.1.`) — 20+ occurrences in ТК РФ alone
- Tombstone articles (`Статья 7. Утратила силу. - Федеральный закон от 30.06.2006 N 90-ФЗ.`) — confirmed in ТК
- Tombstones with date (`Статья 175. Утратила силу с 1 сентября 2013 года.`) — confirmed in ТК
- `Часть вторая утратила силу.` as part-level tombstone within an article
- КонсультантПлюс editor note always on its own line, followed by note text on next line
- `Позиции высших судов по ст. N ГК РФ >>>` — UI element injected between articles

**Statistical summary verified:**

| Law | Lines | Статьи | Главы | Разделы | КонсультантПлюс notes |
|-----|-------|--------|-------|---------|----------------------|
| СК РФ | 1,488 | 173 | 22 | 8 | 21 |
| ТК РФ | 6,222 | 538 | 69 | 13 | 53 |
| ГК РФ ч.1 | 6,046 | 591 | 32 | 3 | 103 |

**4 design corrections applied:**

1. Dense dim: confirmed 384 from `embedding_service.dimension`, `czech_laws_v2` schema, and `embed_documents()` output. Original proposal incorrectly stated 768. `qdrant_writer.py` must read dim from `EmbeddingService` at runtime.
2. Sparse/BM25 removed from M1. Qdrant collection schema includes sparse slot (avoids rebuild in M2) but all M1 points written with empty sparse vectors. No BM25 encoder in M1.
3. Fragment ordering made deterministic: `fragment_id = "{law_id}/{article_position:06d}/{chunk_index:04d}"`. `article_position` from explicit `_article_seq` counter incremented only at `flush_article()`. `chunk_index` from `enumerate()` over ordered parts list. No dict traversal.
4. Noise vs legal-status strictly separated: Pass 1 (9 NOISE_PATTERNS) drops КонсультантПлюс annotations. Pass 2 (TOMBSTONE_RE) runs only on lines that survived Pass 1. `(в ред. ... утратил силу)` in parenthetical annotations is dropped in Pass 1, never reaches tombstone detector.

### Verification

- `docker exec ai-legal-backend python3 -c "open('/tmp/sk.txt', encoding='utf-16')"` → СК РФ readable, Cyrillic renders correctly
- Article count scan СК: 173 статьи found ✓
- Article count scan ТК: 538 статьи found ✓
- Article count scan ГК ч.1: 591 статьи found ✓
- Decimal article search ТК: 20+ hits for `Статья \d+\.\d+` ✓
- Tombstone search ТК: `Статья 7. Утратила силу.` confirmed at L222 ✓
- Tombstone with date ТК: `Статья 175. Утратила силу с 1 сентября 2013 года.` confirmed ✓
- `embedding_service.dimension` → 384 ✓
- `embed_documents(["test"])` output length → 384 ✓
- `czech_laws_v2` Qdrant vector size → 384 ✓
- КонсультантПлюс note + next-line pattern confirmed in СК ст.15 (L155–L156) ✓

### Failures / issues

- One stale entry in the Decisions Log: `"Dense model: gte-multilingual-base (768 dim)"` — recorded before runtime check, contradicts confirmed 384. Fixed in same commit.
- GK part 2/3/4 and remaining codices not yet inspected individually. Assumed structure is consistent with ГК ч.1 based on same КонсультантПлюс formatting. Must verify during ingest — parser parse_errors[] will surface any deviation.
- `Федеральный закон` files in `opeka/` and `cizinec_v_rusku/` subdirectories not inspected. Their law ID mapping is not yet defined. Deferred — not in M1 scope.

### Decision

**Step accepted.**

Corpus structure is confirmed consistent across 3 representative files. All 4 design corrections are locked in. The design is concrete enough to begin implementation without further research.

### Next recommended step

Create branch `feature/russia-law-ingestion`, then implement `modules/russia/ingestion/schemas.py` — the dataclasses (`RussianArticlePart`, `RussianArticle`, `ParseResult`, `RussianChunk`, `IngestReport`) that all subsequent ingestion modules depend on.

### Milestone status

**In progress** — Step 1 complete (schemas + loader + parser, 29/29 tests passing).

### Design changes

- **Old assumption**: Dense dim = 768 (from memory, `gte-multilingual-base` described as 768-dim in some docs)
- **New confirmed reality**: Dense dim = 384 (runtime-verified: `embedding_service.dimension`, actual vector output, `czech_laws_v2` Qdrant schema)
- **Reason**: The project uses the `hash` embedding provider by default which produces 384-dim vectors; `gte-multilingual-base` in full sentence-transformer mode produces 768 but that is not the active provider

---

## Step 1 — schemas.py + loader.py + parser.py

**Status:** VERIFIED

### Objective

Implement the three foundational ingestion modules that convert raw KonsultantPlus UTF-16 files into structured `ParseResult` objects ready for the chunk builder.

### Scope

**In scope:**
- `schemas.py` — `LawMetadata`, `RussianArticlePart`, `RussianArticle`, `ParseResult` dataclasses
- `loader.py` — UTF-16 LE file reader, law_id derivation from filename, header metadata extraction
- `parser.py` — state-machine parser (HEADER→IN_SECTION→IN_CHAPTER→IN_ARTICLE), Pass 1 noise filter, Pass 2 tombstone detector, part splitter
- `tests/russia/test_parser.py` — 29 tests covering counts, headings, decimal articles, tombstones, noise removal, part splitting, ordering, metadata

**Out of scope:**
- chunk_builder.py (Step 2)
- embedder.py, qdrant_writer.py (Step 3)

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/ingestion/schemas.py` | Created — parsing dataclasses |
| `backend/app/modules/russia/ingestion/loader.py` | Created — UTF-16 loader + law_id map |
| `backend/app/modules/russia/ingestion/parser.py` | Created — state-machine parser |
| `backend/tests/russia/test_parser.py` | Created — 29 parser tests |

### Implementation details

**Three bugs found and fixed during test run:**

1. **Empty tombstone text** — Articles like ст.7 ТК РФ declare repeal only in the heading line (`Статья 7. Утратила силу. - ...`), leaving `raw_text=""`. Fixed: when `is_tombstone=True` and `raw_text` is empty, use `heading` as the chunk content so Qdrant always receives non-empty text.

2. **False tombstone on пункт list items** — ст.81 ТК РФ contains `12) утратил силу.` inside a `1) 2) 3)` пункт list. Pass 2 was incorrectly flagging the entire article as tombstone. Fixed: skip tombstone detection when line matches `^\d+(?:\.\d+)?\)` (пункт format).

3. **Wrong article for split test** — ТК РФ uses `1) 2) 3)` пункты throughout (no `1. 2. 3.` части format). Test updated to use ГК РФ ч.1 which has 445+ articles with части format.

**Article counts verified:**

| Law | Expected | Got |
|-----|----------|-----|
| СК РФ | ~173 | 173 |
| ТК РФ | ~538 | 538 |
| ГК РФ ч.1 | ~591 | 591 |

**Test results:** 29/29 pass.

---

## Step 2 — chunk_builder.py

**Status:** VERIFIED

### Objective

Convert `ParseResult` objects from the parser into flat, ordered lists of `RussianChunk` objects ready for embedding and Qdrant ingestion. Establish deterministic chunk IDs.

### Scope

**In scope:**
- `RussianChunk` dataclass added to `schemas.py`
- `chunk_builder.py` — `build_chunks(result: ParseResult) -> list[RussianChunk]`
- `test_chunk_builder.py` — 23 tests

**Out of scope:**
- Embedding (Step 3)
- Qdrant writer (Step 3)
- BM25 / sparse vectors (Milestone 2)

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/ingestion/schemas.py` | Added `RussianChunk` dataclass |
| `backend/app/modules/russia/ingestion/chunk_builder.py` | Created — `build_chunks()` function |
| `backend/tests/russia/test_chunk_builder.py` | Created — 23 tests |

### Implementation details

**Design decisions locked during implementation:**

- `chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, fragment_id))` — fully deterministic, reruns produce identical UUIDs.
- `fragment_id = '{law_id}/{article_position:06d}/{chunk_index:04d}'` — lexsortable, encodes both article order and part order within article.
- `source_type = 'tombstone' | 'article'` — tombstone chunks remain retrievable, never discarded.
- Empty text assertion in `build_chunks()` — catches any future parser regression that produces empty parts immediately at build time.

**Bug found and fixed during test run:**

- **Fragment ID regex in test** — law_id `local:ru/gk/1` contains slashes; regex `^[^/]+/...` failed. Fixed to `^.+/\d{6}/\d{4}$`.
- **Multi-part grouping by article_num** — ст.123.7 appeared twice in ГК РФ ч.1 (GK1 genuinely has duplicate decimal article numbers from different amendments). Fixed: group by `fragment_id.rsplit("/", 1)[0]` (article_position prefix) instead of article_num.

**Chunk counts:**

| Law | Articles | Chunks | Multi-part articles |
|-----|----------|--------|---------------------|
| СК РФ | 173 | ≥173 | yes (>0) |
| ТК РФ | 538 | 538 | 0 (all пункты, not части) |
| ГК РФ ч.1 | 591 | >591 | ≥10 |

**Test results:** 23/23 pass. Total Russia tests: 52/52.

---

## Step 3 — embedder.py + qdrant_writer.py

**Status:** VERIFIED

### Objective

Implement dense embedding and Qdrant persistence for Russian law chunks. Create `russian_laws_v1` collection with correct schema (dense + sparse slot). Verify collection isolation from `czech_laws_v2`.

### Scope

**In scope:**
- `embedder.py` — `RussianLawEmbedder` wrapping `EmbeddingService`; `EmbeddedRussianChunk` dataclass
- `qdrant_writer.py` — `RussianLawQdrantWriter`: `ensure_collection()`, `upsert_batch()`, `count()`, `health_check()`
- `test_qdrant_writer.py` — 11 integration tests against live Qdrant

**Out of scope:**
- Retrieval (Step 4)
- BM25 / sparse retrieval (Milestone 2)
- Celery / background tasks

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/ingestion/embedder.py` | Created — `RussianLawEmbedder`, `EmbeddedRussianChunk` |
| `backend/app/modules/russia/ingestion/qdrant_writer.py` | Created — `RussianLawQdrantWriter`, collection `russian_laws_v1` |
| `backend/tests/russia/test_qdrant_writer.py` | Created — 11 integration tests |

### Implementation details

**Runtime embedding dimension: 384**

Confirmed at test time:
```
provider=hash  model=Alibaba-NLP/gte-multilingual-base  dim=384
```
Dimension is never hardcoded — `embedder.dimension` reads from `EmbeddingService.dimension` which reads from the active provider at runtime.

**Collection schema:**
- `dense`: COSINE, size=384 (from runtime)
- `sparse`: SparseVectorParams, on_disk=False — empty in M1, populated by Russian BM25 encoder in M2

**Chunk point ID:** `chunk_id` from `chunk_builder` (already UUID5) — no second UUID derivation needed.

**Empty-text guard:** `_to_point()` asserts `chunk.text.strip()` before constructing the PointStruct — catches any upstream regression immediately.

**Collection isolation:** `_assert_target_collection()` is a hard guard called at the start of every public method — raises `AssertionError` if `COLLECTION_NAME` has been changed.

**Test results:** 11/11 pass. Total Russia tests: 63/63.

---

## Step 4 — service.py + cli.py

**Status:** VERIFIED

### Objective

Wire the full ingestion pipeline into a callable orchestrator. Add file-level checkpoint support and a CLI for manual corpus runs.

### Scope

**In scope:**
- `service.py` — `ingest_law_file()`, `ingest_corpus()`, `FileIngestResult`, `IngestReport`
- `cli.py` — `--file` and `--corpus` modes, `--checkpoint`, `--no-checkpoint`, `--quiet`
- `test_service.py` — 16 orchestration tests

**Out of scope:**
- Retrieval (Step 5)
- Celery / background tasks
- Prometheus metrics

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/ingestion/service.py` | Created — orchestrator with checkpoint |
| `backend/app/modules/russia/ingestion/cli.py` | Created — `--file` / `--corpus` CLI |
| `backend/tests/russia/test_service.py` | Created — 16 orchestration tests |

### Implementation details

**Runtime embedding profile (recorded at Step 4):**

```
provider  = hash
model     = deterministic-hash-384
dim       = 384
revision  = deterministic_hash_v2
```

**Checkpoint format:**
```json
{
  "version": 1,
  "files": {
    "filename.txt": {
      "law_id": "local:ru/tk",
      "law_short": "ТК РФ",
      "chunks": 538,
      "ingested_at": "2026-04-12T..."
    }
  }
}
```
Written atomically (`.tmp` → rename). Key is basename, not full path — checkpoint is portable if the corpus is moved.

**File discovery order:** sorted by derived `law_id` — deterministic regardless of filesystem ordering.

**Unrecognized files:** law files whose filename does not match `_LAW_ID_MAP` (law_id starts with `local:ru/unknown/`) are counted in `IngestReport.files_unrecognized` and never checkpointed.

**Milestone corpus counts (all three laws):**

| Law | law_id | Articles | Tombstones | Chunks |
|-----|--------|----------|------------|--------|
| ГК РФ ч.1 | local:ru/gk/1 | 591 | ~11 | >591 |
| СК РФ | local:ru/sk | 173 | 0 | 173 |
| ТК РФ | local:ru/tk | 538 | 37 | 538 |

**Test results:** 16/16 pass. Total Russia tests: 79/79.

---

## Step 5 — exact_lookup.py + retrieval service

**Status:** VERIFIED

### Objective

Implement deterministic exact article lookup against `russian_laws_v1`. No vector search — pure payload filter + sort.

### Scope

**In scope:**
- `retrieval/schemas.py` — `RussianChunkResult`, `ArticleLookupResult`
- `retrieval/exact_lookup.py` — `RussianExactLookup.get_article(law_id, article_num, part_num=None)`
- `retrieval/service.py` — thin `RussianRetrievalService` wrapper (M1 only)
- `test_exact_lookup.py` — 27 tests

**Out of scope:**
- Dense / semantic search
- Topic retrieval
- BM25 query-time retrieval
- Ambiguity handling
- LLM integration

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/retrieval/schemas.py` | Created — `RussianChunkResult`, `ArticleLookupResult` |
| `backend/app/modules/russia/retrieval/exact_lookup.py` | Created — `RussianExactLookup` |
| `backend/app/modules/russia/retrieval/service.py` | Created — `RussianRetrievalService` (exact lookup only) |
| `backend/tests/russia/test_exact_lookup.py` | Created — 27 tests |

### Implementation details

**Retrieval strategy:** Qdrant scroll with payload filter (`law_id` + `article_num` + optional `part_num`), then sort results by `chunk_index` ASC in Python. No vector search, no embedding call at query time.

**Tombstone handling:** Tombstone articles are returned normally with `is_tombstone=True` and `source_type='tombstone'` — the caller decides how to present the repeal notice.

**No-hit contract:** Missing articles always return `ArticleLookupResult(hit=False, chunks=[], ...)` — never raise.

**Decimal article numbers:** Stored as strings in Qdrant (`"19.1"`), matched exactly via `MatchValue`. No float parsing needed.

**Test coverage:**
- ст.81 ТК РФ — active, correct heading, non-tombstone
- ст.1 СК РФ — active, correct heading  
- ст.169 ГК РФ ч.1 — active, has text
- ст.7 ТК РФ — tombstone flagged, source_type='tombstone', has text
- ст.9999 ТК РФ — nonexistent → no-hit, law_id preserved
- local:ru/uk ст.1 — unindexed law → no-hit
- Cross-law isolation — TK chunks not returned for SK query
- Ordering determinism — two identical calls return same chunk order
- chunk_index ascending with no gaps
- Optional part_num filter
- Decimal article ст.19.1 found
- Service wrapper matches direct lookup

**Test results:** 27/27 pass. Total Russia tests: 106/106.

---

## Step 6 — dense_retriever.py + service.py extension

**Status:** VERIFIED

### Objective

Implement semantic dense vector search against `russian_laws_v1`. Extend `RussianRetrievalService` with a `search()` method. Add `RussianSearchResult` schema.

### Scope

**In scope:**
- `retrieval/schemas.py` — `RussianSearchResult` dataclass added
- `retrieval/dense_retriever.py` — `RussianDenseRetriever.search(query, law_id, top_k)`
- `retrieval/service.py` — `search()` method added; constructor now takes `embedding_service`
- `test_dense_retriever.py` — 20 tests
- `test_exact_lookup.py` — service fixture updated for new constructor signature

**Out of scope:**
- BM25 query-time retrieval
- Query expansion / reranking
- Topic taxonomy
- Ambiguity handling
- LLM integration

### Files changed

| File | Change |
|------|--------|
| `backend/app/modules/russia/retrieval/schemas.py` | `RussianSearchResult` added |
| `backend/app/modules/russia/retrieval/dense_retriever.py` | Created — `RussianDenseRetriever` |
| `backend/app/modules/russia/retrieval/service.py` | `search()` added; constructor requires `embedding_service` |
| `backend/tests/russia/test_dense_retriever.py` | Created — 20 tests |
| `backend/tests/russia/test_exact_lookup.py` | Service fixture updated for new constructor |

### Implementation details

**Retrieval path:** `embed_query(query)` → `query_points(using="dense", query_filter=law_filter)` → sort by score (Qdrant returns descending by default) → map to `RussianSearchResult`.

**law_id filter:** Optional `MatchValue` filter on the `law_id` payload field. When `None`, all 2,508 ingested chunks are candidates.

**No LLM:** Verified structurally — `dense_retriever.py` imports only `EmbeddingService`, `QdrantClient`, and local schemas. Test `test_dense_search_does_not_import_llm` confirms this.

**Tombstone preservation:** `is_tombstone` and `source_type` are read directly from the Qdrant payload — tombstone chunks surface normally in search results with correct flags.

**Constructor change in service.py:** `RussianRetrievalService` now requires `embedding_service` as first argument (needed for dense search). Existing `test_exact_lookup.py` service fixture was updated accordingly.

**Test note:** `test_qdrant_writer` and `test_service` delete `russian_laws_v1` in their teardown. Dense retrieval tests require the collection to be pre-populated — run the M1 corpus ingest before running these tests in isolation.

**Test results:** 20/20 dense tests + 27/27 exact lookup tests = 47/47 pass.

---

---

## Step 7 — Sparse BM25 Retrieval + Hybrid RRF Fusion (VERIFIED 2026-04-12)

**Status**: ACCEPTED ✓

### What was built

| File | Role |
|------|------|
| `backend/app/modules/russia/ingestion/sparse_encoder.py` | `RussianBM25Encoder`, `IDFTable`, `IDFTableBuilder`, Cyrillic-native tokenizer |
| `backend/app/modules/russia/ingestion/embedder.py` | Extended with optional `bm25_encoder` param |
| `backend/app/modules/russia/ingestion/service.py` | Two-pass IDF build; `idf_checkpoint_path` param |
| `backend/app/modules/russia/ingestion/cli.py` | `--idf-checkpoint PATH` flag |
| `backend/app/modules/russia/retrieval/sparse_retriever.py` | `RussianSparseRetriever` — BM25 against `russian_laws_v1` |
| `backend/app/modules/russia/retrieval/fusion.py` | `reciprocal_rank_fusion()` — RRF over `list[RussianSearchResult]` |
| `backend/app/modules/russia/retrieval/service.py` | `sparse_search()` + `hybrid_search()` with RRF fallback |
| `backend/tests/russia/test_sparse_encoder.py` | 36 pure-Python unit tests |
| `backend/tests/russia/test_sparse_retriever.py` | 23 integration tests |

### IDF statistics (from corpus)

| Metric | Value |
|--------|-------|
| Documents (chunks) | 2,508 |
| Vocabulary (min_df=2) | 7,919 tokens |
| Average document length | 72.3 tokens |

### Tokenizer design

The Russian tokenizer uses a Cyrillic-native regex `[а-яё]{2,}` (min 2 chars) plus short numeric tokens `[0-9]{1,6}`. Latin characters are excluded. `ё` (U+0451) is explicitly included since it falls outside the contiguous а–я range. No external NLP dependencies.

### Re-ingestion command (required before running sparse tests)

```bash
python -m app.modules.russia.ingestion.cli \
  --corpus /app/Ruske_zakony \
  --no-checkpoint \
  --idf-checkpoint /app/storage/idf_russian_laws_v1.json \
  --quiet
```

### Test results

- **36/36** pure-Python unit tests (tokenizer, IDFTable, encoder, RRF)
- **23/23** integration tests (sparse search, law_id filter, hybrid fusion)
- **59/59 total** — all pass

---

## Step 8 — Law-Constrained Topic Retrieval (VERIFIED 2026-04-12)

**Status**: ACCEPTED ✓

### What was built

| File | Role |
|------|------|
| `backend/app/modules/russia/retrieval/query_analyzer.py` | `RussianQueryAnalyzer` — law aliases, article refs, topic detection |
| `backend/app/modules/russia/retrieval/retrieval_planner.py` | `RussianRetrievalPlanner` — maps understanding → retrieval plan |
| `backend/app/modules/russia/retrieval/service.py` | `analyze_query()` + `topic_search()` added |
| `backend/tests/russia/test_query_analyzer.py` | 55 pure-Python unit tests |
| `backend/tests/russia/test_topic_retrieval.py` | 23 integration tests |

### Query modes

| Mode | Trigger | Strategy |
|------|---------|----------|
| `exact_lookup` | Law alias + article ref (e.g. "ст. 81 тк рф") | `get_article()` → convert to `list[RussianSearchResult]` |
| `law_constrained_search` | Explicit alias only (e.g. "ск рф права ребенка") | `hybrid_search(law_id=detected)` |
| `topic_search` | Topic signals, no alias (e.g. "лишение родительских прав") | `hybrid_search(law_id=preferred)` |
| `broad_search` | No signals | `hybrid_search(law_id=None)` |

### Law aliases supported

| Alias(es) | Maps to |
|-----------|---------|
| `ск рф`, `семейный кодекс`, `семейного кодекса` | `local:ru/sk` |
| `гпк рф`, `гражданский процессуальный кодекс` | `local:ru/gpk` |
| `гк рф`, `гражданский кодекс` | `local:ru/gk/1` |
| `тк рф`, `трудовой кодекс` | `local:ru/tk` |

### Topic signals

| Topic | Sample signal phrases | Preferred law |
|-------|-----------------------|---------------|
| `family_law` | порядок общения с ребенком, лишение родительских прав, орган опеки | `local:ru/sk` |
| `procedural_law` | апелляционная жалоба, процессуальные нарушения, отмена решения суда | `local:ru/gpk` |
| `civil_law` | гражданские права, недействительная сделка, исковая давность | `local:ru/gk/1` |
| `employment_law` | трудовой договор, расторжение, права работника | `local:ru/tk` |

### Representative topic queries (VERIFIED against corpus)

```
# Family law — all results from СК РФ:
"порядок общения с ребенком"          → SK results (all 10)
"лишение родительских прав"           → SK results (all 10)
"орган опеки и попечительства"        → SK results (all 10)
"определение места жительства ребенка" → SK results (all 10)

# Law alias constraints:
"ск рф права ребенка"                 → SK only
"тк рф расторжение договора"          → TK only
"гк рф недействительная сделка"       → GK/1 only

# Exact article lookup via topic_search:
"ст. 69 ск рф"                        → SK article 69, score=1.0
"ст. 81 тк рф"                        → TK article 81, score=1.0

# GPK (not yet in corpus) — handled gracefully:
"апелляционная жалоба"                → no error; returns empty or other law results
"гпк рф ст. 131"                      → no error; returns empty (GPK not ingested)

# Topic search beats unconstrained:
"порядок общения с ребенком":
  topic_search  → 10/10 SK results
  hybrid_search → mixed results from all 3 laws
```

### GPK note

`local:ru/gpk` is recognized by the analyzer and planner but GPK is not yet ingested into `russian_laws_v1`. Queries with GPK alias or procedural topic signals are handled without raising — they return empty results or fall back to broad search. GPK ingestion is covered in Step 9.

### Test results

- **55/55** pure-Python unit tests (analyzer + planner)
- **23/23** integration tests (topic search, SK constraints, exact lookup, GPK graceful)
- **78/78 total** — all pass

---

## Step 9 — GPK Ingest + Procedural Retrieval Verification (COMPLETED 2026-04-12)

### Goal

Ingest `Гражданский процессуальный кодекс РФ` into `russian_laws_v1` alongside GK/1, SK, and TK. Verify that procedural topic queries now return real GPK results, exact article lookup works for representative GPK articles, and existing laws are not regressed.

### Ingest statistics

IDF was rebuilt from all four laws to ensure GPK-specific vocabulary is covered.

| Law | law_id | Articles | Tombstones | Chunks |
|-----|--------|----------|------------|--------|
| ГК РФ ч.1 | `local:ru/gk/1` | 591 | 38 | 1582 |
| ГПК РФ | `local:ru/gpk` | 489 | 21 | 1279 |
| СК РФ | `local:ru/sk` | 173 | 5 | 388 |
| ТК РФ | `local:ru/tk` | 538 | 37 | 538 |
| **Total** | | **1791** | **101** | **3787** |

IDF rebuild: `n_docs=3787`, `vocab=9454` (↑1535 from Step 7), `avg_dl=64.5`

### Re-ingest command

```bash
# From inside the container (or via docker exec):
python -m app.modules.russia.ingestion.cli \
  --corpus /app/Ruske_zakony \
  --qdrant-url http://qdrant:6333 \
  --idf-checkpoint /app/storage/idf_russian_laws_v1.json \
  --no-checkpoint \
  --checkpoint /app/russian_laws_checkpoint.json
```

Note: `--no-checkpoint` forces re-ingest of all files. The IDF is rebuilt from scratch if `idf_russian_laws_v1.json` does not exist; if it already exists, the existing IDF is loaded (faster, avoids Pass 1 scan).

### GPK corpus characteristics

GPK is structurally similar to TK and SK: single text file, UTF-16 LE encoding, standard `Статья N.` header pattern. No special parsing changes were needed — the existing ingestion pipeline handled it without modification.

Notable GPK articles verified via exact lookup:

| Article | Heading | Chunks |
|---------|---------|--------|
| 56 | Обязанность доказывания | 2 |
| 113 | Судебные извещения и вызовы | 5 |
| 131 | Форма и содержание искового заявления | 3 |
| 320 | Право апелляционного обжалования | 2 |

### Verified queries (Step 9)

| Query | Mode | Expected | Result |
|-------|------|----------|--------|
| `ст. 113 гпк рф` | exact_lookup | GPK ст.113 chunks, score=1.0 | ✓ |
| `ст. 131 гпк рф` | exact_lookup | GPK ст.131 chunks, score=1.0 | ✓ |
| `ст. 320 гпк рф` | exact_lookup | GPK ст.320 chunks, score=1.0 | ✓ |
| `апелляционная жалоба гпк рф` | law_constrained_search | All results local:ru/gpk | ✓ |
| `извещение лиц о судебном заседании` | topic_search | GPK in results | ✓ |
| `апелляционная жалоба на решение суда` | topic_search | GPK in results | ✓ |
| `доказательства в суде` | topic_search | GPK in results | ✓ |
| `процессуальные нарушения при рассмотрении дела` | topic_search | GPK in results | ✓ |
| `отмена решения суда апелляционной инстанцией` | topic_search | GPK in results | ✓ |
| `подсудность дел районному суду` | topic_search | GPK in results | ✓ |

### Regression verification

| Query | Expected | Result |
|-------|----------|--------|
| `лишение родительских прав` | All results SK only | ✓ |
| `права ребенка ск рф` | All results SK only | ✓ |
| `расторжение договора тк рф` | All results TK only | ✓ |
| `ст. 69 ск рф` (exact) | SK ст.69 found | ✓ |
| `ст. 81 тк рф` (exact) | TK ст.81 found | ✓ |
| `ст. 169 гк рф` (exact) | GK/1 ст.169 found | ✓ |

### Test results

- **41/41** GPK integration tests (`test_gpk_retrieval.py`)
  - Collection integrity: 4 tests
  - Exact article lookup (direct): 7 tests
  - Exact article via topic_search: 4 tests
  - Procedural topic queries: 8 tests
  - analyze_query GPK: 6 tests
  - Regression (existing laws): 7 tests
  - Result integrity: 5 tests
- **23/23** Step 8 topic retrieval tests — no regressions
- **119/119 total** integration tests — all pass

---

## Step 10 — Foreign Party / Interpreter / Language-of-Proceedings Retrieval (COMPLETED 2026-04-12)

### Goal

Strengthen the legal corpus and retrieval coverage for the foreign-party / interpreter / language-of-proceedings issue. Both supporting sources requested were present and usable:

- `Конвенция о защите прав человека и основных свобод` (ЕКПЧ) — ingested as `local:ru/echr`
- `Федеральный закон от 25.07.2002 N 115-ФЗ` (О правовом положении иностранных граждан) — ingested as `local:ru/fl115`

### Why both sources were added

| Source | Role | Key provisions |
|--------|------|----------------|
| ГПК РФ | **Primary** — civil procedure guarantees | ст. 9 (язык судопроизводства), ст. 162 (переводчик) |
| ЕКПЧ | Supporting — fair trial rights | ст. 5(2) (inform in understood language), ст. 6(3)(e) (free interpreter if needed) |
| ФЗ-115 | Supporting — foreign citizen status | Legal status, rights and obligations of foreigners in Russia |

**GPK remains the primary source** for all interpreter/language procedural guarantees in civil proceedings. ЕКПЧ and ФЗ-115 are supporting sources — reachable via explicit alias or unconstrained hybrid search, but not promoted by topic routing.

### Ingest statistics

IDF rebuilt from all 6 laws.

| Law | law_id | Articles | Tombstones | Chunks |
|-----|--------|----------|------------|--------|
| ЕКПЧ | `local:ru/echr` | 82 | 0 | 158 |
| ФЗ-115 | `local:ru/fl115` | 64 | 22 | 247 |
| ГК РФ ч.1 | `local:ru/gk/1` | 591 | 38 | 1582 |
| ГПК РФ | `local:ru/gpk` | 489 | 21 | 1279 |
| СК РФ | `local:ru/sk` | 173 | 5 | 388 |
| ТК РФ | `local:ru/tk` | 538 | 37 | 538 |
| **Total** | | **1937** | **123** | **4192** |

IDF rebuild: `n_docs=4192`, `vocab=10426` (↑972 from Step 9), `avg_dl=71.9`

### ЕКПЧ parsing note

ЕКПЧ uses `Статья N` (no dot) with the heading on the **next line**, not on the article header line. The existing parser's `_STATYA_RE` pattern uses `\.?` (optional dot) so it matches correctly. Article headings are empty in the `article_heading` field but the heading text appears as the first line of the chunk body. This is acceptable for retrieval — the content is fully searchable.

### Changes to source files

**`backend/app/modules/russia/ingestion/loader.py`**
- Added two entries to `_LAW_ID_MAP`:
  - `("конвенция о защите прав", "local:ru/echr", "ЕКПЧ")`
  - `("115-фз", "local:ru/fl115", "ФЗ-115")`

**`backend/app/modules/russia/retrieval/query_analyzer.py`**
- Added aliases for ЕКПЧ: `"конвенция о защите прав человека и основных свобод"`, `"конвенция о защите прав человека"`, `"екпч"`
- Added aliases for ФЗ-115: `"федеральный закон 115-фз"`, `"фз-115"`, `"115-фз"`
- Extended `procedural_law` phrases with: `"язык судопроизводства"`, `"язык гражданского судопроизводства"`, `"право на переводчика"`, `"не владеющий языком судопроизводства"`, `"лицо не владеющее языком"`, `"переводчик в гражданском процессе"`, `"переводчик в суде"`, `"иностранный гражданин в суде"`
- Extended `procedural_law` stems with: `"переводчик"` (переводчика, переводчику), `"иностран"` (иностранец, иностранного, иностранных)

### Verified queries (Step 10)

| Query | Mode | Primary result | Supporting |
|-------|------|----------------|------------|
| `гпк рф статья 9` | exact_lookup | GPK ст.9, score=1.0 | — |
| `гпк рф статья 162` | exact_lookup | GPK ст.162, score=1.0 | — |
| `переводчик в гражданском процессе` | topic_search | GPK only (10/10) | — |
| `язык судопроизводства` | topic_search | GPK only (10/10) | — |
| `право на переводчика` | topic_search | GPK only (10/10) | — |
| `лицо не владеющее языком судопроизводства` | topic_search | GPK only (10/10) | — |
| `иностранный гражданин в суде` | topic_search | GPK only (10/10) | — |
| `иностранец в российском суде` | broad_search | GPK majority (7/10) | ECHR (2/10) |
| `право на переводчика 115-фз` | law_constrained | FL115 only (10/10) | — |
| `право на переводчика екпч` | law_constrained | ECHR only (10/10) | — |
| `конвенция о защите прав человека ст. 6` | exact_lookup | ECHR ст.6, score=1.0 | — |
| `правовое положение иностранных граждан` | hybrid | FL115 prominent (7/10) | GPK, GK/1 |

**Conclusion: GPK remains the primary source for interpreter/language rights in civil proceedings.** FL115 and ЕКПЧ are reachable via explicit law alias or unconstrained hybrid search.

### Test results

- **43/43** interpreter/language tests (`test_interpreter_language_retrieval.py`)
  - Support corpus integrity: 3 tests
  - GPK exact interpreter articles: 7 tests
  - Interpreter topic returns GPK: 6 tests
  - FL115 retrieval: 5 tests
  - ECHR retrieval: 7 tests
  - analyze_query interpreter: 9 tests
  - No regressions: 6 tests
- **119/119** existing integration tests — zero regressions
- **162/162 total** integration tests — all pass

---

## Step 11 — Issue-Focused Multi-Source Retrieval Entrypoint (COMPLETED 2026-04-13)

### Goal

Build a narrow retrieval composition layer for the foreign-party / interpreter / language-of-proceedings problem. Returns primary (GPK) results and supporting (ECHR, FL115) results in a single structured call.

### New file

**`backend/app/modules/russia/retrieval/interpreter_issue.py`**

Contains:
- `IssueEvidence` — dataclass for a single evidence item, adding `source_role: str` (`"primary"` | `"supporting"`) to the standard search result fields
- `InterpreterIssueResult` — dataclass with `primary`, `supporting`, `combined` lists and the original `query`
- `InterpreterIssueRetrieval` — the retrieval class

### Retrieval logic

```
retrieve(query, top_k_primary=5, top_k_support=3)
  │
  ├── analyze_query(query)
  │     → understand mode, cleaned_query
  │
  ├── Primary pass (always GPK):
  │     if exact_lookup + GPK alias → topic_search(query)   [score=1.0]
  │     else                        → hybrid_search(query, law_id="local:ru/gpk")
  │
  ├── Support pass (unconstrained):
  │     hybrid_search(cleaned_query, law_id=None, top_k=30)
  │     → filter to {local:ru/echr, local:ru/fl115}
  │     → keep up to top_k_support
  │
  └── combine = sorted(primary + supporting, key=-score)
```

### Verified queries and observed primary/support split (VERIFIED)

| Query | Primary | Support |
|-------|---------|---------|
| `суд не предоставил переводчика` | 5 GPK results | 0–1 ECHR (broad query, GPK dominates) |
| `я не понимал язык заседания` | 5 GPK results | 0 (narrow procedural, no support surfaces) |
| `иностранец без переводчика в гражданском процессе` | 5 GPK results | 2–5 FL115 + ECHR |
| `право на переводчика в российском суде` | 5 GPK results | 0–2 ECHR |
| `право на справедливое судебное разбирательство` | 5 GPK results | 3 ECHR art=6 |
| `ст. 162 гпк рф переводчик` | 5 GPK ст.162 exact, score=1.0 | varies |
| `гпк рф статья 9` | 5 GPK ст.9 exact, score=1.0 | varies |

**Note on support depth:** ECHR and FL115 score lower than GPK for most interpreter queries because GPK contains the specific procedural text. ECHR Art. 6 surfaces reliably when the query contains "справедливое судебное разбирательство" (direct Art. 6 language). FL115 surfaces for "иностранец" / "иностранных граждан" queries.

### Design decisions

| Decision | Reason |
|----------|--------|
| Always constrain primary to GPK | This class is narrow — GPK is always the procedural basis |
| Support pool size = 30 (fixed constant) | Guarantees ECHR/FL115 surface even when GPK dominates first positions |
| Exact-lookup mode respected | If query has GPK alias + article number, uses topic_search (score=1.0) |
| Support may be empty | Valid and expected for narrow queries where no ECHR/FL115 content ranks in top 30 |
| source_role on IssueEvidence | Required for downstream synthesis to know what role each piece plays |

### Test results

- **36/36** interpreter issue retrieval tests (`test_interpreter_issue_retrieval.py`)
  - Output types: 6 tests
  - Primary always GPK: 7 tests
  - Supporting results: 7 tests
  - Combined results: 5 tests
  - Top-k constraints: 2 tests
  - Exact lookup: 3 tests
  - No LLM: 1 test
  - No regressions: 5 tests
- **162/162** prior integration tests — zero regressions
- **198/198 total** integration tests — all pass

---

## Step 12 — Case-Text-to-Evidence Bridge (COMPLETED 2026-04-12)

### Goal

Build a case-description-to-evidence bridge covering three sub-issues of the interpreter / language / notice issue cluster. Accepts a short natural-language case description in Russian and returns a structured `CaseBridgeResult` with primary GPK evidence (including deterministic anchor articles) and supporting ECHR/FL115 evidence.

### New file

**`backend/app/modules/russia/retrieval/case_bridge.py`**

Contains:
- `_SUBISSUE_SIGNALS` — phrase + stem matching config for `interpreter_issue`, `language_issue`, `notice_issue`
- `_SUBISSUE_ANCHOR_ARTICLES` — anchor GPK articles fetched via exact lookup per sub-issue: interpreter→[9,162], language→[9], notice→[113]
- `_SUBISSUE_QUERIES` — canonical retrieval queries for semantic enrichment per sub-issue
- `CaseBridgeResult` — structured output dataclass
- `CaseIssueBridge` — bridge class with `analyze()` method
- `_detect_subissues()` — deterministic phrase/stem scoring helper
- `_chunk_to_evidence()` — converts exact-lookup chunks to `IssueEvidence` at score=1.0

### Analysis logic

```
analyze(case_text)
  │
  ├── 1. _detect_subissues(text.lower())
  │       phrase matching (weight=2.0) + stem prefix matching (weight=1.0)
  │       threshold=1.0; returns ordered list of detected sub-issue names
  │
  ├── 2. Anchor article fetch (exact lookup, score=1.0) per sub-issue
  │       interpreter: ст. 9, ст. 162 | language: ст. 9 | notice: ст. 113
  │       deduped (ст. 9 fetched only once for interpreter+language combined)
  │
  ├── 3. Semantic enrichment per sub-issue (hybrid_search, GPK-constrained)
  │       canonical query per sub-issue, top_k=semantic_k (default 3)
  │       adds non-duplicate GPK results to primary_map
  │
  ├── 4. Support pass (unconstrained, pool=30)
  │       hybrid_search(case_text, law_id=None, top_k=30)
  │       filter to {local:ru/echr, local:ru/fl115}
  │       keep up to top_k_support (default 3)
  │
  └── primary = sorted(primary_map)[:top_k_primary]
      combined = sorted(primary + supporting, key=-score)
```

### Bug fix during development

**`вызов` noun stem** — the stem `"вызв"` matches the verb *вызвать* (`вызвали`, `вызвать`) but NOT the noun *вызов* in genitive `вызова` (В-Ы-З-О-В-А). Added `"вызов"` as an additional stem so that `"без официального вызова в суд"` correctly triggers `notice_issue`.

### Verified case descriptions and detected sub-issues

| Case description | Detected sub-issues | Anchor articles |
|------------------|---------------------|-----------------|
| `иностранный гражданин не получил переводчика в суде` | `interpreter_issue` | ст. 9, ст. 162 |
| `я не понимал язык заседания` | `language_issue` | ст. 9 |
| `меня не вызвали в суд надлежащим образом` | `notice_issue` | ст. 113 |
| `я не был официально уведомлен о судебном заседании` | `notice_issue` | ст. 113 |
| `суд рассмотрел дело без моего извещения` | `notice_issue` | ст. 113 |
| `иностранец без переводчика и без официального вызова в суд` | `interpreter_issue`, `notice_issue` | ст. 9, ст. 162, ст. 113 |
| `суд отказал в иске` | *(no match)* | — |

### Test results

- **77/77** case bridge tests (`test_case_bridge.py`)
  - `TestDetectSubissues`: 19 unit tests (no service; run always)
  - `TestCaseBridgeNoMatch`: 5 tests
  - `TestCaseBridgeInterpreterIssue`: 14 tests
  - `TestCaseBridgeLanguageIssue`: 4 tests
  - `TestCaseBridgeNoticeIssue`: 10 tests (3 case descriptions × 3 parametrized + 1)
  - `TestCaseBridgeCombinedIssue`: 10 tests
  - `TestCaseBridgeSupportingSources`: 3 tests
  - `TestCaseBridgeOutputTypes`: 8 tests
  - `TestCaseBridgeRegressions`: 4 tests
- **275/275 total** integration tests — all pass

---

## Step 13 — Dedicated Russian HTTP API (separate from Czech)

### Goal

Expose the verified Russian retrieval stack over **dedicated REST routes** under `/api/russia/*`. Czech law remains on `/api/search`, `/api/search/answer`, and related paths. There is **no** routing of Russian retrieval through the Czech pipeline or the default `czech_laws_v2` collection.

### Architecture rule (ongoing)

| Layer | Russian | Czech |
|--------|---------|--------|
| HTTP prefix | `/api/russia/...` | `/api/search`, `/api/search/answer`, … |
| Qdrant collection | `russian_laws_v1` | `czech_laws_v2` (and Czech adapters) |
| Dependency | `get_russian_retrieval_service` | `get_czech_law_retrieval_service`, `get_czech_search_answer_service`, … |

No silent country switching inside `/api/search/answer` for Russia: use the Russian endpoints below.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/russia/article` | Exact article lookup: `law_id`, `article_num`, optional `part_num` |
| POST | `/api/russia/search` | Body: `query`, optional `law_id`, `top_k`, `mode` (`hybrid` \| `dense` \| `sparse` \| `topic`) |
| POST | `/api/russia/interpreter-issue` | Thin wrapper over `CaseIssueBridge` (interpreter / language / notice cluster) |

**No-hit behavior (GET article):** HTTP **200** with `hit: false`, `chunks: []`, and empty `article_heading` when the article does not exist — **not** HTTP 404 (deterministic, machine-friendly).

**Tombstone:** HTTP 200 with `hit: true`, `is_tombstone: true`, and repeal text in chunks (e.g. ст. 7 ТК РФ).

### UTF-8 and Cyrillic

- JSON request bodies must use **UTF-8** (`Content-Type: application/json` or `application/json; charset=utf-8`).
- Swagger (`/docs`) accepts Cyrillic in the request body examples.

**curl**

```bash
curl -s -X POST "http://localhost:8000/api/russia/search" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{\"query\":\"язык судопроизводства\",\"law_id\":\"local:ru/gpk\",\"top_k\":3}"
```

**PowerShell** (recommended: build JSON from a hashtable so Cyrillic is encoded correctly; avoid raw string bodies with Cyrillic on Windows PowerShell 5.x and avoid `-Body` as byte array, which can trigger chunked encoding issues):

```powershell
$base = "http://localhost:8000"
$body = @{
    query   = "переводчик в гражданском процессе"
    law_id  = "local:ru/gpk"
    top_k   = 3
    mode    = "hybrid"
} | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "$base/api/russia/search" -Method POST `
  -ContentType "application/json; charset=utf-8" -Body $body
```

**Example GET**

```text
GET /api/russia/article?law_id=local%3Aru%2Fgpk&article_num=9
```

### Code locations

| Item | Path |
|------|------|
| Routes | `backend/app/api/routes/russia.py` |
| Router include | `backend/app/api/router.py` |
| DI | `get_russian_retrieval_service` in `backend/app/core/dependencies.py` |
| Contract tests (no Qdrant) | `backend/tests/russia/test_russia_api_contract.py` |
| Live stack tests (Docker / populated `russian_laws_v1`) | `backend/tests/russia/test_russia_api.py` |
| Smoke script | `test_russia_interpreter_notice.ps1` (repo root) |

### Verified Cyrillic query examples (for manual / integration checks)

- `переводчик в гражданском процессе`
- `язык судопроизводства`
- `я не был официально уведомлен о судебном заседании`
- `суд рассмотрел дело без моего извещения`
- `иностранный гражданин без переводчика в суде`

### Test status

- **Contract tests** (`test_russia_api_contract.py`): **VERIFIED** — run `pytest backend/tests/russia/test_russia_api_contract.py` (no Qdrant).
- **Live HTTP tests** (`test_russia_api.py`): **VERIFIED** (2026-04-13) — úspěšně spuštěno proti běžícímu API a kolekci `russian_laws_v1` (skip guard v souboru přeskočen = stack připraven).

## Step 14 — Deterministic legal taxonomy layer (focused scope)

### Goal

Add a rigid retrieval taxonomy under AI reasoning for the currently active scope only:
- procedural language/interpreter/notice defects (GPK),
- alimony and alimony debt/enforcement support (SK),
- supporting fair-trial/foreign-party sources (ECHR / FL115).

### Implemented

- New module: `backend/app/modules/common/legal_taxonomy/`
  - `schemas.py` — typed law/article taxonomy contracts
  - `russia_focus_taxonomy.py` — curated focused dataset (`ru_focus_v1`)
  - `service.py` — deterministic lookups (`get_articles_for_issue`, anchor/topic/law maps)
- New tests: `backend/tests/common/test_russia_focus_legal_taxonomy.py`

### Coverage

- Laws: `local:ru/gpk`, `local:ru/sk`, `local:ru/echr`, `local:ru/fl115`
- Core procedural anchors: GPK ст. 9 / 162 / 113 (+ support 116 / 167)
- Core alimony anchors: SK ст. 80 / 81 / 83 / 107 / 113 / 115 / 117
- Supporting: ECHR ст. 6, FL115 topic support layer

### Test status

- **Taxonomy unit tests** (`test_russia_focus_legal_taxonomy.py`): **VERIFIED** (6 passed).

## Step 15 — Taxonomy-first retrieval routing (API + service consistency)

### Goal

Enforce one shared deterministic control path for Russian retrieval:
1) issue detection,
2) taxonomy candidate article/law selection,
3) anchor/law boosting,
4) scope filtering,
then hybrid/dense/sparse ranking.

### Implemented

- Shared wrapper: `backend/app/modules/russia/retrieval/taxonomy_first.py`
- `/api/russia/search` now uses shared taxonomy-first wrapper (not duplicated logic)
- `RussianRetrievalService` now uses the same wrapper for:
  - `search()` (dense path),
  - `sparse_search()`,
  - `hybrid_search()`,
  - `topic_search()`
- Added DI for taxonomy service: `get_russia_focus_taxonomy_service()`

### Expected behavior (deterministic routing)

- `алименты` → SK-focused articles
- `без уведомления` → GPK notice cluster (incl. ст.113)
- `без переводчика` → GPK language/interpreter cluster (ст.9 / ст.162)

### Test status

- **Route + service alignment** (`test_topic_search_taxonomy_alignment.py`): **VERIFIED**
- **Search taxonomy contract** (`test_russia_search_taxonomy_contract.py`): **VERIFIED**
- Combined contract run (`test_russia_api_contract.py`, taxonomy tests, alignment tests): **VERIFIED** (22 passed in latest run)

---

| Date | Decision | Reason |
|------|----------|--------|
| 2026-04-12 | UTF-16 LE encoding confirmed for all files | Direct byte inspection + Python read test |
| 2026-04-12 | `статья` is primary chunk unit, not `глава` | Exact lookup targets are always articles |
| 2026-04-12 | Decimal article numbers stored as strings ("19.1") | Avoids float comparison issues |
| 2026-04-12 | Tombstones indexed, not skipped | Must be retrievable to inform users article was repealed |
| 2026-04-12 | `КонсультантПлюс: примечание.` strips NEXT line too | Editor notes always follow on the next line |
| 2026-04-12 | Пункты (1) 2) 3)) are NOT split boundaries | Keep related list items together in one chunk |
| 2026-04-12 | Collection `russian_laws_v1` isolated from `czech_laws_v2` | Hard assert in qdrant_writer before any write |
| 2026-04-12 | Work in new branch `feature/russia-law-ingestion` | Isolate from main, zero risk to Czech pipeline |
| 2026-04-12 | Dense model: active embedding provider, dim=384 at runtime | Confirmed via `embedding_service.dimension`; original assumption of 768 was wrong |
| 2026-04-12 | No vector search for exact lookup | Pure payload filter + sort by chunk_index is deterministic and faster |
| 2026-04-12 | Dense dim read from `embedding_service.dimension`, not hardcoded | Confirmed 384 at runtime; hardcoding 768 was wrong |
| 2026-04-12 | Sparse vectors empty in M1, schema present | Avoids collection rebuild when M2 adds BM25; no BM25 encoder in M1 |
| 2026-04-12 | fragment_id = law_id/article_position:06d/chunk_index:04d | Lexsortable, derived from explicit sequential counters only |
| 2026-04-12 | Noise filter (Pass 1) runs before tombstone detector (Pass 2) | Prevents `(в ред. ... утратил силу)` annotation from triggering tombstone flag |
| 2026-04-12 | Editor noise and legal-status content are strictly separate categories | Drop: КонсультантПлюс annotations. Preserve: Утратила силу in official text |
| 2026-04-13 | Russian HTTP API only under `/api/russia/*`; Czech unchanged | Explicit separation; no Russian retrieval via `/api/search/answer` in this step |
| 2026-04-13 | Retrieval taxonomy limited to active procedural/alimony scope | Deterministic precision; avoid broad corpus drift in current phase |
| 2026-04-13 | One shared taxonomy-first engine for API and internal service | Guarantees consistent routing/boost/filter logic across entry points |
