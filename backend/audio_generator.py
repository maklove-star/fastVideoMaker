from __future__ import annotations

import base64
import json
import re
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import requests

from .config import get_settings
from .schemas import VoiceOption
from .utils.file_utils import ensure_parent, output_url
from .utils.logger import get_logger


logger = get_logger(__name__)
TTS_SUCCESS_CODE = 20000000
V1_SUCCESS_CODES = {0, 3000, "0", "3000"}
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "voices_catalog.json"
PREVIEW_TEXT = "你好，我是当前选中的音色，来听听口播效果吧。"


@dataclass
class AudioGenerationResult:
    audio_path: str
    request_id: str
    task_id: str | None = None
    audio_url: str | None = None
    source_audio_url: str | None = None


# Small fallback if catalog file is missing.
VOICE_PRESETS: dict[str, VoiceOption] = {
    "zh_female_shuangkuaisisi_uranus_bigtts": VoiceOption(
        id="zh_female_shuangkuaisisi_uranus_bigtts",
        name="爽快思思 2.0",
        style="通用场景",
        resourceId="seed-tts-2.0",
    ),
    "zh_female_vv_uranus_bigtts": VoiceOption(
        id="zh_female_vv_uranus_bigtts",
        name="Vivi 2.0",
        style="通用场景",
        resourceId="seed-tts-2.0",
    ),
    "zh_male_m191_uranus_bigtts": VoiceOption(
        id="zh_male_m191_uranus_bigtts",
        name="云舟 2.0",
        style="通用场景",
        resourceId="seed-tts-2.0",
    ),
}


@lru_cache
def _load_voice_catalog() -> tuple[VoiceOption, ...]:
    if not CATALOG_PATH.exists():
        logger.warning("Voice catalog missing at %s, using built-in presets", CATALOG_PATH)
        return tuple(VOICE_PRESETS.values())

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    voices: list[VoiceOption] = []
    for item in raw:
        speaker_id = str(item.get("id") or "").strip()
        if not speaker_id or not _is_supported_public_speaker(speaker_id):
            continue
        voices.append(
            VoiceOption(
                id=speaker_id,
                name=str(item.get("name") or speaker_id),
                style=str(item.get("style") or "") or None,
                resourceId=str(item.get("resourceId") or _infer_resource_id(speaker_id)),
            )
        )
    if not voices:
        return tuple(VOICE_PRESETS.values())
    return tuple(voices)


def _is_supported_public_speaker(speaker: str) -> bool:
    """Skip classic BV voices that require volc.tts.default (often not granted)."""
    if speaker.startswith("BV") and speaker.endswith("_streaming"):
        return False
    if speaker.startswith("VC_"):
        return False
    return True


def _friendly_tts_error(raw: str) -> str:
    text = raw.strip()
    lowered = text.lower()
    if "volc.tts.default" in lowered or "resource not granted" in lowered:
        return "当前账号未开通该音色对应资源，请改选大模型音色（名称含 2.0 / bigtts）后再试。"
    if "resource id is mismatched" in lowered:
        return "音色与资源版本不匹配，请刷新音色列表后重试。"
    return text


def _infer_resource_id(speaker: str) -> str:
    if speaker.endswith("_uranus_bigtts") or speaker.startswith("saturn_"):
        return "seed-tts-2.0"
    return "seed-tts-1.0"


def list_available_voices() -> list[VoiceOption]:
    """Return the full official speaker catalog for the frontend selector."""
    settings = get_settings()
    voices = {voice.id: voice for voice in _load_voice_catalog()}
    if settings.doubao_tts_default_speaker and settings.doubao_tts_default_speaker not in voices:
        voices[settings.doubao_tts_default_speaker] = VoiceOption(
            id=settings.doubao_tts_default_speaker,
            name="默认音色",
            style="来自 DOUBAO_TTS_DEFAULT_SPEAKER",
            resourceId=_infer_resource_id(settings.doubao_tts_default_speaker),
        )
    # Prefer 2.0 voices first, then stable alphabetical by name.
    ordered = sorted(
        voices.values(),
        key=lambda voice: (
            0 if (voice.resourceId or "").endswith("2.0") else 1,
            voice.style or "",
            voice.name,
            voice.id,
        ),
    )
    return ordered


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _resolve_speaker(voice_id: str) -> str:
    settings = get_settings()
    speaker = (voice_id or settings.doubao_tts_default_speaker).strip()
    if not speaker:
        raise ValueError("请选择音色。")
    return speaker


def _resource_for_speaker(speaker: str) -> str:
    for voice in _load_voice_catalog():
        if voice.id == speaker and voice.resourceId:
            return voice.resourceId
    preset = VOICE_PRESETS.get(speaker)
    if preset and preset.resourceId:
        return preset.resourceId
    return _infer_resource_id(speaker)


def _split_text_chunks(text: str, max_bytes: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        raise ValueError("合成文本不能为空。")
    if len(cleaned.encode("utf-8")) <= max_bytes:
        return [cleaned]

    parts = re.split(r"(?<=[。！？!?；;\n])", cleaned)
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{part}".strip()
        if not candidate:
            continue
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(part.encode("utf-8")) <= max_bytes:
            current = part.strip()
            continue
        buffer = ""
        for char in part:
            trial = f"{buffer}{char}"
            if len(trial.encode("utf-8")) > max_bytes and buffer:
                chunks.append(buffer)
                buffer = char
            else:
                buffer = trial
        current = buffer.strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def _speech_rate_from_ratio(speed_ratio: float) -> int:
    return int(round(_clamp((speed_ratio - 1.0) * 100, -50, 100)))


def _loudness_rate_from_ratio(volume_ratio: float) -> int:
    return int(round(_clamp((volume_ratio - 1.0) * 100, -50, 100)))


def _decode_chunked_json_audio(raw: str) -> bytes:
    """Parse concatenated JSON objects from V3 unidirectional chunked response."""
    decoder = json.JSONDecoder()
    index = 0
    audio_chunks: list[bytes] = []
    final_code: int | None = None
    final_message = ""

    while index < len(raw):
        while index < len(raw) and raw[index] in " \n\r\t":
            index += 1
        if index >= len(raw):
            break
        obj, index = decoder.raw_decode(raw, index)
        if not isinstance(obj, dict):
            continue
        data = obj.get("data")
        if isinstance(data, str) and data:
            audio_chunks.append(base64.b64decode(data))
        code = obj.get("code")
        if code in (0, TTS_SUCCESS_CODE, "0", str(TTS_SUCCESS_CODE)):
            final_code = int(code) if not isinstance(code, int) else code
            final_message = str(obj.get("message") or "")
        elif code not in (None,):
            # Non-success terminal/error frame.
            if not audio_chunks:
                raise RuntimeError(f"豆包 TTS V3 失败：{obj}")

    if not audio_chunks:
        raise RuntimeError(f"豆包 TTS V3 未返回音频数据：code={final_code} message={final_message}")
    return b"".join(audio_chunks)


def doubao_tts_http_v3(
    text: str,
    voice_id: str = "zh_female_shuangkuaisisi_moon_bigtts",
    output_file: Optional[str] = None,
    speed_ratio: float | None = None,
    volume_ratio: float | None = None,
) -> AudioGenerationResult:
    """V3 HTTP unidirectional TTS (App ID + Access Key)."""
    settings = get_settings()
    if not settings.doubao_tts_app_id or not settings.doubao_tts_access_key:
        raise RuntimeError(
            "缺少 DOUBAO_TTS_APP_ID 或 DOUBAO_TTS_ACCESS_KEY。"
            "请在火山引擎语音合成控制台获取 App ID 与 Access Token。"
        )

    request_id = str(uuid.uuid4())
    output_path = ensure_parent(output_file or settings.output_dir / "audio" / f"{request_id}.mp3")
    speaker = _resolve_speaker(voice_id)
    resource_id = _resource_for_speaker(speaker)
    speed = _clamp(
        float(speed_ratio if speed_ratio is not None else settings.doubao_tts_speed_ratio),
        0.1,
        2.0,
    )
    volume = _clamp(
        float(volume_ratio if volume_ratio is not None else settings.doubao_tts_volume_ratio),
        0.1,
        3.0,
    )

    headers = {
        "Content-Type": "application/json",
        "X-Api-App-Id": settings.doubao_tts_app_id,
        "X-Api-Access-Key": settings.doubao_tts_access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
    }
    payload = {
        "user": {"uid": settings.doubao_tts_uid},
        "req_params": {
            "text": text.strip(),
            "speaker": speaker,
            "audio_params": {
                "format": settings.doubao_tts_encoding,
                "sample_rate": settings.doubao_tts_sample_rate,
                "speech_rate": _speech_rate_from_ratio(speed),
                "loudness_rate": _loudness_rate_from_ratio(volume),
            },
        },
    }

    logger.info(
        "Submitting Volcengine V3 TTS request_id=%s speaker=%s resource=%s speed=%.2f volume=%.2f",
        request_id,
        speaker,
        resource_id,
        speed,
        volume,
    )
    response = requests.post(
        settings.doubao_tts_v3_url,
        headers=headers,
        json=payload,
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(_friendly_tts_error(f"豆包 TTS V3 HTTP {response.status_code}：{response.text[:500]}"))

    audio_bytes = _decode_chunked_json_audio(response.text)
    output_path.write_bytes(audio_bytes)
    return AudioGenerationResult(
        audio_path=str(Path(output_path).resolve()),
        audio_url=output_url(output_path, settings.output_dir),
        request_id=request_id,
    )


def doubao_tts_http_v1(
    text: str,
    voice_id: str = "zh_female_shuangkuaisisi_moon_bigtts",
    output_file: Optional[str] = None,
    speed_ratio: float | None = None,
    volume_ratio: float | None = None,
    pitch_ratio: float | None = None,
) -> AudioGenerationResult:
    """HTTP V1 non-streaming TTS (Authorization Bearer;token). Supports pitch."""
    settings = get_settings()
    if not settings.doubao_tts_app_id or not settings.doubao_tts_access_key:
        raise RuntimeError(
            "缺少 DOUBAO_TTS_APP_ID 或 DOUBAO_TTS_ACCESS_KEY。"
            "请在火山引擎语音合成控制台（service/10007）获取 App ID 与 Access Token。"
        )

    request_id = str(uuid.uuid4())
    output_path = ensure_parent(output_file or settings.output_dir / "audio" / f"{request_id}.mp3")
    speaker = _resolve_speaker(voice_id)
    speed = _clamp(
        float(speed_ratio if speed_ratio is not None else settings.doubao_tts_speed_ratio),
        0.1,
        2.0,
    )
    volume = _clamp(
        float(volume_ratio if volume_ratio is not None else settings.doubao_tts_volume_ratio),
        0.1,
        3.0,
    )
    pitch = _clamp(
        float(pitch_ratio if pitch_ratio is not None else settings.doubao_tts_pitch_ratio),
        0.1,
        3.0,
    )

    chunks = _split_text_chunks(text, settings.doubao_tts_max_chunk_bytes)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer;{settings.doubao_tts_access_key}",
    }
    audio_bytes = bytearray()

    logger.info(
        "Submitting Volcengine V1 TTS request_id=%s speaker=%s chunks=%s speed=%.2f volume=%.2f pitch=%.2f",
        request_id,
        speaker,
        len(chunks),
        speed,
        volume,
        pitch,
    )

    for index, chunk in enumerate(chunks):
        chunk_reqid = request_id if len(chunks) == 1 else f"{request_id}-{index}"
        payload = {
            "app": {
                "appid": settings.doubao_tts_app_id,
                "token": settings.doubao_tts_access_key,
                "cluster": settings.doubao_tts_cluster,
            },
            "user": {"uid": settings.doubao_tts_uid},
            "audio": {
                "voice_type": speaker,
                "encoding": settings.doubao_tts_encoding,
                "speed_ratio": speed,
                "volume_ratio": volume,
                "pitch_ratio": pitch,
                "rate": settings.doubao_tts_sample_rate,
            },
            "request": {
                "reqid": chunk_reqid,
                "text": chunk,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }
        response = requests.post(
            settings.doubao_tts_http_url,
            headers=headers,
            json=payload,
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                _friendly_tts_error(f"豆包 TTS 合成失败 HTTP {response.status_code}：{response.text[:500]}")
            )
        result = response.json()
        code = result.get("code")
        if code not in V1_SUCCESS_CODES:
            raise RuntimeError(_friendly_tts_error(f"豆包 TTS 合成失败：{result.get('message') or result}"))

        audio_base64 = result.get("data")
        if not audio_base64:
            raise RuntimeError(f"豆包 TTS 未返回音频数据：{result}")
        audio_bytes.extend(base64.b64decode(audio_base64))

    output_path.write_bytes(bytes(audio_bytes))
    return AudioGenerationResult(
        audio_path=str(Path(output_path).resolve()),
        audio_url=output_url(output_path, settings.output_dir),
        request_id=request_id,
    )


def _v3_async_headers(resource_id: str, request_id: str) -> dict[str, str]:
    settings = get_settings()
    return {
        "Content-Type": "application/json",
        "X-Api-App-Id": settings.doubao_tts_app_id,
        "X-Api-Access-Key": settings.doubao_tts_access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
    }


def _download_audio(audio_download_url: str, output_path: Path) -> None:
    response = requests.get(audio_download_url, timeout=120)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def doubao_tts_async_long_text(
    text: str,
    voice_id: str = "zh_female_shuangkuaisisi_moon_bigtts",
    output_file: Optional[str] = None,
    tts_resource_id: str = "",
    speed_ratio: float | None = None,
    volume_ratio: float | None = None,
) -> AudioGenerationResult:
    """Optional V3 async long-text TTS using the same App ID / Access Key."""
    settings = get_settings()
    if not settings.doubao_tts_app_id or not settings.doubao_tts_access_key:
        raise RuntimeError("缺少 DOUBAO_TTS_APP_ID 或 DOUBAO_TTS_ACCESS_KEY。")

    request_id = str(uuid.uuid4())
    output_path = ensure_parent(output_file or settings.output_dir / "audio" / f"{request_id}.mp3")
    speaker = _resolve_speaker(voice_id)
    resource_id = (tts_resource_id or _resource_for_speaker(speaker)).strip()
    speed = _clamp(
        float(speed_ratio if speed_ratio is not None else settings.doubao_tts_speed_ratio),
        0.1,
        2.0,
    )
    volume = _clamp(
        float(volume_ratio if volume_ratio is not None else settings.doubao_tts_volume_ratio),
        0.1,
        3.0,
    )

    submit_payload = {
        "user": {"uid": settings.doubao_tts_uid},
        "unique_id": request_id,
        "namespace": "BidirectionalTTS",
        "req_params": {
            "text": text.strip(),
            "speaker": speaker,
            "audio_params": {
                "format": "mp3",
                "sample_rate": settings.doubao_tts_sample_rate,
                "speech_rate": _speech_rate_from_ratio(speed),
                "loudness_rate": _loudness_rate_from_ratio(volume),
            },
            "callback_url": "",
        },
    }
    headers = _v3_async_headers(resource_id, request_id)

    logger.info(
        "Submitting async Doubao TTS request_id=%s speaker=%s resource=%s",
        request_id,
        speaker,
        resource_id,
    )
    submit_response = requests.post(
        settings.doubao_tts_submit_url,
        headers=headers,
        json=submit_payload,
        timeout=60,
    )
    submit_response.raise_for_status()
    submit_data = submit_response.json()
    if submit_data.get("code") != TTS_SUCCESS_CODE:
        raise RuntimeError(f"豆包异步 TTS 提交失败：{submit_data}")

    task_id = (submit_data.get("data") or {}).get("task_id") or request_id
    deadline = time.monotonic() + settings.doubao_tts_timeout_seconds
    query_payload = {"task_id": task_id}

    while time.monotonic() < deadline:
        query_request_id = str(uuid.uuid4())
        query_response = requests.post(
            settings.doubao_tts_query_url,
            headers=_v3_async_headers(resource_id, query_request_id),
            json=query_payload,
            timeout=60,
        )
        query_response.raise_for_status()
        query_data = query_response.json()
        if query_data.get("code") != TTS_SUCCESS_CODE:
            raise RuntimeError(f"豆包异步 TTS 查询失败：{query_data}")

        data = query_data.get("data") or {}
        task_status = data.get("task_status")
        if task_status == 2:
            source_audio_url = data.get("audio_url")
            if not source_audio_url:
                raise RuntimeError(f"豆包异步 TTS 成功但未返回 audio_url：{query_data}")
            _download_audio(source_audio_url, output_path)
            return AudioGenerationResult(
                audio_path=str(Path(output_path).resolve()),
                audio_url=output_url(output_path, settings.output_dir),
                request_id=request_id,
                task_id=task_id,
                source_audio_url=source_audio_url,
            )
        if task_status == 3:
            raise RuntimeError(f"豆包异步 TTS 任务失败：{query_data}")

        time.sleep(settings.doubao_tts_poll_interval_seconds)

    raise TimeoutError(f"豆包异步 TTS 超时：task_id={task_id}")


def doubao_tts_create(
    text: str,
    voice_id: str = "zh_female_shuangkuaisisi_uranus_bigtts",
    output_file: Optional[str] = None,
    tts_resource_id: str = "",
    speed_ratio: float | None = None,
    volume_ratio: float | None = None,
    pitch_ratio: float | None = None,
    use_async: bool = False,
) -> AudioGenerationResult:
    """Generate audio from script text with speaker + prosody controls (no cloning)."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("合成文本不能为空。")

    if use_async:
        return doubao_tts_async_long_text(
            cleaned,
            voice_id=voice_id,
            output_file=output_file,
            tts_resource_id=tts_resource_id,
            speed_ratio=speed_ratio,
            volume_ratio=volume_ratio,
        )

    speaker = _resolve_speaker(voice_id)
    # TTS 2.0 voices are more reliable on V3 unidirectional.
    if _resource_for_speaker(speaker) == "seed-tts-2.0":
        try:
            return doubao_tts_http_v3(
                cleaned,
                voice_id=speaker,
                output_file=output_file,
                speed_ratio=speed_ratio,
                volume_ratio=volume_ratio,
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("V3 TTS failed for %s, falling back to V1: %s", speaker, error)

    return doubao_tts_http_v1(
        cleaned,
        voice_id=speaker,
        output_file=output_file,
        speed_ratio=speed_ratio,
        volume_ratio=volume_ratio,
        pitch_ratio=pitch_ratio,
    )


def doubao_tts_preview(
    voice_id: str,
    speed_ratio: float | None = None,
    volume_ratio: float | None = None,
    pitch_ratio: float | None = None,
    text: str = "",
) -> AudioGenerationResult:
    """Synthesize a short sample for the selected voice."""
    preview_text = (text or PREVIEW_TEXT).strip()
    request_id = str(uuid.uuid4())
    settings = get_settings()
    output_file = str(settings.output_dir / "audio" / f"preview-{request_id}.mp3")
    return doubao_tts_create(
        preview_text,
        voice_id=voice_id,
        output_file=output_file,
        speed_ratio=speed_ratio,
        volume_ratio=volume_ratio,
        pitch_ratio=pitch_ratio,
    )


def minimax_tts_async(text: str, voice_id: str, output_file: str = "output/audio/output.mp3") -> str:
    """Compatibility wrapper for the old function name."""
    result = doubao_tts_create(text, voice_id=voice_id, output_file=output_file)
    return result.audio_path
