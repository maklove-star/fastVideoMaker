"""Persist and list generated TTS audio under output/audio/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .schemas import AudioHistoryItem
from .utils.file_utils import output_url
from .utils.logger import get_logger

logger = get_logger(__name__)


def _audio_dir() -> Path:
    settings = get_settings()
    path = settings.output_dir / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path_for(audio_file: Path) -> Path:
    return audio_file.with_suffix(audio_file.suffix + ".meta.json")


def _is_history_audio(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg"}:
        return False
    if name.startswith("preview-"):
        return False
    return True


def save_audio_history_meta(
    *,
    audio_path: str | Path,
    audio_url: str | None,
    source_audio_url: str | None,
    voice_id: str | None,
    text: str | None,
    request_id: str | None = None,
    task_id: str | None = None,
) -> None:
    path = Path(audio_path)
    if not path.is_file():
        return
    preview = (text or "").strip().replace("\n", " ")
    if len(preview) > 160:
        preview = preview[:157] + "..."
    payload: dict[str, Any] = {
        "id": request_id or path.stem,
        "fileName": path.name,
        "audioPath": str(path.resolve()),
        "audioUrl": audio_url or output_url(path, get_settings().output_dir),
        "sourceAudioUrl": source_audio_url,
        "voiceId": voice_id,
        "textPreview": preview or None,
        "taskId": task_id,
        "createdAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "sizeBytes": path.stat().st_size,
    }
    meta = _meta_path_for(path)
    try:
        meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write audio history meta %s", meta)


def _load_meta(audio_file: Path) -> dict[str, Any]:
    meta_file = _meta_path_for(audio_file)
    if not meta_file.is_file():
        return {}
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def list_audio_history(limit: int = 50) -> list[AudioHistoryItem]:
    settings = get_settings()
    directory = _audio_dir()
    files = [p for p in directory.iterdir() if p.is_file() and _is_history_audio(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[AudioHistoryItem] = []
    for path in files[: max(1, min(limit, 200))]:
        meta = _load_meta(path)
        stat = path.stat()
        created = meta.get("createdAt")
        if not isinstance(created, str) or not created:
            created = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        audio_url = meta.get("audioUrl") if isinstance(meta.get("audioUrl"), str) else None
        if not audio_url:
            audio_url = output_url(path, settings.output_dir)
        items.append(
            AudioHistoryItem(
                id=str(meta.get("id") or path.stem),
                fileName=path.name,
                audioPath=str(path.resolve()),
                audioUrl=audio_url,
                sourceAudioUrl=meta.get("sourceAudioUrl") if isinstance(meta.get("sourceAudioUrl"), str) else None,
                voiceId=meta.get("voiceId") if isinstance(meta.get("voiceId"), str) else None,
                textPreview=meta.get("textPreview") if isinstance(meta.get("textPreview"), str) else None,
                createdAt=created,
                sizeBytes=int(meta.get("sizeBytes") or stat.st_size),
            )
        )
    return items
