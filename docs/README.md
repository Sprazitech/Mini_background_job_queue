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
