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

- JWT authentication for users.
- Internal API key between backend and AI service.
- Roles: Admin, Manager, Operator, Viewer.
- Audit logs for create/update/delete/start/stop actions.
- Face files are served locally for MVP only. Use private storage or signed URLs in production.
