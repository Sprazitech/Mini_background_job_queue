# Security Checklist and M5 Audit

Updated: October 23, 2026
Owner: M5 — DevOps/Deployment

## Requested repository security audit

- [x] `.env` is in `.gitignore`.
- [ ] `git log --all -S "eyJ"` returns nothing. **Unresolved:** the repository history contains the non-secret placeholder `eyJ...` in `M5_HANDOFF.txt`; no real JWT was found. Removing this historical match requires an approved history rewrite and force-push, so it was not performed.
- [x] `API_KEY` is compared with `secrets.compare_digest` in `app/security.py`.
- [x] All `/jobs` routes use `Depends(verify_api_key)`.
- [x] `JobCreate` uses `ConfigDict(extra="forbid")`.
- [x] Job type is restricted with `Literal["send_email", "generate_report"]`.
- [x] The create-job route rejects payloads larger than 4096 bytes with HTTP 422.
- [x] SlowAPI rate limiting is applied to `POST /jobs`.
- [x] CORS is restricted to the production frontend origin:
  `https://mini-background-job-queue.vercel.app`.
- [x] RLS is enabled on `jobs` and `worker_heartbeat` in `scripts/schema.sql`.
- [x] No API response includes `SUPABASE_SERVICE_ROLE_KEY`.
- [x] Error responses exposed by routes are generic and do not include tracebacks.
- [x] `/health` is public and `/metrics` requires `X-API-Key`.
- [x] Worker logs do not log job payloads; failure logs contain job ID, job type,
  attempt, and error type only.
- [x] All production dependencies in `requirements.txt` are pinned.
- [x] `.github/workflows/deploy.yml` uses the `production` environment, which
  provides GitHub Environment approval when configured by M5.

## Existing authentication and input controls

- [x] API key authentication is implemented for protected endpoints.
- [x] Rate limiting is configured for job creation.
- [x] User input is validated by Pydantic and route constraints.
- [x] Production credentials are read from environment variables.
- [x] Service-role credentials are not returned by API responses.
- [x] SQL queries use SQLAlchemy parameters or ORM expressions.
- [ ] Public browser authentication is not yet user/session based. The current
  API key prompt is suitable only for controlled MVP testing.

## Data protection and infrastructure controls

- [x] Database credentials are environment variables.
- [x] Sensitive credentials are not intentionally logged.
- [x] API route errors do not expose tracebacks to clients.
- [x] Production frontend/backend communication uses HTTPS URLs.
- [x] Dependencies are pinned.
- [ ] Dependency vulnerability scanning is not yet enforced in CI.
- [x] Environment-specific configuration is used.
- [ ] Security headers such as CSP and HSTS require production-platform review.

## Supabase and operational controls

- [x] RLS is enabled on `jobs`, `worker_heartbeat`, and `dead_letter_queue` in
  the verified Supabase schema.
- [ ] Final least-privilege database-role review is pending M4/M5.
- [ ] Automated backup retention and restore testing require Supabase Dashboard
  confirmation by M4/M5.
- [x] DLQ schema, trigger, functions, indexes, and views were verified through
  the Supabase SQL Editor.
- [ ] Production SMTP/Resend provider credentials must be verified in Render
  without exposing their values.

## CI/CD controls

- [x] CI runs linting and tests without `|| true` masking failures.
- [x] Production deployment uses a protected `production` environment.
- [ ] M5 must configure GitHub Environment reviewers/approval rules.
- [ ] M5 must add `RENDER_DEPLOY_HOOK_URL` and `VERCEL_DEPLOY_HOOK_URL` as
  GitHub Actions secrets before the deployment workflow can trigger services.

## Owner follow-up issues

The following items are outside a security-only code fix and require owner
follow-up:

- M1/M2: Replace the shared browser API key with approved user/session auth
  before public launch.
- M4/M5: Complete least-privilege database role review and backup/restore test.
- M5: Configure GitHub production-environment reviewers and deployment-hook
  secrets.
- M5: Add dependency vulnerability scanning and production security headers.
- M3/M5: Verify Resend production configuration and real-email delivery.

Do not place database passwords, service-role keys, API keys, deployment hooks,
or Resend keys in source code, Vercel frontend variables, or chat messages.
