from __future__ import annotations

import base64
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

import requests

from .config import get_settings
from .utils.file_utils import ensure_parent
from .utils.logger import get_logger


logger = get_logger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://www.douyin.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

TRANSCRIPT_PROMPT = (
    "请一字不差地转写这段视频里的口播全文。"
    "完整保留语气词、口误和重复表述。"
    "只输出转写正文，不要标题、标签、概括或解释；不要用换行把句子拆成很多短行。"
)


def _decode_js_string(raw: str) -> str:
    return json.loads(f'"{raw}"')


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(
            "缺少 ffmpeg。请安装依赖：pip install imageio-ffmpeg"
        ) from error


def _collect_play_urls(html: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r'"url_list"\s*:\s*\[(.*?)\]', html, re.S):
        chunk = match.group(1)
        for raw in re.findall(r'"((?:\\.|[^"\\])*)"', chunk):
            try:
                decoded = _decode_js_string(raw)
            except Exception:  # noqa: BLE001
                continue
            lower = decoded.lower()
            if any(
                token in lower
                for token in (".webp", ".jpeg", ".jpg", ".png", "douyinpic.com", "avatar", "cover")
            ):
                continue
            if not any(
                token in lower
                for token in ("/play", "video_id=", "aweme/v1/play", "bytevcloud", "douyinvod")
            ):
                continue
            urls.append(decoded)

    ranked: list[str] = []
    seen: set[str] = set()
    for url in urls:
        no_wm = url.replace("/playwm/", "/play/")
        for candidate in (no_wm, url):
            if candidate in seen:
                continue
            seen.add(candidate)
            ranked.append(candidate)

    ranked.sort(
        key=lambda u: (
            0 if ("/play/?" in u or "/play?" in u) and "playwm" not in u else 1,
            0 if "video_id=" in u else 1,
            len(u),
        )
    )
    return ranked


def _has_audio_stream(media_path: Path) -> bool:
    result = subprocess.run(
        [_ffmpeg_exe(), "-i", str(media_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    probe = (result.stderr or "") + (result.stdout or "")
    return "Audio:" in probe


def download_douyin_video(share_url: str, output_path: Path, timeout: int = 180) -> Path:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    page = session.get(share_url, allow_redirects=True, timeout=30)
    page.raise_for_status()

    play_urls = _collect_play_urls(page.text)
    if not play_urls:
        raise RuntimeError("未能从抖音页面解析到视频播放地址。")

    ensure_parent(output_path)
    last_error: Exception | None = None
    for play_url in play_urls[:10]:
        try:
            response = session.get(play_url, timeout=timeout, stream=True)
            content_type = (response.headers.get("Content-Type") or "").lower()
            if response.status_code != 200:
                continue
            if any(token in content_type for token in ("image/", "text/", "json", "html")):
                continue

            data = b"".join(chunk for chunk in response.iter_content(256 * 1024) if chunk)
            if len(data) < 300_000:
                continue
            if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
                continue

            output_path.write_bytes(data)
            if not _has_audio_stream(output_path):
                logger.warning("Downloaded media has no audio stream, skip bytes=%s", len(data))
                output_path.unlink(missing_ok=True)
                continue

            logger.info("Downloaded Douyin video bytes=%s path=%s", len(data), output_path)
            return output_path
        except Exception as error:  # noqa: BLE001
            last_error = error
            logger.warning("Douyin video download failed url=%s error=%s", play_url[:120], error)
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass

    raise RuntimeError(f"下载抖音视频失败：{last_error or '无可用带音轨的播放地址'}")


def extract_audio_mp3(video_path: Path, audio_path: Path) -> Path:
    ensure_parent(audio_path)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size < 1000:
        detail = (result.stderr or result.stdout or "")[-500:]
        raise RuntimeError(f"抽取音频失败：{detail}")
    return audio_path


def _normalize_transcript(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text.strip()
    # Model often emits one phrase per line; stitch for readable口播文案.
    joined = "".join(lines)
    return re.sub(r"[ \t]+", "", joined).strip()


def _extract_response_text(data: dict) -> str:
    output = data.get("output") or []
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "reasoning":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"}:
                text = (part.get("text") or "").strip()
                if text:
                    texts.append(text)
    return "\n".join(texts).strip()


def upload_ark_file(path: Path, mime_type: str, timeout: int = 300) -> str:
    settings = get_settings()
    if not settings.ark_api_key:
        raise RuntimeError("缺少 ARK_API_KEY，无法上传视频给豆包模型。")

    with path.open("rb") as handle:
        response = requests.post(
            settings.ark_files_url,
            headers={"Authorization": f"Bearer {settings.ark_api_key}"},
            files={"file": (path.name, handle, mime_type)},
            data={"purpose": "user_data"},
            timeout=timeout,
        )
    response.raise_for_status()
    file_id = response.json().get("id")
    if not file_id:
        raise RuntimeError(f"Files API 未返回 file id：{response.text[:300]}")

    for _ in range(90):
        meta = requests.get(
            f"{settings.ark_files_url.rstrip('/')}/{file_id}",
            headers={"Authorization": f"Bearer {settings.ark_api_key}"},
            timeout=30,
        )
        meta.raise_for_status()
        status = meta.json().get("status")
        if status in {"active", "processed", "ready", "uploaded"}:
            logger.info("Ark file ready id=%s status=%s", file_id, status)
            return file_id
        if status in {"failed", "error"}:
            raise RuntimeError(f"Files API 处理失败：{meta.text[:300]}")
        time.sleep(1)

    raise RuntimeError(f"Files API 文件仍未就绪：{file_id}")


def model_video_transcribe(video_path: Path) -> str:
    """Use configured Doubao Responses model with input_video + file_id."""
    settings = get_settings()
    if not settings.ark_api_key:
        raise RuntimeError("缺少 ARK_API_KEY。")

    file_id = upload_ark_file(video_path, "video/mp4")
    payload = {
        "model": settings.ark_model or settings.glm_model,
        "max_output_tokens": max(settings.ark_max_output_tokens, 4096),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_video", "file_id": file_id},
                    {"type": "input_text", "text": TRANSCRIPT_PROMPT},
                ],
            }
        ],
    }
    response = requests.post(
        settings.ark_api_url,
        headers={
            "Authorization": f"Bearer {settings.ark_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    text = _normalize_transcript(_extract_response_text(data))
    if not text:
        raise RuntimeError(f"豆包视频转写未返回正文：{data}")
    logger.info("Model video transcript ok chars=%s file_id=%s", len(text), file_id)
    return text


def flash_asr_transcribe(audio_path: Path) -> str:
    """Volcengine flash ASR fallback. Reuses TTS AppID / Access Token."""
    settings = get_settings()
    if not settings.doubao_tts_app_id or not settings.doubao_tts_access_key:
        raise RuntimeError("缺少 DOUBAO_TTS_APP_ID / DOUBAO_TTS_ACCESS_KEY，无法做语音转写。")

    audio_bytes = audio_path.read_bytes()
    max_bytes = settings.doubao_asr_max_bytes
    if len(audio_bytes) > max_bytes:
        raise RuntimeError(
            f"音频过大（{len(audio_bytes)} bytes），超过 ASR 限制 {max_bytes}。"
        )

    payload = {
        "user": {"uid": settings.doubao_tts_uid},
        "audio": {
            "data": base64.b64encode(audio_bytes).decode("ascii"),
            "format": "mp3",
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Api-App-Key": settings.doubao_tts_app_id,
        "X-Api-Access-Key": settings.doubao_tts_access_key,
        "X-Api-Resource-Id": settings.doubao_asr_resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }
    response = requests.post(
        settings.doubao_asr_flash_url,
        headers=headers,
        json=payload,
        timeout=settings.doubao_asr_timeout_seconds,
    )
    status = response.headers.get("X-Api-Status-Code", "")
    if response.status_code >= 400 or (status and status not in {"20000000"}):
        raise RuntimeError(
            f"语音转写失败 HTTP {response.status_code} status={status} body={response.text[:400]}"
        )

    data = response.json()
    text = ((data.get("result") or {}).get("text") or "").strip()
    if not text:
        raise RuntimeError(f"语音转写成功但结果为空：{data}")
    logger.info(
        "Flash ASR ok chars=%s duration=%s",
        len(text),
        (data.get("audio_info") or {}).get("duration"),
    )
    return text


def extract_douyin_spoken_script(share_url: str, keep_files: bool = False) -> str:
    """
    Download Douyin video, then transcript via Doubao model (primary) or Flash ASR.
    Direct video_url / share link alone does not work — must upload local file.
    """
    settings = get_settings()
    provider = (settings.douyin_transcript_provider or "model").strip().lower()
    job_id = str(uuid.uuid4())
    work_dir = settings.output_dir / "transcripts" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    video_path = work_dir / "video.mp4"
    audio_path = work_dir / "audio.mp3"
    errors: list[str] = []

    try:
        download_douyin_video(share_url, video_path)

        if provider in {"model", "auto", ""}:
            try:
                script = model_video_transcribe(video_path)
                (work_dir / "script.txt").write_text(script, encoding="utf-8")
                return script
            except Exception as error:  # noqa: BLE001
                logger.exception("Model video transcript failed")
                errors.append(f"model: {error}")
                if provider == "model":
                    raise

        if provider in {"asr", "auto"} or errors:
            extract_audio_mp3(video_path, audio_path)
            script = flash_asr_transcribe(audio_path)
            (work_dir / "script.txt").write_text(script, encoding="utf-8")
            return script

        raise RuntimeError(f"未知 DOUYIN_TRANSCRIPT_PROVIDER：{provider}")
    except Exception:
        if errors and provider == "auto":
            raise RuntimeError("；".join(errors))
        raise
    finally:
        if not keep_files:
            for path in (video_path, audio_path):
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
