# Docker deployment

This folder contains production-style Docker deployment files for the KNetraAI MVP.

## Files

```text
docker/docker-compose.yml          Main deployment stack
docker/backend.Dockerfile          FastAPI backend image
docker/ai-service.Dockerfile       Python AI inference image
docker/frontend.Dockerfile         Nuxt frontend image
docker/nginx/nginx.conf            HTTP reverse proxy for frontend + /api
docker/nginx/nginx-ssl.example.conf Optional HTTPS example
docker/.env.production.example     Production environment template
docker/scripts/deploy.sh           Build and start helper
docker/scripts/logs.sh             Tail logs helper
docker/scripts/backup-postgres.sh  Database backup helper
docker/scripts/restore-postgres.sh Database restore helper
```

## First deployment

From the project root:

```bash
cp docker/.env.production.example docker/.env.production
# Edit docker/.env.production and change all passwords/secrets.
docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d --build
```

Or use the helper:

```bash
cp docker/.env.production.example docker/.env.production
sh docker/scripts/deploy.sh
```

Open:

```text
App: http://localhost
API through proxy: http://localhost/api
Backend health through proxy: http://localhost/api/health
Nginx health: http://localhost/health
```

Default admin is controlled by `DEFAULT_ADMIN_EMAIL` and `DEFAULT_ADMIN_PASSWORD` in `docker/.env.production`.

## Useful commands

```bash
# Show containers
docker compose --env-file docker/.env.production -f docker/docker-compose.yml ps

# Tail all logs
docker compose --env-file docker/.env.production -f docker/docker-compose.yml logs -f --tail=200

# Tail backend only
sh docker/scripts/logs.sh backend

# Stop stack
docker compose --env-file docker/.env.production -f docker/docker-compose.yml down

# Stop and remove data volumes - destructive
docker compose --env-file docker/.env.production -f docker/docker-compose.yml down -v
```

## Storage and database

The deployment stack uses named Docker volumes:

```text
vision-ai-postgres-data  PostgreSQL data
vision-ai-redis-data     Redis append-only data
vision-ai-storage-data   Uploaded face images and detection snapshots
```

Back up PostgreSQL:

```bash
sh docker/scripts/backup-postgres.sh
```

Restore PostgreSQL:

```bash
sh docker/scripts/restore-postgres.sh backups/knetraai-postgres-YYYYMMDD-HHMMSS.sql.gz
```

## RTSP camera notes

The AI container connects to RTSP URLs from inside Docker. Use RTSP URLs reachable from the Docker host/network, for example:

```text
rtsp://username:password@192.168.1.50:554/stream1
```

For local laptop testing with a camera server running on the host, use the host LAN IP instead of `localhost`.

## Face detection provider

The default production template uses `AI_PROVIDER=insightface` with `ALLOW_PROVIDER_FALLBACK=false`, so the AI service does not silently fall back to the weak OpenCV development detector. The first start downloads InsightFace model weights into the container cache.

If the Settings page shows `opencv_mock_...`, accurate CCTV face detection is not active yet. Rebuild the AI service after changing provider settings:

```bash
docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d --build ai-service
```

## GPU override

The default deployment uses CPU mode. For an NVIDIA GPU host, install the NVIDIA Container Toolkit on the host, then run:

```bash
docker compose --env-file docker/.env.production \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.gpu.yml \
  up -d --build
```

## HTTPS

The default `nginx.conf` is HTTP-only. For HTTPS, use a real certificate from your infrastructure or reverse proxy. `docker/nginx/nginx-ssl.example.conf` shows the expected proxy settings. Do not deploy face recognition over public HTTP.

## Production checklist

- Change `POSTGRES_PASSWORD`, `JWT_SECRET`, `INTERNAL_API_KEY`, and admin password.
- Use HTTPS in front of nginx.
- Restrict server firewall access to ports you actually need.
- Keep PostgreSQL and Redis private; do not publish their ports publicly.
- Review consent, retention, and deletion requirements before registering biometric data.
- Back up PostgreSQL and the `vision-ai-storage-data` volume.
