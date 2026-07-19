CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role_id UUID REFERENCES roles(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cameras (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    branch TEXT,
    location TEXT,
    rtsp_url TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ai_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'stopped',
    last_seen_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'onvif', 'test')),
    onvif_host TEXT,
    onvif_profile_token TEXT,
    -- Attendance mode: which door this camera watches ('none' = not used for attendance).
    attendance_role TEXT NOT NULL DEFAULT 'none' CHECK (attendance_role IN ('none', 'entry', 'exit', 'both')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_type TEXT NOT NULL CHECK (person_type IN ('staff', 'customer')),
    full_name TEXT NOT NULL,
    gender TEXT CHECK (gender IN ('male', 'female', 'unknown')) DEFAULT 'unknown',
    branch TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    staff_id TEXT,
    department TEXT,
    position TEXT,
    customer_id TEXT,
    customer_type TEXT,
    vip_flag BOOLEAN NOT NULL DEFAULT FALSE,
    email TEXT,
    phone TEXT,
    -- Attendance mode: staff user ID on the fingerprint machine (falls back to staff_id)
    -- and optional per-staff shift times ("HH:MM") overriding the global settings.
    fp_user_id TEXT,
    shift_start TEXT,
    shift_end TEXT,
    consent_at TIMESTAMPTZ,
    notes TEXT,
    -- Dummy demo rows created by Settings > Maintenance "Init dummy data"; the
    -- matching Clear button deletes everything flagged here.
    is_dummy BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_persons_type ON persons(person_type);
CREATE INDEX IF NOT EXISTS idx_persons_status ON persons(status);

CREATE TABLE IF NOT EXISTS person_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    original_filename TEXT,
    quality_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    person_image_id UUID REFERENCES person_images(id) ON DELETE SET NULL,
    embedding vector(512) NOT NULL,
    model_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_face_embeddings_person ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS idx_face_embeddings_vector_cosine ON face_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS detection_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,
    person_type TEXT NOT NULL DEFAULT 'unknown' CHECK (person_type IN ('staff', 'customer', 'unknown')),
    confidence DOUBLE PRECISION,
    gender_estimate TEXT,
    gender_confidence DOUBLE PRECISION,
    greeting TEXT NOT NULL,
    snapshot_path TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_detection_events_detected_at ON detection_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_detection_events_camera ON detection_events(camera_id);
CREATE INDEX IF NOT EXISTS idx_detection_events_person ON detection_events(person_id);

CREATE TABLE IF NOT EXISTS greeting_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    language TEXT NOT NULL DEFAULT 'en',
    known_template TEXT NOT NULL DEFAULT 'Welcome back, {name}',
    male_template TEXT NOT NULL DEFAULT 'Hello sir',
    female_template TEXT NOT NULL DEFAULT 'Hello madam',
    neutral_template TEXT NOT NULL DEFAULT 'Hello, welcome',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(language)
);

-- ---------------------------------------------------------------------------
-- Attendance mode (optional): fingerprint devices, punch records, and alerts.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fp_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    -- How punches reach this system:
    --   'zk'        direct ZKTeco device protocol (host/port/comm key, polled)
    --   'adms_push' device pushes to this server's /iclock endpoints (matched by serial)
    --   'biotime'   ZKTeco BioTime/ZKBioTime server REST API (URL + username/password, polled)
    protocol TEXT NOT NULL DEFAULT 'zk' CHECK (protocol IN ('zk', 'adms_push', 'biotime')),
    host TEXT NOT NULL DEFAULT '',
    port INTEGER NOT NULL DEFAULT 4370,
    comm_key TEXT NOT NULL DEFAULT '0',
    use_udp BOOLEAN NOT NULL DEFAULT FALSE,
    api_url TEXT NOT NULL DEFAULT '',
    api_username TEXT NOT NULL DEFAULT '',
    api_password TEXT NOT NULL DEFAULT '',
    branch TEXT,
    location TEXT,
    -- Which punches this machine records: 'in' (entry door), 'out' (exit door),
    -- or 'both' (staff choose check-in/check-out on the device keypad).
    direction TEXT NOT NULL DEFAULT 'both' CHECK (direction IN ('in', 'out', 'both')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'unknown',
    device_serial TEXT,
    last_seen_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES fp_devices(id) ON DELETE SET NULL,
    device_user_id TEXT NOT NULL,
    person_id UUID REFERENCES persons(id) ON DELETE SET NULL,
    punch_type TEXT NOT NULL DEFAULT 'unknown' CHECK (punch_type IN ('in', 'out', 'unknown')),
    punched_at TIMESTAMPTZ NOT NULL,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_records_dedupe
    ON attendance_records (COALESCE(device_id, '00000000-0000-0000-0000-000000000000'::uuid), device_user_id, punched_at);
CREATE INDEX IF NOT EXISTS idx_attendance_records_person_time ON attendance_records(person_id, punched_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_records_time ON attendance_records(punched_at DESC);

CREATE TABLE IF NOT EXISTS attendance_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES persons(id) ON DELETE CASCADE,
    camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('missed_check_in', 'missed_check_out')),
    message TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_attendance_alerts_time ON attendance_alerts(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_alerts_person ON attendance_alerts(person_id, alert_type, detected_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
