# Architecture

## Pipeline

RTSP camera -> threaded latest-frame reader -> motion gate -> face detection -> alignment/embedding -> backend recognition with pgvector -> known/unknown decision -> gender estimate for unknown -> greeting -> detection event -> SSE dashboard.

## Face detection: YOLO person cascade

`AI_PROVIDER=yolo_cascade` (default) runs detection in two stages instead of scanning
each full frame with the heavy face model:

1. A YOLO12n person detector (ONNX Runtime, ~640px input) finds people in the frame in
   a few milliseconds - most of a CCTV frame is background, so this cheaply narrows down
   where a face could even be.
2. InsightFace (SCRFD detector + ArcFace embeddings + gender) runs only on those person
   crops. Cropping to a person also zooms in on faces that would otherwise be tiny in a
   wide shot, which improves small/far-face recall for less compute than brute-force
   tiling the whole frame.
3. Safety net: if the crop pass finds zero faces (e.g. a close-up greeting-kiosk camera
   where a face fills the frame but little body is visible for YOLO to key off), one
   full-frame InsightFace pass runs as a fallback.

`AI_PROVIDER=insightface` runs InsightFace alone (optionally with frame tiling for wide
shots). The cascade provider falls back to this automatically if the YOLO ONNX model is
missing (e.g. an image built without the Dockerfile's `model-export` stage).

Both stages auto-detect the fastest available ONNX Runtime execution provider (CUDA/
TensorRT/CoreML/DirectML, else CPU) unless `INSIGHTFACE_PROVIDERS`/`YOLO_PROVIDERS` are
set explicitly. Tuning knobs (confidence thresholds, crop padding, input sizes, etc.) are
documented inline in `.env.example`.

By default the image ships CPU-only `onnxruntime` to stay slim. On a host with an NVIDIA
GPU and the NVIDIA Container Toolkit installed, build with the GPU overlay to swap in
`onnxruntime-gpu` and grant the container GPU access, and both stages above will pick up
`CUDAExecutionProvider` automatically:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

## Runtime pipeline performance

- **Threaded frame reader**: each camera worker reads RTSP frames on a dedicated thread
  that always exposes only the newest frame. This stops slow AI inference from causing
  the live view/detections to drift behind wall-clock time (a plain `cap.read()` loop
  backs up when processing can't keep up with the source frame rate).
- **Motion-gated inference**: a cheap grayscale frame-diff skips the AI pass on an
  unchanged scene, with a periodic idle poll (`MOTION_GATING_IDLE_INTERVAL_SECONDS`) as a
  safety net so a person who walks in and immediately holds still is still caught. Cuts
  average CPU/GPU load on scenes that are empty most of the time. Disable with
  `MOTION_GATING_ENABLED=false` if continuous full-rate inference is required.
- **Adaptive frame skip**: each camera worker tracks a rolling average of its own
  inference time. If a device can't keep up with `PROCESS_FPS`, the worker backs its
  target rate off to whatever it can actually sustain instead of continuously falling
  further behind. Disable with `ADAPTIVE_FRAME_SKIP=false`.
- **Inference concurrency cap**: `MAX_CONCURRENT_INFERENCE` (0 = unlimited) bounds how
  many camera workers may run AI inference at the same instant, shared process-wide via
  an `asyncio.Semaphore`. On a single-board computer, several cameras all inferring in
  parallel thrashes the CPU worse than making them take turns - each finishes faster with
  exclusive use of the core budget than all of them crawling forward together.

## Device profiles (Raspberry Pi / low-power tuning)

`DEVICE_PROFILE` (default `auto`) resolves at startup to `low`/`balanced`/`high` and
adjusts a set of performance-sensitive defaults accordingly - model input sizes, ONNX
Runtime thread counts, target FPS, motion-gating thresholds, and (for `low`) which model
files/packs are used. `auto` classifies the host from `platform.machine()` and CPU count
(`app/vision/hw.py::detect_device_class`): an ARM board with 4 or fewer CPUs (Raspberry
Pi 3/4/5 and similar SBCs) resolves to `low`; ARM architecture alone is not treated as a
weak-device signal (Apple Silicon, AWS Graviton, etc. are ARM and fast), only ARM paired
with a modest core count is.

The override only touches settings still at their hardcoded default - anything you've
set explicitly in `.env` (even to a value that happens to match the default) is left
alone. This is checked against the field's default, not whether it appears in `.env`,
since `.env.example` spells out an explicit value for nearly everything and
`env_file: .env` injects all of it as real process env vars either way.

The `low` tier:

- `YOLO_PERSON_MODEL_PATH` -> `yolo12n-int8.onnx`, a dynamically-quantized (INT8
  weights) copy the Docker build produces alongside the fp32 model. Roughly a third
  the size and noticeably faster on CPUs without AVX512/VNNI - i.e. essentially any
  ARM SBC. Produced via `onnxruntime.quantization.quantize_dynamic` after the
  recommended `quant_pre_process` shape-inference pass (see the `model-export` stage
  in `ai-service/Dockerfile` / `docker/ai-service.Dockerfile`, or run
  `scripts/export_yolo_person_model.py --quantize` for local/dev use).
- `YOLO_INPUT_SIZE` / `YOLO_FACE_DET_SIZE` drop from 640 to 320, `INSIGHTFACE_DET_SIZE`
  from 960 to 480, and `INSIGHTFACE_MODEL` switches from `buffalo_l` to InsightFace's
  smaller `buffalo_s` pack (downloads automatically the same way as `buffalo_l`).
- `ONNX_INTRA_OP_THREADS`/`ONNX_INTER_OP_THREADS` are capped so one camera's inference
  doesn't claim every core, and `MAX_CONCURRENT_INFERENCE=1` serializes multiple
  cameras instead of letting them contend.
- `PROCESS_FPS` drops to 1.0 and motion-gating thresholds loosen, since a slower device
  should aim to do less work per second, not just the same work faster.

InsightFace's own model loader (`insightface.model_zoo.get_model`) only ever forwards
`providers`/`provider_options` on to ONNX Runtime - any other kwarg, including
`sess_options`, is silently dropped. There's no supported way to hand it a tuned
`SessionOptions` directly, so `InsightFaceProvider._configure_thread_settings()` patches
the `PickableInferenceSession` class it instantiates internally instead, so every
sub-model it loads (detector, recognizer, genderage, ...) picks up the thread cap. This
only patches anything at all when `ONNX_INTRA_OP_THREADS`/`ONNX_INTER_OP_THREADS` are
actually set (i.e. never on the default `high` profile).

Override the resolved tier explicitly (`DEVICE_PROFILE=low|balanced|high`) if
auto-detection picks the wrong one for a given board, or to try low-power settings on
a machine that wouldn't otherwise qualify.

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
- The browser never talks to the backend directly - see "Same-origin API access" below.

## Same-origin API access

The browser only ever talks to the frontend's own origin. Every REST call, the SSE
dashboard feed, and MJPEG live-view streams go through `/api/**`, which the frontend's
own Nitro server (`frontend/server/api/[...path].ts`) reverse-proxies to the backend
server-side (`BACKEND_URL`/`NUXT_BACKEND_URL`, a container-to-container address never
sent to the client). `frontend/app/composables/useApiBaseUrl.ts` is the single seam this
routes through - every call site in the app already builds its URL from that composable,
so nothing else needed to change.

This means:
- The backend's own address/port doesn't need to be reachable from the browser or LAN at
  all - `docker-compose.yml` still publishes it (`BACKEND_HOST_PORT`) only for direct API
  docs/debugging access, not because the app needs it.
- No CORS is involved in the app's own traffic (same-origin request), though the backend
  still accepts `CORS_ORIGINS` for anyone hitting its published port directly.
- `redirect: 'manual'` on the proxy matters for one path, `/auth/oidc/login`: the backend
  answers with a 302 to the external IdP, and the *browser* (not the proxy) has to follow
  it so the IdP sees the user's own cookies. The rest of the OIDC round trip
  (IdP -> callback) happens via direct browser navigation to the backend's own
  `API_BASE_URL`, independent of this proxy - see `backend/app/routers/auth.py`'s
  `_oidc_redirect_uri()`.

The `docker/` production compose stack (nginx in front of frontend + backend) already
solves the same problem a different way: `nginx.conf` routes `/api/` straight to the
backend container, bypassing the frontend entirely, so this Nitro proxy is simply never
invoked there - both mechanisms are safe to keep since only one is ever on the request
path for a given deployment.

## Runtime configuration

- Settings table drives AI thresholds, greeting templates, appearance (app name, logo, primary/secondary colors), and the detection schedule.
- The detection schedule is enforced at the backend event-ingest endpoint; outside the window, camera workers keep running but events are not recorded.
- Appearance is exposed on a public endpoint so the login page is branded before authentication; the frontend applies colors as CSS variables at load.
