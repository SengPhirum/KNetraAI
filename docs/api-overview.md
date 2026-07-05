# API Overview

Interactive documentation: `http://localhost:8000/docs` (Swagger UI).

## Public (no authentication)

- GET /auth/methods - which login methods are enabled (password, OIDC, LDAP)
- GET /public/appearance - branding (app name, logo path, primary/secondary colors)
- GET /auth/oidc/login - starts the OIDC single sign-on flow (browser redirect)
- GET /auth/oidc/callback - OIDC provider redirect target

## Authentication

- POST /auth/login - local email/password login, returns a bearer token
- POST /auth/ldap/login - LDAP / Active Directory login (username + password)
- GET /auth/me - current user

## Authenticated API

- GET/POST /cameras
- GET/PUT/DELETE /cameras/{id}
- POST /cameras/{id}/start
- POST /cameras/{id}/stop
- GET/POST /persons
- POST /persons/import - bulk CSV import (multipart `file`, `mode`=create|upsert)
- POST /persons/import-json - bulk JSON import/sync for HR/CRM integrations
- GET/PUT/DELETE /persons/{id}
- POST /persons/{id}/images
- GET /detection-events
- GET /dashboard/stats
- GET /events/stream?token=JWT
- GET /settings, PUT /settings/{key} (secret values are masked as `********` in responses and audit logs)
- GET /settings/auth-config - effective auth configuration, secrets masked with `*_set` flags (Admin)
- PUT /settings/auth-config - enable/configure local (incl. password rules), OIDC, and LDAP login; partial sections allowed; blank secrets keep the stored value; rejects configs that would disable every method (Admin)
- POST /settings/appearance/logo - upload a custom app logo (Admin)
- GET /settings/ai-provider - live deep-learning provider status from the AI service
- GET/PUT /greeting-templates/{language}
- GET/POST/PUT /users
- GET /audit-logs

### Person import/sync

`POST /persons/import-json` body:

```json
{
  "mode": "upsert",
  "persons": [
    { "person_type": "staff", "full_name": "Jane Doe", "staff_id": "EMP-001", "branch": "HQ" }
  ]
}
```

With `mode=upsert`, rows are matched on `staff_id` (staff) or `customer_id` (customer) and updated instead of duplicated - suitable for scheduled HR/CRM sync. `mode=create` skips duplicates and reports them in `errors`.

### Settings keys

Besides the AI tuning keys (`recognition_threshold`, ...), the settings store holds:

- `appearance.app_name`, `appearance.logo_url`, `appearance.primary_color`, `appearance.secondary_color`
- `schedule.enabled`, `schedule.start_time`, `schedule.end_time`, `schedule.days`

## Internal API

These require `x-internal-api-key`.

Backend:

- POST /internal/recognize
- POST /internal/detection-events (returns `{"skipped": "outside_schedule"}` when the detection schedule excludes the current time)

AI service:

- POST /embeddings/from-path
- POST /cameras/start
- POST /cameras/{id}/stop
- GET /cameras
