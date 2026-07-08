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
