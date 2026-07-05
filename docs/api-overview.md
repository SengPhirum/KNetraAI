# API Overview

## Public authenticated API

- POST /auth/login
- GET /auth/me
- GET/POST /cameras
- GET/PUT/DELETE /cameras/{id}
- POST /cameras/{id}/start
- POST /cameras/{id}/stop
- GET/POST /persons
- GET/PUT/DELETE /persons/{id}
- POST /persons/{id}/images
- GET /detection-events
- GET /dashboard/stats
- GET /events/stream?token=JWT
- GET/PUT /settings/{key}
- GET/PUT /greeting-templates/{language}
- GET/POST/PUT /users
- GET /audit-logs

## Internal API

These require `x-internal-api-key`.

Backend:

- POST /internal/recognize
- POST /internal/detection-events

AI service:

- POST /embeddings/from-path
- POST /cameras/start
- POST /cameras/{id}/stop
- GET /cameras
