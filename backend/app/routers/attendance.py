"""Attendance mode: fingerprint devices, punch records, and missed scan-in/out alerts.

Device support:
  - ZKTeco-protocol terminals (the most common fingerprint attendance machines)
    are polled directly over TCP/UDP port 4370 via the ``pyzk`` library.
  - Anything else can push punches to POST /attendance/push.

Alert logic runs when the AI recognizes a staff member on a camera marked as an
entry/exit door (cameras.attendance_role) - see check_attendance_on_detection().
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..audit import write_audit
from ..db import execute, fetch, fetchrow
from ..schemas import (
    AttendanceAlertsClearRequest,
    AttendancePushRequest,
    FpDeviceCreate,
    FpDeviceUpdate,
    FpDiscoverRequest,
)
from ..security import require_roles
from ..utils import rows_to_dicts, to_jsonable

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attendance"])

_TRUTHY = ("1", "true", "yes")

# ZK punch codes -> punch type. Staff often never press the in/out key, so
# 'unknown' is common and treated as matching either direction in the rules.
_PUNCH_CODE_MAP = {0: "in", 1: "out", 2: "out", 3: "in", 4: "in", 5: "out"}

_sync_running = asyncio.Lock()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

async def _setting(key: str, default: str) -> str:
    row = await fetchrow("SELECT value FROM settings WHERE key = $1", key)
    return row["value"] if row and row["value"] != "" else default


async def _setting_float(key: str, default: float) -> float:
    try:
        return float(await _setting(key, str(default)))
    except ValueError:
        return default


async def attendance_enabled() -> bool:
    return (await _setting("attendance.enabled", "false")).lower() in _TRUTHY


async def business_tz() -> tzinfo:
    """Timezone all attendance rules are evaluated in (devices report wall time)."""
    name = await _setting("attendance.timezone", "")
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            logger.warning("Invalid attendance.timezone %r, using server timezone", name)
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def _parse_hhmm(value: str, fallback: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", (value or "").strip())
    if not match:
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", fallback)
    hour, minute = int(match.group(1)), int(match.group(2))
    return min(hour, 23), min(minute, 59)


# ---------------------------------------------------------------------------
# ZKTeco device I/O (sync functions run in a worker thread)
# ---------------------------------------------------------------------------

def _zk_connect(host: str, port: int, comm_key: str, use_udp: bool, timeout: int = 10):
    try:
        from zk import ZK
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyzk is not installed on the backend") from exc
    try:
        key = int(comm_key or 0)
    except ValueError:
        key = 0
    zk = ZK(host, port=port, timeout=timeout, password=key, force_udp=use_udp, ommit_ping=True)
    return zk.connect()


def _zk_test_sync(host: str, port: int, comm_key: str, use_udp: bool) -> dict:
    conn = _zk_connect(host, port, comm_key, use_udp, timeout=8)
    try:
        info: dict[str, Any] = {
            "serial": conn.get_serialnumber(),
            "firmware": conn.get_firmware_version(),
            "device_name": None,
            "device_time": None,
            "users": None,
            "records": None,
        }
        try:
            info["device_name"] = conn.get_device_name()
        except Exception:
            pass
        try:
            conn.read_sizes()
            info["users"] = conn.users
            info["records"] = conn.records
        except Exception:
            pass
        try:
            device_time = conn.get_time()
            info["device_time"] = device_time.isoformat()
            info["clock_drift_seconds"] = round((device_time - datetime.now()).total_seconds())
        except Exception:
            pass
        return info
    finally:
        conn.disconnect()


def _zk_pull_sync(host: str, port: int, comm_key: str, use_udp: bool, since: datetime | None) -> dict:
    """Read attendance records (newer than ``since``, naive device wall time)."""
    conn = _zk_connect(host, port, comm_key, use_udp)
    try:
        serial = None
        try:
            serial = conn.get_serialnumber()
        except Exception:
            pass
        records = []
        for att in conn.get_attendance():
            if since is not None and att.timestamp <= since:
                continue
            records.append(
                {
                    "user_id": str(att.user_id).strip(),
                    "timestamp": att.timestamp,
                    "punch": int(getattr(att, "punch", 255) or 0),
                    "status": int(getattr(att, "status", 0) or 0),
                }
            )
        return {"serial": serial, "records": records}
    finally:
        conn.disconnect()


# ---------------------------------------------------------------------------
# Punch ingestion (shared by device sync and the push endpoint)
# ---------------------------------------------------------------------------

async def _map_person(device_user_id: str, cache: dict[str, str | None]) -> str | None:
    if device_user_id in cache:
        return cache[device_user_id]
    row = await fetchrow(
        """
        SELECT id FROM persons
        WHERE person_type = 'staff' AND (fp_user_id = $1 OR staff_id = $1)
        ORDER BY (fp_user_id = $1) DESC
        LIMIT 1
        """,
        device_user_id,
    )
    person_id = str(row["id"]) if row else None
    cache[device_user_id] = person_id
    return person_id


def _resolve_punch_type(punch_code: int, device_direction: str) -> str:
    if device_direction in ("in", "out"):
        return device_direction
    return _PUNCH_CODE_MAP.get(punch_code, "unknown")


async def remap_person_punches(person_id: str, fp_user_id: str | None, staff_id: str | None) -> int:
    """Attach unmatched punch records to a person whose FP/staff ID was just
    created or changed - covers punches synced before the profile existed."""
    ids = [value for value in (fp_user_id, staff_id) if value]
    if not ids:
        return 0
    rows = await fetch(
        "UPDATE attendance_records SET person_id = $1::uuid WHERE person_id IS NULL AND device_user_id = ANY($2::text[]) RETURNING id",
        person_id,
        ids,
    )
    return len(rows)


async def _insert_punch(
    device_id: str | None,
    device_user_id: str,
    punched_at: datetime,
    punch_type: str,
    raw: dict,
    person_cache: dict[str, str | None],
) -> bool:
    person_id = await _map_person(device_user_id, person_cache)
    result = await execute(
        """
        INSERT INTO attendance_records (device_id, device_user_id, person_id, punch_type, punched_at, raw)
        VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6::jsonb)
        ON CONFLICT DO NOTHING
        """,
        device_id,
        device_user_id,
        person_id,
        punch_type,
        punched_at,
        json.dumps(raw),
    )
    return result.endswith("1")


# BioTime JWT tokens cached per device id.
_biotime_tokens: dict[str, str] = {}


async def _biotime_token(device: dict, force_refresh: bool = False) -> str:
    key = str(device["id"])
    if not force_refresh and key in _biotime_tokens:
        return _biotime_tokens[key]
    base = (device["api_url"] or "").rstrip("/")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{base}/jwt-api-token-auth/",
            json={"username": device["api_username"], "password": device["api_password"]},
        )
    response.raise_for_status()
    token = response.json().get("token", "")
    if not token:
        raise RuntimeError("BioTime login returned no token - check username/password")
    _biotime_tokens[key] = token
    return token


async def _biotime_pull(device: dict, since: datetime | None) -> dict:
    """Fetch punch transactions from a ZKTeco BioTime / ZKBioTime server."""
    base = (device["api_url"] or "").rstrip("/")
    if not base:
        raise RuntimeError("BioTime server URL is not configured")
    token = await _biotime_token(device)
    params: dict[str, Any] = {"page_size": 500, "ordering": "punch_time"}
    if since is not None:
        params["start_time"] = since.strftime("%Y-%m-%d %H:%M:%S")
    records: list[dict] = []
    url: str | None = f"{base}/iclock/api/transactions/"
    async with httpx.AsyncClient(timeout=25) as client:
        for _ in range(20):  # hard page cap per cycle
            if not url:
                break
            response = await client.get(url, headers={"Authorization": f"JWT {token}"}, params=params)
            if response.status_code == 401:
                token = await _biotime_token(device, force_refresh=True)
                response = await client.get(url, headers={"Authorization": f"JWT {token}"}, params=params)
            response.raise_for_status()
            data = response.json()
            for item in data.get("data", []):
                try:
                    timestamp = datetime.strptime(str(item.get("punch_time")), "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    continue
                try:
                    punch = int(item.get("punch_state", 255))
                except (TypeError, ValueError):
                    punch = 255
                records.append(
                    {
                        "user_id": str(item.get("emp_code", "")).strip(),
                        "timestamp": timestamp,
                        "punch": punch,
                        "status": 0,
                        "terminal_sn": item.get("terminal_sn"),
                    }
                )
            url = data.get("next")
            params = {}  # `next` already carries the query string
    return {"serial": None, "records": [r for r in records if r["user_id"]]}


async def _device_since(device_id: str, tz: tzinfo) -> datetime | None:
    last = await fetchrow(
        "SELECT MAX(punched_at) AS max_at FROM attendance_records WHERE device_id = $1::uuid", device_id
    )
    if last and last["max_at"]:
        # Small overlap so a punch landing mid-read is never missed; dedupe absorbs it.
        return last["max_at"].astimezone(tz).replace(tzinfo=None) - timedelta(minutes=5)
    return None


async def sync_device(device: dict) -> dict:
    """Pull new punches from one fingerprint source into attendance_records.

    'adms_push' devices are not polled - their records arrive on /iclock/cdata.
    """
    if device["protocol"] == "adms_push":
        return {"device_id": str(device["id"]), "ok": True, "new_records": 0, "note": "push device - waiting for /iclock data"}

    tz = await business_tz()
    since = await _device_since(str(device["id"]), tz)
    try:
        if device["protocol"] == "biotime":
            result = await _biotime_pull(device, since)
            source = "biotime"
        else:
            result = await asyncio.to_thread(
                _zk_pull_sync, device["host"], device["port"], device["comm_key"], device["use_udp"], since
            )
            source = "zk"
    except Exception as exc:
        await execute(
            "UPDATE fp_devices SET status = 'offline', last_error = $2, updated_at = now() WHERE id = $1::uuid",
            device["id"],
            str(exc)[:400],
        )
        return {"device_id": str(device["id"]), "ok": False, "error": str(exc)}

    person_cache: dict[str, str | None] = {}
    inserted = 0
    for record in result["records"]:
        punched_at = record["timestamp"].replace(tzinfo=tz)
        punch_type = _resolve_punch_type(record["punch"], device["direction"])
        raw = {"punch": record["punch"], "status": record["status"], "source": source}
        if record.get("terminal_sn"):
            raw["terminal_sn"] = record["terminal_sn"]
        if await _insert_punch(str(device["id"]), record["user_id"], punched_at, punch_type, raw, person_cache):
            inserted += 1

    await execute(
        """
        UPDATE fp_devices
        SET status = 'online', last_seen_at = now(), last_sync_at = now(), last_error = NULL,
            device_serial = COALESCE($2, device_serial), updated_at = now()
        WHERE id = $1::uuid
        """,
        device["id"],
        result.get("serial"),
    )
    return {"device_id": str(device["id"]), "ok": True, "new_records": inserted}


async def run_sync_cycle() -> float:
    """One poll of every enabled device. Returns the configured interval seconds."""
    interval = await _setting_float("attendance.sync_interval_seconds", 30)
    if not await attendance_enabled():
        return max(interval, 30)
    if _sync_running.locked():
        return interval
    async with _sync_running:
        devices = await fetch("SELECT * FROM fp_devices WHERE enabled = TRUE")
        for device in rows_to_dicts(devices):
            try:
                await sync_device(device)
            except Exception as exc:  # pragma: no cover - keep the loop alive
                logger.warning("Attendance sync failed for %s: %s", device.get("name"), exc)
    return interval


# ---------------------------------------------------------------------------
# Missed scan-in / scan-out alerts (called from detection event ingestion)
# ---------------------------------------------------------------------------

async def _recent_alert_exists(person_id: str, alert_type: str, repeat_minutes: float) -> bool:
    row = await fetchrow(
        """
        SELECT 1 FROM attendance_alerts
        WHERE person_id = $1::uuid AND alert_type = $2
          AND detected_at > now() - make_interval(mins => $3)
        LIMIT 1
        """,
        person_id,
        alert_type,
        repeat_minutes,
    )
    return row is not None


async def _has_punch(person_id: str, punch_types: tuple[str, ...], after: datetime) -> bool:
    row = await fetchrow(
        """
        SELECT 1 FROM attendance_records
        WHERE person_id = $1::uuid AND punched_at >= $2 AND punch_type = ANY($3::text[])
        LIMIT 1
        """,
        person_id,
        after,
        list(punch_types),
    )
    return row is not None


async def _emit_alert(
    person: dict,
    camera_id: str | None,
    alert_type: str,
    message: str,
    publish: Callable[[dict, str], Awaitable[None]] | None,
) -> dict:
    row = await fetchrow(
        """
        INSERT INTO attendance_alerts (person_id, camera_id, alert_type, message)
        VALUES ($1::uuid, $2::uuid, $3, $4)
        RETURNING id, detected_at
        """,
        str(person["id"]),
        camera_id,
        alert_type,
        message,
    )
    camera = await fetchrow("SELECT name FROM cameras WHERE id = $1::uuid", camera_id) if camera_id else None
    alert = {
        "id": str(row["id"]),
        "person_id": str(person["id"]),
        "person_name": person["full_name"],
        "camera_id": camera_id,
        "camera_name": camera["name"] if camera else None,
        "alert_type": alert_type,
        "message": message,
        "detected_at": row["detected_at"].isoformat(),
    }
    if publish is not None:
        await publish(alert, "attendance")
    logger.info("Attendance alert: %s - %s", alert_type, message)
    return alert


async def check_attendance_on_detection(
    person_id: str,
    camera_id: str | None,
    attendance_role: str | None,
    publish: Callable[[dict, str], Awaitable[None]] | None = None,
) -> dict | None:
    """Fire a missed check-in/check-out alert for a recognized staff member.

    Rules (all times in the configured attendance timezone):
      - Missed check-in: staff seen on an entry camera inside the morning window
        with no 'in' (or 'unknown') punch recorded today.
      - Missed check-out: staff seen on an exit camera at/after their shift end
        (person.shift_end, else attendance.checkout_time) with no 'out'/'unknown'
        punch within the lookback window.
    Alerts repeat at most once per attendance.alert_repeat_minutes per person.
    """
    try:
        if attendance_role in (None, "", "none") or not await attendance_enabled():
            return None
        person = await fetchrow(
            "SELECT id, full_name, person_type, status, shift_end FROM persons WHERE id = $1::uuid", person_id
        )
        if person is None or person["person_type"] != "staff" or person["status"] != "active":
            return None

        tz = await business_tz()
        now = datetime.now(tz)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        repeat_minutes = await _setting_float("attendance.alert_repeat_minutes", 30)

        if attendance_role in ("entry", "both"):
            start_h, start_m = _parse_hhmm(await _setting("attendance.checkin_window_start", "06:00"), "06:00")
            end_h, end_m = _parse_hhmm(await _setting("attendance.checkin_window_end", "12:00"), "12:00")
            window_start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            window_end = now.replace(hour=end_h, minute=end_m, second=59, microsecond=0)
            if window_start <= now <= window_end:
                if not await _has_punch(person_id, ("in", "unknown"), day_start):
                    if not await _recent_alert_exists(person_id, "missed_check_in", repeat_minutes):
                        template = await _setting(
                            "attendance.msg_missed_in", "{name}, you missed scan in. Please scan your fingerprint."
                        )
                        return await _emit_alert(
                            dict(person), camera_id, "missed_check_in",
                            template.replace("{name}", person["full_name"]), publish,
                        )
                return None

        if attendance_role in ("exit", "both"):
            shift_end = person["shift_end"] or await _setting("attendance.checkout_time", "17:00")
            end_h, end_m = _parse_hhmm(shift_end, "17:00")
            checkout_from = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            if now >= checkout_from:
                lookback = await _setting_float("attendance.checkout_lookback_minutes", 120)
                lookback_start = max(day_start, now - timedelta(minutes=lookback))
                if not await _has_punch(person_id, ("out", "unknown"), lookback_start):
                    if not await _recent_alert_exists(person_id, "missed_check_out", repeat_minutes):
                        template = await _setting(
                            "attendance.msg_missed_out", "{name}, you are missing scan out. Please scan before leaving."
                        )
                        return await _emit_alert(
                            dict(person), camera_id, "missed_check_out",
                            template.replace("{name}", person["full_name"]), publish,
                        )
        return None
    except Exception as exc:  # pragma: no cover - alerts must never break detections
        logger.warning("Attendance check failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# API: status, devices, records, alerts, summary
# ---------------------------------------------------------------------------

@router.get("/attendance/status")
async def attendance_status(user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer"))):
    enabled = await attendance_enabled()
    voice = (await _setting("attendance.voice_alerts", "true")).lower() in _TRUTHY
    return {"enabled": enabled, "voice_alerts": voice}


def _mask_device(device: dict) -> dict:
    device["api_password"] = "********" if device.get("api_password") else ""
    return device


@router.get("/fingerprint-devices")
async def list_fp_devices(user=Depends(require_roles("Admin", "Manager", "Operator"))):
    rows = await fetch(
        """
        SELECT d.*,
               (SELECT COUNT(*) FROM attendance_records ar WHERE ar.device_id = d.id) AS record_count
        FROM fp_devices d
        ORDER BY d.created_at DESC
        """
    )
    return [_mask_device(d) for d in rows_to_dicts(rows)]


@router.post("/fingerprint-devices")
async def create_fp_device(payload: FpDeviceCreate, user=Depends(require_roles("Admin", "Manager"))):
    if payload.protocol == "zk" and not payload.host.strip():
        raise HTTPException(status_code=400, detail="Direct ZK devices need a host/IP")
    if payload.protocol == "biotime" and not payload.api_url.strip():
        raise HTTPException(status_code=400, detail="BioTime devices need the server API URL")
    if payload.protocol == "adms_push" and not (payload.device_serial or "").strip():
        raise HTTPException(status_code=400, detail="ADMS push devices need the device serial number (SN)")
    row = await fetchrow(
        """
        INSERT INTO fp_devices (
            name, protocol, host, port, comm_key, use_udp, api_url, api_username, api_password,
            device_serial, branch, location, direction, enabled
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING *
        """,
        payload.name,
        payload.protocol,
        payload.host.strip(),
        payload.port,
        payload.comm_key,
        payload.use_udp,
        payload.api_url.strip(),
        payload.api_username,
        payload.api_password,
        (payload.device_serial or "").strip() or None,
        payload.branch,
        payload.location,
        payload.direction,
        payload.enabled,
    )
    await write_audit(user, "fp_device.create", "fp_device", str(row["id"]), {"protocol": payload.protocol})
    return _mask_device(to_jsonable(row))


@router.put("/fingerprint-devices/{device_id}")
async def update_fp_device(device_id: str, payload: FpDeviceUpdate, user=Depends(require_roles("Admin", "Manager"))):
    existing = await fetchrow("SELECT * FROM fp_devices WHERE id = $1::uuid", device_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Fingerprint device not found")
    data = payload.model_dump(exclude_unset=True)
    # Blank/masked password input means "keep the stored one".
    if data.get("api_password") in ("", "********"):
        data.pop("api_password", None)
    merged = {**dict(existing), **data}
    row = await fetchrow(
        """
        UPDATE fp_devices
        SET name = $1, protocol = $2, host = $3, port = $4, comm_key = $5, use_udp = $6,
            api_url = $7, api_username = $8, api_password = $9, device_serial = $10,
            branch = $11, location = $12, direction = $13, enabled = $14, updated_at = now()
        WHERE id = $15::uuid
        RETURNING *
        """,
        merged["name"],
        merged["protocol"],
        merged["host"],
        merged["port"],
        merged["comm_key"],
        merged["use_udp"],
        merged["api_url"],
        merged["api_username"],
        merged["api_password"],
        merged["device_serial"],
        merged["branch"],
        merged["location"],
        merged["direction"],
        merged["enabled"],
        device_id,
    )
    # Reset the cached BioTime token in case credentials changed.
    _biotime_tokens.pop(device_id, None)
    await write_audit(user, "fp_device.update", "fp_device", device_id)
    return _mask_device(to_jsonable(row))


@router.delete("/fingerprint-devices/{device_id}")
async def delete_fp_device(device_id: str, user=Depends(require_roles("Admin"))):
    await execute("DELETE FROM fp_devices WHERE id = $1::uuid", device_id)
    await write_audit(user, "fp_device.delete", "fp_device", device_id)
    return {"ok": True}


@router.post("/fingerprint-devices/{device_id}/test")
async def test_fp_device(device_id: str, user=Depends(require_roles("Admin", "Manager"))):
    device = await fetchrow("SELECT * FROM fp_devices WHERE id = $1::uuid", device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Fingerprint device not found")

    if device["protocol"] == "adms_push":
        last_seen = device["last_seen_at"].isoformat() if device["last_seen_at"] else None
        return {
            "ok": last_seen is not None,
            "protocol": "adms_push",
            "last_seen_at": last_seen,
            "note": (
                "Push device: set its Cloud Server / ADMS address to this server "
                "(http://<server-ip>:8010, no HTTPS) and it will report in automatically."
                if last_seen is None else "Device has pushed data to /iclock - link is working."
            ),
        }

    try:
        if device["protocol"] == "biotime":
            token = await _biotime_token(dict(device), force_refresh=True)
            info: dict[str, Any] = {"protocol": "biotime", "server": device["api_url"], "authenticated": bool(token)}
        else:
            info = await asyncio.to_thread(
                _zk_test_sync, device["host"], device["port"], device["comm_key"], device["use_udp"]
            )
            info["protocol"] = "zk"
    except Exception as exc:
        await execute(
            "UPDATE fp_devices SET status = 'offline', last_error = $2, updated_at = now() WHERE id = $1::uuid",
            device_id,
            str(exc)[:400],
        )
        return {"ok": False, "error": str(exc)}
    await execute(
        """
        UPDATE fp_devices SET status = 'online', last_seen_at = now(), last_error = NULL,
            device_serial = COALESCE($2, device_serial), updated_at = now()
        WHERE id = $1::uuid
        """,
        device_id,
        info.get("serial"),
    )
    return {"ok": True, **info}


@router.post("/fingerprint-devices/{device_id}/sync")
async def sync_fp_device_now(device_id: str, user=Depends(require_roles("Admin", "Manager", "Operator"))):
    device = await fetchrow("SELECT * FROM fp_devices WHERE id = $1::uuid", device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Fingerprint device not found")
    result = await sync_device(dict(device))
    await write_audit(user, "fp_device.sync", "fp_device", device_id, result)
    return result


@router.post("/fingerprint-devices/discover")
async def discover_fp_devices(payload: FpDiscoverRequest, user=Depends(require_roles("Admin", "Manager"))):
    """TCP sweep of <network_base>.1-254 for the ZK service port, then a quick
    protocol probe of responders to pull serial/model info."""
    if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", payload.network_base.strip()):
        raise HTTPException(status_code=400, detail="network_base must look like 192.168.1")
    base = payload.network_base.strip()

    semaphore = asyncio.Semaphore(64)

    async def probe(host: str) -> str | None:
        async with semaphore:
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(host, payload.port), timeout=0.7)
                writer.close()
                return host
            except Exception:
                return None

    hosts = await asyncio.gather(*(probe(f"{base}.{i}") for i in range(1, 255)))
    open_hosts = [h for h in hosts if h]

    devices = []
    for host in open_hosts[:20]:
        info: dict[str, Any] = {"host": host, "port": payload.port}
        try:
            details = await asyncio.to_thread(_zk_test_sync, host, payload.port, "0", False)
            info.update({k: details.get(k) for k in ("serial", "firmware", "device_name", "users", "records")})
            info["ok"] = True
        except Exception as exc:
            info["ok"] = False
            info["error"] = f"Port open but ZK handshake failed: {exc}"
        devices.append(info)
    return {"scanned": 254, "devices": devices}


# ---------------------------------------------------------------------------
# ZKTeco ADMS / push protocol receiver ("Cloud Server" mode on the device).
# The device initiates plain-HTTP requests to /iclock/*; there is no way to give
# it an API key, so records are only accepted from serial numbers registered as
# 'adms_push' devices.
# ---------------------------------------------------------------------------

async def _adms_device_by_serial(serial: str) -> dict | None:
    if not serial:
        return None
    row = await fetchrow(
        "SELECT * FROM fp_devices WHERE protocol = 'adms_push' AND device_serial = $1 AND enabled = TRUE", serial
    )
    return dict(row) if row else None


@router.get("/iclock/cdata", response_class=PlainTextResponse)
async def iclock_handshake(SN: str = ""):
    device = await _adms_device_by_serial(SN)
    if device:
        await execute(
            "UPDATE fp_devices SET status = 'online', last_seen_at = now(), last_error = NULL WHERE id = $1::uuid",
            device["id"],
        )
    # Registry reply: ask the device for realtime attendance pushes.
    return (
        f"GET OPTION FROM: {SN}\n"
        "ATTLOGStamp=None\nOPERLOGStamp=9999\nATTPHOTOStamp=None\n"
        "ErrorDelay=30\nDelay=10\nTransTimes=00:00;14:05\nTransInterval=1\n"
        "TransFlag=1111000000\nRealtime=1\nEncrypt=None\n"
    )


@router.get("/iclock/getrequest", response_class=PlainTextResponse)
async def iclock_getrequest(SN: str = ""):
    device = await _adms_device_by_serial(SN)
    if device:
        await execute("UPDATE fp_devices SET last_seen_at = now() WHERE id = $1::uuid", device["id"])
    return "OK"


@router.post("/iclock/cdata", response_class=PlainTextResponse)
async def iclock_receive(request: Request, SN: str = "", table: str = ""):
    device = await _adms_device_by_serial(SN)
    if device is None:
        logger.warning("Rejected /iclock push from unregistered SN %r", SN)
        return "OK"  # acknowledge anyway so unknown devices don't retry-flood

    body = (await request.body()).decode("utf-8", errors="replace")
    inserted = 0
    if table.upper() == "ATTLOG":
        tz = await business_tz()
        person_cache: dict[str, str | None] = {}
        for line in body.splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            user_id = parts[0].strip()
            try:
                punched_at = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            except ValueError:
                continue
            try:
                punch_code = int(parts[2]) if len(parts) > 2 else 255
            except ValueError:
                punch_code = 255
            punch_type = _resolve_punch_type(punch_code, device["direction"])
            raw = {"punch": punch_code, "source": "adms_push", "sn": SN}
            if user_id and await _insert_punch(str(device["id"]), user_id, punched_at, punch_type, raw, person_cache):
                inserted += 1

    await execute(
        "UPDATE fp_devices SET status = 'online', last_seen_at = now(), last_sync_at = now(), last_error = NULL WHERE id = $1::uuid",
        device["id"],
    )
    return f"OK: {inserted}"


def _parse_date_param(value: str) -> date:
    """asyncpg binds ``$n::date`` parameters as real dates - a raw query string
    fails to encode, so parse (and validate) the filter here."""
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date filter (use YYYY-MM-DD)") from exc


@router.get("/attendance/records")
async def list_attendance_records(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    person_id: str | None = None,
    device_id: str | None = None,
    punch_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    matched: bool | None = None,
    q: str | None = None,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if person_id:
        add_clause("ar.person_id = {}::uuid", person_id)
    if device_id:
        add_clause("ar.device_id = {}::uuid", device_id)
    if punch_type in ("in", "out", "unknown"):
        add_clause("ar.punch_type = {}", punch_type)
    if date_from:
        add_clause("ar.punched_at >= {}::date", _parse_date_param(date_from))
    if date_to:
        add_clause("ar.punched_at < ({}::date + interval '1 day')", _parse_date_param(date_to))
    if matched is True:
        clauses.append("ar.person_id IS NOT NULL")
    elif matched is False:
        clauses.append("ar.person_id IS NULL")
    if q:
        values.append(f"%{q}%")
        n = len(values)
        clauses.append(f"(p.full_name ILIKE ${n} OR ar.device_user_id ILIKE ${n})")

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    values.extend([limit, offset])
    rows = await fetch(
        f"""
        SELECT ar.*, p.full_name AS person_name, p.staff_id, d.name AS device_name
        FROM attendance_records ar
        LEFT JOIN persons p ON p.id = ar.person_id
        LEFT JOIN fp_devices d ON d.id = ar.device_id
        {where}
        ORDER BY ar.punched_at DESC
        LIMIT ${len(values) - 1} OFFSET ${len(values)}
        """,
        *values,
    )
    return rows_to_dicts(rows)


@router.post("/attendance/push")
async def push_attendance_records(payload: AttendancePushRequest, user=Depends(require_roles("Admin", "Manager"))):
    """Punch import for non-ZKTeco systems. Naive timestamps are interpreted in
    the attendance timezone; duplicates are ignored."""
    tz = await business_tz()
    person_cache: dict[str, str | None] = {}
    inserted = 0
    errors: list[dict] = []
    for index, record in enumerate(payload.records, start=1):
        try:
            punched_at = datetime.fromisoformat(record.punched_at)
        except ValueError:
            errors.append({"row": index, "error": f"Invalid datetime: {record.punched_at}"})
            continue
        if punched_at.tzinfo is None:
            punched_at = punched_at.replace(tzinfo=tz)
        if await _insert_punch(None, record.device_user_id, punched_at, record.punch_type, {"source": "push"}, person_cache):
            inserted += 1
    await write_audit(user, "attendance.push", "attendance_record", None, {"received": len(payload.records), "inserted": inserted})
    return {"received": len(payload.records), "inserted": inserted, "duplicates": len(payload.records) - inserted - len(errors), "errors": errors}


@router.get("/attendance/alerts")
async def list_attendance_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    date_from: str | None = None,
    date_to: str | None = None,
    alert_type: str | None = None,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    values: list = []
    clauses: list[str] = []

    def add_clause(sql: str, value) -> None:
        values.append(value)
        clauses.append(sql.format(f"${len(values)}"))

    if alert_type in ("missed_check_in", "missed_check_out"):
        add_clause("aa.alert_type = {}", alert_type)
    if date_from:
        add_clause("aa.detected_at >= {}::date", _parse_date_param(date_from))
    if date_to:
        add_clause("aa.detected_at < ({}::date + interval '1 day')", _parse_date_param(date_to))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    values.append(limit)
    rows = await fetch(
        f"""
        SELECT aa.*, p.full_name AS person_name, c.name AS camera_name
        FROM attendance_alerts aa
        LEFT JOIN persons p ON p.id = aa.person_id
        LEFT JOIN cameras c ON c.id = aa.camera_id
        {where}
        ORDER BY aa.detected_at DESC
        LIMIT ${len(values)}
        """,
        *values,
    )
    return rows_to_dicts(rows)


@router.post("/attendance/alerts/clear")
async def clear_attendance_alerts(payload: AttendanceAlertsClearRequest, user=Depends(require_roles("Admin"))):
    if payload.alert_ids:
        result = await fetch(
            "DELETE FROM attendance_alerts WHERE id = ANY($1::uuid[]) RETURNING id", payload.alert_ids
        )
    else:
        result = await fetch("DELETE FROM attendance_alerts RETURNING id")
    await write_audit(user, "attendance_alert.clear", "attendance_alert", None, {"deleted": len(result)})
    return {"ok": True, "deleted": len(result)}


@router.get("/attendance/summary")
async def attendance_summary(
    date: str | None = None,
    user=Depends(require_roles("Admin", "Manager", "Operator", "Viewer")),
):
    """Per-staff first-in / last-out for one day (default: today in the attendance timezone)."""
    tz = await business_tz()
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc
        day_start = day.replace(tzinfo=tz)
    else:
        day_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    rows = await fetch(
        """
        SELECT p.id, p.full_name, p.branch, p.staff_id, p.fp_user_id, p.shift_start, p.shift_end,
               MIN(ar.punched_at) FILTER (WHERE ar.punch_type IN ('in', 'unknown')) AS first_in,
               MAX(ar.punched_at) FILTER (WHERE ar.punch_type IN ('out', 'unknown')) AS last_out,
               COUNT(ar.id) AS punch_count
        FROM persons p
        LEFT JOIN attendance_records ar
               ON ar.person_id = p.id AND ar.punched_at >= $1 AND ar.punched_at < $2
        WHERE p.person_type = 'staff' AND p.status = 'active'
        GROUP BY p.id
        ORDER BY p.full_name
        """,
        day_start,
        day_end,
    )
    return {
        "date": day_start.strftime("%Y-%m-%d"),
        "timezone": str(tz),
        "checkin_deadline": await _setting("attendance.checkin_deadline", "09:00"),
        "checkout_time": await _setting("attendance.checkout_time", "17:00"),
        "staff": rows_to_dicts(rows),
    }
