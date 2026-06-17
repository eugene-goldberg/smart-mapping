# Design: Refactor Web App from Flask + Vanilla JS to FastAPI + React

**Date:** 2026-06-16
**Status:** Approved (design phase)
**Scope:** Replace the Flask backend with FastAPI and the vanilla-JS frontend with a React (TypeScript) app, while preserving all existing business logic and the API contract.

## 1. Goal & Constraints

Port the Smart-Mapping web application transport and presentation layers without changing behavior:

- **Backend:** Flask -> FastAPI ("shell" port). Reuse the existing heuristic/LLM logic and the synchronous `pymysql` connection pool unchanged.
- **Frontend:** Vanilla JS + hand-rolled CSS -> React + TypeScript built with Vite, using Tailwind CSS + shadcn/ui, themed to preserve the current dark glassmorphism aesthetic.
- **API contract is frozen:** the exact JSON envelopes and HTTP status codes are preserved so the backend can be parity-verified before the UI is rebuilt.
- **No mocks, real database, tests live under `tests/`, single test inventory file** (per project development rules).

## 2. Decisions (locked)

| Decision | Choice |
|---|---|
| Backend rewrite depth | FastAPI shell; reuse logic + sync `db.py` as-is |
| React language | TypeScript |
| Build & serve | Vite build, served as static files by FastAPI (single service) |
| UI approach | Rebuild with a component library |
| Component/styling stack | Tailwind CSS + shadcn/ui |
| Aesthetic | Keep current dark glassmorphism (port existing color tokens) |
| Production port | 3000 (env `PORT`, default 3000) |
| Node toolchain | Allowed; pinned via `package.json` |
| Migration strategy | Backend-first, parity-gated |

## 3. Target Repo Structure

```
smart-mapping/
  backend/
    app/
      main.py            # FastAPI app: include router, mount built SPA
      api.py             # APIRouter with the 12 endpoints
      schemas.py         # Pydantic request/response models (mirror current JSON)
      db.py              # MOVED unchanged (sync pymysql pool)
      mappingEngine.py   # MOVED unchanged
      contextService.py  # MOVED unchanged
      llmService.py      # MOVED unchanged
    requirements.txt     # fastapi, uvicorn[standard], pymysql, openai, python-dotenv
    static/              # Vite build output lands here (gitignored)
  frontend/
    index.html
    vite.config.ts
    package.json
    tsconfig.json
    tailwind.config.js
    src/
      main.tsx
      App.tsx
      api/client.ts      # typed fetch wrappers
      types.ts           # TS interfaces mirroring Pydantic models
      lib/               # utilities (formatting, cn helper)
      components/ui/      # shadcn primitives
      components/        # Sidebar, Header, ConceptTable, FilterConsole,
                         # PredictionModal, AnswerModal, Toaster
      state/             # useReducer/Context store
  tests/
    integration/         # pytest: backend contract/parity (real MySQL)
    frontend/            # vitest + React Testing Library
    e2e/                 # Playwright full-flow
  docs/
    test_inventory.md
```

The four Python logic files (`db.py`, `mappingEngine.py`, `contextService.py`, `llmService.py`) move verbatim under `backend/app/`. The heuristic engine, context assembly, and LLM service code stays byte-identical.

## 4. Backend Design (FastAPI shell)

- All 12 endpoints ported 1:1 to an `APIRouter`, preserving exact JSON envelopes:
  - Success: `{"success": true, "<collection>": [...]}` (e.g. `taxonomies`, `concepts`, `candidates`, `groups`, `sites`, `periods`, `result`, `context`, `results`).
  - Error: `{"success": false, "error": "<message>"}` with the same `400` / `404` / `500` status codes used today.
- Path operations are defined as **plain `def`** (not `async def`), so FastAPI executes them in its threadpool and the synchronous `db.py` pool is reused without an async-driver migration.
- `schemas.py` holds Pydantic models for request bodies (e.g. `MappingCreate { positionId: int, taxonomyConceptId: int }`) and typed responses. These Pydantic models are the source of truth for the frontend TypeScript types.
- `main.py` mounts `StaticFiles(directory="static", html=True)` to serve the built SPA at `/`, with the API under `/api/*`. This replaces Flask's `send_static_file` / `send_from_directory` behavior.
- Served via `uvicorn app.main:app`. Production port is env-driven (`PORT`, default `3000`).

### Endpoint inventory (contract to preserve)

1. `GET /api/taxonomies`
2. `GET /api/concepts/{taxonomy_id}`
3. `GET /api/predictions/{taxonomy_id}/{concept_id}`
4. `POST /api/mappings` (body: `positionId`, `taxonomyConceptId`; validates position + concept existence, identifier length >= 3; `INSERT IGNORE`)
5. `DELETE /api/mappings/{position_id}/{concept_id}`
6. `GET /api/customer-groups`
7. `GET /api/sites/{customer_site_id}`
8. `GET /api/periods`
9. `GET /api/find-answer` (query: `taxonomyId`, `taxonomyConceptId` required; `customerSiteId`, `siteId`, `period` optional)
10. `GET /api/llm-context/{taxonomy_id}/{concept_id}`
11. `GET /api/llm-predictions/{taxonomy_id}/{concept_id}`
12. Static SPA serving at `/` and fallback paths

## 5. Frontend Design (React + TS + Vite + Tailwind/shadcn)

- Vite + React + TypeScript. Tailwind configured with CSS variables ported from `:root` in the existing `index.css` (purple/blue HSL tokens, blur radii, border radii) so shadcn components inherit the existing glass look.
- shadcn/ui primitives replace hand-rolled equivalents: `Dialog`, `Select`, `Table`, `Tabs`, `Toast`, `Badge`, `Button`.
- Component decomposition (mirrors current DOM; one responsibility each):
  - `Sidebar` - brand, taxonomy `Select`, filter nav with live count badges.
  - `Header` - concept search box, profile block.
  - `ConceptTable` - classified rows, status/classification badges, action buttons (Find Answer, Link/Map).
  - `FilterConsole` - customer-group / operational-site / period selects (site select depends on group).
  - `PredictionModal` - `Tabs`: Heuristic Candidates, LLM Reranking (lazy-loaded), LLM Context Preview (with copy-to-clipboard).
  - `AnswerModal` - giant value card, source-trace grid, resolved path breadcrumbs, confidence badge variants.
  - `Toaster` - shadcn toast replacing the custom toast center.
- State via a small `useReducer` + Context store mirroring the current `state` object (taxonomies, concepts, filteredConcepts, selectedTaxonomy, activeFilter, searchQuery, activeConcept) plus a small LLM-rerank cache keyed by `taxonomyId_conceptId`.
- `src/api/client.ts`: typed `fetch` wrappers for all 12 endpoints. `src/types.ts`: interfaces mirroring the Pydantic response models.

## 6. Dev & Build/Serve Workflow

- **Dev:** `uvicorn` (API) + `vite` dev server with `server.proxy` forwarding `/api` to the uvicorn port. HMR for the UI, autoreload for the API.
- **Prod:** `vite build` outputs to `backend/static/`; FastAPI serves it. Single-process serving model, matching today.

## 7. Testing Strategy

Per project rules: real database, no mocks, all tests under `tests/`, single inventory file.

- **Backend contract/parity tests:** `pytest` + FastAPI `TestClient` against a live MySQL `sofi` database, asserting exact envelope shape and status code of all 12 endpoints. The two existing `scratch/` scripts (`test_full_cycle.py`, `test_rest_api.py`) are promoted into `tests/integration/` as the parity gate.
- **Frontend unit/component tests:** `Vitest` + React Testing Library, one suite per component.
- **E2E tests:** Playwright (run via the test-runner sub-agent + Playwright MCP) driving the real built app against the real backend. Full flow: select taxonomy -> filter/search -> open prediction modal -> map -> find answer -> unmap.
- LLM-dependent tests read Azure credentials from `.env`; when absent, the existing simulated-fallback path in `llmService.py` is exercised.
- `docs/test_inventory.md` catalogs every test: what it covers, location, run command, external deps (DB, Azure keys), and type (unit / integration / e2e).

## 8. Increment Ladder

Each increment is fully implemented and tested (with passing evidence) before the next begins.

1. **FastAPI backend** serving the current `public/` assets + all 12 APIs. Parity-gated by the promoted integration tests. Flask remains in the tree, removable later.
2. **Frontend scaffold:** Vite + TS + Tailwind + shadcn, themed tokens, API client + types, build pipeline into `backend/static`; smoke test.
3. **UI port in slices**, each with component tests:
   - (a) shell + sidebar + concept table + filters/search
   - (b) prediction modal (3 tabs)
   - (c) answer modal + filter console
   - (d) toasts
4. **Cutover:** FastAPI serves the built bundle; full Playwright E2E parity run; then delete `server.py` and the old `public/`.

## 9. Out of Scope

- No change to the heuristic scoring algorithm, unit-class inference, context assembly, or LLM prompt/reranking logic.
- No async DB migration; the synchronous `pymysql` pool is retained.
- No database schema changes.
- No new product features; this is a transport + presentation refactor only.
