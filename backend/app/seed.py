from .config import settings
from .db import execute, fetchrow
from .security import hash_password


async def run_migrations() -> None:
    """Idempotent schema upgrades for deployments created before a given column existed.

    This project has no migration framework - database/init.sql only runs via
    docker-entrypoint-initdb.d on a brand-new database. Existing deployments upgrade
    in place via these safe-to-repeat statements.
    """
    await execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
    await execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS onvif_host TEXT")
    await execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS onvif_profile_token TEXT")
    await execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN NOT NULL DEFAULT FALSE")
    await execute("ALTER TABLE cameras ALTER COLUMN ai_enabled SET DEFAULT FALSE")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS email TEXT")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS phone TEXT")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS fp_user_id TEXT")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS shift_start TEXT")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS shift_end TEXT")
    await execute("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS attendance_role TEXT NOT NULL DEFAULT 'none'")
    await execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS is_dummy BOOLEAN NOT NULL DEFAULT FALSE")
    # 'test' source = camera playing a looped local video file (Settings > Demo / Live > Test Videos).
    await execute("ALTER TABLE cameras DROP CONSTRAINT IF EXISTS cameras_source_check")
    await execute("ALTER TABLE cameras ADD CONSTRAINT cameras_source_check CHECK (source IN ('manual', 'onvif', 'test'))")
    await execute(
        """
        CREATE TABLE IF NOT EXISTS fp_devices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
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
            direction TEXT NOT NULL DEFAULT 'both' CHECK (direction IN ('in', 'out', 'both')),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status TEXT NOT NULL DEFAULT 'unknown',
            device_serial TEXT,
            last_seen_at TIMESTAMPTZ,
            last_sync_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await execute("ALTER TABLE fp_devices ADD COLUMN IF NOT EXISTS protocol TEXT NOT NULL DEFAULT 'zk'")
    await execute("ALTER TABLE fp_devices ADD COLUMN IF NOT EXISTS api_url TEXT NOT NULL DEFAULT ''")
    await execute("ALTER TABLE fp_devices ADD COLUMN IF NOT EXISTS api_username TEXT NOT NULL DEFAULT ''")
    await execute("ALTER TABLE fp_devices ADD COLUMN IF NOT EXISTS api_password TEXT NOT NULL DEFAULT ''")
    await execute("ALTER TABLE fp_devices ALTER COLUMN host SET DEFAULT ''")
    await execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id UUID REFERENCES fp_devices(id) ON DELETE SET NULL,
            device_user_id TEXT NOT NULL,
            person_id UUID REFERENCES persons(id) ON DELETE SET NULL,
            punch_type TEXT NOT NULL DEFAULT 'unknown' CHECK (punch_type IN ('in', 'out', 'unknown')),
            punched_at TIMESTAMPTZ NOT NULL,
            raw JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_records_dedupe
        ON attendance_records (COALESCE(device_id, '00000000-0000-0000-0000-000000000000'::uuid), device_user_id, punched_at)
        """
    )
    await execute("CREATE INDEX IF NOT EXISTS idx_attendance_records_person_time ON attendance_records(person_id, punched_at DESC)")
    await execute("CREATE INDEX IF NOT EXISTS idx_attendance_records_time ON attendance_records(punched_at DESC)")
    await execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            person_id UUID REFERENCES persons(id) ON DELETE CASCADE,
            camera_id UUID REFERENCES cameras(id) ON DELETE SET NULL,
            alert_type TEXT NOT NULL CHECK (alert_type IN ('missed_check_in', 'missed_check_out')),
            message TEXT NOT NULL,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await execute("CREATE INDEX IF NOT EXISTS idx_attendance_alerts_time ON attendance_alerts(detected_at DESC)")
    await execute("CREATE INDEX IF NOT EXISTS idx_attendance_alerts_person ON attendance_alerts(person_id, alert_type, detected_at DESC)")


async def seed_data() -> None:
    await run_migrations()

    roles = [
        ("Admin", "Full access"),
        ("Manager", "Dashboard, reports, and staff/customer profiles"),
        ("Operator", "Live monitoring and limited registration"),
        ("Viewer", "Read-only dashboard and reports"),
    ]
    for name, description in roles:
        await execute(
            "INSERT INTO roles (name, description) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING",
            name,
            description,
        )

    admin_role = await fetchrow("SELECT id FROM roles WHERE name = 'Admin'")
    admin = await fetchrow("SELECT id FROM users WHERE lower(email) = lower($1)", settings.default_admin_email)
    if admin is None:
        await execute(
            """
            INSERT INTO users (email, full_name, password_hash, role_id)
            VALUES ($1, $2, $3, $4)
            """,
            settings.default_admin_email,
            settings.default_admin_name,
            hash_password(settings.default_admin_password),
            admin_role["id"] if admin_role else None,
        )

    defaults = [
        ("recognition_threshold", str(settings.recognition_threshold), "Minimum cosine similarity required to accept a face match"),
        ("greeting_cooldown_seconds", str(settings.greeting_cooldown_seconds), "Cooldown before greeting the same person again"),
        ("gender_min_confidence", str(settings.gender_min_confidence), "Minimum confidence for sir/madam unknown greeting"),
        ("appearance.app_name", "KNetraAI", "Application display name shown in the sidebar and login page"),
        ("appearance.logo_url", "", "Custom logo file path (upload via Settings -> Appearance; empty = built-in logo)"),
        ("appearance.primary_color", "#1E90FF", "Primary UI color for buttons and accents"),
        ("appearance.secondary_color", "#0f172a", "Secondary UI color for the sidebar and dark surfaces"),
        ("schedule.enabled", "false", "Restrict detection event recording to the schedule below"),
        ("schedule.start_time", "08:00", "Daily schedule start (HH:MM, server time)"),
        ("schedule.end_time", "20:00", "Daily schedule end (HH:MM, server time)"),
        ("schedule.days", "mon,tue,wed,thu,fri,sat,sun", "Comma-separated days when detection events are recorded"),
        ("presence.absence_seconds", "30", "Seconds a person must be out of camera view before they count as having left the zone (enables a new greeting on return)"),
        ("detection.min_face_capture", "0.75", "Minimum face capture score (visibility x detection quality, 0-1) required to store a detection event"),
        ("detection.require_gender_or_person", "true", "Store a detection event only when the person is recognized or a gender was estimated"),
        ("retention.days", "0", "Auto-delete detection events (and snapshots) older than this many days (0 = keep forever)"),
        ("voice.enabled", "false", "Speak greetings aloud in the browser on the Live Monitoring page"),
        ("voice.greet_known", "true", "Speak greetings for recognized people"),
        ("voice.greet_unknown", "true", "Speak sir/madam/neutral greetings for unknown people"),
        ("voice.repeat_seconds", "60", "Minimum seconds before the same person/zone greeting is spoken again on a device"),
        ("voice.rate", "1.0", "Voice speaking rate (0.5 - 2.0)"),
        ("voice.volume", "1.0", "Voice volume (0.0 - 1.0)"),
        ("voice.voice_name", "", "Preferred browser speech voice name (empty = browser default)"),
        ("person_api.config", "", "External HR/CRM person API import configuration (JSON)"),
        ("attendance.enabled", "false", "Enable attendance mode (fingerprint devices + missed scan-in/out alerts)"),
        ("attendance.timezone", "", "IANA timezone for attendance logic, e.g. Asia/Phnom_Penh (empty = server timezone)"),
        ("attendance.sync_interval_seconds", "30", "How often to pull punch records from fingerprint devices"),
        ("attendance.checkin_window_start", "06:00", "Missed scan-in alerts only fire between these times (HH:MM)"),
        ("attendance.checkin_window_end", "12:00", "End of the morning missed scan-in alert window (HH:MM)"),
        ("attendance.checkin_deadline", "09:00", "Staff scanning in after this time count as late (reports)"),
        ("attendance.checkout_time", "17:00", "Default earliest checkout time; staff-specific shift end overrides this"),
        ("attendance.checkout_lookback_minutes", "120", "An 'out' punch within this many minutes counts as scanned out"),
        ("attendance.alert_repeat_minutes", "30", "Do not repeat the same attendance alert for a person within this window"),
        ("attendance.voice_alerts", "true", "Speak attendance alerts aloud on the Live Monitoring page"),
        ("attendance.msg_missed_in", "{name}, you missed scan in. Please scan your fingerprint.", "Voice/text template for missed check-in ({name} placeholder)"),
        ("attendance.msg_missed_out", "{name}, you are missing scan out. Please scan before leaving.", "Voice/text template for missed check-out ({name} placeholder)"),
    ]
    for key, value, description in defaults:
        await execute(
            """
            INSERT INTO settings (key, value, description)
            VALUES ($1, $2, $3)
            ON CONFLICT (key) DO NOTHING
            """,
            key,
            value,
            description,
        )

    await execute(
        """
        INSERT INTO greeting_templates (language, known_template, male_template, female_template, neutral_template)
        VALUES ('en', 'Welcome back, {name}', 'Hello sir', 'Hello madam', 'Hello, welcome')
        ON CONFLICT (language) DO NOTHING
        """
    )
