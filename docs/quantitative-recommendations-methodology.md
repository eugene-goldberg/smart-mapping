# Quantitative Disclosure → Position Recommendations — Methodology & Technology

**Scope:** how SoFi maps a regulatory **disclosure question** to the internal **ESG metrics ("positions")** that answer it, for the *quantitative* (numeric) questions of two frameworks — **ESRS** and **GRI** — and everything that was tried to get the best results.
**Two deliverable CLIs:** `smart-mapping/esrsmap.py` (ESRS) and `smart-mapping/grimap.py` (GRI).
**Last updated:** 2026-06-21.

---

## 0. The core problem

> Given a disclosure question, return the short list (≈3–10) of internal positions most likely to be the expert-chosen answer — or correctly say none exists.

Two entities, everything is about mapping one to the other:
- **Disclosure question** — a regulatory ask (demand side). E.g. ESRS § 44 "disclose gross Scope 1/2/3 GHG emissions".
- **Position** — an internal, measurable ESG metric in SoFi's hierarchical catalog (supply side). E.g. "Scope 1 GHG emissions". Collected values live in the `transaction` table.

This work informs the production **"Disclosure AI"** feature (separate codebase). Production used bi-encoder embeddings → cross-encoder rerank and underperforms; this study diagnosed why and built better, evidence-backed methods.

---

## 1. The SoFi database (`sofi`, MySQL 8, 264 tables) and how its concepts relate

### 1.1 Universal conventions
- **Temporal versioning:** core entities are keyed by `(id, term_start)` where `term_start`/`term_end` are `YYYYMM` zero-filled ints. **Active row = `term_end IS NULL`.** `*_index` tables are stable identity anchors.
- **Localization:** display text lives in `*_dict` tables keyed by `(id, term_start, language_id)`. **`language_id = 2` = English.**
- **Access:** MySQL is bound on a remote Docker host; every query runs over SSH: `ssh sofi 'docker exec sofi_mysql mysql -uroot -psofi sofi …'`. Always add `--default-character-set=utf8mb4` (else `§` → latin1 `0xA7` and JSON breaks).

### 1.2 The two halves of the schema

```
SUPPLY SIDE (metrics)                         DEMAND SIDE (questions)
─────────────────────                         ───────────────────────
position (tree)                               disclosure_framework (6)
  ├ position_dict (name/desc/question)          └ disclosure_template (per year; content = JSON tree)
  ├ position_path (closure: ancestor/desc)          └ disclosure (template applied to a site/period)
  ├ position_types (8)                                  └ disclosure_question (flattened questions)
  ├ tag_position (groupings)                                  │  template_question_sid = nodeId
  └ questionnaire_template_position (groupings)               │
                                                              ▼
            disclosure_question_position  ◄────────── THE GOLDEN LINK (question → position)
            transaction (collected values, position×questionnaire×period)
```

### 1.3 Positions — the mapping target (~1,156 active)
- **`position`** — a node in a hierarchical tree: self-referential `parent_position_id`, **materialized `path`** (e.g. `/4831/4853/5028/5301/`, last id = self), `unit_class_id`, `position_type`, `formula` (for Indicators), `use_in_report`.
- **`position_dict`** — localized `name`, `description`, `question`.
- **`position_path`** — closure table (ancestor/descendant/depth). We mostly derive ancestry from the `path` string (parent = 2nd-to-last id).
- **`position_types`** (8): **structure/headers** → `Outline`, `Overview`, `Text`, `Question`; **measurable data** → `Flow`, `Indicator` (has a `formula`), `Asset`, `Distance Mapper`. **The quantitative answer space = the measurable types `{Flow, Indicator, Asset}`.**
- **`tag_position`** (~1,071 rows) and **`questionnaire_template_position`** (~777) — curator-defined *grouping bridges*: which positions share a tag, and which positions are collected together in a questionnaire. (`position_taxonomy_concept` is **empty** — not usable.)

### 1.4 Disclosures — the question source
Chain: **framework → template → disclosure → question**.
- **`disclosure_framework`** (6): `1` CDP, **`2` GRI**, **`3` ESRS**, `4` EU Taxonomy, `5` IFRS-ISSB, `6` SB 253. (Names live in `disclosure_framework_dict`; abbreviations like "GRI"/"CDP" are **not** stored — only the full name.)
- **`disclosure_template`** — versioned by `year`; **the entire question structure is a recursive JSON tree in `content`**. Each node has `nodeId`, `nodeType` (`section`/`question`), `title.en`, `description.en` (the real question text; `title` is often just a `§`/clause ref), `guidance.en`, `isMandatory`, and either:
  - **ESRS:** `xbrlConcepts` — a list of XBRL datapoint concept names (the datatype signal), OR
  - **GRI:** `displayType` / `type` / `columns` — grid (table) questions carry `displayType=="grid"` with `type` `matrixdynamic`/`matrixset` and a `columns[]` array whose descriptions are the numeric datapoints.
- **`disclosure`** — a template applied to a `site` for a period. (`is_template` flag does NOT indicate golden.)
- **`disclosure_question`** — flattened per-disclosure questions. **`template_question_sid` = the `nodeId`** in the template JSON. Carries no text itself — text comes from the template.

### 1.5 The golden data (the labeled bridge that makes everything work)
- **`disclosure_question_position`** = the **GOLDEN** question→position mappings: **3,052 links**, 472 distinct positions, 348 questions. `creator`/`created` columns; **hand-curated by real Sphera staff** — **Hermann Ruhe** (`user_id 6`, 2,902 of 3,052 links), Antonia Rehl (uid 3, 11), D. Maheswaran. Genuine, not synthetic.
- Concentrated in **two disclosures**: **disclosure 9** (GRI, template 24, year 2025 — 2,899 links) and **disclosure 1** (ESRS, template 18, year 2024 — 148 links).
- A **second** golden source exists: `docs/disclosure_benchmark.xlsx` (GRI "Expected Metrics", 88 questions). The two sources **disagree (~Jaccard 0.15), mostly by *granularity*** (same topic subtree, different depth) — a fact that drives the whole validation philosophy below.
- ⚠️ **Open decision:** which golden source is authoritative is still pending from the business.

### 1.6 How a recommendation traverses these relationships
1. Take a question node from `disclosure_template.content` (by `nodeId`).
2. Map `nodeId → disclosure_question.template_question_sid → disclosure_question_id`.
3. The golden answer = `disclosure_question_position` rows for that `disclosure_question_id` → `position_id`s (filtered to active, measurable positions).
4. Curator grouping context for a position: `tag_position`, `questionnaire_template_position`. Cross-framework confirmation: the same `position_id` appearing in golden of a *different* framework's disclosures.

---

## 2. ESRS quantitative recommendations — `smart-mapping/esrsmap.py`

### 2.1 Why this method (what was tried)
- **The stored production embeddings are useless.** `disclosure_ai_embedding` (MiniLM-384) scored **recall@10 ≈ 2%**, median rank ≈ random — because they were built from near-empty `§`-title text. *This is why the production system fails.* **Do not reuse them.**
- **Real embeddings on rich text fix retrieval.** `text-embedding-3-large` (even ada-002) over rich position text → **recall@150 ≈ 93%**. Embedding quality was never the bottleneck.
- **Concept-driven beats paragraph-driven.** A quantitative ESRS question is a *bundle of atomic XBRL datapoints* (e.g. `esrs:GrossScope1GreenhouseGasEmissions`). Matching the **concept name** (not the question paragraph) → positions → expanding to tree siblings gave **91% recall@~17** on the 2024 ESRS analog — far better than matching the paragraph.
- **The hard part is compression**, not recall: turning a high-recall pool into a precise 3–10 shortlist. `gpt-5.4` (full model, not the mini) materially beats fusion/the mini at this judging step.

### 2.2 Technology & pipeline (printed as `▶ STEP n`)
1. **Extract** from `sofi` via SSH (positions text/attrs/unit, ESRS template JSON, `nodeId→question_id` map) — **always fresh, no cached data files**.
2. **Load & classify** question nodes: split `xbrlConcepts` into numeric metrics vs **parameter-numerics** (regex `PARAM` drops `TimeHorizon`/`InYears`/`Date…` — config, not metrics) vs narrative.
3. **Embed positions** with `text-embedding-3-large` on **rich text** = `name + description + path-lineage + unit-class + type` (re-embedded every run, 3072-dim).
4. **Embed** the numeric XBRL concept names (humanized: `GrossScope1…` → "Gross Scope 1 …").
5. **Retrieve & gate:** per concept → top-3 positions by cosine → expand to **sibling cluster** → confidence gate (**top-1 cosine ≥ `--conf` 0.55**; per-candidate floor `--floor` 0.50).
6. **LLM judge** (`gpt-5.4`, **temperature 0**): from the candidate pool pick the precise variant cluster (e.g. Scope 2 → both Location- and Market-based); **abstain** if none fits. Verdicts **cached** keyed on question identity (`nodeId+concepts+desc+model+temp`) in `scratch/judge_cache.json` → reruns are 100% cache hits, bit-for-bit reproducible.
7. **Report** + a status-first ASCII table + a `QUESTION MAPPING STATISTICS` block (mapped vs unmapped).

### 2.3 Statuses & "CONF"
- **MAPPED** (position(s) found) · **GAP** (genuine numeric metric but no position exists — a real taxonomy gap) · **REVIEW** (match too weak) · **SKIP** (reporting parameter, not a metric).
- The `CONF` column is **cosine similarity** between the concept name and a position's rich text (range ~0–1) — **NOT** an LLM probability. 0.55 is a *healthy* match for this score; the yes/no is the judge's, not the number's.

### 2.4 Result (ESRS-2026, template 27, disclosure 5 — the zero-golden production target)
42 quantitative questions → **32 MAPPED, 7 GAP, 3 REVIEW, 1 SKIP**. The 7 GAPs are genuine (stranded assets, transition-risk revenue, governance/financial datapoints) — the position catalog is built for environmental/social *measurement*, so those correctly abstain.

### 2.5 Run it & outputs
```bash
./.venv-tools/bin/python smart-mapping/esrsmap.py run            # full (DB+embed+judge), fresh
./.venv-tools/bin/python smart-mapping/esrsmap.py run --no-judge          # retrieval+gate only
./.venv-tools/bin/python smart-mapping/esrsmap.py run --no-judge-cache    # force fresh verdicts
./.venv-tools/bin/python smart-mapping/esrsmap.py run --template 27 --disclosure 5 --conf 0.55 --floor 0.50
```
Outputs in `smart-mapping/scratch/`: **`esrs27_suggestions.md`** (reporter-facing confident mappings) · **`esrs27_review.md`** (curator queue: parameter/low-conf/judge gaps) · **`esrs27_final.md`** + **`.json`** (finalized variant clusters with judge reasoning).

---

## 3. GRI quantitative recommendations — `smart-mapping/grimap.py`

### 3.1 Why GRI needed a *different* method
GRI templates carry **no `xbrlConcepts`** — so the ESRS concept-driven method finds **0** quantitative questions for GRI. GRI's quantitative questions are **TABLE ("grid") questions** (`displayType=="grid"`, `matrixdynamic`/`matrixset`) — **41 of 245** in template 24 — whose **column descriptions** are the numeric datapoints (e.g. "Area under restoration (ha)", "Scope 1 GHG reporting period emissions (mtCO2e)"). What GRI *does* have is **abundant curated golden** (disclosure 9, 2,899 links).

### 3.2 What was tried, measured against disclosure-9 golden
| Method | recall@20 | notes |
|---|---|---|
| Concept (columns)-only retrieval | ~52% | the ESRS approach — too weak for GRI |
| + question text / wider top-k / subtree | 52–60% | marginal |
| **TRANSFER (nearest already-mapped questions → their positions)** | **~85% (98% seed)** | the strong signal |
| LLM judge (global selector *and* few-shot binary verifier) | **~12% final recall — REJECTED** | see §3.6 |

### 3.3 Chosen method — TRANSFER-CONSENSUS (deterministic)
For a target question:
1. Embed the **question text** (title + description) and find its **K=8 nearest already-mapped GRI questions** (cosine over `text-embedding-3-large`). Reference universe = *all* golden questions (not just grid).
2. **Consensus score** each candidate position = **how many of those neighbours mapped it** (`--weight count`). Positions endorsed by several near neighbours rank highest.
3. **Shortlist:** top-N (`--shortlist 12`) above both a relative floor (`0.5 × top`) and an absolute floor (`--min-score 0.375`).
4. Self-validation on disc 9 uses **leave-one-out** (exclude the question itself). To map a *new* GRI disclosure, pass disc 9 as `--ref-disclosure`.

### 3.4 Corroboration re-tiering (the "DB investigator", deterministic — no LLM)
Medium picks (consensus 0.40–0.60) are the uncertain middle. Instead of asking an LLM "is this relevant?", we follow **independent database linkages** to the question's STRONG anchors:
- **`Q`** = pick shares a **questionnaire** (`questionnaire_template_position`) with a STRONG anchor — *93% precision*
- **`T`** = pick shares a **curator tag** (`tag_position`) — *81%*
- **`X`** = pick is **golden in another framework** (cross-framework confirmation) — *85%*

A medium pick stays **LIKELY** only if corroborated by any of these; otherwise → **WEAK**. Combined rule lifts the medium band's precision **~51% → ~76%**, retaining ~85% of golden. (Investigated as the "LLM investigator" idea, but the chains that matter turned out to be pure SQL + set ops — no GPT needed at runtime.) Toggle with `--no-corroborate`.

### 3.5 Tiers, statuses, and the STRONG-anchor rule
- Per-pick **tier**: **STRONG** (consensus ≥0.60, ~90% near-precision) · **LIKELY** (medium + DB-corroborated, ~76%) · **WEAK** (low, or medium uncorroborated).
- **MAPPED requires a STRONG anchor.** A question whose best pick is only LIKELY/WEAK (a good *neighbour* but scattered *position* votes — e.g. the 103-x energy questions) is routed to **REVIEW** ("no STRONG anchor"). On disc 9: **36 MAPPED, 5 → REVIEW.**
- `SCORE` column = transfer-consensus strength (fraction of K neighbours agreeing) — **not** an LLM confidence. `EVID` column shows the Q/T/X corroboration.

### 3.6 What was REJECTED for GRI (don't repeat)
**The LLM judge.** Both a zero-shot global selector and a few-shot binary verifier collapsed recall to **~12%** (kept 3 of 67 LIKELY). Root cause, confirmed at the per-pair level: the LLM applies **stricter datapoint semantics** than the curators' **loose, granularity-tolerant** golden (e.g. it rejects a "Scope 1 GHG emissions covered by internal carbon price" position for a general Scope-1 GHG question, though golden links it). LLM relevance judgment is **anti-correlated** with this golden set — which is exactly why transfer-consensus (which *imitates* curator behaviour) wins.

### 3.7 Validation methodology (applies to GRI; principle applies to both)
Because golden sources disagree by **tree depth, not topic**, `--validate` reports **two** scores:
- **EXACT** = position-id match (F1 ~64%).
- **NEAR** = granularity-tolerant (exact/parent/child/sibling) — **F1 ~75% (R 73 / P 77)** — *the headline*, and the relevant measure for a curator review queue. Consensus pool recall (ceiling) ~89%.
Exact-id is genuinely bounded ~63–66% by golden granularity + likely incompleteness, **not** by retrieval. Precision is a lower bound (golden may be incomplete).

### 3.8 Run it & outputs
```bash
./.venv-tools/bin/python smart-mapping/grimap.py run            # full run + validate vs golden
./.venv-tools/bin/python smart-mapping/grimap.py run --no-validate
./.venv-tools/bin/python smart-mapping/grimap.py run --no-corroborate     # disable DB re-tiering
./.venv-tools/bin/python smart-mapping/grimap.py run --judge    # EXPERIMENTAL LLM prune (lowers recall — leave off)
```
Defaults: `--template 24 --disclosure 9 --ref-disclosure 9 --transfer-k 8 --shortlist 12 --weight count --conf 0.55 --min-score 0.375`.
Outputs in `smart-mapping/scratch/`: **`gri24_suggestions.md`** (mapped, STRONG-anchored) · **`gri24_review.md`** (no-neighbour + no-STRONG-anchor queues) · **`gri24_final.md`** + **`.json`**. Ends with `PROPOSED-POSITION STATISTICS` (total questions, total mapped positions + distinct, STRONG/LIKELY/WEAK).

---

## 4. How the two fit together (the unifying logic)

1. **Same problem, same data, same backbone — different question-representation.** Both map the *same* positions out of the *same* DB; the only fundamental difference is how each framework encodes a "quantitative datapoint":
   - ESRS → **XBRL concept names** (structured) → concept-driven matching.
   - GRI → **grid column descriptions + curated golden** → transfer-consensus.
   Pick the method by what signal the framework actually provides.
2. **Shared engine.** `grimap.py` **imports `esrsmap.py`** to reuse the Azure client, `text-embedding-3-large` embedding, vector math (`_norm`/`_dot`), narration (`step`/`info`), the ASCII-table renderer, position loading, and the SSH `_sql`/`extract_data` plumbing. One implementation of the expensive/fiddly parts; two thin framework-specific pipelines on top.
3. **Same philosophy:** fresh-from-DB every run (no trusted cached data); embeddings re-built each run; **abstain-first** (never force a low-quality mapping → GAP/REVIEW); narrated step-by-step output; a final status table + statistics block; and **validation against golden with honest dual metrics** where golden exists.
4. **Same "retrieve wide, then compress" shape** — but the *compressor* differs because the data differs: ESRS uses an LLM judge (works on precise XBRL semantics); GRI uses deterministic transfer-consensus + DB-evidence corroboration (the LLM judge is anti-correlated with GRI golden). The lesson: **let measurement choose the compressor**, don't assume the LLM is always the answer.
5. **Framework dispatch:** `esrsmap.py --framework <name>` resolves a framework name → template+disclosure generally, but only ESRS yields XBRL-driven quantitative questions; GRI is handled by `grimap.py`. Other frameworks (CDP, EU Taxonomy, IFRS-ISSB, SB 253) have little/no golden yet.

---

## 5. Pointers (files, commands, outputs)

| Thing | Path |
|---|---|
| ESRS CLI | `smart-mapping/esrsmap.py` |
| GRI CLI | `smart-mapping/grimap.py` |
| ESRS outputs | `smart-mapping/scratch/esrs27_{suggestions,review,final}.md` (+ `esrs27_final.json`) |
| GRI outputs | `smart-mapping/scratch/gri24_{suggestions,review,final}.md` (+ `gri24_final.json`) |
| Full continuity / state | `CONTINUATION_PROMPT.md` (project root) |
| Evidence-backed playbook | `smart-mapping/docs/position-downselection-playbook.md` |
| Method proposal + experiments | `smart-mapping/docs/position-downselection-method.md` |
| Golden dataset assembly | `smart-mapping/docs/golden-dataset-and-matching-logic.md` |
| 2nd golden source (GRI workbook) | `smart-mapping/docs/disclosure_benchmark.xlsx` |
| Git | repo `smart-mapping/`, branch `gri-quant-mapping` (pushed to `github.com/eugene-goldberg/smart-mapping`) |
| Python | `./.venv-tools/bin/python` (venv at project root; `openai`, `python-dotenv`, `openpyxl`) |
| Models | Azure OpenAI: `text-embedding-3-large` (embeddings), `gpt-5.4` (judge), temp 0 — keys in `smart-mapping/.env` |

---

## 6. Open / next steps
- Extend to **qualitative** questions (ESRS ~55%; GRI non-grid) — narrative→Text-position strategy or explicit "no metric" handling.
- Turn the confident mappings (ESRS 32, GRI 36) into a **proposed `disclosure_question_position` rows file for Hermann/Antonia to review** — **do NOT write to the DB without explicit approval.**
- Capture the ESRS **GAPs** as a "new positions needed" list for the taxonomy team.
- Add **`transaction`-usage** as a 4th GRI corroboration signal once live data is available (was 0 in the feature-01 dump).
- Resolve the **authoritative-golden** decision (in-DB vs workbook) — affects every precision number.
