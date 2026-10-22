# Dead Letter Queue System

## Overview
The Dead Letter Queue (DLQ) is a critical component of the Mini Background Job Queue that handles permanently failed jobs. When a job exhausts all retry attempts, it's automatically archived to the DLQ for analysis, monitoring, and potential reprocessing.

## Architecture

### Key Components

1. **dead_letter_queue Table**
   - Stores permanently failed jobs with complete context
   - Includes failure analysis metadata
   - Tracks resolution status

2. **Automatic Archiving Trigger**
   - `archive_to_dead_letter_queue()` function
   - Automatically archives jobs when status changes to 'failed'
   - Captures complete failure context

3. **Reprocessing System**
   - `reprocess_dead_letter_entry()` function
   - Creates new jobs from archived failures
   - Maintains audit trail

4. **Circuit Breaker Integration**
   - Tracks consecutive failures by job type
   - Adds additional delays when circuit is open
   - Automatic reset after timeout

5. **Management API**
   - View and filter DLQ entries
   - Reprocess failed jobs
   - Mark entries as resolved
   - Statistical analysis

## Database Schema

### Tables
```sql
dead_letter_queue (
    id UUID PRIMARY KEY,
    original_job_id UUID REFERENCES jobs(id),
    job_type VARCHAR(100),
    priority INTEGER,
    payload JSONB,
    metadata JSONB,
    final_error_type VARCHAR(100),
    final_error_message TEXT,
    final_error_stack TEXT,
    final_attempt_count INTEGER,
    max_retries INTEGER,
    archived_at TIMESTAMPTZ,
    archived_reason VARCHAR(100),
    failure_category VARCHAR(100),
    resolution_status VARCHAR(50),
    resolution_notes TEXT,
    suggested_fix TEXT,
    -- ... additional fields
)
```

### Key Functions
- `archive_to_dead_letter_queue()` - Automatic archiving trigger
- `reprocess_dead_letter_entry()` - Manual reprocessing
- `get_dead_letter_stats()` - Statistical analysis
- Views: `recent_dead_letter_entries`, `unresolved_dead_letter_entries`

## API Endpoints

### List DLQ Entries
```
GET /dead-letter
```
**Query Parameters:**
- `limit`, `offset` - Pagination
- `resolution_status` - Filter by status
- `failure_category` - Filter by category
- `job_type` - Filter by job type

### Get Specific Entry
```
GET /dead-letter/{entry_id}
```

### Reprocess Entry
```
POST /dead-letter/{entry_id}/reprocess
```
**Body:**
```json
{
  "reason": "bug_fixed"
}
```

### Resolve Entry
```
PUT /dead-letter/{entry_id}/resolve
```
**Body:**
```json
{
  "resolution_status": "resolved",
  "resolution_notes": "Root cause identified and fixed"
}
```

### Get Statistics
```
GET /dead-letter/stats
```
**Query Parameters:**
- `days` - Analysis period (default: 7)

## Worker Integration

### Circuit Breaker Logic
```python
# In app/worker/loop.py
CIRCUIT_BREAKER_THRESHOLD = 5  # Consecutive failures
CIRCUIT_BREAKER_RESET_TIMEOUT = 300  # 5 minutes

# When circuit breaker opens:
# 1. Additional delay added to retries
# 2. Warning logged
# 3. Automatic reset after timeout
```

### Automatic Archiving
When a job fails with `attempts >= max_retries`:
1. Job status updated to 'failed'
2. Trigger automatically archives to DLQ
3. Complete failure context preserved
4. Metrics updated

## Health Monitoring Integration

### Enhanced Metrics Endpoint
```
GET /metrics
```
Now includes:
- DLQ statistics (total, pending, resolved, etc.)
- Failure category distribution
- Circuit breaker status
- Resolution time metrics

## Setup and Deployment

### Initial Setup
```bash
# Apply dead letter queue schema
python scripts/apply_dead_letter_schema.py

# Verify installation
python scripts/apply_dead_letter_schema.py --verify
```

### Environment Variables
```env
# Circuit breaker configuration (optional)
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_RESET_TIMEOUT=300
```

## Monitoring and Alerting

### Key Metrics to Monitor
1. **DLQ Growth Rate** - Rate of new entries
2. **Resolution Time** - Average time to resolve entries
3. **Circuit Breaker Status** - Which job types have open circuits
4. **Failure Categories** - Distribution of failure reasons

### Recommended Alerts
- DLQ entries growing faster than resolution rate
- Circuit breaker open for extended period
- High percentage of specific failure categories
- Unresolved entries older than threshold

## Best Practices

### 1. Regular Monitoring
- Daily review of unresolved entries
- Weekly analysis of failure patterns
- Monthly cleanup of resolved entries

### 2. Failure Analysis
1. **Categorize failures** by type and cause
2. **Identify patterns** across similar failures
3. **Document root causes** in resolution notes
4. **Implement fixes** for systemic issues

### 3. Capacity Planning
- Monitor DLQ table size growth
- Plan archival for old resolved entries
- Consider partitioning for large volumes

### 4. Security Considerations
- DLQ API requires API key authentication
- Sensitive data may be in payloads - consider encryption
- Audit trail of all reprocessing actions

## Troubleshooting

### Common Issues

1. **DLQ Not Archiving**
   - Verify trigger exists: `archive_failed_job_trigger`
   - Check job status transitions
   - Verify max_retries configuration

2. **Circuit Breaker Not Resetting**
   - Check `CIRCUIT_BREAKER_RESET_TIMEOUT` value
   - Verify successful job executions
   - Manual reset available via worker stats

3. **Performance Issues**
   - Index dead_letter_queue table appropriately
   - Consider partitioning by archived_at
   - Archive old resolved entries

### Diagnostic Queries
```sql
-- Check DLQ health
SELECT * FROM get_dead_letter_stats();

-- Find unresolved entries
SELECT * FROM unresolved_dead_letter_entries;

-- Analyze failure patterns
SELECT failure_category, COUNT(*), AVG(final_attempt_count)
FROM dead_letter_queue
WHERE archived_at >= NOW() - INTERVAL '7 days'
GROUP BY failure_category;
```

## Integration with Existing Systems

### With Existing Jobs API
- Failed jobs automatically appear in DLQ
- Reprocessing creates new jobs via existing API
- Metrics integrated with existing health endpoint

### With Monitoring Systems
- Prometheus metrics available via `/metrics`
- Circuit breaker status exposed for alerting
- Resolution time metrics for SLA tracking

### With CI/CD Pipeline
- Schema migrations include DLQ setup
- Tests verify DLQ functionality
- Deployment includes DLQ verification

## Future Enhancements

### Planned Features
1. **Automated Root Cause Analysis** - ML-based failure categorization
2. **Smart Reprocessing** - Automatic retry after fix detection
3. **Integration with Incident Management** - Auto-create tickets for patterns
4. **Advanced Analytics Dashboard** - Visual failure analysis

### Scalability Improvements
1. **Partitioning** - By time or job type
2. **Sharding** - For multi-tenant deployments
3. **Streaming Archival** - Real-time failure processing
4. **External Storage** - For large payloads

## Conclusion
The Dead Letter Queue system provides robust handling of permanent failures with:
- **Complete context preservation** for debugging
- **Automated archiving** without manual intervention
- **Circuit breaker protection** against cascading failures
- **Comprehensive API** for management and analysis
- **Integrated monitoring** with existing health system

This completes M3's worker implementation with production-grade failure handling capabilities.