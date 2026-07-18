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
