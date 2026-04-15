# Architektonický plán: `agent_pravnik` (pouze ruská větev, ruský case)

**Verze dokumentu:** 1.0  
**Účel:** Blueprint pro implementaci nové vrstvy nad Agentem 2 — převod právní analýzy na použitelné procesní texty pro ruské řízení.  
**Jazyk dokumentu:** čeština (vysvětlení). **Generovaný obsah pro právní použití:** ruština.

---

## 1. Účel agenta

### 1.1 Co je `agent_pravnik`

`agent_pravnik` je specializovaný **drafting agent** pro ruskou jurisdikci: bere **uzavřený balík vstupů** (zejména výstup Agenta 2 a stejný `legal_evidence_pack`, který prošel Agentem 2) a produkuje **strukturovaný procesní / advokační výstup** v ruštině — např. návrh žaloby/odvolání, procesní stanovisko, návrh na procesní úkon, nebo interní brief pro advokáta.

Je to vrstva **litigace a formulace**, ne vrstva **vyhledávání práva** ani **doplnění evidence**.

### 1.2 Co dělá

- Převádí **case theory**, **primary/supporting legal basis**, **fact-to-law mapping** a **strategic assessment** do **konkrétního dokumentu** s procesní logikou (úvod, skutková větev, právní argumentace, návrh výroku / procesního úkonu, důkazní návrhy tam, kde to dává smysl).
- Respektuje **hranice grounding**: cituje a používá **pouze** normy a skutkové podklady, které jsou ve vstupu (viz sekce 6).
- Označuje **epistemický status** tvrzení: fakt z případu vs. tvrzení strany vs. právní závěr vs. taktický návrh.
- V režimech „brief / klient“ umí **zjednodušit** bez přidávání nových „tvrdých“ právních citací.

### 1.3 Co NEDĚLÁ

- **Nespouští retrieval** a nevybírá nové články z databáze ani z RAG.
- **Nemění** skutková tvrzení, chronologii událostí ani identitu účastníků oproti vstupu.
- **Nevymýšlí** průběh řízení (čísla jednacích dnů, podání soudem, doručení konkrétního usnesení), pokud nejsou ve vstupu.
- **Není** náhrada za advokáta ani za soud; výstup je **návrh k revizi člověkem**.

### 1.4 Rozdíl: Agent 2 vs. `agent_pravnik`

| Dimense | Agent 2 (`agent2_legal_strategy`) | `agent_pravnik` |
|--------|-------------------------------------|-----------------|
| Role | Právní inteligence: teorie případu, mapování fakt–právo, strategické listy | Procesní drafting: konkrétní text podání / obhajoby / stanoviska |
| Styl | Analytický, více „interní memorandum“ | Advokační, více „soud / protistrana slyší tento text“ |
| Výstup | Strukturovaný JSON (`LegalStrategyAgent2Output`) + validace hloubky | Dokumentově strukturovaný výstup (viz sekce 3) + quality gates |
| Grounding | `legal_evidence_pack` + `contract_violations` | Stejné omezení + **zákaz nových citací** mimo povolenou množinu |

**Explicitně:** Agent 2 dodává **právní a argumentační základ** (včetně `why_it_matters`, `fact_to_law_mapping`, strategických bulletů).  
`agent_pravnik` z toho dělá **útok/obranu v procesní formě**: formulace, členění, procesní návrhy, styl a tonální nástroje ruského civilního procesu — stále vázané na dodaný materiál.

---

## 2. Vstupní kontrakt

Vstup je **jednoznačně definovaný** Pydantic model (název pracovní: `AgentPravnikRuInput` nebo `LawyerDraftRequest` — viz sekce 8). Níže logické pole a povinnost.

### 2.1 Povinné části (MVP)

| Pole | Zdroj | Proč povinné |
|------|--------|----------------|
| `case_id` | metadata | Audit, idempotence testů |
| `jurisdiction` | např. `"Russia"` | Guard proti omylu větvě |
| `document_kind` | enum (viz sekce 4) | Řídí strukturu a tonální šablonu |
| `work_mode` | enum (viz sekce 5) | Klient vs. soud vs. interní brief |
| `agent2_output` | celý `LegalStrategyAgent2Output` | Jádro argumentace |
| `legal_evidence_pack` | stejný objekt jako u Agenta 2 (`LegalEvidencePack`) | Jednotná množina povolených norem |
| `cleaned_summary` | z `LegalStrategyAgent2Input` | Kontext případu pro úvodní části |
| `facts` | seznam faktů ze vstupu Agenta 2 | Neměnný skutkový základ |
| `issue_flags` | ze vstupu Agenta 2 | Navázání na procesní problémy |

**Poznámka:** `agent2_output` už obsahuje vnořené `primary_legal_basis`, `supporting_legal_basis`, `fact_to_law_mapping`, `strategic_assessment`, `missing_evidence_gaps`, `recommended_next_steps`, `draft_argument_direction`, `insufficient_support_items`. Pro `agent_pravnik` je **zdrojem pravdy** zejména tento objekt + **shodný** evidence pack jako u Agenta 2.

### 2.2 Volitelné / podmíněně doporučené

| Pole | Kdy | Účel |
|------|-----|------|
| `timeline` | pokud existuje u Agenta 2 | Procesní chronologie v podání |
| `claims_or_questions` | pokud existuje | Vymezení předmětu sporu |
| `procedural_posture` | nové pole — stručný popis **výhradně ze vstupu** (např. „odvolání podáno“, „první instance“) | Šablona bez halucinací; pokud chybí, agent to musí **nevymýšlet** |
| `party_labels` | např. истец / ответчик | Konzistence oslovení v textu |
| `court_instance_hint` | např. первая инстанция / апелляция | Volba typu dokumentu a stylu |

### 2.3 Co je pro drafting kritické z Agenta 2

- **`case_theory`** + **`draft_argument_direction`** — nosná linie textu podání.
- **`primary_legal_basis`** — jádro citací a argumentačních bloků (musí zůstat v souladu s packem).
- **`fact_to_law_mapping`** — přímý zdroj pro sekce „факты — право — нарушение — последствия“.
- **`strategic_assessment`** — co zdůraznit, co oslabit, co očekávat od protistrany.
- **`missing_evidence_gaps`** + **`insufficient_support_items`** — sekce rizik a „что нужно доказать“ bez vydávání nepodložených tvrzení za jistotu.

---

## 3. Výstupní kontrakt

Výstup je **strukturovaný** (JSON přes Pydantic), přičemž **dlouhé právní pasáže** jsou v ruštině v označených polích. Oddělené sekce umožní render do DOCX/PDF a kontrolu validátory.

### 3.1 Navrhované top-level pole (`AgentPravnikRuOutput`)

| Pole | Typ | Obsah (RU) |
|------|-----|------------|
| `schema_version` | str | Verze schématu |
| `document_kind` | enum | Shoda se vstupem |
| `work_mode` | enum | Shoda se vstupem |
| `document_title` | str | Např. «Апелляционная жалоба», «Процессуальная позиция» |
| `header_block` | str | Záhlaví (soud, účastníci — **jen pokud ve vstupu**; jinak placeholdery nebo explicitní „данные не предоставлены“) |
| `procedural_background` | str | Stručně o stadiu řízení **pouze z dodaných dat** |
| `facts_section` | str | Skutková část ve stylu podání |
| `legal_argument_section` | str | Právní argumentace s odstavci podle článků z packu |
| `violation_and_consequence` | str | Explicitní spojení porušení — následek (ГПК/иной акт) |
| `requested_relief` | `RequestedRelief` | Strukturovaný návrh výroků / procesních úkonů |
| `evidence_requests` | list[`EvidenceRequestItem`] | Návrhy na dokazování / předložení listin (bez vymýšlení existujících listin) |
| `procedural_motions` | list[str] | Navrhované podání (ходатайства) — jako textové návrhy, ne jako hotové soudní příkazy |
| `deadlines_and_posture` | `ProceduralPostureNotes` | Lhůty **jen pokud ve vstupu**; jinak obecné upozornění bez konkrétních dat |
| `risk_notes` | list[`RiskAssessmentItem`] | Slabiny, nejasnosti, chybějící důkazy |
| `grounding_manifest` | `GroundingManifest` | Strojově kontrolovatelný seznam použitých (law, article) z packu |
| `full_document_markdown` | str | Volitelně jeden sloučený text pro náhled |
| `lawyer_brief_ru` | str \| null | Zkrácený interní brief, pokud `work_mode` vyžaduje |
| `client_explanation_ru` | str \| null | Zjednodušený text pro klienta, pokud režim vyžaduje |

### 3.2 Pomocné struktury (logicky)

- **`RequestedRelief`:** `primary_asks: list[str]`, `alternative_asks: list[str]`, `non_claim_procedural: list[str]` (např. восстановление срока).
- **`EvidenceRequestItem`:** `description_ru`, `grounding_reference` (odkaz na fakt nebo mezeru z `missing_evidence`), `epistemic_label` (fact / allegation / to_be_proven).
- **`RiskAssessmentItem`:** `severity`, `description_ru`, `mitigation_ru`.
- **`GroundingManifest`:** `cited_provisions: list[{law, article}]`, `flags: list[str]` (např. `no_new_articles_added`).

### 3.3 Použitelnost pro ruský case

- Texty v **`legal_argument_section`** musí používat **формулировки процессуального права** (ГПК РФ, příp. СК, КоАП…) **jen tam, kde je článek v packu**.
- **`requested_relief`** musí být formulováno tak, aby šlo zkopírovat do žaloby/odvolání po úpravě záhlaví advokátem.
- Pokud vstup nemá údaje o soudu a spisové značce, výstup musí **explicitně** uvést, že jde o šablonu.

---

## 4. Typy dokumentů (RU) — MVP vs. další fáze

### 4.1 MVP (první verze produktu)

| `document_kind` | Ruský název | Účel |
|-----------------|-------------|------|
| `appeal_draft` | апелляционная жалоба (návrh) | Hlavní procesní útok druhého stupně |
| `procedural_motion_restoration` | ходатайство о восстановлении процессуального срока | Častý reálný úkon (ГПК ст. 112) |
| `defense_position_memo` | процессуальная позиция ответчика | Strukturovaná obrana v první instanci |
| `lawyer_internal_brief` | внутренний аналитический меморандум для адвоката | Ne pro soud — vysoká pravdivostní disciplína |

### 4.2 Fáze 2

| `document_kind` | Poznámka |
|-----------------|----------|
| `cassation_outline` | кассационная жалоба — vyšší nároky na formu |
| `objections_to_claim` | возражения на исковое заявление |
| `cassation_vs_appeal_branching` | rozlišení апелляция / кассация podle instance (vyžaduje vstupní metadata) |
| `client_facing_letter` | письмо клиенту — jednodušší jazyk, stejné grounding pravidlo |

### 4.3 Explanatory memo

- **`lawyer_internal_brief`** je v MVP jako **nejbezpečnější** formát pro kalibraci kvality před plným „court-facing“ PDF.

---

## 5. Režimy práce (`work_mode`)

| Režim | Pro koho | Jazyk výstupu | Formalita | Grounding | Taktické hypotézy |
|-------|----------|---------------|-----------|-----------|-------------------|
| `strict_litigation` | Soud / protistrana | RU, formální | Vysoká | Přísně jen pack + vstupní fakta | Povoleny jen jako **условно** („если суд установит…“) s odkazem na mezeru v důkazech |
| `structured_defense` | Obrana v 1. instanci | RU | Vysoká | Stejné | Důraz na slabiny žaloby ze `strategic_assessment` |
| `lawyer_briefing` | Advokát v kanceláři | RU | Střední až vysoká | Stejné | Povoleny **taktické odstavce** odděleně v sekci „рекомендации“, označené jako doporučení |
| `client_explanation` | Klient (bez právnického žargonu kde jde) | RU | Nížší | Stejné — **žádné nové články**; možno obecně říct „по статьям ГПК, указанным в анализе“ | Ano, ale jen jako „možné kroky“, ne jako jisté výsledky řízení |

**Pravidlo:** Čím nižší formalita, tím víc **musí být vidět oddělení** „что доказано“ vs. „что предполагается“.

---

## 6. Bezpečnost a grounding pravidla (přísně)

### 6.1 Tvrdé zákazy

1. **Žádné nové zákony / články** mimo množinu z `allowed_provision_keys(inp)` (stejná logika jako `evidence_contract.py` u Agenta 2).
2. **Žádné nové skutkové detaily** (data, jména, částky, adresy, čísla jednání), které nejsou ve `facts`, `cleaned_summary`, `timeline` nebo explicitně v `agent2_output`.
3. **Žádná smyšlená procesní historie** (např. „суд отклонил ходатайство от 12.03“, pokud to není ve vstupu).
4. **Žádné předstírání**, že dokument je podaný u soudu, pokud výstup je draft — v promptu vynutit formulaci «проект» / «черновик».

### 6.2 Povinné rozlišení typů tvrzení

Výstup musí strukturovaně rozlišovat (buď sekcemi, nebo inline značkami ve strukturovaných polích):

| Typ | Jak se má chovat |
|-----|------------------|
| **Fact** | Pouze ze vstupních faktů / shrnutí |
| **Allegation** | Tvrzení strany — formulovat jako «заявляется, что…», pokud to tak je ve vstupu |
| **Legal conclusion** | Odůvodnění podle článku z packu |
| **Tactical recommendation** | Sekce «рекомендуется», bez předstírání jistoty výsledku |

### 6.3 Silné / slabé / neověřené argumenty

- Převzít z `strategic_assessment` a `insufficient_support_items`.
- V `risk_notes` explicitně uvést **neověřené body** a **chybějící důkazy** (`missing_evidence_gaps`).

### 6.4 Konzistence s Agentem 2

- Pokud Agent 2 uvedl `insufficient_support_items`, `agent_pravnik` **nesmí** tuto mezeru překlopit v „hotový skutkový závěr“ — maximálně podmíněná argumentace nebo návrh doplnit důkaz.

---

## 7. Prompt design pro `agent_pravnik`

### 7.1 Strategie (vysvětlení česky)

- **System prompt** je fixní, bez vloženého surového případu — stejný princip bezpečnosti jako u Agenta 2 (`prompts.py`: case jen v user zprávě).
- **User message** obsahuje JSON: `agent2_output`, `legal_evidence_pack`, fakta, issue flags, `document_kind`, `work_mode`, případně `procedural_posture`.
- **Dvojí kontrola:** (1) model dostane explicitní seznam povolených `(law, article)`; (2) výstupní JSON musí obsahovat `grounding_manifest` pro automatickou validaci.
- **Styl:** instrukce v ruštině pro model, aby psal jako **опытный процессуалист**, ne jako shrnutí; požadovat odstavce, nikoli odrážkový „essay chat“.
- **Šablona dokumentu:** podle `document_kind` vložit krátký „скелет“ očekávaných sekcí (например: вводная часть — описание обстоятельств — правовая оценка — нарушения — просительная часть).

### 7.2 System prompt (RU) — návrh finálního znění

```
Ты — российский процессуалист и адвокат по гражданским делам. Твоя задача — преобразовать предоставленный структурированный правовой анализ (выход Agent 2) в черновик процессуального документа или внутренний меморандум на русском языке.

ЖЁСТКИЕ ПРАВИЛА:
1) Используй нормы права ТОЛЬКО из списка allowed_provisions в пользовательском JSON. Запрещено добавлять новые статьи, кодексы или «типовые» ссылки, которых нет в списке.
2) Не добавляй новые факты, даты, суммы, имена, номера дел, даты заседаний и детали процедуры, если их нет во входных полях facts / cleaned_summary / timeline / agent2_output.
3) Чётко разделяй: (а) установленные входом факты; (б) заявления стороны; (в) правовые выводы, опирающиеся на разрешённые статьи; (г) тактические рекомендации (отдельный блок, без уверенности в исходе).
4) Если анализ указывает на недостаток доказательств или insufficient_support_items, обязательно отрази это в разделе рисков и формулируй выводы условно («если суд установит…»).
5) Пиши в стиле реального судебного документа: связные абзацы, логика факт → норма → нарушение → последствие → просительная часть (где уместно).
6) Не утверждай, что документ уже подан в суд, если пользователь не передал это явно; помечай результат как проект/черновик.

Язык ответа: русский. Не переводите правовые ссылки на другие юрисдикции.
```

### 7.3 Developer / šablona user message (struktura)

Česky: User message sestaví orchestrátor jako JSON s klíči:

- `allowed_provisions`: pole `{ "law": "...", "article": "..." }` — kopie z `allowed_provision_keys` (stejná normalizace jako v `evidence_contract.py`).
- `agent2_output`: kompletní výstup Agenta 2.
- `case_bundle`: `cleaned_summary`, `facts`, `issue_flags`, `timeline`, `claims_or_questions`.
- `task`: `{ "document_kind": "...", "work_mode": "..." }`.

### 7.4 Variantní doplněk podle `document_kind` (fragment RU)

Pro `appeal_draft`:

```
Структура: вводная часть (суд, сторона, обжалуемый акт — только если есть во входе) → краткое изложение фактов по входу → правовая оценка по разрешённым статьям → доводы о нарушении норм материального/процессуального права → просительная часть. Без выдуманных процессуальных эпизодов.
```

*(Plné sady doplňků pro každý typ dokumentu doplní implementace jako `prompt_fragments_ru.py`.)*

---

## 8. Návrh datových schémat (Pydantic)

Níže konceptuální modely — přímo implementovatelné.

### 8.1 `AgentPravnikRuInput`

- `case_id: str`
- `jurisdiction: Literal["Russia"]` (nebo `str` s runtime check)
- `document_kind: DocumentKindRu` (enum)
- `work_mode: PravnikWorkMode` (enum)
- `legal_evidence_pack: LegalEvidencePack` (import z `agent2` input_schemas)
- `agent2_output: LegalStrategyAgent2Output`
- `cleaned_summary: str`
- `facts: list[str]`
- `issue_flags: list[str]`
- `timeline: list[str] = []`
- `claims_or_questions: list[str] = []`
- `procedural_posture: ProceduralPostureInput | None` — volitelné krátké pole ze vstupu uživatele
- `party_labels: dict[str, str] | None` — např. роли

### 8.2 `AgentPravnikRuOutput`

- Pole dle sekce 3 + `schema_version`.

### 8.3 Další modely

| Model | Pole (návrh) |
|-------|----------------|
| `RequestedRelief` | `primary_asks`, `alternative_asks`, `procedural_requests` |
| `EvidenceRequestItem` | `summary_ru`, `link_to_fact_or_gap`, `epistemic_label` |
| `RiskAssessmentItem` | `level: Literal["high","medium","low"]`, `description_ru`, `source: Literal["agent2","input"]` |
| `GroundingManifest` | `cited_provisions: list[SourceRef]`, `validation_status` |
| `ProceduralPostureNotes` | `notes_ru`, `deadline_mentions_only_from_input: bool` |

### 8.4 Enumy

- `DocumentKindRu`: `appeal_draft`, `procedural_motion_restoration`, `defense_position_memo`, `lawyer_internal_brief`, …
- `PravnikWorkMode`: `strict_litigation`, `structured_defense`, `lawyer_briefing`, `client_explanation`

---

## 9. Servisní vrstva — konkrétní struktura souborů (russian branch)

Navrhovaná umístění **pouze pod** `backend/app/modules/russia/` (žádné zbytečné abstrakce pro jiné země):

```
backend/app/modules/russia/agents/agent_pravnik/
    __init__.py
    schemas.py              # AgentPravnikRuInput, AgentPravnikRuOutput, enums, pomocné modely
    prompts_ru.py           # SYSTEM_PRAVNIK_RU, šablony podle document_kind
    validators.py           # kontrola citací proti packu, kontrola „no new facts“ (heuristiky)
    quality_gates.py        # minimální délky, zakázané fráze, povinné sekce
    service.py              # LegalPravnikAgentService.run(): invoke_structured, repair loop, fallback
    fallback_ru.py          # deterministické šablony slabého výstupu (např. jen struktura + kopie agent2)
    telemetry.py            # audit podobně jako Agent2 (bez logování plného textu případu)
```

**Integrace importů:** reuse `LegalEvidencePack`, `LegalStrategyAgent2Output`, `SourceRef` z `app.modules.common.agents.agent2_legal_strategy`.

**`formatter/renderer`:** volitelně `renderer.py` — skládá `full_document_markdown` z polí (pro export).

---

## 10. Fallback a validace kvality

### 10.1 Jak poznat slabý draft

- Příliš krátké sekce vs. minimální limity pro `document_kind`.
- Chybí `requested_relief` nebo je obecné „просим удовлетворить“ bez vazby na `issue_flags`.
- Méně než N odstavců v `legal_argument_section` (N podle režimu).
- **`grounding_manifest` obsahuje článek mimo allowed** → tvrdá chyba / repair.

### 10.2 Repair loop

- Stejný vzor jako Agent 2: max 2–3 pokusy s **repair promptem** (RU), který vkládá seznam violations z `validators.py`.
- Repair nesmí přidat nové články — jen opravit formulaci.

### 10.3 Deterministický fallback

- Pokud LLM selže: sestavit výstup z **šablony** + přímého přepisu `case_theory`, `draft_argument_direction`, odrážek z `strategic_assessment` do sekcí, s hlavičkou «ЧЕРНОВИК (автоматическая сборка)».
- **Žádné** vymýšlení nových norem — fallback jen reorganizuje vstup.

### 10.4 Validace „není to jen summary“

- **Povinné sekce** podle `document_kind` (checklist v `quality_gates.py`).
- **Minimální hustota právních odkazů:** alespoň jedna korektní reference na každý hlavní `issue_flag` nebo explicitní poznámka, že v packu chybí norma (pak odkaz na `insufficient_support_items`).
- **Zakázané fráze** (RU): typické „нейросеть“, «в данной работе рассмотрим», prázdné fráze bez vazby na fakt (seznam doladit z provozu).
- **Argumentační struktura:** stejná logika jako u Agent 2 (fakt → norma → porušení → důsledek) — buď heuristiky, nebo lehký sekundární check.

---

## 11. Integrace do pipeline

### 11.1 Tok dat

```
Agent 1 (retrieval, evidence pack, issue flags, fakta)
        ↓
Agent 2 (LegalStrategyAgent2Input → LegalStrategyAgent2Output + validace + případně fallback)
        ↓
agent_pravnik (AgentPravnikRuInput → AgentPravnikRuOutput + validace)
        ↓
UI / export / DOCX
```

### 11.2 Kde končí analýza a kde začíná drafting

- **Konec analýzy:** po úspěšném Agentu 2 (včetně `contract_violations` prázdných).
- **Začátek draftingu:** nový krok volá se pouze s **kopíí** `LegalStrategyAgent2Input` relevantních částí + `agent2_output` + **stejným** `legal_evidence_pack`.

### 11.3 Jak zabránit „vymýšlení práva“ znovu

- `agent_pravnik` **nemá přístup k retrieval API**.
- Validátor po výstupu: `collect_cited_keys` analog pro výstup `agent_pravnik` (rozšířit o pole, kde jsou články v textu — buď strukturovaně jen přes `grounding_manifest`, nebo extrakce z řetězců + kontrola).
- Doporučený postup MVP: **povinné** vyplnění `grounding_manifest.cited_provisions` pouze z uzavřené množiny; volitelně později NER/extrakce z dlouhého textu.

---

## 12. MVP implementační plán (konkrétní pořadí)

1. **Schémata** — `schemas.py` + enumy; unit testy serializace.
2. **Validátor packu** — reuse `allowed_provision_keys`; funkce `pravnik_contract_violations(output, inp)`.
3. **Service skeleton** — `run()` s jedním `invoke_structured` bez repair.
4. **Prompts RU** — system + user builder + fragmenty pro 2–3 `document_kind` (MVP).
5. **Quality gates** — minimální délky, povinné sekce, zakázané fráze.
6. **Repair loop** — 2 pokusy.
7. **Fallback** — šablona z vstupu Agenta 2.
8. **Telemetrie** — audit eventy (`agent_pravnik_draft_rejected`, `agent_pravnik_fallback`, …).
9. **Wire do API** — jeden endpoint nebo interní volání z existujícího Russia flow (podle toho, kde dnes končí Agent 2).

**MVP hotové =** alespoň jeden `document_kind` + jeden `work_mode` end-to-end s testy a validací citací.

**Odloženo:** plný DOCX export, kassace, klientské dopisy bez review.

---

## 13. Testovací strategie

### 13.1 Contract tests

- Vstupní JSON musí projít Pydantic; výstupní JSON stejně.
- `document_kind` + `work_mode` na výstupu shodné se vstupem (nebo explicitní transformace zakázána).

### 13.2 Grounding integrity

- Pro fixní `LegalEvidencePack` a umělý `agent2_output` s známými články: výstupní `grounding_manifest` nesmí obsahovat jiné páry `(law, article)`.
- Test negativní: model (nebo mock) vrátí cizí článek → očekávat `repair` nebo fail.

### 13.3 „No new laws invented“

- Seznam povolených norem = 1–2 články; výstup nesmí citovat třetí.

### 13.4 Structure tests

- Pro `appeal_draft` musí existovat neprázdné `legal_argument_section` a `requested_relief`.
- Pro `lawyer_internal_brief` musí existovat `risk_notes` pokud `insufficient_support_items` neprázdné.

### 13.5 Jazykové role

- System prompt a logy vývojáře česky/anglicky OK; **assert**: klíčová uživatelská pole dokumentu jsou v ruštině (jednoduchá heuristika: podíl кириллицы).

### 13.6 Regrese na konkrétní ruský case

- Uložit **golden snapshot** vstupu (anonymizovaný): Agent 2 output + pack; porovnávat hash struktury a minimální délky sekcí; při změně promptu spustit diff review.

---

## Shrnutí závislostí na existujícím kódu

| Existující modul | Využití |
|------------------|---------|
| `agent2_legal_strategy/input_schemas.py` | `LegalEvidencePack`, struktura vstupu |
| `agent2_legal_strategy/schemas.py` | `LegalStrategyAgent2Output`, `SourceRef` |
| `agent2_legal_strategy/evidence_contract.py` | `allowed_provision_keys`, vzor validace citací |
| `app.modules.russia.services.strategy` | Kontext deskriptoru (jen orientace; nový agent je samostatný modul) |

---

*Konec architektonického plánu.*
