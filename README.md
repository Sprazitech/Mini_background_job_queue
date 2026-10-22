# Mini Background Job Queue

A lightweight background job queue system built with Python, FastAPI, and Supabase.

## Quick Start

```bash
./scripts/dev.sh
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for system design and component details.

## Deployment

Deployment instructions are available in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Testing

```bash
pytest tests/ -v --cov=app
```

## Database migrations

See [docs/DATABASE_MIGRATIONS.md](docs/DATABASE_MIGRATIONS.md) for applying
Alembic migrations to a new database or adopting the existing Supabase schema.

## TODO: M2 - API Implementation
- [ ] Define API endpoints and request/response schemas
- [ ] Implement job submission and status retrieval
- [ ] Add API authentication and rate limiting
- [ ] Write API documentation with OpenAPI/Swagger

## TODO: M3 - Worker Implementation  
- [ ] Design job processing architecture
- [ ] Implement retry logic with exponential backoff
- [ ] Add failure handling and dead letter queue
- [ ] Implement worker health monitoring

## TODO: M4 - Database & Models
- [x] Design Supabase database schema
- [x] Implement SQLAlchemy models
- [x] Create database migration scripts
- [x] Add database-level type and status constraints
- [x] Apply and validate the schema in Supabase
