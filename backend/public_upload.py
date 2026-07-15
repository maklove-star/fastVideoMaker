"""Upload local files to temporary public hosts for Volc CV (image_url / audio_url).

When PUBLIC_BASE_URL is unset, Volc cannot reach localhost. This module posts the
file to a short-lived anonymous host and returns an https URL.

Privacy: portraits/audio leave your machine. Disable with PUBLIC_FILE_HOST=off.
Prefer configuring PUBLIC_BASE_URL (tunnel / CDN) for production.
"""

from __future__ import annotations

from pathlib import Path

import requests

from .config import get_settings
from .utils.logger import get_logger

logger = get_logger(__name__)

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def _content_type(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/octet-stream")


def _upload_uguu(path: Path, timeout: int) -> str:
    # Works well from mainland China networks; temporary anonymous host.
    with path.open("rb") as handle:
        response = requests.post(
            "https://uguu.se/upload",
            files={"files[]": (path.name, handle, _content_type(path))},
            timeout=timeout,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"uguu 上传失败：{response.text[:200]}")
    files = payload.get("files") or []
    if not files or not files[0].get("url"):
        raise RuntimeError(f"uguu 未返回 url：{response.text[:200]}")
    url = str(files[0]["url"]).strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"uguu 返回异常 url：{url}")
    return url


def _upload_litterbox(path: Path, timeout: int) -> str:
    with path.open("rb") as handle:
        response = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": (path.name, handle, _content_type(path))},
            timeout=timeout,
        )
    response.raise_for_status()
    url = response.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"litterbox 返回异常：{response.text[:200]}")
    return url


def _upload_catbox(path: Path, timeout: int) -> str:
    with path.open("rb") as handle:
        response = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (path.name, handle, _content_type(path))},
            timeout=timeout,
        )
    response.raise_for_status()
    url = response.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"catbox 返回异常：{response.text[:200]}")
    return url


def _upload_0x0(path: Path, timeout: int) -> str:
    with path.open("rb") as handle:
        response = requests.post(
            "https://0x0.st",
            files={"file": (path.name, handle, _content_type(path))},
            timeout=timeout,
        )
    response.raise_for_status()
    url = response.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"0x0.st 返回异常：{response.text[:200]}")
    return url


_HOSTS = {
    "uguu": _upload_uguu,
    "litterbox": _upload_litterbox,
    "catbox": _upload_catbox,
    "0x0": _upload_0x0,
}


def upload_public_file(path: Path | str, *, kind: str = "文件") -> str:
    """Return an https URL for a local file, or raise RuntimeError."""
    settings = get_settings()
    host_mode = (settings.public_file_host or "auto").strip().lower()
    if host_mode in {"", "off", "false", "0", "none", "disabled"}:
        raise RuntimeError(
            f"{kind}需要公网 URL，但 PUBLIC_FILE_HOST=off 且未配置 PUBLIC_BASE_URL。"
        )

    file_path = Path(path)
    if not file_path.is_file():
        raise RuntimeError(f"{kind}文件不存在：{file_path}")

    size = file_path.stat().st_size
    if size > 90 * 1024 * 1024:
        raise RuntimeError(f"{kind}过大（{size} bytes），临时图床无法上传。请配置 PUBLIC_BASE_URL。")

    timeout = settings.public_upload_timeout_seconds
    if host_mode == "auto":
        # uguu first: reachable from CN and returns raw media bytes.
        order = ["uguu", "litterbox", "catbox", "0x0"]
    elif host_mode in _HOSTS:
        order = [host_mode]
    else:
        raise RuntimeError(
            f"未知 PUBLIC_FILE_HOST={host_mode}（可选 auto/uguu/litterbox/catbox/0x0/off）"
        )

    errors: list[str] = []
    for name in order:
        try:
            url = _HOSTS[name](file_path, timeout)
            logger.info("Uploaded %s via %s → %s", file_path.name, name, url)
            return url
        except Exception as error:  # noqa: BLE001
            logger.warning("Public upload via %s failed: %s", name, error)
            errors.append(f"{name}: {error}")

    raise RuntimeError(
        f"{kind}临时公网上传失败。可配置 PUBLIC_BASE_URL（内网穿透）后重试。"
        f"详情：{'; '.join(errors)}"
    )
