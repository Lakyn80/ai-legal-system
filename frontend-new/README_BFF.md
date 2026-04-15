# Frontend-New BFF Integration

This frontend uses a Next.js BFF layer (route handlers in `app/api/...`) and never calls backend services directly from browser components.

## Required env variable

- `BACKEND_URL` - full backend base URL including `/api` prefix
  - Docker default: `http://backend:8000/api`
  - Local (outside Docker): `http://localhost:8030/api`

## Implemented BFF routes

- `GET /api/cases/[caseId]`
- `GET /api/cases/[caseId]/tree`
- `GET /api/cases/[caseId]/documents/[documentId]`
- `GET /api/cases/[caseId]/full-case`
- `POST /api/cases/[caseId]/legal-agent/run`
- `GET /api/cases/[caseId]/legal-agent/[runId]`
- `GET /api/cases/[caseId]/legal-agent/[runId]/result`

## Run

### Docker Compose

From repository root:

```bash
docker compose up --build backend frontend-new
```

Open frontend at:

- `http://localhost:3016`

### Local frontend dev (optional)

In `frontend-new`:

```bash
# PowerShell
$env:BACKEND_URL="http://localhost:8030/api"
npm ci
npm run dev
```

Open frontend at:

- `http://localhost:3001`
