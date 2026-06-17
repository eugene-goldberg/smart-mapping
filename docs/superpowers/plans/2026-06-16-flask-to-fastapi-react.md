# Flask -> FastAPI + React Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Flask backend with FastAPI and the vanilla-JS frontend with a React + TypeScript (Vite, Tailwind, shadcn/ui) app, preserving all business logic, the exact API contract, and the dark glassmorphism look.

**Architecture:** Backend-first, parity-gated migration. Stand up FastAPI serving the existing `public/` assets plus all APIs and prove API parity with promoted integration tests; then build the React UI against the proven API; then cut over and remove Flask. The synchronous `pymysql` pool and the heuristic/LLM logic move verbatim under `backend/app/`.

**Tech Stack:** FastAPI, uvicorn, pymysql (sync, run in FastAPI threadpool), Pydantic v2; React 18 + TypeScript, Vite, Tailwind CSS, shadcn/ui; pytest + FastAPI TestClient, Vitest + React Testing Library, Playwright.

---

## Conventions & Pre-Flight (read before any task)

These project rules are NON-NEGOTIABLE and apply to every task below:

- **Python:** always `python3` and the project virtualenv. Activate `venv` (or `.venv`) before running any Python or pytest command.
- **Sub-agents:** create/modify Python and config files via the `file-creator` sub-agent; create/modify `.md` files via the `markdown-doc-expert` sub-agent; run all tests via the `test-runner` sub-agent. Run bash via the `bash-runner` sub-agent.
- **Libraries:** before writing FastAPI, Vite, Tailwind, or shadcn code, consult current docs via the Context7 MCP tool, and check real-world reference patterns via the exa search MCP tool. Do not guess SDK/library behavior.
- **Tests:** real MySQL database, NO mocks, NO hardcoded magic values in production code. All tests live under `tests/`. Intermediate/scratch experiments go under `/tmp`.
- **Test inventory:** keep `docs/test_inventory.md` current — every test's coverage, location, run command, external deps (DB, Azure keys), and type (unit/integration/e2e).
- **Status docs:** keep `docs/implementation_plan.md` and `docs/implementation_status.md` updated; update status after each increment with evidence (command + output/log path).
- **Database:** a live MySQL `sofi` database must be running on `127.0.0.1:3306` (user `root`, password `sofi`) for integration/e2e tests. Read `.env` for Azure OpenAI keys; if absent, the LLM path exercises the existing simulated fallback.
- **GIT:** DO NOT run any git command unless the user has explicitly authorized it. Every "Commit" step below is GATED: run it only with explicit user authorization (via the `git-workflow` sub-agent). Otherwise, treat the increment as complete once its tests pass and record that in `docs/implementation_status.md`.
- **No regressions:** after each increment, run that increment's tests AND the full existing suite (regression).

---

## File Structure (target)

```
backend/
  app/
    __init__.py
    main.py            # FastAPI app: include router, mount built SPA
    api.py             # APIRouter: the 11 JSON endpoints
    schemas.py         # Pydantic request/response models
    db.py              # MOVED unchanged from repo root
    mappingEngine.py   # MOVED unchanged from repo root
    contextService.py  # MOVED unchanged from repo root
    llmService.py      # MOVED unchanged from repo root
  requirements.txt
  static/              # vite build output (gitignored)
frontend/
  index.html
  package.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts
  tailwind.config.js
  postcss.config.js
  components.json      # shadcn config
  src/
    main.tsx
    App.tsx
    index.css          # tailwind layers + ported glass tokens
    types.ts
    api/client.ts
    lib/utils.ts
    lib/format.ts
    state/store.tsx
    components/ui/      # shadcn primitives
    components/Sidebar.tsx
    components/Header.tsx
    components/ConceptTable.tsx
    components/FilterConsole.tsx
    components/PredictionModal.tsx
    components/AnswerModal.tsx
tests/
  integration/         # pytest backend contract/parity (real MySQL)
  frontend/            # vitest + RTL
  e2e/                 # playwright
docs/
  test_inventory.md
  implementation_status.md
```

---

## Increment 0: Project Skeleton & Tooling

### Task 0.1: Create backend package and move Python logic files

**Files:**
- Create: `backend/app/__init__.py` (empty)
- Move (verbatim, no content change): repo-root `db.py` -> `backend/app/db.py`; `mappingEngine.py` -> `backend/app/mappingEngine.py`; `contextService.py` -> `backend/app/contextService.py`; `llmService.py` -> `backend/app/llmService.py`
- Create: `backend/requirements.txt`

- [ ] **Step 1: Copy the four Python files into `backend/app/` unchanged**

Use the bash-runner sub-agent:
```bash
mkdir -p backend/app
cp db.py backend/app/db.py
cp mappingEngine.py backend/app/mappingEngine.py
cp contextService.py backend/app/contextService.py
cp llmService.py backend/app/llmService.py
: > backend/app/__init__.py
```
Note: COPY (not move) for now so the existing Flask app keeps working until cutover (Increment 4). The intra-module imports (`import db`, `import mappingEngine`) still resolve because all four files sit together in `backend/app/`.

- [ ] **Step 2: Create `backend/requirements.txt`**

```
fastapi
uvicorn[standard]
pymysql
openai
python-dotenv
pydantic
```

- [ ] **Step 3: Create/locate the virtualenv and install backend deps**

Use the test-runner/bash-runner sub-agent. If a `venv` or `.venv` already exists, reuse it (do NOT create a new one):
```bash
test -d venv || test -d .venv || python3 -m venv venv
source venv/bin/activate 2>/dev/null || source .venv/bin/activate
pip install -r backend/requirements.txt
```
Expected: installs complete without error.

- [ ] **Step 4: Verify the moved modules import**

```bash
source venv/bin/activate 2>/dev/null || source .venv/bin/activate
cd backend && python3 -c "from app import mappingEngine, contextService, llmService, db; print('imports OK')"
```
Expected: prints `imports OK` (and the db.py import-time connection message if MySQL is up).

- [ ] **Step 5: Commit (GATED — only if user authorized git)**

```bash
git add backend/
git commit -m "chore: scaffold backend package with moved logic modules"
```

### Task 0.2: Create tests skeleton and pytest config

**Files:**
- Create: `tests/__init__.py`, `tests/integration/__init__.py` (empty)
- Create: `backend/pytest.ini`
- Create: `docs/test_inventory.md`, `docs/implementation_status.md`

- [ ] **Step 1: Create empty test package files**

```bash
mkdir -p tests/integration tests/frontend tests/e2e
: > tests/__init__.py
: > tests/integration/__init__.py
```

- [ ] **Step 2: Create `backend/pytest.ini`**

```ini
[pytest]
testpaths = ../tests/integration
python_files = test_*.py
addopts = -v
```

- [ ] **Step 3: Create `docs/test_inventory.md` (initial)**

```markdown
# Test Inventory

| Test | Covers | Location | Run command | Deps | Type |
|---|---|---|---|---|---|
| (to be filled per task) | | | | | |

## External dependencies
- MySQL `sofi` on 127.0.0.1:3306 (root/sofi) — required by integration & e2e tests.
- Azure OpenAI keys in `.env` — optional; absence exercises the simulated LLM fallback.
```

- [ ] **Step 4: Create `docs/implementation_status.md` (initial)**

```markdown
# Implementation Status: Flask -> FastAPI + React Refactor

## Increment 0: Skeleton & tooling — IN PROGRESS
## Increment 1: FastAPI backend (parity) — NOT STARTED
## Increment 2: Frontend scaffold — NOT STARTED
## Increment 3: UI component port — NOT STARTED
## Increment 4: Cutover — NOT STARTED
```

- [ ] **Step 5: Commit (GATED — only if user authorized git)**

```bash
git add tests/ backend/pytest.ini docs/test_inventory.md docs/implementation_status.md
git commit -m "chore: add tests skeleton, pytest config, status/inventory docs"
```

---

## Increment 1: FastAPI Backend (API parity)

The contract to preserve (exact envelopes & status codes) is defined in `server.py` (root) and the spec. FastAPI path operations are plain `def` (threadpool) so `db.py` is reused unchanged.

### Task 1.1: Pydantic schemas

**Files:**
- Create: `backend/app/schemas.py`

- [ ] **Step 1: Create `backend/app/schemas.py`**

```python
from typing import Any, Optional
from pydantic import BaseModel


class MappingCreate(BaseModel):
    positionId: int
    taxonomyConceptId: int


class SuccessEnvelope(BaseModel):
    success: bool = True


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: str
```
Note: responses are returned as plain dicts (to match the existing exact JSON keys like `taxonomies`, `concepts`, `candidates`, `result`, `context`, `results`). Only the request body (`MappingCreate`) is strictly validated by Pydantic. This keeps the envelope byte-compatible with the current Flask output.

- [ ] **Step 2: Commit (GATED)**

```bash
git add backend/app/schemas.py
git commit -m "feat(api): add pydantic request schema"
```

### Task 1.2: Failing parity test for read endpoints

**Files:**
- Create: `tests/integration/test_api_read_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_taxonomies_envelope():
    r = client.get("/api/taxonomies")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["taxonomies"], list)
    if body["taxonomies"]:
        row = body["taxonomies"][0]
        assert "taxonomy_id" in row and "name" in row and "uuid" in row


def test_concepts_envelope():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    if not tax:
        return
    tid = tax[0]["taxonomy_id"]
    r = client.get(f"/api/concepts/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["concepts"], list)
    if body["concepts"]:
        c = body["concepts"][0]
        for key in ("taxonomyConceptId", "identifier", "classification", "mappedStatus", "isAbstract"):
            assert key in c


def test_customer_groups_periods():
    g = client.get("/api/customer-groups").json()
    assert g["success"] is True and isinstance(g["groups"], list)
    p = client.get("/api/periods").json()
    assert p["success"] is True and isinstance(p["periods"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run (via test-runner): `source venv/bin/activate 2>/dev/null || source .venv/bin/activate; python3 -m pytest tests/integration/test_api_read_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.app.main` (not created yet).

### Task 1.3: Implement the APIRouter (read endpoints) and FastAPI app

**Files:**
- Create: `backend/app/api.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/api.py` (read endpoints)**

Port these endpoints 1:1 from `server.py`, preserving SQL and envelopes. Path operations are plain `def`.

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import db, mappingEngine, contextService, llmService

router = APIRouter(prefix="/api")


def _error(message: str, status: int):
    return JSONResponse({"success": False, "error": message}, status_code=status)


@router.get("/taxonomies")
def get_taxonomies():
    try:
        sql = """
            SELECT t.taxonomy_id, td.name, t.uuid, t.created
            FROM taxonomy t
            JOIN taxonomy_dict td ON t.taxonomy_id = td.taxonomy_id
            WHERE td.language_id = 2
        """
        return {"success": True, "taxonomies": db.query(sql)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/concepts/{taxonomy_id}")
def get_concepts(taxonomy_id: int):
    try:
        return {"success": True, "concepts": mappingEngine.get_classified_concepts(taxonomy_id)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/predictions/{taxonomy_id}/{concept_id}")
def get_predictions(taxonomy_id: int, concept_id: int):
    try:
        candidates = mappingEngine.predict_candidate_positions(taxonomy_id, concept_id, 5)
        return {"success": True, "candidates": candidates}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/customer-groups")
def get_customer_groups():
    try:
        sql = """
            SELECT s.site_id as customerSiteId, sd.name as customerName
            FROM site s
            JOIN site_dict sd ON s.site_id = sd.site_id AND s.term_start = sd.term_start
            WHERE s.parent_site_id IS NULL
              AND sd.language_id = 2
              AND s.term_end IS NULL
            ORDER BY sd.name ASC
        """
        return {"success": True, "groups": db.query(sql)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/sites/{customer_site_id}")
def get_sub_sites(customer_site_id: int):
    try:
        sql = """
            SELECT s.site_id as siteId, sd.name as siteName
            FROM site s
            JOIN site_dict sd ON s.site_id = sd.site_id AND s.term_start = sd.term_start
            JOIN site_path sp ON s.site_id = sp.descendant_site_id AND s.term_start = sp.descendant_term_start
            WHERE sp.ancestor_site_id = %s
              AND sd.language_id = 2
              AND s.term_end IS NULL
              AND sp.depth > 0
            ORDER BY sd.name ASC
        """
        return {"success": True, "sites": db.query(sql, (customer_site_id,))}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/periods")
def get_periods():
    try:
        sql = "SELECT DISTINCT term_start as period FROM transaction ORDER BY period DESC LIMIT 50"
        rows = db.query(sql)
        return {"success": True, "periods": [r["period"] for r in rows]}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/llm-context/{taxonomy_id}/{concept_id}")
def get_llm_context(taxonomy_id: int, concept_id: int):
    try:
        return {"success": True, "context": contextService.assemble_llm_context(taxonomy_id, concept_id)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/llm-predictions/{taxonomy_id}/{concept_id}")
def get_llm_predictions(taxonomy_id: int, concept_id: int):
    try:
        return {"success": True, "results": llmService.query_llm_rerank(taxonomy_id, concept_id)}
    except Exception as e:
        return _error(str(e), 500)
```

- [ ] **Step 2: Create `backend/app/main.py`**

```python
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router

app = FastAPI(title="Smart-Mapping")
app.include_router(router)

# Static SPA mount is added in Increment 2/4. For Increment 1 we serve the
# existing root-level public/ assets so the app keeps working during migration.
_PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "public")
if os.path.isdir(_PUBLIC_DIR):
    app.mount("/", StaticFiles(directory=_PUBLIC_DIR, html=True), name="public")
```

- [ ] **Step 3: Run the read-endpoint test to verify it passes**

Run: `python3 -m pytest tests/integration/test_api_read_endpoints.py -v`
Expected: PASS (requires live MySQL `sofi`).

- [ ] **Step 4: Commit (GATED)**

```bash
git add backend/app/api.py backend/app/main.py tests/integration/test_api_read_endpoints.py
git commit -m "feat(api): port read endpoints to FastAPI router"
```

### Task 1.4: Mapping write/delete endpoints (POST/DELETE) + validation

**Files:**
- Modify: `backend/app/api.py` (add endpoints)
- Create: `tests/integration/test_api_mappings.py`

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _first_concrete_concept():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    tid = tax[0]["taxonomy_id"]
    concepts = client.get(f"/api/concepts/{tid}").json()["concepts"]
    concrete = [c for c in concepts if not c["isAbstract"]]
    return tid, concrete[0]


def test_post_mapping_validation_missing_fields():
    r = client.post("/api/mappings", json={})
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_post_mapping_nonexistent_position():
    _, concept = _first_concrete_concept()
    r = client.post("/api/mappings", json={"positionId": 999999999, "taxonomyConceptId": concept["taxonomyConceptId"]})
    assert r.status_code == 404
    assert r.json()["success"] is False


def test_map_then_unmap_roundtrip():
    tid, concept = _first_concrete_concept()
    cid = concept["taxonomyConceptId"]
    cands = client.get(f"/api/predictions/{tid}/{cid}").json()["candidates"]
    pid = cands[0]["positionId"]

    created = client.post("/api/mappings", json={"positionId": pid, "taxonomyConceptId": cid})
    assert created.status_code == 200 and created.json()["success"] is True

    deleted = client.delete(f"/api/mappings/{pid}/{cid}")
    assert deleted.status_code == 200 and deleted.json()["success"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_api_mappings.py -v`
Expected: FAIL — 404/405 because POST/DELETE not yet defined.

- [ ] **Step 3: Add the endpoints to `backend/app/api.py`**

Append to `backend/app/api.py` (and add `from fastapi import Body` at top, plus import the schema):

```python
from fastapi import Body
from .schemas import MappingCreate


@router.post("/mappings")
def save_mapping(payload: MappingCreate = Body(...)):
    position_id = payload.positionId
    taxonomy_concept_id = payload.taxonomyConceptId
    if not position_id or not taxonomy_concept_id:
        return _error("positionId and taxonomyConceptId are required.", 400)
    try:
        pos_check = db.query("SELECT position_id FROM position_index WHERE position_id = %s", (position_id,))
        if not pos_check:
            return _error(f"Position with ID {position_id} does not exist.", 404)

        concept_check = db.query(
            "SELECT taxonomy_concept_id, identifier FROM taxonomy_concept WHERE taxonomy_concept_id = %s",
            (taxonomy_concept_id,),
        )
        if not concept_check:
            return _error(f"Taxonomy concept with ID {taxonomy_concept_id} does not exist.", 404)

        identifier = concept_check[0]["identifier"]
        if not identifier or len(identifier) < 3:
            return _error("Taxonomy concept identifier is invalid.", 400)

        db.query(
            "INSERT IGNORE INTO position_taxonomy_concept (position_id, taxonomy_concept_id) VALUES (%s, %s)",
            (position_id, taxonomy_concept_id),
        )
        return {"success": True, "message": "Mapping successfully persisted."}
    except Exception as e:
        return _error(str(e), 500)


@router.delete("/mappings/{position_id}/{concept_id}")
def delete_mapping(position_id: int, concept_id: int):
    try:
        db.query(
            "DELETE FROM position_taxonomy_concept WHERE position_id = %s AND taxonomy_concept_id = %s",
            (position_id, concept_id),
        )
        return {"success": True, "message": "Mapping successfully removed."}
    except Exception as e:
        return _error(str(e), 500)
```
Note on the 400-empty-body case: FastAPI returns 422 for a body that fails Pydantic validation. To preserve the legacy 400 contract, accept the body as optional raw dict instead. Replace the signature with `payload: dict = Body(default={})` and read `payload.get("positionId")` / `payload.get("taxonomyConceptId")`, mirroring the Flask `request.json or {}` behavior exactly. Verify the chosen approach against the test in Step 1 (it expects 400, not 422).

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_api_mappings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (GATED)**

```bash
git add backend/app/api.py tests/integration/test_api_mappings.py
git commit -m "feat(api): port mapping create/delete endpoints with legacy 400/404 contract"
```

### Task 1.5: find-answer endpoint

**Files:**
- Modify: `backend/app/api.py`
- Create: `tests/integration/test_api_find_answer.py`

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_find_answer_requires_params():
    r = client.get("/api/find-answer")
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_find_answer_returns_result_shape():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    tid = tax[0]["taxonomy_id"]
    concepts = client.get(f"/api/concepts/{tid}").json()["concepts"]
    cid = [c for c in concepts if not c["isAbstract"]][0]["taxonomyConceptId"]
    r = client.get(f"/api/find-answer?taxonomyId={tid}&taxonomyConceptId={cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "found" in body["result"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_api_find_answer.py -v`
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Add the endpoint to `backend/app/api.py`**

Add `from fastapi import Query` at top, then:

```python
@router.get("/find-answer")
def find_answer(
    taxonomyId: int = Query(default=None),
    taxonomyConceptId: int = Query(default=None),
    customerSiteId: int = Query(default=None),
    siteId: int = Query(default=None),
    period: int = Query(default=None),
):
    if not taxonomyId or not taxonomyConceptId:
        return _error("taxonomyId and taxonomyConceptId are required parameters.", 400)
    try:
        result = mappingEngine.find_best_answer(
            taxonomy_id=taxonomyId,
            taxonomy_concept_id=taxonomyConceptId,
            customer_site_id=customerSiteId,
            site_id=siteId,
            period=period,
        )
        return {"success": True, "result": result}
    except Exception as e:
        return _error(str(e), 500)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_api_find_answer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit (GATED)**

```bash
git add backend/app/api.py tests/integration/test_api_find_answer.py
git commit -m "feat(api): port find-answer endpoint"
```

### Task 1.6: Promote scratch scripts as full-cycle parity tests + run server

**Files:**
- Create: `tests/integration/test_full_cycle.py` (ported from `scratch/test_full_cycle.py`)
- Create: `tests/integration/test_rest_api.py` (ported from `scratch/test_rest_api.py`)

- [ ] **Step 1: Copy the two scratch scripts into tests/integration unchanged in logic**

```bash
cp scratch/test_full_cycle.py tests/integration/test_full_cycle.py
cp scratch/test_rest_api.py tests/integration/test_rest_api.py
```
These hit `http://localhost:3000` over HTTP, so they validate the running uvicorn server end-to-end (not just TestClient).

- [ ] **Step 2: Start the FastAPI server on port 3000 (background) and tail logs**

Run (background, via test-runner per long-running rule):
```bash
source venv/bin/activate 2>/dev/null || source .venv/bin/activate
PORT=3000 uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 3000 > /tmp/test_logs/uvicorn.log 2>&1 &
sleep 2 && tail -n 20 /tmp/test_logs/uvicorn.log
```
Expected: uvicorn running on :3000; db.py connection message in log.

- [ ] **Step 3: Run the two promoted scripts against the live server**

```bash
python3 tests/integration/test_full_cycle.py
python3 tests/integration/test_rest_api.py
```
Expected: both print their `ALL ... TESTS ... SUCCESSFULLY` banners with exit code 0.

- [ ] **Step 4: Run the FULL backend test suite (regression)**

Run: `python3 -m pytest tests/integration -v`
Expected: all pass.

- [ ] **Step 5: Update `docs/test_inventory.md` and `docs/implementation_status.md`**

Add rows for every `tests/integration/*.py` file (covers, location, run cmd, deps=MySQL, type=integration). Mark Increment 1 COMPLETE in status with the pytest output summary.

- [ ] **Step 6: Commit (GATED)**

```bash
git add tests/integration/ docs/test_inventory.md docs/implementation_status.md
git commit -m "test(api): promote full-cycle and rest-api parity tests; backend parity verified"
```

---

## Increment 2: Frontend Scaffold (Vite + TS + Tailwind + shadcn)

### Task 2.1: Initialize Vite React-TS project

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`

- [ ] **Step 1: Scaffold via Vite**

Consult Context7 for the current Vite React-TS template invocation, then (via bash-runner):
```bash
cd frontend && npm create vite@latest . -- --template react-ts
npm install
```

- [ ] **Step 2: Configure dev proxy + build output in `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:3000' },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 3: Verify dev server boots**

```bash
cd frontend && npm run build
```
Expected: build succeeds, output written to `backend/static/`.

- [ ] **Step 4: Gitignore the build output**

Add `backend/static/` to `.gitignore`.

- [ ] **Step 5: Commit (GATED)**

```bash
git add frontend/ .gitignore
git commit -m "chore(frontend): scaffold vite react-ts with api proxy and build output"
```

### Task 2.2: Add Tailwind + shadcn with ported glassmorphism tokens

**Files:**
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/components.json`, `frontend/src/index.css`, `frontend/src/lib/utils.ts`

- [ ] **Step 1: Install and init Tailwind + shadcn**

Consult Context7 for current Tailwind v4/shadcn init steps before running. Then:
```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npx shadcn@latest init
```

- [ ] **Step 2: Port the glass design tokens into `frontend/src/index.css`**

Reproduce the HSL tokens from the existing `public/index.css` `:root` block (lines 6-32) as CSS variables, and keep Tailwind layers. Required tokens (copy values verbatim from `public/index.css`): `--bg-gradient-start`, `--bg-gradient-end`, `--panel-bg`, `--panel-border`, `--text-primary/secondary/muted`, `--accent-blue`, `--accent-purple`, `--success-green`, `--warning-orange`, `--danger-red`, `--border-radius-lg/md`. Set `body` to the radial-gradient background from `public/index.css` lines 41-51.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg-gradient-start: hsl(220, 25%, 7%);
  --bg-gradient-end: hsl(224, 20%, 12%);
  --panel-bg: hsla(220, 20%, 12%, 0.65);
  --panel-border: hsla(220, 10%, 25%, 0.3);
  --text-primary: hsl(210, 20%, 95%);
  --text-secondary: hsl(215, 12%, 70%);
  --text-muted: hsl(215, 10%, 50%);
  --accent-blue: hsl(210, 100%, 60%);
  --accent-purple: hsl(270, 95%, 65%);
  --success-green: hsl(145, 80%, 45%);
  --warning-orange: hsl(35, 90%, 55%);
  --danger-red: hsl(5, 85%, 55%);
  --border-radius-lg: 16px;
  --border-radius-md: 8px;
}

body {
  font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: radial-gradient(circle at 50% 0%, hsl(220, 30%, 12%) 0%, var(--bg-gradient-start) 100%);
  color: var(--text-primary);
  min-height: 100vh;
}
```

- [ ] **Step 3: Map tokens into `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'accent-blue': 'var(--accent-blue)',
        'accent-purple': 'var(--accent-purple)',
        'success-green': 'var(--success-green)',
        'warning-orange': 'var(--warning-orange)',
        'danger-red': 'var(--danger-red)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
        'panel-bg': 'var(--panel-bg)',
        'panel-border': 'var(--panel-border)',
      },
      borderRadius: { lg: 'var(--border-radius-lg)', md: 'var(--border-radius-md)' },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Add the Outfit font link to `frontend/index.html`**

Copy the two `<link rel="preconnect">` tags and the Outfit `<link>` from `public/index.html` lines 8-10 into `frontend/index.html` `<head>`.

- [ ] **Step 5: Build and verify tokens compile**

```bash
cd frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 6: Commit (GATED)**

```bash
git add frontend/
git commit -m "feat(frontend): tailwind + shadcn themed with ported glass tokens"
```

### Task 2.3: Typed API client + shared types

**Files:**
- Create: `frontend/src/types.ts`, `frontend/src/api/client.ts`

- [ ] **Step 1: Create `frontend/src/types.ts`**

Mirror the backend response rows exactly (field names match the SQL aliases / engine output).

```ts
export interface Taxonomy { taxonomy_id: number; name: string; uuid: string; created: string }

export interface Concept {
  taxonomyConceptId: number
  identifier: string
  name: string | null
  type: string | null
  presentationType: string | null
  periodType: string | null
  subGroup: string | null
  isAbstract: boolean
  mappedStatus: 'Mapped' | 'Unmapped'
  mappedPositionId: number | null
  mappedPositionName: string | null
  classification: string
}

export interface Breakdown { lexical: number; unit: number; temporal: number; structural: number }

export interface Candidate {
  positionId: number
  positionName: string
  positionTypeName: string
  unitClassName: string
  score: number
  breakdown: Breakdown
}

export interface CustomerGroup { customerSiteId: number; customerName: string }
export interface SubSite { siteId: number; siteName: string }

export interface AnswerResult {
  found: boolean
  positionId?: number
  positionName?: string
  positionTypeName?: string
  score?: number
  breakdown?: Breakdown
  value?: string | number
  isNumeric?: boolean
  unitName?: string
  period?: number
  occurrenceDate?: string | null
  siteName?: string
  positionPath?: string
  confidence?: string
  historicPreference?: { distinctYears: number; totalTransactions: number; isPreferred: boolean }
  candidates?: Array<Candidate & { historicPreference?: AnswerResult['historicPreference'] }>
}

export interface LlmRanking { positionId: number; positionName: string; rank: number; reasoning: string; suggestedRename: string | null }
export interface LlmResults { targetConcept: string; rankings: LlmRanking[]; simulated?: boolean; debugMessage?: string }
```

- [ ] **Step 2: Create `frontend/src/api/client.ts`**

```ts
import type { Taxonomy, Concept, Candidate, CustomerGroup, SubSite, AnswerResult, LlmResults } from '@/types'

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  const body = await r.json()
  if (!body.success) throw new Error(body.error || 'Request failed')
  return body as T
}

export const api = {
  taxonomies: () => getJson<{ taxonomies: Taxonomy[] }>('/api/taxonomies').then(b => b.taxonomies),
  concepts: (tid: number) => getJson<{ concepts: Concept[] }>(`/api/concepts/${tid}`).then(b => b.concepts),
  predictions: (tid: number, cid: number) =>
    getJson<{ candidates: Candidate[] }>(`/api/predictions/${tid}/${cid}`).then(b => b.candidates),
  customerGroups: () => getJson<{ groups: CustomerGroup[] }>('/api/customer-groups').then(b => b.groups),
  sites: (csid: number) => getJson<{ sites: SubSite[] }>(`/api/sites/${csid}`).then(b => b.sites),
  periods: () => getJson<{ periods: number[] }>('/api/periods').then(b => b.periods),
  llmContext: (tid: number, cid: number) =>
    getJson<{ context: string }>(`/api/llm-context/${tid}/${cid}`).then(b => b.context),
  llmPredictions: (tid: number, cid: number) =>
    getJson<{ results: LlmResults }>(`/api/llm-predictions/${tid}/${cid}`).then(b => b.results),
  findAnswer: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)) })
    return getJson<{ result: AnswerResult }>(`/api/find-answer?${q.toString()}`).then(b => b.result)
  },
  createMapping: async (positionId: number, taxonomyConceptId: number) => {
    const r = await fetch('/api/mappings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positionId, taxonomyConceptId }),
    })
    const b = await r.json(); if (!b.success) throw new Error(b.error); return b
  },
  deleteMapping: async (positionId: number, conceptId: number) => {
    const r = await fetch(`/api/mappings/${positionId}/${conceptId}`, { method: 'DELETE' })
    const b = await r.json(); if (!b.success) throw new Error(b.error); return b
  },
}
```

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no type errors.

- [ ] **Step 4: Commit (GATED)**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts
git commit -m "feat(frontend): typed api client and shared types mirroring backend"
```

### Task 2.4: Install Vitest and add a client smoke test

**Files:**
- Modify: `frontend/package.json`, `frontend/vite.config.ts` (add test config)
- Create: `tests/frontend/api-client.test.ts`

- [ ] **Step 1: Install Vitest + RTL**

```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @testing-library/user-event
```

- [ ] **Step 2: Add test config to `frontend/vite.config.ts`**

Add to the `defineConfig` object:
```ts
  test: { environment: 'jsdom', globals: true, setupFiles: [] },
```

- [ ] **Step 3: Write `tests/frontend/api-client.test.ts` (URL-building, no network)**

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../../frontend/src/api/client'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ json: async () => ({ success: true, periods: [202312] }) })) as any)
})

describe('api client', () => {
  it('unwraps the success envelope', async () => {
    const periods = await api.periods()
    expect(periods).toEqual([202312])
  })
  it('throws on error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ json: async () => ({ success: false, error: 'boom' }) })) as any)
    await expect(api.periods()).rejects.toThrow('boom')
  })
})
```
Note: this is a boundary test of the envelope-unwrapping logic; `fetch` is stubbed only because there is no business logic here, per the project rule that business logic is tested against real systems. The real API is covered by the backend integration tests and the e2e suite.

- [ ] **Step 4: Run the test**

```bash
cd frontend && npx vitest run ../tests/frontend/api-client.test.ts
```
Expected: 2 passed.

- [ ] **Step 5: Update `docs/test_inventory.md`, then commit (GATED)**

```bash
git add frontend/ tests/frontend/ docs/test_inventory.md
git commit -m "test(frontend): vitest setup and api client smoke test"
```

---

## Increment 3: UI Component Port

The reference implementation is the existing `public/app.js` (972 lines) and `public/index.html`. Each component below ports a specific region of that file; line ranges are given so the executor can match behavior exactly. Install each shadcn primitive with `npx shadcn@latest add <name>` before use.

### Task 3.1: State store

**Files:**
- Create: `frontend/src/state/store.tsx`

- [ ] **Step 1: Create the store**

Port the shape of the `state` object in `public/app.js:6-15`. Provide a `useReducer`-backed Context exposing `{ taxonomies, concepts, filteredConcepts, selectedTaxonomy, activeFilter, searchQuery, activeConcept }` plus actions `setTaxonomies`, `selectTaxonomy`, `setConcepts`, `setFilter`, `setSearch`, `setActiveConcept`. Derive `filteredConcepts` from `concepts + activeFilter + searchQuery` exactly per the filter logic in `public/app.js:282-309`. Include an `llmCache` map keyed by `${'${'}taxonomyId}_${'${'}conceptId}` (per `public/app.js:870-880`).

```tsx
import { createContext, useContext, useMemo, useReducer, type ReactNode } from 'react'
import type { Taxonomy, Concept } from '@/types'

interface State {
  taxonomies: Taxonomy[]
  concepts: Concept[]
  selectedTaxonomy: Taxonomy | null
  activeFilter: string
  searchQuery: string
  activeConcept: Concept | null
}

type Action =
  | { t: 'setTaxonomies'; v: Taxonomy[] }
  | { t: 'selectTaxonomy'; v: Taxonomy }
  | { t: 'setConcepts'; v: Concept[] }
  | { t: 'setFilter'; v: string }
  | { t: 'setSearch'; v: string }
  | { t: 'setActiveConcept'; v: Concept | null }

const initial: State = { taxonomies: [], concepts: [], selectedTaxonomy: null, activeFilter: 'all', searchQuery: '', activeConcept: null }

function reducer(s: State, a: Action): State {
  switch (a.t) {
    case 'setTaxonomies': return { ...s, taxonomies: a.v }
    case 'selectTaxonomy': return { ...s, selectedTaxonomy: a.v }
    case 'setConcepts': return { ...s, concepts: a.v }
    case 'setFilter': return { ...s, activeFilter: a.v }
    case 'setSearch': return { ...s, searchQuery: a.v }
    case 'setActiveConcept': return { ...s, activeConcept: a.v }
  }
}

function filterConcepts(concepts: Concept[], filter: string, q: string): Concept[] {
  let r = concepts
  if (filter === 'Quantitative' || filter === 'Narrative' || filter === 'Choice') r = r.filter(c => c.classification === filter)
  else if (filter === 'Unmapped') r = r.filter(c => c.mappedStatus === 'Unmapped' && !c.isAbstract)
  else if (filter === 'Mapped') r = r.filter(c => c.mappedStatus === 'Mapped' && !c.isAbstract)
  const query = q.toLowerCase().trim()
  if (query) r = r.filter(c =>
    c.identifier.toLowerCase().includes(query) ||
    (c.name && c.name.toLowerCase().includes(query)) ||
    (c.subGroup && c.subGroup.toLowerCase().includes(query)))
  return r
}

const Ctx = createContext<{ state: State; dispatch: React.Dispatch<Action>; filteredConcepts: Concept[] } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial)
  const filteredConcepts = useMemo(() => filterConcepts(state.concepts, state.activeFilter, state.searchQuery), [state.concepts, state.activeFilter, state.searchQuery])
  return <Ctx.Provider value={{ state, dispatch, filteredConcepts }}>{children}</Ctx.Provider>
}

export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStore must be used within StoreProvider')
  return v
}
```

- [ ] **Step 2: Write `tests/frontend/store.test.tsx`** — test `filterConcepts` via the provider for each filter + search. (Use RTL `renderHook` with `StoreProvider` wrapper; assert `filteredConcepts` length for a fixture concept array covering Quantitative/Narrative/Mapped/Unmapped/abstract rows.)

- [ ] **Step 3: Run** `cd frontend && npx vitest run ../tests/frontend/store.test.tsx` — Expected: PASS.

- [ ] **Step 4: Commit (GATED)** `git commit -m "feat(frontend): state store with derived filtering"`

### Task 3.2: Sidebar + Header + count badges

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`, `frontend/src/components/Header.tsx`
- shadcn: `select`, `badge`, `button`

**Responsibilities:** Sidebar reproduces `public/index.html:19-84` — brand block, taxonomy `Select` (options from `state.taxonomies`, label `"${name} (UUID: ${uuid.slice(0,8)}...)"` per `app.js:208-213`), filter nav buttons with live count badges computed per `app.js:263-279`, footer status. Header reproduces `public/index.html:90-104` — search input wired to `setSearch`, profile block. On taxonomy change call `api.concepts` and `setConcepts` (logic from `app.js:93-100, 225-260`).

- [ ] **Step 1:** Implement both components using the shadcn `Select`/`Badge`/`Button`, reading/writing the store. Count badges: `all`, `quantitative`, `narrative`, `choice`, `unmapped`, `mapped` exactly per `app.js:264-271`.
- [ ] **Step 2:** Write `tests/frontend/sidebar.test.tsx` — render with fixture taxonomies/concepts; assert all six badge counts render correct numbers; assert selecting a filter updates active state.
- [ ] **Step 3:** Run vitest — Expected: PASS.
- [ ] **Step 4:** Commit (GATED) `git commit -m "feat(frontend): sidebar, header, live count badges"`

### Task 3.3: ConceptTable

**Files:**
- Create: `frontend/src/components/ConceptTable.tsx`
- shadcn: `table`, `badge`, `button`

**Responsibilities:** Port `renderConceptsTable` (`app.js:312-404`). Columns: identifier (+ subGroup + mapped-info sub-line), data type badge, period style, classification badge (+ status badge), action cell. Classification badge color classes map: Quantitative->accent-blue, Narrative->accent-purple, Choice->success-green, else muted (per `app.js:332-336` and `index.css:450-472`). Abstract rows show "Structural" text and no actions. Concrete rows show "Find Answer" and "Link"/"Link (Mapped)" buttons (per `app.js:345-363`). Empty state per `app.js:313-324`.

- [ ] **Step 1:** Implement using shadcn `Table`. Buttons call props `onFindAnswer(conceptId)` and `onOpenPrediction(conceptId)` (no inline `onclick`).
- [ ] **Step 2:** Write `tests/frontend/concept-table.test.tsx` — fixture with one abstract + one mapped + one unmapped concept; assert: abstract row renders "Structural" and no buttons; mapped row renders mapped-to sub-line + "Link (Mapped)"; classification badge text present; empty-array renders empty state.
- [ ] **Step 3:** Run vitest — Expected: PASS.
- [ ] **Step 4:** Commit (GATED) `git commit -m "feat(frontend): concept table with classification/status badges"`

### Task 3.4: PredictionModal (3 tabs)

**Files:**
- Create: `frontend/src/components/PredictionModal.tsx`
- shadcn: `dialog`, `tabs`, `button`

**Responsibilities:** Port `openPredictionModal` + `renderCandidates` + `triggerLlmReranking` + `renderLlmCandidates` (`app.js:407-585, 869-971`) and the modal markup `index.html:173-235`. Three `Tabs`: (1) Heuristic Candidates — candidate cards with score, breakdown pills (lexical/unit/temporal/structural per `app.js:562-582`), Map/Unmap buttons, and the "currently mapped" highlight (`app.js:496-528`); (2) LLM Reranking — lazy fetch `api.llmPredictions` on first open, cache in store `llmCache`, render rank cards + reasoning + optional `suggestedRename` banner (`app.js:931-971`); (3) LLM Context Preview — lazy fetch `api.llmContext`, render in `<pre>`, copy-to-clipboard button (`app.js:171-186, 451-463`). Map/Unmap call `api.createMapping`/`api.deleteMapping`, then refresh concepts and toast.

- [ ] **Step 1:** Implement. Props: `concept: Concept | null`, `taxonomyId`, `onClose`, `onChanged` (refetch concepts), `toast`. Tab content lazy-loads on tab activation (heuristic loads on open).
- [ ] **Step 2:** Write `tests/frontend/prediction-modal.test.tsx` — stub `api` module; assert: opening renders heuristic candidate cards with score % and four breakdown pills; switching to LLM tab triggers exactly one `llmPredictions` call and renders rank + reasoning; clicking Map calls `createMapping` with correct ids.
- [ ] **Step 3:** Run vitest — Expected: PASS.
- [ ] **Step 4:** Commit (GATED) `git commit -m "feat(frontend): prediction modal with heuristic/LLM/context tabs"`

### Task 3.5: FilterConsole + AnswerModal

**Files:**
- Create: `frontend/src/components/FilterConsole.tsx`, `frontend/src/components/AnswerModal.tsx`
- Create: `frontend/src/lib/format.ts` (period formatter: `"YYYYMM" -> "YYYY-MM"`, per `app.js:690-692, 775-776`)
- shadcn: `dialog`, `select`, `badge`

**Responsibilities:** FilterConsole reproduces `index.html:117-143` + `app.js:666-726`: customer-group `Select` (loads on mount via `api.customerGroups`), operational-site `Select` (disabled until a group is chosen; loads via `api.sites`), period `Select` (via `api.periods`, formatted). Selected values feed AnswerModal. AnswerModal ports `findBestAnswer` (`app.js:728-861`) + markup `index.html:238-292`: giant value card, source-trace grid, resolved path breadcrumbs (split on `/`), confidence badge variant mapping (`Mapped Direct Answer`->success, `High`->info, `Medium`->warning, else danger, per `app.js:810-821`), and the not-found state showing recommended candidate (`app.js:824-851`).

- [ ] **Step 1:** Implement `lib/format.ts` formatter + both components. AnswerModal reads the three filter values from the store/props and calls `api.findAnswer`.
- [ ] **Step 2:** Write `tests/frontend/format.test.ts` (formatter: `202312 -> "2023-12"`, passthrough for non-6-digit) and `tests/frontend/answer-modal.test.tsx` (stub `api.findAnswer`: found-case renders value+unit+confidence badge variant; not-found renders "No Data" + recommended candidate).
- [ ] **Step 3:** Run vitest — Expected: PASS.
- [ ] **Step 4:** Commit (GATED) `git commit -m "feat(frontend): filter console and answer discovery modal"`

### Task 3.6: Toaster + App composition

**Files:**
- Create: `frontend/src/components/AppShell.tsx` (or wire in `App.tsx`)
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- shadcn: `toast` (+ `useToast`)

**Responsibilities:** Replace `showToast` (`app.js:644-664`) with shadcn toast. Compose the full layout (`index.html:16-170` shell: sidebar + main + header + banner + filter console + table) inside `StoreProvider`, wiring: load taxonomies on mount (`app.js:198-222`), load filter console data on mount (`app.js:667-699`), open PredictionModal/AnswerModal from ConceptTable callbacks, refresh concepts after map/unmap.

- [ ] **Step 1:** Implement `main.tsx` (wrap `<App/>` in `StoreProvider` + `<Toaster/>`) and `App.tsx` (layout + data bootstrapping + modal state).
- [ ] **Step 2:** Write `tests/frontend/app.test.tsx` — stub `api`; assert on mount taxonomies populate the sidebar select and customer groups populate the filter console; selecting a taxonomy renders concept rows.
- [ ] **Step 3:** Run `cd frontend && npx vitest run` (full frontend suite, regression) — Expected: all pass.
- [ ] **Step 4:** Build `cd frontend && npm run build` — Expected: succeeds into `backend/static/`.
- [ ] **Step 5:** Update `docs/test_inventory.md` + `docs/implementation_status.md` (Increment 3 COMPLETE with vitest summary). Commit (GATED) `git commit -m "feat(frontend): toaster and full app composition"`

---

## Increment 4: Cutover

### Task 4.1: Serve built SPA from FastAPI static/

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Point the static mount at `backend/static` (built SPA)**

Replace the `public/` mount in `main.py` with:
```python
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .api import router

app = FastAPI(title="Smart-Mapping")
app.include_router(router)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="spa")
```

- [ ] **Step 2: Build the frontend, then start uvicorn on :3000**

```bash
cd frontend && npm run build && cd ..
source venv/bin/activate 2>/dev/null || source .venv/bin/activate
PORT=3000 uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 3000 > /tmp/test_logs/uvicorn.log 2>&1 &
sleep 2 && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
```
Expected: `200` (index.html served) and `/api/taxonomies` still returns the JSON envelope.

- [ ] **Step 3: Commit (GATED)** `git commit -m "feat: serve built react spa from fastapi"`

### Task 4.2: Playwright E2E parity

**Files:**
- Create: `tests/e2e/full_flow.spec.ts` (or `.py` if using pytest-playwright)

- [ ] **Step 1: Write the E2E flow** (run via the test-runner sub-agent + Playwright MCP). Steps against `http://localhost:3000`:
  1. Load app; assert taxonomy select is populated.
  2. Select first taxonomy; assert concept rows render and sidebar badge counts are non-zero.
  3. Type in search; assert the row set narrows.
  4. Click "Link" on a concrete concept; assert PredictionModal opens with candidate cards + score %.
  5. Switch to LLM Reranking tab; assert rank cards (or simulated-fallback) render.
  6. Switch to LLM Context Preview; assert the prompt text and Copy button render.
  7. Click Map on the top candidate; assert success toast and the concept becomes "Mapped".
  8. Click "Find Answer" on a mapped concept; assert AnswerModal shows a value or the "No Data" state.
  9. Re-open the prediction modal; click Unmap; assert it returns to "Unmapped".

- [ ] **Step 2: Run the E2E suite** — Expected: all steps pass against the live server.

- [ ] **Step 3: Update `docs/test_inventory.md`** with the e2e entry. Commit (GATED) `git commit -m "test(e2e): playwright full-flow parity"`

### Task 4.3: Remove Flask and legacy frontend

**Files:**
- Delete: `server.py`, `public/` (entire dir), root-level `db.py`, `mappingEngine.py`, `contextService.py`, `llmService.py`, `scratch/` (now promoted into tests)
- Modify: root `requirements.txt` (point to `backend/requirements.txt` or remove `flask`)

- [ ] **Step 1: Confirm nothing else imports the root copies**

```bash
grep -rn "import server\|from server\|send_static_file\|Flask" --include=*.py . | grep -v backend/ | grep -v venv/
```
Expected: no results (other than this plan/docs). If results appear, STOP and resolve before deleting.

- [ ] **Step 2: Delete legacy files**

```bash
rm -f server.py db.py mappingEngine.py contextService.py llmService.py
rm -rf public/ scratch/
```

- [ ] **Step 3: Update root `requirements.txt`** to remove `flask` (the canonical deps now live in `backend/requirements.txt`).

- [ ] **Step 4: Full regression** — restart uvicorn, run `python3 -m pytest tests/integration -v`, `cd frontend && npx vitest run`, and the e2e suite. Expected: ALL pass.

- [ ] **Step 5: Mark Increment 4 COMPLETE in `docs/implementation_status.md`** with all three suite summaries + the uvicorn log path. Commit (GATED) `git commit -m "chore: remove flask and legacy vanilla-js frontend"`

---

## Definition of Done

- All 11 JSON endpoints respond with byte-compatible envelopes/status codes (backend integration suite green).
- React UI reproduces every behavior of `public/app.js` (component suite + e2e green) with the dark glassmorphism look.
- Single uvicorn process on port 3000 serves the built SPA + APIs.
- Flask, `public/`, and `scratch/` removed; logic modules live under `backend/app/` unchanged.
- `docs/test_inventory.md` and `docs/implementation_status.md` current; full regression passes.
