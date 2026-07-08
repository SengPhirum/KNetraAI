# KNetraAI - Walk-in Greeting AI MVP

KNetraAI ("netra" = eye) is a CCTV-connected Vision AI system. The first module is **Walk-in Greeting AI**:

- Connect RTSP/IP cameras (guided setup for Hikvision, EZVIZ, Dahua, Tapo, and more), or connect a camera/NVR over ONVIF and pick channels from a list instead of typing RTSP URLs.
- Real-time CCTV-style live view (MJPEG) with a multi-camera grid, layout switcher, and fullscreen per-camera focus.
- Detect faces from live video.
- Register staff and customers with face photos, CSV import, or HR/CRM API sync.
- Generate 512-dimensional embeddings.
- Search embeddings with PostgreSQL + pgvector.
- Greet known people by name.
- Greet unknown people as sir, madam, or neutral when gender confidence is low.
- Save detection events and push live dashboard updates by SSE.
- Optional detection schedule (record events only during configured hours/days).
- Sign in with local accounts, OIDC single sign-on (Keycloak, Authentik, ...), or LDAP/Active Directory.
- Admin-configurable appearance: app name, logo, primary/secondary colors (default primary: dodgerblue).
- PWA-ready branding: web manifest plus a full icon set generated from the KNetraAI logo.

The project is intentionally modular so more vision modules can be added later, such as PPE detection, queue counting, intrusion alerts, attendance, people counting, and license plate recognition.

## Interface preview

These screenshots show the MVP admin console with seeded demo data. Full-size images are stored in `docs/screenshots/`.

| Dashboard | Live Monitoring |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Live Monitoring](docs/screenshots/live-monitoring.png) |

| Camera Management | Staff / Customer Database |
|---|---|
| ![Camera Management](docs/screenshots/camera-management.png) | ![Staff and Customer Database](docs/screenshots/staff-customer-database.png) |

| Detection History | Settings / Configuration |
|---|---|
| ![Detection History](docs/screenshots/detection-history.png) | ![Settings](docs/screenshots/settings.png) |

## Documentation

- [User Manual and Configuration Guide](docs/user-manual-and-configuration.md)
- [Editable DOCX Manual](docs/Vision_AI_System_User_Manual_and_Configuration_Guide.docx) (older snapshot; the Markdown manual is current)
- [PDF Manual](docs/Vision_AI_System_User_Manual_and_Configuration_Guide.pdf) (older snapshot; the Markdown manual is current)
- [Architecture](docs/architecture.md)
- [API Overview](docs/api-overview.md)
- [Role Permission Matrix](docs/role-permission-matrix.md)
- [Docker Deployment Guide](docker/README.md)

## Services

```text
frontend/      Nuxt 4 web UI
backend/       FastAPI API, auth, database, dashboard, event stream
ai-service/    FastAPI AI inference service, RTSP workers, embeddings
database/      PostgreSQL schema with pgvector
storage/       Local shared storage for face images and snapshots
docker/        Production-style Docker deployment files
```

## Quick start

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Start the local stack:

```bash
docker compose up --build
```

3. Open the app:

```text
Frontend: http://localhost:3000
Backend API docs: http://localhost:8000/docs
AI service docs: http://localhost:8001/docs
```

Default login:

```text
Email: admin@example.com
Password: admin123
```

Change this password immediately for any real deployment.

## MVP flow

1. Login.
2. Add an RTSP camera in Camera Management.
3. Create a staff or customer profile.
4. Upload one or more face images for that person.
5. The backend calls the AI service to generate embeddings.
6. Start the camera worker.
7. The AI service captures frames, detects faces, generates embeddings, calls the backend for pgvector recognition, creates a greeting, saves a snapshot, and posts a detection event.
8. The dashboard receives the event in real time over SSE.

## Production-style Docker deployment

A complete deployment set is included under `docker/`. The original root `docker-compose.yml` remains as a simple local quick start. For a cleaner deployment with nginx reverse proxy, healthchecks, named volumes, and production env template, use:

```bash
cp docker/.env.production.example docker/.env.production
# Edit docker/.env.production and change every password/secret.
docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d --build
```

Then open:

```text
App: http://localhost
API: http://localhost/api
Health: http://localhost/health
```

Deployment files included:

```text
docker/docker-compose.yml
docker/backend.Dockerfile
docker/ai-service.Dockerfile
docker/frontend.Dockerfile
docker/nginx/nginx.conf
docker/.env.production.example
docker/scripts/
```

See `docker/README.md` for logs, backup, restore, GPU override, and HTTPS notes.

## AI provider modes

The AI service supports provider abstraction:

- `AI_PROVIDER=opencv_mock` is the lightweight development mode. It uses OpenCV Haar face detection and a deterministic 512-value embedding fallback. This is useful for UI/API development but not production face recognition.
- `AI_PROVIDER=insightface` uses InsightFace when the optional dependencies are installed. This is the intended production path for deep-learning face detection and ArcFace-style embeddings.

To use InsightFace in the AI container, edit `ai-service/requirements.txt` and uncomment or add InsightFace dependencies, then set:

```env
AI_PROVIDER=insightface
```

Production recognition quality depends on camera angle, lighting, face image quality, enrollment photos, model choice, and threshold tuning.

## Main environment variables

See `.env.example` and `docker/.env.production.example` for all values.

```env
DATABASE_URL=postgresql://vision:vision@postgres:5432/vision_ai
AI_SERVICE_URL=http://ai-service:8001
BACKEND_URL=http://backend:8000
INTERNAL_API_KEY=change-this-in-production
JWT_SECRET=change-this-in-production
RECOGNITION_THRESHOLD=0.45
GREETING_COOLDOWN_SECONDS=300
NUXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Optional single sign-on and directory login (see Settings -> Authentication in the app)
OIDC_ENABLED=false        # Keycloak, Authentik, or any OpenID Connect provider
LDAP_ENABLED=false        # LDAP / Active Directory
```

The full OIDC/LDAP variable reference is in `.env.example`, and the in-app **Settings → Authentication** page has step-by-step Keycloak and Authentik guides.

## Important privacy notes

Face images and embeddings are biometric data. Before real use, add consent forms, signage, strict retention policies, encryption, access review, and local legal review. This scaffold includes role access, audit logs, delete endpoints, and local/private file serving, but it is not a complete compliance program by itself.

## Suggested production hardening

- Use HTTPS and a real reverse proxy.
- Replace default secrets.
- Disable public access to storage files.
- Use private object storage with signed URLs.
- Enable database backups.
- Use GPU acceleration for inference.
- Add monitoring, log aggregation, and camera health alerts.
- Perform face-recognition bias, accuracy, and privacy reviews.
