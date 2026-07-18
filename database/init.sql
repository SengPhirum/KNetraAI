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
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'onvif')),
    onvif_host TEXT,
    onvif_profile_token TEXT,
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
    consent_at TIMESTAMPTZ,
    notes TEXT,
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
