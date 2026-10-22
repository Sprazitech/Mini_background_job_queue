# Queueboard

A static dashboard for submitting background jobs and viewing queue health.
It uses plain HTML, CSS, and JavaScript; there is no build step.

## Configure the API

Open `index.html` and update the `content` value on this meta tag:

```html
<meta name="api-base" content="https://job-queue-api.onrender.com">
```

Use the API origin only, without a trailing `/jobs` path. The dashboard sends
requests to `/jobs`, `/health`, and `/metrics` under that base URL.

## Deploy

Vercel serves this `docs/` folder as-is. Set the project output directory to
`docs`; no framework preset, install command, or build command is needed.

## API key handling

The dashboard asks for an API key and stores it in `sessionStorage` for the
current browser tab session. It never stores the key in `localStorage` or logs
it. Use this only with an API that permits browser requests from the dashboard
origin; configure the API's CORS policy for that origin.

## M1 production-readiness decision

- **Frontend deployment:** The repository contains the complete static dashboard, but the expected Vercel URL (`https://job-queue-docs.vercel.app`) returned HTTP 404 during verification. Vercel deployment or project configuration still needs to be completed by M5 or an authorized Vercel administrator.
- **API base URL:** `docs/index.html` is configured for `https://job-queue-api.onrender.com`. The API health and OpenAPI URLs timed out during verification, so the production backend URL and availability still need confirmation.
- **Dead-letter queue UI:** A dedicated dead-letter queue screen is not required for the initial frontend MVP. The backend DLQ management endpoints remain available for an operational/admin client and can be added to Queueboard as a later enhancement.
- **Authentication:** The dashboard asks for the API key and keeps it only in the current tab's `sessionStorage`. This avoids persistent browser storage but does not make a static API key suitable for a public production browser application, because the key can still be inspected and reused. M2 and M5 must approve a browser-safe authentication design before public launch.

Until the backend is reachable and the Vercel deployment is configured, frontend job submission and status retrieval remain pending live verification.