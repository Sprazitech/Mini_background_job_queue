# Security Checklist

## Authentication & Authorization
- [ ] API key authentication implemented for all endpoints
- [ ] Rate limiting configured per API key/IP address
- [ ] Input validation on all user-provided data
- [ ] No default credentials in production
- [ ] Service role key stored securely, not in source code

## Data Protection
- [ ] Database credentials stored as environment variables
- [ ] No sensitive data logged (passwords, API keys, PII)
- [ ] Error messages don't expose system details
- [ ] HTTPS enforced for all external communications
- [ ] SQL injection prevention (parameterized queries)

## Infrastructure Security
- [ ] All dependencies pinned to specific versions
- [ ] Regular dependency updates for security patches
- [ ] No secrets committed to version control
- [ ] Environment-specific configuration
- [ ] Secure headers configured (CSP, HSTS, etc.)

## Monitoring & Compliance
- [ ] Logging configured for security events
- [ ] Failed authentication attempts logged
- [ ] Rate limit violations monitored
- [ ] Regular security scanning of dependencies
- [ ] Backup and recovery procedures documented

## Deployment Security
- [ ] CI/CD pipeline runs security checks
- [ ] Automated tests include security scenarios
- [ ] Production environment isolated from development
- [ ] Access controls for deployment credentials
- [ ] Regular security audits scheduled

## Supabase Security
- [ ] Row Level Security (RLS) policies configured
- [ ] Database schema follows principle of least privilege
- [ ] Connection pooling with proper timeouts
- [ ] Regular database backups enabled
- [ ] Audit trail for data modifications