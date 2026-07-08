from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

import cv2

from .config import settings

logger = logging.getLogger(__name__)


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
                        "hint": _guess_name(scopes),
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


def _guess_name(scopes: list[str]) -> str | None:
    for scope in scopes:
        lowered = scope.lower()
        if "hardware" in lowered or "/name/" in lowered:
            return scope.rsplit("/", 1)[-1]
    return None


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

            channels = [await _describe_profile(media, profile, username, password) for profile in profiles]
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


async def _describe_profile(media: Any, profile: Any, username: str, password: str) -> dict[str, Any]:
    token = getattr(profile, "token", None)
    name = getattr(profile, "Name", None) or token or "Channel"
    resolution = None
    encoding = None
    framerate = None

    video_cfg = getattr(profile, "VideoEncoderConfiguration", None)
    if video_cfg is not None:
        encoding = getattr(video_cfg, "Encoding", None)
        res = getattr(video_cfg, "Resolution", None)
        if res is not None:
            resolution = f"{getattr(res, 'Width', '?')}x{getattr(res, 'Height', '?')}"
        rate_control = getattr(video_cfg, "RateControl", None)
        if rate_control is not None:
            framerate = getattr(rate_control, "FrameRateLimit", None)

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
        "name": name,
        "resolution": resolution,
        "encoding": encoding,
        "framerate": framerate,
        "rtsp_url": rtsp_url,
        "error": error,
    }


def _inject_credentials(rtsp_url: str, username: str, password: str) -> str:
    if not username:
        return rtsp_url
    parsed = urlsplit(rtsp_url)
    netloc = f"{username}:{password}@{parsed.hostname}"
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
