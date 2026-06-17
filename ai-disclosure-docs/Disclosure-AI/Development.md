[[_TOC_]]  
  
## Disclosure AI — Technical Reference  
  
**Feature Branch:** `feature/disclosure_ai/m1` forked against **development**
  
Returns up to 10 ranked position/report suggestions per disclosure question (ESRS/GRI/CDP). All ML inference runs locally — no customer data leaves the server.  
  
**Pipeline:** bi-encoder pre-filter → cross-encoder reranking → cache  
  
## Project Details  
  
*   **Feature**: Disclosures AI enabled - Smart Data Mapping & Discovery
*   **Models**: `paraphrase-multilingual-MiniLM-L12-v2` (bi-encoder, 384-dim) · `cross-encoder/ms-marco-MiniLM-L-6-v2` (cross-encoder)  
*   **Languages**: 50+ (multilingual bi-encoder; English cross-encoder)  
*   **PHP Namespace**: `App\SoFi\DisclosureManagement\Ai\`  
*   **Python scripts**: `sofi/app/cli/disclosure_ai/`  
*   **Bulk indexer**: `sofi/app/cli/disclosure_ai/indexer.py`  

## Database
[Database Schema](https://app.moqups.com/j6NJGn1DHhhwJyH6OsjcDSSIoxgceePo/edit/page/a4a56e037)
---  
  
## Transport  
  
Python inference runs via **CLI only**. PHP spawns `embed.py` / `rerank.py` as short-lived processes via `Symfony\Component\Process`, passing JSON on stdin and reading results from stdout.  
  
> **Note:** Each call reloads the model from disk (~10–20 s for `embed.py`, ~5–10 s for `rerank.py`). Results are cached for 1 hour per question so the cost is paid once per cache miss.  
  
---  
  
## Architecture  
  
```  
ExtJS → Controller::aiPositionSuggestions()  
          → SmartMapperService::suggestPositions()
              1. Build question context (title, description, guidance, framework, template path) via extractNodeContext() — reads template JSON tree
              2. preFilterCandidates()
                 a. EmbeddingService::search(query, type, termStart, limit=60)  
                    → Symfony Process → cli/disclosure_ai/search.py (stdin/stdout)
                    - Embeds query + loads stored vectors from DB + cosine similarity in Python/numpy
                    - Returns entity IDs ordered best → worst
                 b. Fallback: keywordPreFilter() or broadKeywordScore()(MAX_CANDIDATES=60)
                 c. Fallback: keywordPreFilter() or broadKeywordScore()
             3. RerankingService::rerank()
                → Symfony Process → cli/disclosure_ai/rerank.py (stdin/stdout)
                - Filtering (RERANK_MIN_SCORE, RERANK_GAP_THRESHOLD) and normalisation in Python
                - Returns [{id, confidence}] already filtered and limited to RERANK_MAX_SUGGESTIONS
            4. Cache result (1 h TTL) and return top suggestions
```  
   
## Data Models  
  
### `disclosure_ai_embedding`  
### `disclosure_ai_feedback`  
  
---  
  
## Service Interfaces  
  
### `EmbeddingService` — `App\SoFi\DisclosureManagement\Ai\EmbeddingService`  
  
| Method | Description |  
|---|---|  
| `isAvailable(): bool` | `true` if `EMBED_PYTHON_BIN` is non-empty |  
| `search(string $queryText, int $type, int $termStart, int $limit = 60): int[]` | Delegates to `search.py`: embeds query + cosine similarity in Python/numpy; returns entity IDs ordered best → worst |  
| `hasEmbeddings(int $type, int $termStart): bool` | Row existence check (`DisclosureAiEmbedding::TYPE_*` constants) |  
| `triggerBackgroundIndexing(string $type, int $termStart): void` | Spawns `indexer.py` non-blocking when embeddings are missing |  
  
No class-level constants. Cosine similarity is entirely in Python (`search.py`) — PHP only passes IDs back.  
  
---  
  
### `RerankingService` — `App\SoFi\DisclosureManagement\Ai\RerankingService`  
  
`isAvailable(): bool` — `true` if `EMBED_PYTHON_BIN` is non-empty.  
  
`rerank(string $queryText, array $candidates): array`  
  
Each candidate forwarded to `rerank.py`: `[id, name, unitClass → unit_class, description, scopes, ancestorPath → ancestor_path, tags, positionNames → position_names]`.  
Each result returned: `[id, name, confidence (0–1), reason, ancestorPath, positionCategories, tags]`.  
  
No scoring constants in PHP. All filtering and normalisation is handled in `rerank.py` — see `RERANK_MIN_SCORE`, `RERANK_GAP_THRESHOLD`, `RERANK_MAX_SUGGESTIONS` env vars.  
  
---  
  
### `SmartMapperService` — `App\SoFi\DisclosureManagement\Ai\SmartMapperService`  
  
| Method | Signature |  
|---|---|  
| `suggestPositions` | `(int $disclosureQuestionId, int $termStart, int $termEnd, ?string $templateNodeId): array` |  
| `suggestReports` | `(int $disclosureQuestionId, ?string $templateNodeId): array` |  
  
Constants: `MAX_CANDIDATES=60`, `MAX_GUIDANCE_LENGTH=600 chars`, `CACHE_TTL=3600s`.  
  
Candidate fetching delegates to:  
- `PositionRepository::findAiCandidates($termStart, $termEnd, $languageId, $defaultLanguageId)` — returns `id, name, unitClass, description, scopes, ancestorPath, tags`  
- `ReportRepository::findAiCandidates($languageId, $defaultLanguageId)` — returns `id, name, description, positionCategories, positionNames, tags`  
  
---  
  
### `Exception\AiInferenceException`  
  
Thrown by `EmbeddingService` and `RerankingService` when a Python CLI process fails. Extends `RuntimeException`.  
  
---  
  
## Pipeline Algorithms  
  
### Common Prefix Stripping (`rerank.py`)  
Shared preamble across sub-queries is removed before cross-encoder scoring to focus on discriminative tokens (≥2 shared tokens stripped; each suffix retains ≥2 alphanumeric tokens).  
  
### Multi-Query Score Normalisation (`rerank.py`)  
Per sub-query, scores are min-max normalised to [0,1]; final score is `MAX` across sub-queries. Ensures the best match for any sub-query reaches 1.0 regardless of absolute logit magnitude.  
  
### Candidate Text Construction (`indexer.py`)  
  
Positions:  
```  
"{name} [{unit_class}]. Category: {ancestor_path}. Scopes: {scopes}. Tags: {tags (capped)}. Related: {siblings (capped)}. Sub-positions: {children (capped)}. {description}"  
```  
Reports:  
```  
"{name}. Categories: {position_categories}. Positions: {position_names (capped)}. Tags: {tags (capped)}. Scopes: {scopes}. {description}"  
```  
Lists (tags, siblings, children, position_names) are capped at 5 items with a `(+N more)` suffix to avoid embedding token overflow.  
  
### Pre-filter Noise Word Stripping (`AiSuggestionService`)  
Before embedding the query, words like `other`, `provide`, `additional`, `relevant`, etc. are stripped via regex to avoid false semantic matches (e.g. "Other" in "Other climate-related metrics" matching "Other hazardous waste" positions).  
  
### Confidence Normalisation (Python, inside `rerank.py`)  
```  
confidence = (score - min_passing_score) / (top_score - min_passing_score)  
```  
Top candidate = 1.0; rounded to 4 decimal places. Applied after `RERANK_MIN_SCORE` / `RERANK_GAP_THRESHOLD` filtering.  
  
### Score Thresholds (calibrated for ms-marco-MiniLM-L-6-v2)  
  
| Logit range | Interpretation |  
|---|---|  
| `> -6.0` | Strong semantic match |  
| `-6.0` to `-7.5` | Relevant (semantic match, correct topic) |  
| `-7.5` to `-9.0` | Marginal (surface keyword only) — filtered at `-8.5` |  
| `< -9.0` | Unrelated |  
  
---  
  
## Configuration  
  
### Symfony Services (`services.yaml`)  
  
```yaml  
App\SoFi\DisclosureManagement\Ai\EmbeddingService:  
    arguments:      $pythonBin:  '%env(EMBED_PYTHON_BIN)%'      $scriptDir:  '%env(EMBED_SCRIPT_DIR)%'  
App\SoFi\DisclosureManagement\Ai\RerankingService:  
    arguments:      $pythonBin:  '%env(EMBED_PYTHON_BIN)%'      $scriptDir:  '%env(EMBED_SCRIPT_DIR)%'  
```  
  
### Environment Variables  
  
| Variable | Default | Notes |  
|---|---|---|  
| `EMBED_PYTHON_BIN` | `/usr/local/bin/python` | Python executable path |  
| `EMBED_SCRIPT_DIR` | `/var/www/sofi/app/cli/disclosure_ai` | Directory containing `embed.py`, `rerank.py`, `indexer.py` |  
| `EMBED_BI_ENCODER_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | **Must match at index and query time** |  
| `EMBED_CROSS_ENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model |  
| `RERANK_MIN_SCORE` | `-8.5` | Hard logit floor in `rerank.py` |  
| `RERANK_GAP_THRESHOLD` | `2.5` | Max logit gap from top score in `rerank.py` |  
| `RERANK_MAX_SUGGESTIONS` | `10` | Maximum suggestions returned by `rerank.py` |  
| `DISCLOSURE_EMBED_LOG_FILE` | `var/log/disclosure-embed-YYYY-MM-DD.log` | Override log path for indexer |  
  
> **Critical:** changing `EMBED_BI_ENCODER_MODEL` requires a full re-index — old vectors become incomparable.  
  
Cache pool: `cache.disclosure.ai_suggestions`, TTL 3600 s.  
  
---  
  
## Python Scripts  
  
| Script | Purpose |  
|---|---|  
| `search.py` | stdin: `{"query":"...","type":1,"term_start":202301,"limit":60}` → stdout: `{"entity_ids":[42,7,...]}` — embed query + cosine similarity in Python/numpy; no PHP vector math |  
| `rerank.py` | stdin: `{"query":"...","candidates":[...]}` (or `"queries":[...]`) → stdout: `{"results":[{"id":N,"confidence":F}]}` — already filtered and normalised |  
| `indexer.py` | Bulk-index positions/reports into `disclosure_ai_embedding`; reads `.env`/`.env.local` automatically |  
| `embed.py` | Legacy single-text embedder (stdin: `{"texts":[...]}` → stdout: `{"embeddings":[[...]]}`) — no longer called by PHP; kept for manual testing |  
| `disclosure_ai/` | Package used by `indexer.py`: `config.py`, `db.py`, `embedder.py`, `log.py` |  
  
**`indexer.py` flags:**  
```bash  
python indexer.py --type=all                           # positions + reportspython indexer.py --type=position --term-start=202601python indexer.py --type=all --force                   # re-index existing rowspython indexer.py --type=all -v                        # verbose logging```  
  
---  
  
## Frontend Integration  
  
**Ext.Direct calls** (triggered by drag-and-drop onto a question node):  
  
| Action | Backend method | Key params |  
|---|---|---|  
| Position suggestions | `aiPositionSuggestions` | `disclosureQuestionId`, `termStart`, `termEnd` |  
| Report suggestions | `aiReportSuggestions` | `disclosureQuestionId` |  
| Save AI feedback | `saveAiFeedback` | `templateNodeId`, `type`, `itemId`, `rating` (+1 / -1) |  
  
### SmartMapper Wizard  
  
The SmartMapper is a two-step ExtJS wizard (`SmartMapper\Window` → `SmartMapper\SuggestionsPage` + `MappingPage`):  
  
**Step 1 — SuggestionsPage** (`smartmapper/SuggestionsPage.js`)  
- Fires both AI calls in parallel on open (`startLoading`).  
- Renders position and report suggestions side-by-side in two `tq-extendedoptionfield` pickers loaded from in-memory demo stores.  
- Confidence score (%) and thumbs-up/down feedback buttons are rendered inline in the name column via `decorateGrid`/`buildNameRenderer`.  
- Next button is enabled as soon as ≥1 position or report is selected. Validity is tracked by hooking `field.handleModifiedRecords` and the value store `add`/`remove` events; both paths call `updateValidity()`, which calls `setIsValid()` and directly drives `win.updateStatus()`.  
  
**Step 2 — MappingPage** (`wizard/position/MappingPage.js`)  
- Activated when the user clicks Next from step 1.  
- `onActivatePage` reads selected positions. In the standard position wizard it looks up a `sofi-disclosuremanagement-position-positionpage` component; in the SmartMapper layout that component is absent, so it falls back to `this.selectedPositions` which `SmartMapper\Window.onNextClick` pre-sets before navigating.  
- Only positions with `position_type` ≠ 3/4 get a mapping panel; others show a "no mapping needed" notice.  
  
**Save behaviour (`SmartMapper\Window.onSaveClick`)**  
- When only positions are selected: fires `savewizardcontent` with `{ positions, reports: undefined }`.  
- When only reports are selected: fires `savewizardcontent` with `{ reports }`.  
- When **both** are selected: fires a **single** `savewizardcontent` with `{ positions, reports }` (area = `'position'`). `QuestionContainer.onSaveWizard` handles both report and position processing in one pass, preventing the double-event race that caused a `getSections` null crash.  
  
---  
  
## Indexing & Maintenance  
  
### First-Time Setup  
  
Python runs inside the **php** container (venv at `/usr/local`). The `disclosure_ai` package must be installed once into the venv, then the indexer can be run:  
  
```bash  
# 1. Install the disclosure_ai package into the venv (run once, or after code changes)  
docker compose exec -u root php bash -c "  
  cd /var/www/sofi/app/cli/disclosure_ai  /usr/local/bin/pip install -e . -q"  
  
# 2. Run the indexer to populate disclosure_ai_embedding  
docker compose exec php /usr/local/bin/python3 /var/www/sofi/app/cli/disclosure_ai/indexer.py --type=all  
```  
  
> **Note:** The `-u root` flag is required for the pip install step because `/usr/local` is owned by root. The indexer itself runs as the normal container user.  
  
### When to Re-index  
  
| Trigger | Command |  
|---|---|  
| New/changed positions | `docker compose exec php /usr/local/bin/python3 .../indexer.py --type=position [--force]` |  
| New/changed reports | `docker compose exec php /usr/local/bin/python3 .../indexer.py --type=report [--force]` |  
| Model change | Delete `disclosure_ai_embedding`, then re-run with `--type=all --force` |  
| Term rollover | `docker compose exec php /usr/local/bin/python3 .../indexer.py --type=position --term-start=<6-digit-term> --force` |  
  
Full path for brevity: `/var/www/sofi/app/cli/disclosure_ai/indexer.py`  
  
### Detect Model Mismatch  
  
```sql  
SELECT embedding_model, COUNT(*) FROM disclosure_ai_embedding GROUP BY embedding_model;  
-- Remove stale rows:  
DELETE FROM disclosure_ai_embedding WHERE embedding_model != 'paraphrase-multilingual-MiniLM-L12-v2';  
```  
  
### Rebuild PHP Image  
  
Required after changing Python dependencies in the Dockerfile venv:  
```bash  
docker compose build php```  
  
---  
  
## Health Checks & Troubleshooting  
  
```bash  
# Verify embeddings are indexed  
docker compose exec mysql mysql -uroot -psofi sofi \  
    -e "SELECT type, COUNT(*), MAX(updated_at) FROM disclosure_ai_embedding GROUP BY type;"  
# Clear suggestion cache  
docker compose exec php php bin/console cache:pool:clear cache.disclosure.ai_suggestions  
  
# Tail AI-related log entries  
docker compose exec php tail -f var/log/dev.log | grep -i "EmbeddingService\|RerankingService\|AiSuggestion"  
  
# Smoke-test CLI scripts directly  
echo '{"texts":["test"]}' | python3 /var/www/sofi/app/cli/disclosure_ai/embed.py  
```  
  
| Symptom | Likely cause | Fix |  
|---|---|---|  
| No suggestions | No embeddings indexed | `python indexer.py --type=all` |  
| No suggestions | Wrong `EMBED_PYTHON_BIN` or `EMBED_SCRIPT_DIR` | Check env vars |  
| Wrong suggestions | Model mismatch (index vs query) | Check `embedding_model` column; re-index |  
| Slow first load (~27–30 s) | Model loading on each CLI spawn | Expected; cached for 1 h after first call |  
  
---  
  
## Known Gotchas  
  
1. **`term_start` format** — Positions use 6-digit terms (`000000`, `202301`). Indexing under `term_start=2026` (4-digit) will never be found. The `hasEmbeddings` / `findSimilar` queries use `term_start <= :termStart` to cover global positions (`term_start=0`).  
  
2. **`language_id` must be configured** — Default is `2`. If `position_dict` rows only exist for a specific `language_id`, queries return 0 rows. Check `EMBED_BI_ENCODER_MODEL` env and the language setting.  
  
3. **Model mismatch silent failure** — Mismatched embedding spaces produce plausible but wrong cosine similarities inside `search.py`. Always check the `embedding_model` column after changing models. `EMBED_BI_ENCODER_MODEL` must match the value used at index time.  
  
4. **Keyword fallback for reports** — Zero-score candidates are excluded from `broadKeywordScore()` for reports (but not positions). Report names without descriptions produce false cross-encoder matches, so only keyword-matched reports are passed to the reranker.  
  
5. **Linux case sensitivity** — PHP namespace is `Ai\` (lowercase `i`). Directory must be `src/SoFi/DisclosureManagement/Ai/`. Use `git mv` to rename on Linux.  
  
6. **Docker image bakes models** — `pip install` and model downloads run at image build time. A `docker compose build python` is required after changing `requirements.txt` or model names in the Dockerfile.  
  
---  
  
## Additional Resources  
  
| What | Where |  
|---|---|  
| paraphrase-multilingual-MiniLM-L12-v2 model card | [huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |  
| cross-encoder/ms-marco-MiniLM-L-6-v2 model card | [huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2) |
| ONNX Concepts | [https://onnx.ai/onnx/intro/concepts.html](https://onnx.ai/onnx/intro/concepts.html) |
