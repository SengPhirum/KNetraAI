# KNetraAI - User Manual and Configuration Guide

Version: Walk-in Greeting AI MVP  
Updated: 2026-07-05

This guide explains how to deploy, configure, and use KNetraAI. The first module is Walk-in Greeting AI, which connects to CCTV/IP cameras, detects faces, recognizes registered staff or customers, and saves greeting events in real time.

> Screenshot examples use demo data and are stored in `docs/screenshots/`.

## 1. Interface preview

![Dashboard](screenshots/dashboard.png)

![Live Monitoring](screenshots/live-monitoring.png)

![Camera Management](screenshots/camera-management.png)

![Staff and Customer Database](screenshots/staff-customer-database.png)

## 2. Default access

Local quick start URLs:

```text
Frontend: http://localhost:3010
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

1. Login as Admin (local password, SSO, or LDAP - see section 11).
2. Add a camera in Camera Management - use **Discover Cameras (ONVIF)** to connect by IP and pick a channel from a list (section 6.0), or add an RTSP URL manually (in-app Camera Setup Help covers Hikvision, EZVIZ, Dahua, and more).
3. Create staff or customer profiles - one at a time, by CSV import, or by HR/CRM API sync (section 7).
4. Upload multiple clear face images for each person.
5. Start the camera worker.
6. Monitor the real-time live view grid and recognition events on the dashboard and Live Monitoring page (section 6.8).
7. Review Detection History and export reports.
8. Tune AI thresholds, greeting templates, appearance, and the detection schedule in Settings.

## 5. User roles

| Role | Main permissions |
| --- | --- |
| Admin | Full access to users, cameras, persons, settings, events, and audit logs. |
| Manager | Dashboard, reports, staff/customer profile management, detection history. |
| Operator | Live monitoring, camera operation, limited person registration if allowed. |
| Viewer | Read-only access to dashboard and reports. |

## 6. Camera configuration

The system connects to any camera or NVR that provides an RTSP stream. This section explains the RTSP URL format, how to find the required information on your camera, and step-by-step integration guides for common third-party brands (Hikvision, EZVIZ, Dahua, TP-Link Tapo, Reolink, and generic ONVIF cameras).

The same guidance is also available inside the app: open **Camera Management** and click **Camera Setup Help** next to the Add Camera form.

### 6.0 ONVIF discovery and channel picker (recommended first)

Most modern cameras and NVRs (Hikvision, Dahua, Uniview, Axis, Reolink, and most generic IP cameras) support the ONVIF standard. Instead of typing an RTSP URL, use the **Discover Cameras (ONVIF)** panel at the top of Camera Management:

1. **Scan Network** (optional) tries to auto-find ONVIF devices on the local network. This is best-effort: it uses a discovery broadcast that often cannot reach devices from inside a Docker container, so an empty result is normal - just enter the IP directly in step 2.
2. **Connect by IP**: enter the camera or NVR's IP address, port (usually 80), and its ONVIF username/password (this is often the same admin login used for the camera's web page, not a cloud app account).
3. Click **Fetch Channels**. The app lists every channel/profile the device reports (name, resolution, codec) with a checkbox and an editable name.
4. Use **Test** to confirm a channel streams correctly before adding it.
5. Check the channel(s) you want - on an NVR this lets you add every camera channel in one pass - and click **Add Selected Channels**. The RTSP URL for each channel is resolved and saved automatically; no manual URL entry needed.

If a camera does not support ONVIF (or discovery fails), use the manual **Add Camera** form below with the brand guides in section 6.1-6.4.

### 6.1 RTSP URL anatomy

Every RTSP URL has the same structure:

```text
rtsp://<username>:<password>@<camera-ip>:<port>/<stream-path>
        └── camera login ──┘  └─ LAN IP ─┘ └554┘ └─ brand specific ─┘
```

- **username / password** - the camera's own login (not your cloud app login, unless noted below).
- **camera-ip** - the camera's LAN IP address (see 6.2).
- **port** - RTSP port, `554` on almost every brand. If omitted, 554 is assumed.
- **stream-path** - differs per brand; see the brand table in 6.4.

> **Special characters in passwords must be URL-encoded.** A password like `P@ss#1` must be written as `P%40ss%231` inside the URL (`@` → `%40`, `#` → `%23`, `:` → `%3A`, `/` → `%2F`, space → `%20`). Otherwise the URL parser reads the `@` as the end of the credentials.

**Main stream vs sub stream.** Most cameras publish two streams: a high-resolution *main stream* and a lighter *sub stream*. For face recognition, use the **main stream** when the entrance is more than ~3 m from the camera; use the sub stream only if CPU or bandwidth is limited.

### 6.2 Finding your camera's IP address

Pick whichever is easiest:

1. **Router admin page** - open your router's DHCP client list and look for the camera's brand name or MAC vendor.
2. **Brand discovery tool** - Hikvision **SADP**, Dahua **ConfigTool**, EZVIZ **Studio** (PC app), Reolink Client. These scan the LAN and list every camera of that brand.
3. **Generic scanner** - [ONVIF Device Manager](https://sourceforge.net/projects/onvifdm/) (Windows, free) discovers most IP cameras and can display the exact RTSP URL of each stream (Live video → right side shows the URI).
4. **Mobile network scanner** - apps such as Fing list all devices on the Wi-Fi.

Once found, log in to the camera's web page (`http://<camera-ip>`) and set a **static IP** or create a **DHCP reservation** in the router, so the RTSP URL does not break when the camera reboots.

### 6.3 Before you add the camera - checklist

- [ ] Camera and the KNetraAI server are on the same network (or routable to each other).
- [ ] Camera has a static IP or DHCP reservation.
- [ ] RTSP is **enabled** on the camera (some brands ship with it off - see brand guides).
- [ ] You know the camera's local username/password (or verification code for EZVIZ).
- [ ] Test the URL in VLC first (see 6.5) - if VLC can play it, the system can too.

### 6.4 RTSP URL quick reference by brand

| Brand | Main stream URL | Sub stream URL |
| --- | --- | --- |
| Hikvision / HiLook / Annke | `rtsp://user:pass@IP:554/Streaming/Channels/101` | `.../Channels/102` |
| EZVIZ | `rtsp://admin:VERIFY_CODE@IP:554/h264/ch1/main/av_stream` | `.../ch1/sub/av_stream` |
| Dahua / Imou / Amcrest | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` | `...&subtype=1` |
| TP-Link Tapo / VIGI | `rtsp://user:pass@IP:554/stream1` | `.../stream2` |
| Reolink | `rtsp://user:pass@IP:554/h264Preview_01_main` | `.../h264Preview_01_sub` |
| Uniview (UNV) | `rtsp://user:pass@IP:554/unicast/c1/s0/live` | `.../c1/s1/live` |
| Axis | `rtsp://user:pass@IP:554/axis-media/media.amp` | add `?resolution=640x480` |
| Generic ONVIF | Use ONVIF Device Manager to read the exact URI | - |

If your brand is not listed, search the [iSpy camera connection database](https://www.ispyconnect.com/cameras) - it documents RTSP paths for hundreds of models.

### 6.4.1 Hikvision - detailed guide

1. **Find and activate the camera.** Install [SADP](https://www.hikvision.com/en/support/tools/hitools/) on a PC in the same LAN. It lists all Hikvision devices. A brand-new camera shows *Inactive* - select it and set a strong admin password to activate it.
2. **Log in to the web interface** at `http://<camera-ip>` with the admin account.
3. **Enable RTSP.** Go to **Configuration → Network → Advanced Settings → Integration Protocol** and check that RTSP is enabled (it is on by default on most firmware). Confirm the RTSP port under **Network → Basic Settings → Port** (default `554`).
4. **Set RTSP authentication.** Under **Configuration → System → Security → Authentication**, set *RTSP Authentication* to **digest** (recommended) or *digest/basic*.
5. **(Recommended) Create a dedicated viewer account** under **Configuration → System → User Management** with the *User* level, and use it in the RTSP URL instead of admin.
6. **Build the URL.** The channel code is `<channel><stream>`: channel `1`, main stream `01` → `101`; sub stream → `102`.

   ```text
   Direct camera:  rtsp://viewer:MyPass123@192.168.1.64:554/Streaming/Channels/101
   ```
7. **Hikvision NVR:** connect to the NVR's IP instead; camera N main stream is channel `N01`:

   ```text
   NVR channel 1:  rtsp://viewer:MyPass123@192.168.1.100:554/Streaming/Channels/101
   NVR channel 2:  rtsp://viewer:MyPass123@192.168.1.100:554/Streaming/Channels/201
   NVR channel 2 sub-stream: .../Streaming/Channels/202
   ```
8. Test in VLC (6.5), then add the URL in **Camera Management → Add Camera**.

> If you get *401 Unauthorized* even with the correct password, the account may be locked after failed attempts (wait 30 minutes or reboot the camera) or RTSP authentication is set to a mode your client does not support - switch it to *digest/basic*.

### 6.4.2 EZVIZ - detailed guide

EZVIZ is Hikvision's consumer brand and behaves differently from typical IP cameras:

1. **The RTSP password is the verification code**, not your EZVIZ cloud account password. Find the 6-character code (often labeled *Verification Code*) on the **sticker on the camera body** or the box. The username is always `admin`.
2. **Check that RTSP is enabled.** Newer EZVIZ firmware disables local RTSP by default on some models:
   - Install **EZVIZ Studio** (PC app) → open the camera → **Device Settings → Advanced → Local Service**, and enable RTSP, or
   - In the EZVIZ mobile app, check **Settings → Device Settings** for a *Local streaming / RTSP* toggle (name varies by model), or
   - Log in to the camera's local web page at `http://<camera-ip>` (user `admin`, password = verification code) if your model has one.
3. **Turn off image encryption** in the EZVIZ app (**Settings → Privacy → Image Encryption**), otherwise the stream is scrambled. Note this trade-off: encryption protects cloud clips; local RTSP requires it off.
4. **Build the URL:**

   ```text
   Main stream: rtsp://admin:ABCDEF@192.168.1.80:554/h264/ch1/main/av_stream
   Sub stream:  rtsp://admin:ABCDEF@192.168.1.80:554/h264/ch1/sub/av_stream
   ```

   (`ABCDEF` = your verification code, all capital letters as printed.)
5. Test in VLC, then add it in **Camera Management**.

> **Model limitations:** some recent budget EZVIZ models (and battery models) removed local RTSP entirely and only stream via the EZVIZ cloud. If EZVIZ Studio shows no *Local Service* option and VLC cannot connect, check your model on EZVIZ's support pages; the workaround is to pair the camera to a Hikvision/EZVIZ NVR and pull RTSP from the NVR.

### 6.4.3 Dahua / Imou - quick guide

1. Find the camera with Dahua **ConfigTool** or your router's client list; log in at `http://<camera-ip>`.
2. Ensure RTSP is enabled under **Network → Port** (default 554). For Imou consumer cameras, the password is the *device safety code* on the sticker unless you changed it in the Imou app.
3. URL format:

   ```text
   Main:  rtsp://admin:MyPass@192.168.1.90:554/cam/realmonitor?channel=1&subtype=0
   Sub:   rtsp://admin:MyPass@192.168.1.90:554/cam/realmonitor?channel=1&subtype=1
   ```

   On a Dahua NVR, change `channel=N` to select the camera.

### 6.4.4 TP-Link Tapo - quick guide

1. In the Tapo app: **Camera → Settings (gear) → Advanced Settings → Camera Account** and create a local account (this is separate from your TP-Link ID).
2. URL format:

   ```text
   Main:  rtsp://camaccount:campass@192.168.1.70:554/stream1
   Sub:   rtsp://camaccount:campass@192.168.1.70:554/stream2
   ```

### 6.4.5 Generic / unknown brand (ONVIF)

1. Run **ONVIF Device Manager** on a PC in the same LAN - most IP cameras appear automatically.
2. Enter the camera's credentials, open **Live video**, and copy the RTSP URI shown on screen.
3. If the URI has no credentials embedded, add `user:pass@` after `rtsp://`.

### 6.5 Verify the stream before adding it

Test on the machine that runs the AI service (or at least the same network):

```text
VLC:      Media → Open Network Stream → paste the rtsp:// URL
ffprobe:  ffprobe -rtsp_transport tcp "rtsp://user:pass@ip:554/..."
```

- Plays in VLC → the URL is correct; add it in **Camera Management**.
- Asks for credentials repeatedly → wrong user/password (or EZVIZ verification code).
- Times out → wrong IP/port, RTSP disabled, or a firewall/VLAN blocks port 554.

### 6.6 Placement and performance recommendations

- Stable wired network for entrance cameras.
- Camera positioned near face height.
- Good front lighting.
- Avoid strong backlight.
- Start with 3-5 AI FPS and increase only after testing CPU/GPU capacity.

![Camera Management](screenshots/camera-management.png)

### 6.7 Camera connection troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| VLC plays it but the system shows `error` | AI service container cannot reach the camera IP - check Docker network/routes and that the camera is not on an isolated VLAN or guest Wi-Fi. |
| 401 Unauthorized | Wrong credentials; URL-encode special characters; on Hikvision set RTSP Authentication to digest/basic; account may be temporarily locked. |
| 404 / stream not found | Wrong stream path for the model - confirm the exact path via ONVIF Device Manager or the iSpy database. |
| Connects, then drops after a few seconds | Force TCP transport (the worker uses TCP by default), reduce main stream bitrate, or use the sub stream. |
| Works on phone app but RTSP refuses | RTSP/local service disabled (common on EZVIZ) - enable it per 6.4.2, or the model is cloud-only. |
| Image is scrambled/garbled | EZVIZ image encryption still on, or H.265+ enabled - switch the camera stream to plain H.264. |
| Stream lags several seconds behind | Lower the camera resolution/bitrate or switch to the sub stream; check CPU load on the AI service. |

### 6.8 Live view (real-time CCTV-style grid)

The **Live Monitoring** page shows a real-time video grid, not just detection snapshots:

- A camera's live feed appears as soon as its AI worker is **running** (Start button in Camera Management or the live page). Stopped cameras show a placeholder instead of a broken stream.
- Choose a **1 / 4 / 6 / 9-up** layout; if there are more cameras than fit on one page, use Prev/Next to page through them.
- Double-click a tile, or click **Focus**, to view one camera large; click the fullscreen icon on any tile for a fullscreen feed. Click **Back to grid** to return.
- The feed auto-reconnects a few seconds after a network hiccup.
- This uses MJPEG streaming (one JPEG frame at a time over HTTP), reusing the same video the AI worker already captures - there is no extra RTSP connection per viewer. It is intentionally simple (works in every browser, no plugins) rather than the lowest-possible-latency option; very high camera counts or many simultaneous viewers of the same camera will use more bandwidth than a dedicated NVR client.

## 7. Person registration and face enrollment

Register each staff/customer profile with consent before uploading face images. Use 3-5 clear enrollment photos from different angles. The backend calls the AI service to create embeddings and stores them in PostgreSQL with pgvector.

![Staff and Customer Database](screenshots/staff-customer-database.png)

### 7.1 Ways to add people

1. **One at a time** - Staff/Customer Database → Add Person.
2. **CSV import** - Staff/Customer Database → Import / Sync → upload a CSV. Only `full_name` is required; download the template from the same panel for all optional columns (`person_type`, `staff_id`, `customer_id`, `branch`, `vip_flag`, `consent_confirmed`, ...).
3. **API sync from HR/CRM systems** - external systems push people to `POST /persons/import-json` with an Admin/Manager bearer token.

### 7.2 Sync mode (avoiding duplicates)

Both import paths support two modes:

- **Create** (default): rows whose `staff_id`/`customer_id` already exists are skipped and reported.
- **Sync (upsert)**: rows are matched on `staff_id` (staff) or `customer_id` (customer) and updated in place. Run a scheduled `import-json` call in this mode to keep KNetraAI aligned with your HR or CRM system.

Rows without a `staff_id`/`customer_id` have no sync key and are always created, so include stable IDs when you plan to re-import. Face images must still be enrolled in the app after import.

## 8. AI settings

Important settings:

| Setting | Purpose | Typical value |
| --- | --- | --- |
| recognition_threshold | Minimum vector similarity for known face match. | 0.60-0.70 |
| greeting_cooldown_seconds | Prevents duplicate greetings for the same person. | 300 |
| gender_min_confidence | Uses neutral greeting below confidence. | 0.75 |
| AI_PROVIDER | `opencv_mock` for development or `insightface` for production. | opencv_mock / insightface |

![Settings](screenshots/settings.png)

### 8.1 Deep learning provider

Settings → **Deep Learning Provider** shows the provider the AI service is actually running. `opencv_mock_...` means the lightweight development provider (not real face recognition). To switch to InsightFace:

1. Uncomment `insightface` and `onnxruntime` in `ai-service/requirements.txt`.
2. Set `AI_PROVIDER=insightface` in `.env`.
3. Rebuild: `docker compose up -d --build ai-service` (first start downloads model weights).
4. Confirm the provider name changes on the settings card.

## 9. Appearance and branding

Settings → **Appearance** (Admin only) controls the look of the whole app without code changes:

- **Application name** - shown in the sidebar, login page, and browser title.
- **Primary color** - buttons and accents. Default: dodgerblue `#1E90FF`.
- **Secondary color** - sidebar and dark surfaces. Default: `#0f172a`.
- **App logo** - upload PNG/SVG/JPG/WebP; square images look best. Reset restores the built-in KNetraAI logo.

Changes apply immediately for all users, including the login page (branding is public). The built-in logo also ships as a full PWA icon set (`frontend/public/icons/`) with a web manifest, so the app installs with proper icons on mobile and desktop.

## 10. Detection schedule

Settings → **Detection Schedule** limits when detection events are recorded (server time):

- Enable the schedule, pick start/end times and active days.
- Outside the window, camera workers keep running but events and greetings are suppressed at the backend (`{"skipped": "outside_schedule"}`).
- Overnight windows (e.g. 20:00 → 06:00) are supported.

## 11. Authentication: local, OIDC SSO, and LDAP

KNetraAI supports three login methods, all configured directly in the app under **Settings → Authentication** (Admin only). Each method has its own panel with an enable toggle and its configuration; changes apply immediately - no restart needed. Environment variables in `.env` still work as initial defaults, but values saved in the UI override them.

Safety guard: the backend refuses to save a configuration that would disable every login method, so you cannot lock yourself out.

### 11.1 Local accounts

Default method. Admins manage accounts on the Users page. The Local panel also sets **password rules** enforced when creating users or changing passwords (existing passwords are unaffected):

- Minimum length (default 8)
- Require uppercase / lowercase / digit / special character (each optional)

### 11.2 OIDC single sign-on (Keycloak, Authentik, ...)

Works with any OpenID Connect provider. Users are matched by email and auto-created with `OIDC_DEFAULT_ROLE` on first login (set `OIDC_AUTO_CREATE_USERS=false` to require pre-created accounts).

**Keycloak:**

1. Admin console → your realm → Clients → Create client (type OpenID Connect, ID `knetraai`).
2. Enable Client authentication + Standard flow.
3. Valid redirect URIs: `<API_BASE_URL>/auth/oidc/callback`; Web origins: your frontend URL.
4. Copy the secret from the Credentials tab; ensure users have an email set.

**Authentik:**

1. Applications → Providers → Create → OAuth2/OpenID Provider (Confidential) with redirect URI `<API_BASE_URL>/auth/oidc/callback`.
2. Create an Application with slug `knetraai` linked to the provider.
3. Issuer URL: `https://<authentik-host>/application/o/knetraai/`.

**Then in KNetraAI:** open **Settings → Authentication → OIDC Single Sign-On**, toggle it on, and fill in the issuer URL, client ID, and client secret (the same guides are shown inline there). Save - a "Continue with ..." button appears on the login page immediately.

The redirect URI to register at the provider is `<API_BASE_URL>/auth/oidc/callback`; `API_BASE_URL` and `FRONTEND_BASE_URL` in `.env` must match the public URLs the browser uses. The client secret is stored server-side and never shown again - the form displays a placeholder and leaving it blank keeps the saved value.

### 11.3 LDAP / Active Directory

Open **Settings → Authentication → LDAP / Active Directory**, toggle it on, and configure:

- **Server URL**, e.g. `ldaps://ad.example.com:636`
- **Option A - direct bind:** a user DN template such as `uid={username},ou=users,dc=example,dc=org`
- **Option B - search + bind** (typical for Active Directory): a service-account bind DN + password and a search base; the default filter matches `uid`, `sAMAccountName`, or `mail`
- Email/name attributes and the default role for new LDAP users

Save - the login page gains an "LDAP / Active Directory" tab immediately; users are provisioned on first successful bind using their directory email and name. The same settings can be pre-seeded via `LDAP_*` variables in `.env` (UI values override them).

## 12. Detection history

Every event stores timestamp, camera, snapshot, known/unknown person decision, confidence, gender estimate when unknown, and greeting text.

![Detection History](screenshots/detection-history.png)

## 13. Privacy and security checklist

- Get consent before registering biometric face data.
- Use signage that AI CCTV detection is active.
- Replace all default secrets.
- Use HTTPS in production.
- Restrict access by role.
- Keep audit logs.
- Define retention for snapshots and event logs.
- Delete face images and embeddings when a person requests removal.
- Do not expose images through public URLs.

## 14. Troubleshooting

| Problem | Check |
| --- | --- |
| Camera does not start | Confirm RTSP URL, network route, camera credentials, and firewall. See section 6.4 for brand-specific URLs and 6.7 for detailed camera troubleshooting. |
| No detections | Check lighting, camera angle, AI worker logs, and process FPS. |
| Wrong recognition | Add better enrollment photos and tune `recognition_threshold`. |
| Dashboard not updating | Check backend SSE endpoint, nginx proxy, and browser console. |
| Upload fails | Check storage volume permissions and AI service health. |
| Docker stack fails | Run `docker compose ps` and review service logs. |
| SSO button missing on login page | `OIDC_ENABLED` not true or backend not restarted; check `GET /auth/methods`. |
| OIDC login loops with an error | Redirect URI in the provider must exactly match `<API_BASE_URL>/auth/oidc/callback`; check `OIDC_ISSUER` and that the user has an email claim. |
| LDAP login rejected | Verify `LDAP_SERVER_URL`, bind mode (template vs search), and test the same credentials with `ldapsearch`. |
| No events recorded during the day | Detection schedule may be enabled with a narrow window - check Settings → Detection Schedule. |
| Import CSV rejected | Ensure the file has a `full_name` header column; download the template from the Import / Sync panel. |

## 15. Backup and restore

Backup:

```bash
bash docker/scripts/backup-postgres.sh
```

Restore:

```bash
bash docker/scripts/restore-postgres.sh backups/your-backup.sql
```

## 16. Important files

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
