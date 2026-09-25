# RouteWise Dashboard

React + TypeScript + Vite frontend for RouteWise. A real client of the
FastAPI backend (`api/`) — it contains no ML prediction, route scoring,
reliability calculation, or rerouting logic of its own; every intelligent
value displayed comes from an API response.

## Development

Requires the backend running first (see the repo root README's "API Usage"
section — `uvicorn api.main:app --reload --host 0.0.0.0 --port 8000`).

```bash
cp .env.example .env.local   # adjust VITE_API_BASE_URL if the backend isn't on localhost:8000
npm install
npm run dev                  # http://localhost:5173
```

## Testing

```bash
npm run test          # vitest, component/unit tests (MSW-mocked API — standard practice for unit tests)
npm run lint           # oxlint
npm run build          # tsc -b && vite build
```

### Real, non-mocked integration check

`scripts/integration-check.mjs` drives an actual Chromium browser (via
Playwright) against the REAL running backend and dev server — no mocked
API responses anywhere in this script. Requires both servers already
running (see above):

```bash
npx playwright install chromium   # once
node scripts/integration-check.mjs
```

It walks the full flow: open the app → select a real origin/destination →
search → view real candidate routes → open route details → trigger
adaptive rerouting → verify the updated recommendation → confirm model
lifecycle status. Screenshots land in `./screenshots/`.

`scripts/responsive-check.mjs` captures the same running app at desktop/
laptop/tablet widths.

## Architecture

- `src/api/` — typed API client (`client.ts`: base URL, request/response
  handling, typed `ApiError`), `types.ts` (mirrors `api/schemas/*.py` by
  hand), `endpoints.ts` (one typed function per backend endpoint).
- `src/hooks/` — `useAsync` (generic idle/loading/success/error + abort-
  on-superseding-request), plus one thin hook per endpoint.
- `src/lib/` — presentation-only logic: `risk.ts` (buckets a real API risk
  value into Low/Moderate/High using thresholds the BACKEND serves, never
  a value hardcoded in the frontend), `format.ts`, `errorMessages.ts`
  (backend error code → user-facing copy, never a raw stack trace).
- `src/components/` — `layout/`, `search/`, `results/`, `details/`,
  `rerouting/`, `status/`, `common/`. Each component receives data as
  props; no component fetches on its own. `status/MlopsStatusPanel.tsx`
  shows Stage 9's real per-category monitoring statuses (data quality,
  data drift, prediction drift, performance, monitoring decision) and
  live operational status straight from `GET /system/status`'s
  `monitoring` block — `NOT_RUN`/"Never run" if no monitoring pass has
  ever completed, never a fabricated "healthy".

## Design

Cool, restrained "instrument panel" palette (IBM Plex Sans + IBM Plex
Mono), a persistent left console (search + live system/model/MLOps
status) alongside a results viewport — deliberately not a centered
consumer search-box layout, to read as a mobility-operations tool rather
than a generic travel app. See `src/styles/tokens.css` for the full token
system.
