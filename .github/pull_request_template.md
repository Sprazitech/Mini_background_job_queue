# Pull Request

## Owner Ticklist
- [ ] M1 (DevOps) - Infrastructure & CI/CD
- [ ] M2 (API) - FastAPI endpoints & business logic
- [ ] M3 (Worker) - Background job processor
- [ ] M4 (Persistence) - Database & models
- [ ] M5 (Security) - Security review & compliance

## Checklist
### Before submitting:
- [ ] **Only own files**: I've only changed files in my assigned module
- [ ] **Ruff passes**: `ruff check app/ tests/` passes (no linting errors)
- [ ] **Pytest passes**: `pytest tests/ -v --cov=app` passes with coverage ≥60%
- [ ] **No secrets**: No API keys, passwords, or secrets in code
- [ ] **No Docker files**: No Dockerfile, docker-compose.yml, or container configs
- [ ] **.env.example updated**: Updated .env.example if new environment variables added
- [ ] **API changes announced**: If API endpoints changed, updated OpenAPI docs

### Security Checklist:
- [ ] Input validation implemented for all user inputs
- [ ] Rate limiting configured appropriately
- [ ] No sensitive data exposed in logs or responses
- [ ] Error messages don't leak internal details
- [ ] API key authentication in place for protected endpoints

## How to test manually
1. Clone the branch
2. Run `./scripts/dev.sh` to set up environment
3. Configure .env with test credentials
4. Start the server: `uvicorn app.main:app --reload --port 8000`
5. Test the endpoints using:
   ```bash
   # Test job submission
   curl -X POST http://localhost:8000/api/jobs \
     -H "X-API-Key: dev-key-change-me" \
     -H "Content-Type: application/json" \
     -d '{"task": "test_job", "data": {"test": "data"}}'
   
   # Check job status
   curl -X GET http://localhost:8000/api/jobs/{job_id} \
     -H "X-API-Key: dev-key-change-me"
   ```

## Screenshots
(For docs/ changes, include before/after screenshots here)