# Architecture

## Pipeline

RTSP camera -> frame capture -> face detection -> alignment/embedding -> backend recognition with pgvector -> known/unknown decision -> gender estimate for unknown -> greeting -> detection event -> SSE dashboard.

## Runtime services

- Frontend: Nuxt 4 single page admin console.
- Backend: FastAPI API for auth, roles, camera CRUD, person CRUD, image upload, pgvector recognition, event history, dashboard stats, SSE.
- AI service: FastAPI inference API. Runs one background worker per active camera.
- PostgreSQL + pgvector: relational data and face vector search.
- Redis: reserved for future queues/caching.
- Storage: shared local volume for face images and snapshots.

## Security model

- JWT authentication for users; three login methods: local password, OIDC single sign-on (Keycloak/Authentik/any OpenID Connect provider), and LDAP / Active Directory. OIDC and LDAP users are provisioned just-in-time with a configurable default role.
- Internal API key between backend and AI service.
- Roles: Admin, Manager, Operator, Viewer.
- Audit logs for create/update/delete/start/stop/import/provision actions.
- Face files are served locally for MVP only. Use private storage or signed URLs in production.

## Runtime configuration

- Settings table drives AI thresholds, greeting templates, appearance (app name, logo, primary/secondary colors), and the detection schedule.
- The detection schedule is enforced at the backend event-ingest endpoint; outside the window, camera workers keep running but events are not recorded.
- Appearance is exposed on a public endpoint so the login page is branded before authentication; the frontend applies colors as CSS variables at load.
