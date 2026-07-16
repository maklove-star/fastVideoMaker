"""Persist and list uploaded portrait images under output/portraits/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .schemas import PortraitHistoryItem
from .utils.file_utils import output_url
from .utils.logger import get_logger

logger = get_logger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _portrait_dir() -> Path:
    settings = get_settings()
    path = settings.output_dir / "portraits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path_for(image_file: Path) -> Path:
    return image_file.with_suffix(image_file.suffix + ".meta.json")


def _is_history_portrait(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_SUFFIXES


def save_portrait_history_meta(
    *,
    portrait_path: str | Path,
    portrait_url: str | None = None,
    file_name: str | None = None,
    portrait_id: str | None = None,
) -> None:
    path = Path(portrait_path)
    if not path.is_file() or not _is_history_portrait(path):
        return

    settings = get_settings()
    payload: dict[str, Any] = {
        "id": portrait_id or path.stem,
        "fileName": (file_name or "").strip() or path.name,
        "portraitPath": str(path.resolve()),
        "portraitUrl": portrait_url or output_url(path, settings.output_dir),
        "createdAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sizeBytes": path.stat().st_size,
    }
    meta = _meta_path_for(path)
    try:
        meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write portrait history meta %s", meta)


def _load_meta(image_file: Path) -> dict[str, Any]:
    meta_file = _meta_path_for(image_file)
    if not meta_file.is_file():
        return {}
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_portrait_history(limit: int = 50) -> list[PortraitHistoryItem]:
    settings = get_settings()
    directory = _portrait_dir()
    files = [p for p in directory.iterdir() if p.is_file() and _is_history_portrait(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[PortraitHistoryItem] = []
    for path in files[: max(1, min(limit, 200))]:
        meta = _load_meta(path)
        stat = path.stat()
        created = meta.get("createdAt")
        if not isinstance(created, str) or not created:
            created = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        portrait_url = meta.get("portraitUrl") if isinstance(meta.get("portraitUrl"), str) else None
        if not portrait_url:
            portrait_url = output_url(path, settings.output_dir)
        file_name = meta.get("fileName") if isinstance(meta.get("fileName"), str) else None
        items.append(
            PortraitHistoryItem(
                id=str(meta.get("id") or path.stem),
                fileName=file_name or path.name,
                portraitPath=str(path.resolve()),
                portraitUrl=portrait_url or "",
                createdAt=created,
                sizeBytes=int(meta.get("sizeBytes") or stat.st_size),
            )
        )
    return items
