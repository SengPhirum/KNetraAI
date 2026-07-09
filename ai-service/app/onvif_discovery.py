from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import quote, unquote, urlsplit

os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

import cv2

from .config import settings

logger = logging.getLogger(__name__)

try:
    cv2.setLogLevel(0)  # SILENT: keep OpenCV/FFmpeg stream timeout chatter out of normal logs.
except Exception:  # pragma: no cover - OpenCV builds expose this differently.
    pass


class OnvifError(RuntimeError):
    """Raised for ONVIF failures that should surface as a readable message in the UI."""


async def scan_network(timeout: float | None = None) -> list[dict[str, Any]]:
    """Best-effort WS-Discovery LAN scan.

    Returns an empty list when nothing responds. This is expected in most Docker
    deployments: WS-Discovery relies on UDP multicast, which typically does not
    cross a bridge network to the physical LAN. Probing a known IP (probe_device)
    is the reliable path; this scan is a convenience on top of it.
    """

    def _scan() -> list[dict[str, Any]]:
        from wsdiscovery.discovery import ThreadedWSDiscovery

        wsd = ThreadedWSDiscovery()
        wsd.start()
        try:
            services = wsd.searchServices(timeout=timeout or settings.onvif_discovery_timeout)
            results: list[dict[str, Any]] = []
            for service in services:
                try:
                    xaddrs = list(service.getXAddrs() or [])
                    scopes = [str(scope) for scope in (service.getScopes() or [])]
                except Exception as exc:  # defensive: a malformed WS-Discovery reply shouldn't break the scan
                    logger.warning("Skipping malformed WS-Discovery service: %s", exc)
                    continue
                if not xaddrs:
                    continue
                parsed = urlsplit(xaddrs[0])
                if not parsed.hostname:
                    continue
                results.append(
                    {
                        "host": parsed.hostname,
                        "port": parsed.port or 80,
                        "xaddrs": xaddrs,
                        "scopes": scopes,
                        **_scope_details(scopes),
                    }
                )
            return results
        finally:
            wsd.stop()

    return await asyncio.to_thread(_scan)


def _normalize_host(host: str) -> str:
    """Strip an accidentally-pasted scheme/path so 'http://192.168.1.9/' behaves like '192.168.1.9'."""
    host = host.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    return host.split("/", 1)[0]


def _is_unreachable(exc: Exception) -> bool:
    """True for network-level failures (unreachable host, connection refused, DNS, timeout) rather
    than protocol/auth-level failures (SOAP fault, wrong credentials) - the latter is worth retrying
    with a different auth mode, the former is not."""
    return isinstance(exc, (OSError, asyncio.TimeoutError))


def _scope_tail(scope: str) -> str:
    return unquote(scope.rstrip("/").rsplit("/", 1)[-1]).strip()


def _scope_details(scopes: list[str]) -> dict[str, Any]:
    details: dict[str, Any] = {"name": None, "hardware": None, "location": None, "types": []}
    for scope in scopes:
        lowered = scope.lower()
        if "/name/" in lowered and not details["name"]:
            details["name"] = _scope_tail(scope)
        elif "/hardware/" in lowered and not details["hardware"]:
            details["hardware"] = _scope_tail(scope)
        elif "/location/" in lowered and not details["location"]:
            details["location"] = _scope_tail(scope)
        elif "/type/" in lowered:
            details["types"].append(_scope_tail(scope))

    details["hint"] = details["name"] or details["hardware"] or details["location"]
    return details


async def probe_device(host: str, port: int, username: str, password: str) -> dict[str, Any]:
    """Connect to a camera/NVR over ONVIF and list its channels (media profiles) with resolved RTSP URLs.

    Some devices reject correct credentials at the WS-Security layer even though the same
    login works fine on the camera's web UI - usually clock skew (ONVIF auth is timestamp-signed)
    or a device that only supports PasswordText instead of PasswordDigest. ``adjust_time=True``
    compensates for the former; retrying once with ``encrypt=False`` covers the latter.
    """
    try:
        from onvif import ONVIFCamera
    except ImportError as exc:  # pragma: no cover - dependency always installed in the image
        raise OnvifError("ONVIF client library is not installed") from exc

    host = _normalize_host(host)

    last_exc: Exception | None = None
    for encrypt in (True, False):
        camera = ONVIFCamera(host, port, username, password, adjust_time=True, encrypt=encrypt)
        try:
            try:
                await camera.update_xaddrs()
            except Exception as exc:
                last_exc = exc
                logger.warning("ONVIF update_xaddrs failed for %s:%s (encrypt=%s): %s", host, port, encrypt, exc)
                if _is_unreachable(exc):
                    # A real network/connect failure - retrying with a different auth mode won't help,
                    # and each attempt can take up to ~30s to time out, so fail fast instead of doubling that wait.
                    raise OnvifError(
                        f"Could not reach {host}:{port} ({exc}). Check that the IP and port are correct and that "
                        "the ONVIF/HTTP service on the camera or NVR is reachable from this server (some devices use "
                        "a different port than 80 for ONVIF, e.g. 8000, 8080, or 2020 - check the camera's network settings)."
                    ) from exc
                continue

            device_info: dict[str, Any] = {"manufacturer": None, "model": None, "firmware_version": None}
            try:
                devicemgmt = await camera.create_devicemgmt_service()
                info = await devicemgmt.GetDeviceInformation()
                device_info = {
                    "manufacturer": getattr(info, "Manufacturer", None),
                    "model": getattr(info, "Model", None),
                    "firmware_version": getattr(info, "FirmwareVersion", None),
                }
            except Exception as exc:
                logger.warning("ONVIF GetDeviceInformation failed for %s:%s (encrypt=%s): %s", host, port, encrypt, exc)

            try:
                media = await camera.create_media_service()
                profiles = await media.GetProfiles()
            except Exception as exc:
                last_exc = exc
                logger.warning("ONVIF GetProfiles failed for %s:%s (encrypt=%s): %s", host, port, encrypt, exc)
                continue

            video_sources = await _get_video_sources(media, host, port, encrypt)
            channels = [
                await _describe_profile(media, profile, username, password, index + 1, video_sources)
                for index, profile in enumerate(profiles)
            ]
            return {**device_info, "host": host, "port": port, "channels": channels}
        finally:
            try:
                await camera.close()
            except Exception as exc:
                logger.warning("Error closing ONVIF connection to %s:%s: %s", host, port, exc)

    raise OnvifError(
        f"Connected to {host}:{port}, but the camera rejected the ONVIF login ({last_exc}). "
        "The IP/port are reachable - if this same username/password works on the camera's web page, "
        "some devices require a separate ONVIF/Integration-protocol account distinct from the web login, "
        "or have ONVIF itself disabled in advanced network settings - check those next."
    ) from last_exc


async def _get_video_sources(media: Any, host: str, port: int, encrypt: bool) -> dict[str, dict[str, Any]]:
    try:
        sources = await media.GetVideoSources()
    except Exception as exc:
        logger.warning("ONVIF GetVideoSources failed for %s:%s (encrypt=%s): %s", host, port, encrypt, exc)
        return {}

    details: dict[str, dict[str, Any]] = {}
    for source in sources or []:
        token = getattr(source, "token", None)
        if not token:
            continue
        resolution = None
        res = getattr(source, "Resolution", None)
        if res is not None:
            resolution = f"{getattr(res, 'Width', '?')}x{getattr(res, 'Height', '?')}"
        details[token] = {
            "source_token": token,
            "source_resolution": resolution,
            "source_framerate": getattr(source, "Framerate", None),
        }
    return details


def _clean_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _guess_stream_label(profile_name: str | None, encoder_name: str | None, resolution: str | None) -> str:
    text = " ".join(part for part in (profile_name, encoder_name) if part).lower()
    if any(marker in text for marker in ("sub", "secondary", "minor", "low", "stream2", "stream 2")):
        return "Sub stream"
    if any(marker in text for marker in ("main", "primary", "major", "high", "stream1", "stream 1")):
        return "Main stream"
    if resolution and "x" in resolution:
        try:
            width, height = [int(part) for part in resolution.lower().split("x", 1)]
            return "Main stream" if width >= 1280 or height >= 720 else "Sub stream"
        except ValueError:
            pass
    return "Stream"


async def _describe_profile(
    media: Any,
    profile: Any,
    username: str,
    password: str,
    index: int,
    video_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    token = getattr(profile, "token", None)
    profile_name = _clean_name(getattr(profile, "Name", None))
    name = profile_name or token or f"Channel {index}"
    resolution = None
    encoding = None
    framerate = None
    width = None
    height = None

    video_source_cfg = getattr(profile, "VideoSourceConfiguration", None)
    source_name = _clean_name(getattr(video_source_cfg, "Name", None)) if video_source_cfg is not None else None
    source_token = getattr(video_source_cfg, "SourceToken", None) if video_source_cfg is not None else None

    video_cfg = getattr(profile, "VideoEncoderConfiguration", None)
    encoder_name = _clean_name(getattr(video_cfg, "Name", None)) if video_cfg is not None else None
    if video_cfg is not None:
        encoding = getattr(video_cfg, "Encoding", None)
        res = getattr(video_cfg, "Resolution", None)
        if res is not None:
            width = getattr(res, "Width", None)
            height = getattr(res, "Height", None)
            resolution = f"{width or '?'}x{height or '?'}"
        rate_control = getattr(video_cfg, "RateControl", None)
        if rate_control is not None:
            framerate = getattr(rate_control, "FrameRateLimit", None)

    stream_label = _guess_stream_label(profile_name, encoder_name, resolution)
    configured_name = source_name or profile_name or encoder_name or f"Channel {index}"
    display_name = configured_name if stream_label == "Main stream" else f"{configured_name} ({stream_label})"

    rtsp_url = None
    error = None
    if token:
        try:
            stream_setup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
            uri_resp = await media.GetStreamUri({"StreamSetup": stream_setup, "ProfileToken": token})
            raw_uri = getattr(uri_resp, "Uri", None)
            if raw_uri:
                rtsp_url = _inject_credentials(raw_uri, username, password)
            else:
                error = "Camera did not return a stream URI for this channel"
        except Exception as exc:
            error = str(exc)
            logger.warning("ONVIF GetStreamUri failed for profile %s: %s", token, exc)
    else:
        error = "Channel has no profile token"

    return {
        "profile_token": token,
        "name": display_name,
        "configured_name": configured_name,
        "profile_name": profile_name or name,
        "source_name": source_name,
        "encoder_name": encoder_name,
        "source_token": source_token,
        "stream_label": stream_label,
        "channel_index": index,
        "resolution": resolution,
        "resolution_width": width,
        "resolution_height": height,
        "encoding": encoding,
        "framerate": framerate,
        **video_sources.get(source_token, {}),
        "rtsp_url": rtsp_url,
        "error": error,
        "usable": bool(rtsp_url and not error),
    }


def _inject_credentials(rtsp_url: str, username: str, password: str) -> str:
    if not username:
        return rtsp_url
    parsed = urlsplit(rtsp_url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def _test_stream_sync(rtsp_url: str, timeout_ms: int) -> dict[str, Any]:
    # Timeouts must be passed at open time (via the params overload) - setting them
    # on the VideoCapture object after construction is too late, since the connection
    # attempt already happened synchronously inside the constructor.
    try:
        params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms, cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms]
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG, params)
    except Exception:
        cap = cv2.VideoCapture(rtsp_url)  # older OpenCV build without the params overload
    try:
        if not cap.isOpened():
            return {"ok": False, "error": "Could not open the stream - check the URL, credentials, and network reachability"}
        ok, frame = cap.read()
        if not ok or frame is None:
            return {"ok": False, "error": "Connected, but no video frame could be read"}
        height, width = frame.shape[:2]
        return {"ok": True, "width": int(width), "height": int(height)}
    finally:
        cap.release()


async def test_stream(rtsp_url: str, timeout_ms: int = 6000) -> dict[str, Any]:
    return await asyncio.to_thread(_test_stream_sync, rtsp_url, timeout_ms)
