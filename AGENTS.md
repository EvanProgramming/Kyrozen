# Repository Guidelines

## Project Structure & Module Organization

Kyrozen is a multi-client application. The FastAPI backend lives in `kyrozen/`, organized by capability (`api/`, `auth/`, `core/`, `project/`, `tools/`, and agent-specific packages such as `planning/` and `testing/`). Python tests are in `tests/` and follow the backend package boundaries. `frontend/` contains the React/Vite web app; `desktop/` contains the Electron/React client, its native Python agent, and Playwright tests. Browser-extension sources are under `browser-extension/`, database changes under `migrations/`, and operational documentation under `docs/`. Treat `PHASE*.md` and audit reports as historical context, not executable configuration.

## Build, Test, and Development Commands

- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` creates the backend environment.
- `.venv/bin/uvicorn kyrozen.api.server:app --reload --port 8000` runs the API locally.
- `.venv/bin/python -m pytest` runs the complete Python suite; add a path such as `tests/test_api.py` for a focused run.
- `cd frontend && npm ci && npm run dev` starts the web client; `npm run build` type-checks and creates a production bundle, while `npm run lint` runs oxlint.
- `cd desktop && npm install && npm run dev` starts the desktop renderer. Use `npm run build:renderer`, `npm run lint`, and `npm run test:e2e` for verification; full packaging requires Electron release tooling.

## Coding Style & Naming Conventions

Use four spaces in Python, type annotations for public interfaces, `snake_case` for functions/modules, and `PascalCase` for classes. Keep FastAPI routes thin and place domain logic in the relevant package. TypeScript uses two spaces, `PascalCase.tsx` for React components/pages, `camelCase` for functions and stores, and explicit shared types in `src/types/`. Follow existing import ordering and run the component’s configured linter before submitting.

## Testing Guidelines

Pytest discovers `tests/test_*.py`; name tests `test_<behavior>` and use fixtures from `tests/conftest.py`. Add regression coverage for API, authentication, permissions, path validation, and project isolation changes. Desktop end-to-end specs belong in `desktop/e2e/*.spec.ts`. No fixed coverage percentage is enforced, but changed behavior should have focused tests.

## Commit & Pull Request Guidelines

Follow the existing Conventional Commit pattern: `feat: ...`, `fix(api): ...`, `test(desktop): ...`, or `chore(scope): ...`. Keep commits focused and imperative. Pull requests should explain intent, list verification commands, link related issues, call out migrations or configuration changes, and include screenshots for visible web or desktop updates. Never commit `.env`, secrets, local databases, generated `dist/` output, or Playwright artifacts.
