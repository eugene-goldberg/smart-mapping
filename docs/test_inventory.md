# Test Inventory

_Last updated: 2026-06-16_

## External dependencies
- **MySQL `sofi`** on `127.0.0.1:3306` (root/sofi) — required by all backend integration tests and the live-server scripts.
- **Azure OpenAI keys** in `.venv` (dotenv file at repo root) — optional; absence exercises the simulated LLM fallback in `llmService.py`.
- **venv:** `venv/` (real Python virtualenv). Run backend tests from repo root.

## Backend — integration (pytest + FastAPI TestClient, real DB)

| Test file | Covers | Run command | Type |
|---|---|---|---|
| `tests/integration/test_api_read_endpoints.py` | `/api/taxonomies`, `/api/concepts/{id}`, `/api/customer-groups`, `/api/periods` envelope + shape | `venv/bin/python -m pytest tests/integration/test_api_read_endpoints.py -v` | integration |
| `tests/integration/test_api_mappings.py` | POST `/api/mappings` validation (400/404), map→unmap roundtrip | `venv/bin/python -m pytest tests/integration/test_api_mappings.py -v` | integration |
| `tests/integration/test_api_find_answer.py` | `/api/find-answer` required-param 400, result shape | `venv/bin/python -m pytest tests/integration/test_api_find_answer.py -v` | integration |
| `tests/integration/test_full_cycle.py` | Full lifecycle over HTTP (taxonomies→concepts→predictions→context→llm→map→find→unmap) | start uvicorn :3000, then `venv/bin/python tests/integration/test_full_cycle.py` | integration (HTTP) |
| `tests/integration/test_rest_api.py` | REST API eval over HTTP (taxonomies, customer-groups, periods, find-answer global + filtered) | start uvicorn :3000, then `venv/bin/python tests/integration/test_rest_api.py` | integration (HTTP) |

Run all TestClient tests: `venv/bin/python -m pytest tests/integration -v` → **8 passed**.
Start server: `PORT=3000 venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 3000`

## Frontend — unit/component (Vitest + React Testing Library)

Runnable copies live in `frontend/tests/` (Vite `@fs` restriction); reference copies in `tests/frontend/`.
Run all: `cd frontend && npx vitest run` → **30 passed (5 files)**.

| Test file | Tests | Covers |
|---|---|---|
| `frontend/tests/api-client.test.ts` | 6 | envelope unwrap, URL building, POST body (stubbed fetch — boundary only) |
| `frontend/tests/sidebar.test.tsx` | 4 | badge counts, taxonomy options, active filter |
| `frontend/tests/concept-table.test.tsx` | 7 | abstract/mapped/unmapped rows, badges, empty state |
| `frontend/tests/prediction-modal.test.tsx` | 8 | candidates, breakdown pills, LLM tab + cache, Map action, context |
| `frontend/tests/app.test.tsx` | 5 | bootstrap: taxonomies, customer groups, periods, sidebar render, search |

Typecheck: `cd frontend && npx tsc --noEmit` → clean.

## E2E (live, Playwright MCP smoke — not yet a committed spec file)
Performed against uvicorn :3000 serving the built SPA: app loads, taxonomy select → sidebar counts populate (All 4954 / Quant 276 / Narrative 524 / Choice 362 / Unmapped 1217), filter console populated (480 groups, periods), 0 console errors. A committed `tests/e2e/full_flow.spec.ts` is an optional follow-up.
