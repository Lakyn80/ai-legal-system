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
