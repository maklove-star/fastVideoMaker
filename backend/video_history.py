"""Persist and list generated digital-human videos under output/video/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .schemas import VideoHistoryItem
from .utils.file_utils import output_url
from .utils.logger import get_logger

logger = get_logger(__name__)


def _video_dir() -> Path:
    settings = get_settings()
    path = settings.output_dir / "video"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path_for(video_file: Path) -> Path:
    return video_file.with_suffix(video_file.suffix + ".meta.json")


def _is_history_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"}


def save_video_history_meta(
    *,
    video_path: str | Path | None,
    video_url: str | None = None,
    source_video_url: str | None = None,
    task_id: str | None = None,
    script: str | None = None,
    title: str | None = None,
    resolution: str | None = None,
    portrait_path: str | None = None,
) -> None:
    if not video_path:
        return
    path = Path(video_path)
    if not path.is_file() or not _is_history_video(path):
        return

    preview = (script or "").strip().replace("\n", " ")
    if len(preview) > 160:
        preview = preview[:157] + "..."

    settings = get_settings()
    payload: dict[str, Any] = {
        "id": task_id or path.stem,
        "fileName": path.name,
        "localVideoPath": str(path.resolve()),
        "videoUrl": video_url or output_url(path, settings.output_dir),
        "sourceVideoUrl": source_video_url,
        "taskId": task_id or path.stem,
        "textPreview": preview or None,
        "title": (title or "").strip() or None,
        "resolution": resolution,
        "portraitPath": portrait_path,
        "createdAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sizeBytes": path.stat().st_size,
    }
    meta = _meta_path_for(path)
    try:
        meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write video history meta %s", meta)


def _load_meta(video_file: Path) -> dict[str, Any]:
    meta_file = _meta_path_for(video_file)
    if not meta_file.is_file():
        return {}
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_video_history(limit: int = 50) -> list[VideoHistoryItem]:
    settings = get_settings()
    directory = _video_dir()
    files = [p for p in directory.iterdir() if p.is_file() and _is_history_video(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[VideoHistoryItem] = []
    for path in files[: max(1, min(limit, 200))]:
        meta = _load_meta(path)
        stat = path.stat()
        created = meta.get("createdAt")
        if not isinstance(created, str) or not created:
            created = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        video_url = meta.get("videoUrl") if isinstance(meta.get("videoUrl"), str) else None
        if not video_url:
            video_url = output_url(path, settings.output_dir)
        items.append(
            VideoHistoryItem(
                id=str(meta.get("id") or path.stem),
                fileName=path.name,
                localVideoPath=str(path.resolve()),
                videoUrl=video_url,
                sourceVideoUrl=meta.get("sourceVideoUrl") if isinstance(meta.get("sourceVideoUrl"), str) else None,
                taskId=str(meta.get("taskId") or path.stem),
                textPreview=meta.get("textPreview") if isinstance(meta.get("textPreview"), str) else None,
                title=meta.get("title") if isinstance(meta.get("title"), str) else None,
                resolution=meta.get("resolution") if isinstance(meta.get("resolution"), str) else None,
                createdAt=created,
                sizeBytes=int(meta.get("sizeBytes") or stat.st_size),
            )
        )
    return items
