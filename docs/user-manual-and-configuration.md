# Vision AI System - User Manual and Configuration Guide

Version: Walk-in Greeting AI MVP  
Generated: 2026-07-04

This guide explains how to deploy, configure, and use the Vision AI System MVP. The first module is Walk-in Greeting AI, which connects to CCTV/IP cameras, detects faces, recognizes registered staff or customers, and saves greeting events in real time.

> Screenshot examples use demo data and are stored in `docs/screenshots/`.

## 1. Interface preview

![Dashboard](screenshots/dashboard.png)

![Live Monitoring](screenshots/live-monitoring.png)

![Camera Management](screenshots/camera-management.png)

![Staff and Customer Database](screenshots/staff-customer-database.png)

## 2. Default access

Local quick start URLs:

```text
Frontend: http://localhost:3000
Backend API docs: http://localhost:8000/docs
AI service docs: http://localhost:8001/docs
```

Production-style Docker URLs:

```text
App: http://localhost
API: http://localhost/api
Health: http://localhost/health
```

Default login:

```text
Email: admin@example.com
Password: admin123
```

Change the default password before real deployment.

## 3. Deployment quick start

Simple local stack:

```bash
cp .env.example .env
docker compose up --build
```

Production-style stack with nginx reverse proxy:

```bash
cp docker/.env.production.example docker/.env.production
# edit all passwords and secrets before starting
docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d --build
```

![Deployment configuration](screenshots/deployment.png)

## 4. Main workflow

1. Login as Admin.
2. Add an RTSP camera in Camera Management.
3. Create staff or customer profiles.
4. Upload multiple clear face images for each person.
5. Start the camera worker.
6. Monitor live recognition on the dashboard and live page.
7. Review Detection History and export reports.
8. Tune AI thresholds and greeting templates in Settings.

## 5. User roles

| Role | Main permissions |
| --- | --- |
| Admin | Full access to users, cameras, persons, settings, events, and audit logs. |
| Manager | Dashboard, reports, staff/customer profile management, detection history. |
| Operator | Live monitoring, camera operation, limited person registration if allowed. |
| Viewer | Read-only access to dashboard and reports. |

## 6. Camera configuration

Use RTSP camera URLs in this format:

```text
rtsp://username:password@camera-ip:554/stream1
rtsp://username:password@camera-ip:554/h264/ch1/main/av_stream
```

Recommended configuration:

- Stable wired network for entrance cameras.
- Camera positioned near face height.
- Good front lighting.
- Avoid strong backlight.
- Start with 3-5 AI FPS and increase only after testing CPU/GPU capacity.

![Camera Management](screenshots/camera-management.png)

## 7. Person registration and face enrollment

Register each staff/customer profile with consent before uploading face images. Use 3-5 clear enrollment photos from different angles. The backend calls the AI service to create embeddings and stores them in PostgreSQL with pgvector.

![Staff and Customer Database](screenshots/staff-customer-database.png)

## 8. AI settings

Important settings:

| Setting | Purpose | Typical value |
| --- | --- | --- |
| recognition_threshold | Minimum vector similarity for known face match. | 0.60-0.70 |
| greeting_cooldown_seconds | Prevents duplicate greetings for the same person. | 300 |
| gender_min_confidence | Uses neutral greeting below confidence. | 0.75 |
| AI_PROVIDER | `opencv_mock` for development or `insightface` for production. | opencv_mock / insightface |

![Settings](screenshots/settings.png)

## 9. Detection history

Every event stores timestamp, camera, snapshot, known/unknown person decision, confidence, gender estimate when unknown, and greeting text.

![Detection History](screenshots/detection-history.png)

## 10. Privacy and security checklist

- Get consent before registering biometric face data.
- Use signage that AI CCTV detection is active.
- Replace all default secrets.
- Use HTTPS in production.
- Restrict access by role.
- Keep audit logs.
- Define retention for snapshots and event logs.
- Delete face images and embeddings when a person requests removal.
- Do not expose images through public URLs.

## 11. Troubleshooting

| Problem | Check |
| --- | --- |
| Camera does not start | Confirm RTSP URL, network route, camera credentials, and firewall. |
| No detections | Check lighting, camera angle, AI worker logs, and process FPS. |
| Wrong recognition | Add better enrollment photos and tune `recognition_threshold`. |
| Dashboard not updating | Check backend SSE endpoint, nginx proxy, and browser console. |
| Upload fails | Check storage volume permissions and AI service health. |
| Docker stack fails | Run `docker compose ps` and review service logs. |

## 12. Backup and restore

Backup:

```bash
bash docker/scripts/backup-postgres.sh
```

Restore:

```bash
bash docker/scripts/restore-postgres.sh backups/your-backup.sql
```

## 13. Important files

```text
docker/docker-compose.yml              Production-style Docker Compose
docker/.env.production.example         Production env template
docker/nginx/nginx.conf                Reverse proxy configuration
database/init.sql                      PostgreSQL and pgvector schema
backend/app/                           FastAPI backend
ai-service/app/                        AI inference service
frontend/app/                          Nuxt frontend
storage/                               Shared local file storage
```
