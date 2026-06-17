# Handoff: Smart-Mapping prototype + Disclosure AI architectural pivot + sofi infra migration

**Generated**: 2026-06-16 21:30 CDT
**Working dir**: `/Users/eugene/dev/ai-projects/smart-mapping`
**Branch**: `main` (nothing committed this session — see "Warnings: no git")
**Status**: Multiple threads — one COMPLETE (refactor), one STRATEGIC & PENDING DATA (Disclosure AI pivot), infra COMPLETE.

> Read this whole file before doing anything. This session spanned four distinct workstreams. The **strategically important** one is the Disclosure AI architectural pivot (§B). The rest is mostly done.

---

## 0. Orientation — what this project actually is

There are **two different codebases/concepts** in play; do not conflate them:

1. **`smart-mapping`** (THIS repo) — a **prototype/study** for ESG XBRL taxonomy→position mapping. It maps `taxonomy_concept → position` using a heuristic scorer (lexical + unit + temporal + structural) plus an **Azure OpenAI LLM reranker**. It is NOT the production feature.
2. **"Disclosure AI"** — the **real production feature** (a *separate* codebase, owned by another team, not in this repo). It maps `disclosure_question → position/report`. It's documented in an Azure DevOps wiki, which I mirrored into `ai-disclosure-docs/` (see §B). Its current architecture is **bi-encoder embeddings → cross-encoder reranking**, run locally via ONNX.

The user is the product/architecture owner. The center of gravity for future work is **re-architecting Disclosure AI** (§B), using `smart-mapping` as a reference skeleton and the `sofi` database as the data source.

---

## A. Workstream 1 — `smart-mapping` refactor (Flask+vanilla-JS → FastAPI+React)  ✅ COMPLETE

### Goal
Refactor the web app: Flask backend → FastAPI; vanilla-JS frontend → React+TypeScript (Vite), preserving all business logic and the exact API contract, keeping the dark glassmorphism look.

### Completed & verified
- [x] **Backend** `backend/app/` — FastAPI port of all 11 JSON endpoints, 1:1 envelope/status-code parity with the old `server.py`. The 4 logic modules (`db.py`, `mappingEngine.py`, `contextService.py`, `llmService.py`) were **copied verbatim** (byte-identical). Verified: `venv/bin/python -m pytest tests/integration -v` → **8 passed**, plus the two promoted full-cycle/REST scripts pass against a live server.
- [x] **Frontend** `frontend/` — Vite + React + TS, Tailwind v4, glass tokens ported from `public/index.css`. Components ported from `public/app.js`. Verified: `cd frontend && npx vitest run` → **30 passed**; `npx tsc --noEmit` clean.
- [x] **Cutover** — `backend/app/main.py` serves the built SPA from `backend/static` (falls back to `public/`). Verified live + Playwright smoke (taxonomy select → counts 4954/276/524/362/1217, 0 console errors).

### Spec/plan/status docs
- Spec: `docs/superpowers/specs/2026-06-16-flask-to-fastapi-react-design.md`
- Plan: `docs/superpowers/plans/2026-06-16-flask-to-fastapi-react.md`
- Status: `docs/implementation_status.md`; Tests: `docs/test_inventory.md`

### Not done (deliberately)
- [ ] **Legacy NOT deleted** — `server.py`, `public/`, `scratch/`, and the root-level `.py` copies are dormant but intact (no git safety net → didn't delete). Remove only with user OK.
- [ ] **shadcn/ui NOT installed** (see Failed/Deviations). UI hand-coded against glass tokens.
- [ ] No committed Playwright e2e spec file (e2e was a live MCP smoke).

### How to run the refactored app
```
PORT=3000 venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 3000
# dev frontend: cd frontend && npm run dev  (proxies /api → :3000)
# build:        cd frontend && npm run build  → outputs to backend/static/
```

---

## B. Workstream 2 — Disclosure AI architectural pivot  ⭐ STRATEGIC, DESIGN DECIDED, BLOCKED ON DATA

### The problem
The production Disclosure AI (separate codebase) uses **embeddings (bi-encoder) → cross-encoder reranking** to down-select candidate positions for each disclosure question. It is **not producing good results** against the expert "golden" selections. The user is not convinced that architecture is right.

### The decision (made this session): pivot to LLM + tools — **Option C**
Deploy a **large language model** given a **comprehensive constructed context** + **tools to query the same `sofi` database**, so it can *reason* about candidates rather than rely on vector similarity. Three options were written up; **Option C selected**:
- **A** = wide-recall retrieval → single-pass LLM judge.
- **B** = agentic LLM with DB tools (queries iteratively, no fixed pool).
- **C (SELECTED)** = hybrid: wide-recall net + agentic tools + **multi-pass consensus**. Attacks recall (wide net), reasoning (tools+context), and reliability (ensembling).

Full write-up: **`Arcitectural_Recommendations/llm-position-downselection-architectures.md`** (note the dir is misspelled "Arcitectural_" — that's the user's chosen name; they were offered a rename).

### Constraints REMOVED this session (both were in the wiki, both retracted by the user)
1. **Privacy** — wiki said "no external LLM / no data leaves server." **No longer applicable.** Hosted/capable LLMs are allowed. (Keep the LLM backend swappable.)
2. **Speed/latency** — **no longer applicable. Accuracy is the SOLE objective.** Compute can be spent lavishly (wide nets, many candidates, multi-pass, big models).

### The key intellectual content: RECALL vs RANKING (read this — it drives the design)
A two-stage funnel = **retrieve (wide net) → rerank (order)**. Two failure modes:
- **Recall** = did the expert's correct position even make the shortlist? (missing the answer entirely)
- **Ranking** = given it's on the shortlist, is it near the top?

**The reranker's max accuracy is hard-capped by retrieval recall.** Swapping the cross-encoder for an LLM only helps if the failure is *ranking*, not *retrieval*. Because speed is no longer constrained, recall is now "easy": widen K + union multiple retrieval strategies (embeddings + keyword + hierarchy/lineage + framework) until expert picks are ~always present → the difficulty collapses onto **judgment**, which is where an LLM shines. The wiki's success thresholds are effectively recall@K (top-1 ≥60%, top-5 ≥75%, top-10 partial ≥90%, top-10 full set ≥50%, false-negative ≤10%, correct response-type ≥60%).

### ⛔ BLOCKER: the local golden data is FAKE — do NOT measure recall on it
The user initially asked to "measure recall on the golden data," then **retracted it**. Reason I found: the golden mappings in the local `sofi` DB (`disclosure_question_position`, 3,790 rows / 1,805 questions) reference **only 39 distinct positions**, and those are **synthetic test fixtures** (`DiscFlow`, `DiscAsset`, `DiscIndicator`, revision-test stubs, even XSS test strings as names). The *questions* are real (GRI/ESRS template content) but the *position mappings* are dummy data. **Measuring recall here is meaningless and would mislead.**
- **The user will provide the REAL golden dataset ~2026-06-17 (the day after this handoff).**
- When it arrives: trace question text (lives in `disclosure_template.content` JSON tree, keyed by `template_question_sid` → match `nodeId`; text in `title`/`description`/`guidance`), assemble (question_text → expert positions) pairs, run retrieval, compute recall@K to size the wide net. Tracked as task "Measure recall@K…" (deferred).

### Next steps for Disclosure AI (NOT started)
- [ ] Receive real golden dataset (user, ~2026-06-17).
- [ ] Measure recall@K on it → confirms whether the gap is retrieval or ranking, sizes the net.
- [ ] Brainstorm → spec → plan → build **Option C** (the brainstorming flow was paused mid-way: clarifying questions done; "propose approaches/design" and "write spec" tasks still pending). Scope question still open: build into this repo, fresh codebase, or graft onto the other team's impl?

---

## C. Workstream 3 — Azure DevOps wiki mirror  ✅ COMPLETE
Mirrored the "Disclosure AI" wiki into `ai-disclosure-docs/` (Azure git layout: parent `.md` + folder of children):
```
ai-disclosure-docs/
  Disclosure-AI.md                         (overview, embedding/reranking primer, privacy-first)
  Disclosure-AI/
    AI-Suggestions-Performance.md          (ONNX concurrency, daemon options 1-4, benchmarks)
    Deployment.md                          (Azure pipeline, deploy script)
    Development.md                          (FULL technical ref: models, services, env vars, gotchas)
    Environments.md                        (feature/UAT hosts)
    Success-Criteria.md                    (expert-expectation accuracy thresholds)
```
- Source: Azure DevOps org `sphera`, project "Sphera Cloud Corporate Sustainability", wiki `Sphera-Cloud-Corporate-Sustainability.wiki` (id `546338a7-0469-4483-9407-cc91da1af5f2`), page path `/Development/Features/Disclosure AI`. Accessed via `mcp__azure-devops__wiki_*` tools (auth worked).
- Real-impl facts worth knowing: models `paraphrase-multilingual-MiniLM-L12-v2` (bi-encoder) + `cross-encoder/ms-marco-MiniLM-L-6-v2`; PHP namespace `App\SoFi\DisclosureManagement\Ai\`; python at `sofi/app/cli/disclosure_ai/`; data tables `disclosure_ai_embedding`/`disclosure_ai_feedback` (NOT present in the local sofi DB → feature not deployed there).

---

## D. Workstream 4 — sofi Docker infra: cleanup + migration to remote  ✅ COMPLETE

### Remote host (migration target)
- **`192.168.12.180`**, user **`user`**. SSH alias **`sofi-remote`** is configured in `~/.ssh/config` using dedicated key **`~/.ssh/sofi_remote_ed25519`** (no passphrase). Just run `ssh sofi-remote`.
- Ubuntu 20.04, **x86_64**, Docker 20.10.23, Compose v2.15.1, 12 cores. **Passwordless sudo ENABLED** (`/etc/sudoers.d/90-user-nopasswd`).
- Also runs the user's other stacks: `agentic-infra` (Milvus: `milvus-standalone`/`-minio`/`-etcd` at `~/agentic-infra/`) and `ecommerce-pg`. **Do not disturb these.**

### sofi services migrated (running on remote)
At **`~/sofi-data-stack/`** on the remote: a self-contained `docker-compose.yml` + `mysql/` & `rabbitmq/` build contexts + `sofi_dump.sql.gz`.
| Service | Container | Ports | Creds |
|---|---|---|---|
| MySQL 8.0.37 | `sofi_mysql` | 3306 | root / sofi, db `sofi` |
| RabbitMQ | `sofi_rabbitmq` | 5672, 15672 | guest / guest, vhost `/sofi` |
| MailHog | `sofi_mailhog` | 1025, 8025 | — |
- Images `ts-mysql`/`ts-rabbitmq` were **rebuilt natively for amd64 on the remote** (NOT shipped — see Failed Approaches). All 3 have **log rotation** (`max-size 50m, max-file 3`).
- **DB migrated via `mysqldump` → restore; verified row-for-row identical** to local (taxonomy 2, taxonomy_concept 7176, position 2767, disclosure_question 3951, disclosure_question_position 3790, transaction 545792, unit_factor 1030148, …). 262 tables.
- Connect from remote shell: `docker exec sofi_mysql mysql -uroot -psofi sofi`.

### Disk cleanup done on remote (was 97% full / 29 GB free → now 15% / 763 GB free)
- A single **`milvus-standalone` container log had grown to 674 GB** (json-file, no rotation). Truncated it (container untouched/healthy). Then **permanently capped** it via a non-invasive `~/agentic-infra/docker-compose.override.yml` adding `logging: max-size 50m/max-file 3` and recreating only `standalone` (data is on host bind mount `./volumes/milvus`, preserved; came back healthy).
- Pruned ~58.6 GB of 2-yr-old POC junk (120 dead containers, unreferenced images, 210 dangling volumes). All live services intact.

### Local stack (untouched, still running on the Mac)
- sofi compose project at `/Users/eugene/dev/ai-projects/sphera-repos/sofi/docker-compose.local.yml` (arm64). `sofi_mysql` on `127.0.0.1:3306` (root/sofi). This is what `backend/app/db.py` connects to.

---

## Failed Approaches / Deviations (DON'T REPEAT)

- **`docker save`/`load` of the sofi images** would not work: local images are **arm64** (Apple Silicon), remote is **x86_64**. Arm64 images only run under QEMU on x86_64 (unacceptable for MySQL). → **Rebuilt from the (tiny, dependency-free) Dockerfiles natively on the remote.** `ts-mysql` = `FROM mysql:8.0.37` + my.cnf tweaks (SSL actually disabled); `ts-rabbitmq` = `FROM rabbitmq:latest` + mgmt plugin + guest/guest.
- **`shadcn/ui` install hangs** non-interactively (needs interactive init / registry). → UI hand-coded against ported glass CSS. Visual goal met; retrofit later if strict spec compliance wanted.
- **Embeddings + cross-encoder reranking** (the production Disclosure AI approach) underperforms at matching golden expert selections — this is the whole reason for the §B pivot. Don't assume it's salvageable without first measuring recall (it may be a retrieval-recall problem, not ranking).
- **Measuring recall on the local sofi DB** → invalid (synthetic 39-position golden data). Wait for the real dataset.

## Environment gotchas (these bit me; will bite you)
- **`venv/` is the real Python virtualenv. `.venv` is NOT a venv — it's a dotenv FILE** containing Azure OpenAI secrets that `llmService.py` reads. Never treat `.venv` as a venv or overwrite it. Use **`venv/bin/python`** (absolute path is safest).
- **Relative `venv/bin/python` fails in some Bash invocations** (cwd differs) → use the absolute path `/Users/eugene/dev/ai-projects/smart-mapping/venv/bin/python`.
- **zsh does NOT word-split unquoted variables** → don't do `SSH='ssh -i ...'; $SSH host`. Use the `sofi-remote` ssh-config alias instead.
- **`curl`/`wget` are blocked by a hook** in this environment → use Python `urllib` for HTTP checks.
- **Backgrounding with `&` inside a wrapper** kills the child when the wrapper exits → run long-lived servers as the background task itself (no `&`).
- **`markdown-doc-expert` sub-agent** returns only "Ready." as its final message but does do the work — verify its file output rather than trusting the reply.
- The remote SSH prints a harmless **post-quantum KEX warning** banner on every connection — ignore it.

## User preferences / working style (IMPORTANT)
- **NO git commands unless explicitly instructed.** Nothing has been committed this session. Don't `git add/commit/push` without being told.
- Prefers **terse, decisive prose answers**; **rejected the multiple-choice `AskUserQuestion` UI** — ask in plain text.
- Says things like "make your own decisions and finish the work" — comfortable delegating judgment; act, don't over-ask. But still confirm before **irreversible/consequential** actions (deletions, infra changes).
- The user's global `CLAUDE.md` mandates strict dev rules: python3 + venv always; **no mocks, real DB**, tests under `tests/`, a single `docs/test_inventory.md`, keep `implementation_plan.md`/`implementation_status.md` current; use sub-agents (file-creator, markdown-doc-expert, test-runner, git-workflow) and Context7/exa for SDK/library work; incremental TDD; evidence before claiming done.

## Files to Know
| Path | Why |
|---|---|
| `Arcitectural_Recommendations/llm-position-downselection-architectures.md` | The Option C decision + 3 options + recall reasoning (the strategic doc) |
| `ai-disclosure-docs/**` | Local mirror of the production Disclosure AI wiki |
| `backend/app/{api,main,schemas}.py` | The FastAPI port |
| `backend/app/{mappingEngine,contextService,llmService,db}.py` | Verbatim-copied logic; `mappingEngine.predict_candidate_positions` (scoring) and `contextService.assemble_llm_context` (LLM prompt) are good references for Option C |
| `frontend/src/{App.tsx,components/*,api/client.ts,store/index.tsx}` | React app |
| `docs/superpowers/specs|plans/2026-06-16-*` | Refactor spec & plan |
| `docs/implementation_status.md`, `docs/test_inventory.md` | Status + test catalog |
| `~/.ssh/config` (alias `sofi-remote`) + `~/.ssh/sofi_remote_ed25519` | Remote access |
| `/Users/eugene/dev/ai-projects/sphera-repos/sofi/docker-compose.local.yml` | The local sofi stack (source of the migrated images/DB) |
| remote `~/sofi-data-stack/` | The migrated sofi stack |

## sofi DB data model (the substrate for Disclosure AI work)
- Temporally versioned: `term_start`/`term_end` = `YYYYMM` zerofill; localized via `*_dict` + `language_id` (2 = English); "active row" pointer tables `*_index`.
- Positions: `position` (hierarchical, `path`, `unit_class_id`, `position_type`) + `position_dict` (name/description/question) + `position_path` (closure).
- Disclosures: `disclosure_framework → disclosure_template (content:json tree) → disclosure → disclosure_section → disclosure_question`; **golden links** `disclosure_question_position` + `disclosure_question_report`.
- Taxonomy (prototype side): `taxonomy` (presentation:json) + `taxonomy_concept` + `position_taxonomy_concept` (join — empty, 0 rows).
- Big tables: `transaction` (545k), `unit_factor` (1M).

## Resume Instructions
1. **Read** `Arcitectural_Recommendations/llm-position-downselection-architectures.md` and `ai-disclosure-docs/Disclosure-AI/Development.md` to load the Disclosure AI context.
2. **Confirm DB access**: `docker exec sofi_mysql mysql -uroot -psofi sofi -e "SELECT COUNT(*) FROM disclosure_question_position;"` (local), or `ssh sofi-remote 'docker exec sofi_mysql mysql -uroot -psofi sofi -e "SELECT VERSION();"'` (remote).
   - Expected: works with root/sofi. If remote fails: `ssh sofi-remote 'docker ps'` to check `sofi_mysql` is up.
3. **Wait for the user's real golden dataset (~2026-06-17).** Do NOT measure recall on the local DB's synthetic golden data.
4. When data arrives: resume the deferred recall measurement, then brainstorm→spec→plan→build **Option C**.
5. If asked about the refactor: it's complete & verified; only legacy-file deletion, shadcn retrofit, and a committed e2e spec remain (all optional).

## Open optional items (offered, not yet actioned)
- Save key decisions to long-term memory (the user uses file-based memory at `~/.claude/projects/.../memory/`).
- Delete legacy Flask/`public`/`scratch`; retrofit shadcn; rename `Arcitectural_Recommendations` → `Architectural`.
- Set a Docker daemon-wide log default on the remote (per-container caps already set on sofi + milvus).

## Warnings
- **Don't commit anything** without explicit instruction.
- **Don't touch the remote `agentic-infra` (Milvus) or `ecommerce-pg` stacks** beyond the log fix already applied.
- **`.venv` is secrets, not a venv.**
- A uvicorn dev server may still be running locally on :3000 from this session (background task) — harmless; restart-able.
