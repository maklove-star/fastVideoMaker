from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from .config import get_settings
from .utils.file_utils import ensure_parent, output_url
from .utils.logger import get_logger


logger = get_logger(__name__)

# Docs: https://docs.volcengine.com/docs/86081/1804513
# Step1 形象创建: https://docs.volcengine.com/docs/86081/1804514
# Step2 视频生成: https://docs.volcengine.com/docs/86081/1804515
ROLE_REQ_KEYS = {
    "normal": "realman_avatar_picture_create_role",
    "loopy": "realman_avatar_picture_create_role_loopy",
    "loopyb": "realman_avatar_picture_create_role_loopyb",
}
VIDEO_REQ_KEYS = {
    "normal": "realman_avatar_picture_v2",
    "loopy": "realman_avatar_picture_loopy",
    "loopyb": "realman_avatar_picture_loopyb",
}


@dataclass
class VideoGenerationResult:
    video_url: str | None
    local_video_path: str | None
    task_id: str | None = None
    source_video_url: str | None = None


def _estimate_duration_seconds(script: str) -> int:
    length = len(script.strip()) or 240
    return min(90, max(15, round(length / 4.2)))


def _is_http_url(value: str | None) -> bool:
    return bool(value and value.startswith(("http://", "https://")))


def _output_http_url(local_path: str | Path) -> str | None:
    settings = get_settings()
    if not settings.public_base_url:
        return None
    relative_url = output_url(local_path, settings.output_dir)
    if not relative_url:
        return None
    return urljoin(settings.public_base_url.rstrip("/") + "/", relative_url.lstrip("/"))


def _local_path_from_output_url(value: str) -> Path | None:
    """Map '/output/...' (or full URL containing it) to a file under output_dir."""
    settings = get_settings()
    marker = "/output/"
    idx = value.find(marker)
    if idx < 0:
        # Also accept Windows-style relative 'output\...' / 'output/...'
        normalized = value.replace("\\", "/").lstrip("/")
        if normalized.startswith("output/"):
            relative = normalized[len("output/") :]
            local = settings.output_dir.joinpath(*Path(relative).parts)
            return local if local.is_file() else None
        return None
    relative = value[idx + len(marker) :].lstrip("/")
    local = settings.output_dir.joinpath(*Path(relative).parts)
    return local if local.is_file() else None


def _resolve_public_url(value: str, *, kind: str) -> str:
    """Volc CV APIs require publicly reachable image/audio URLs."""
    from .public_upload import upload_public_file

    text = (value or "").strip()
    if not text:
        raise ValueError(f"{kind} 不能为空。")

    # Relative /output/... URLs from the API — resolve to local file first.
    mapped = _local_path_from_output_url(text)
    if mapped is not None:
        return _resolve_public_url(str(mapped), kind=kind)

    if _is_http_url(text):
        if "127.0.0.1" in text or "localhost" in text:
            raise RuntimeError(
                f"{kind} 使用了本地地址，火山视觉服务无法访问。"
                "请配置公网可访问的 PUBLIC_BASE_URL，或开启临时图床 PUBLIC_FILE_HOST=auto。"
            )
        return text

    path = Path(text)
    if not path.is_file():
        raise RuntimeError(f"{kind} 文件不存在：{text}")

    public = _output_http_url(path)
    if public and "127.0.0.1" not in public and "localhost" not in public:
        return public

    # Fallback: upload to a temporary public host (local-dev friendly).
    return upload_public_file(path, kind=kind)


def _download_video(video_url: str, task_id: str) -> str | None:
    settings = get_settings()
    output_path = ensure_parent(settings.output_dir / "video" / f"{task_id}.mp4")
    response = requests.get(video_url, timeout=300)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return str(Path(output_path).resolve())


def _create_placeholder(
    portrait_asset_id: str,
    audio_path: str,
    script: str,
    resolution: str,
    audio_source_url: str | None,
) -> VideoGenerationResult:
    settings = get_settings()
    job_id = str(uuid.uuid4())
    placeholder_path = ensure_parent(settings.output_dir / "video" / f"{job_id}.json")
    payload = {
        "status": "placeholder",
        "message": (
            "真实视频生成未开启。配置 ENABLE_REAL_VIDEO=true、"
            "VOLC_ACCESS_KEY / VOLC_SECRET_KEY（及 PUBLIC_BASE_URL 或临时图床）"
            "后将调用火山「单图音频驱动」。"
        ),
        "provider": settings.video_provider,
        "docs": "https://docs.volcengine.com/docs/86081/1804513",
        "portrait_asset_id": portrait_asset_id,
        "audio_path": str(Path(audio_path).resolve()) if not _is_http_url(audio_path) else audio_path,
        "audio_source_url": audio_source_url,
        "script": script,
        "resolution": resolution,
        "estimated_duration_seconds": _estimate_duration_seconds(script),
    }
    placeholder_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Created video placeholder metadata=%s", placeholder_path)
    return VideoGenerationResult(None, str(Path(placeholder_path).resolve()), task_id=job_id)


def _looks_like_iam_access_key(ak: str) -> bool:
    """Volc IAM Access Key IDs are typically long and often start with AKLT/AK…"""
    text = (ak or "").strip()
    if len(text) < 20:
        return False
    if text.startswith(("AKLT", "AKTP", "AKAP", "AK")):
        return True
    # Some accounts use other prefixes; still reject obvious short product API keys.
    return len(text) >= 24 and "." not in text


def _visual_service():
    settings = get_settings()
    ak = (settings.volc_access_key or "").strip()
    sk = (settings.volc_secret_key or "").strip()
    if not ak or not sk:
        raise RuntimeError(
            "缺少 VOLC_ACCESS_KEY / VOLC_SECRET_KEY。"
            "请到火山引擎控制台「访问控制 → 访问密钥」创建一对 IAM AK/SK："
            "https://console.volcengine.com/iam/keymanage/"
        )
    if not _looks_like_iam_access_key(ak) or sk.count(".") >= 2:
        raise RuntimeError(
            "当前 VOLC_ACCESS_KEY / VOLC_SECRET_KEY 看起来是「产品 API Key」，"
            "而不是 IAM 访问密钥。火山视觉 CVSubmitTask（单图音频驱动）必须用 "
            "控制台 → 头像 → API 访问密钥（Access Key ID + Secret Access Key）。\n"
            "请打开 https://console.volcengine.com/iam/keymanage/ 新建密钥，"
            "写入 .env 的 VOLC_ACCESS_KEY / VOLC_SECRET_KEY 后重启后端。\n"
            f"当前 AccessKey 前缀：{ak[:8]}…（长度 {len(ak)}）"
        )
    from volcengine.visual.VisualService import VisualService

    service = VisualService()
    service.set_ak(ak)
    service.set_sk(sk)
    return service


def _decode_volc_sdk_error(error: BaseException) -> dict[str, Any] | None:
    """Parse Exception(b'{json...}') raised by volcengine VisualService wrappers."""
    text = str(error).strip()
    if text.startswith("b'") or text.startswith('b"'):
        text = text[2:-1]
        try:
            text = bytes(text, "utf-8").decode("unicode_escape")
        except Exception:  # noqa: BLE001
            pass
    # Also handle raw bytes repr already partially decoded
    if "Access Denied" in text or '"code"' in text:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                payload = json.loads(text[start : end + 1])
                if isinstance(payload, dict):
                    return payload
        except json.JSONDecodeError:
            return None
    return None


def _format_cv_50215_hint(action: str, message: str, request_id: Any = None) -> str:
    """50215 on CVGetResult usually means the async job rejected its inputs."""
    return (
        f"火山视觉 {action} 失败 code=50215：{message or 'Input invalid for this service'}。"
        "这通常不是 task_id 写错，而是提交任务时的人像/音频不符合「单图音频驱动」入参规则，"
        "查询结果时把算法侧失败原样返回。\n"
        "请检查：\n"
        "1) 人像：正面、单人、下巴与额头完整入画；避免侧脸过大、遮挡嘴唇、分辨率过低；"
        "loopyb（大画幅）还要求脸四周留白足够（脸不宜占满画面）。"
        "规则：https://www.volcengine.com/docs/86081/1804516\n"
        "2) 公网 URL：人像 image_url / 音频 audio_url 须可被火山直接下载；"
        "临时图床若过期，请重新上传后再生成。\n"
        "3) 模式一致：形象创建与视频生成必须同为 normal / loopy / loopyb；"
        "换模式请勿混用旧的 resource_id 缓存。\n"
        f"request_id={request_id}"
    )


def _raise_friendly_cv_error(error: BaseException, action: str) -> None:
    payload = _decode_volc_sdk_error(error)
    if payload:
        code = payload.get("code") or payload.get("status")
        message = payload.get("message") or ""
        if code in (50400, "50400") or "Access Denied" in str(message):
            raise RuntimeError(
                "火山视觉拒绝访问（50400 Access Denied）。"
                "AK/SK 已能连通，但账号未开通「单图音频驱动」或 IAM 缺少视觉权限。\n"
                "请按文档开通服务：https://www.volcengine.com/docs/86081/1660357\n"
                "产品介绍：https://www.volcengine.com/docs/86081/1804513\n"
                "控制台一般在「智能视觉 / 图像生成大模型 → 单图音频驱动」点开通；"
                "若使用 IAM 子用户，需授予视觉相关策略（如全读写）后等待几分钟再生效。\n"
                f"原始信息：{message} request_id={payload.get('request_id')}"
            ) from error
        if code in (50215, "50215") or "Input invalid for this service" in str(message):
            raise RuntimeError(
                _format_cv_50215_hint(action, str(message), payload.get("request_id"))
            ) from error
        raise RuntimeError(
            f"火山视觉 {action} 失败 code={code}：{message or payload}"
        ) from error
    raise RuntimeError(f"火山视觉 {action} 失败：{error}") from error


def _assert_cv_ok(data: dict[str, Any], action: str) -> dict[str, Any]:
    meta_error = ((data.get("ResponseMetadata") or {}) if isinstance(data, dict) else {}).get("Error") or {}
    if isinstance(meta_error, dict) and meta_error.get("Code") in {"InvalidAccessKey", "SignatureDoesNotMatch"}:
        raise RuntimeError(
            f"火山视觉鉴权失败（{meta_error.get('Code')}）：{meta_error.get('Message')}。"
            "请确认 .env 使用的是 IAM「访问密钥」AK/SK（控制台 → API访问密钥），"
            "不是视觉/方舟产品页复制的 API Key。"
            "创建地址：https://console.volcengine.com/iam/keymanage/"
        )
    code = data.get("code")
    if code not in (10000, "10000", None) and data.get("ResponseMetadata"):
        # Some SDK wrappers unwrap differently.
        error = (data.get("ResponseMetadata") or {}).get("Error") or {}
        raise RuntimeError(f"火山视觉 {action} 失败：{error or data}")
    if code not in (10000, "10000"):
        message = data.get("message") or data.get("msg") or data
        if code in (50400, "50400") or "Access Denied" in str(message):
            raise RuntimeError(
                "火山视觉拒绝访问（50400 Access Denied）。"
                "请先开通「单图音频驱动」：https://www.volcengine.com/docs/86081/1660357 ；"
                "并确认 IAM 有视觉服务权限。"
            )
        if code in (50215, "50215") or "Input invalid for this service" in str(message):
            raise RuntimeError(
                _format_cv_50215_hint(action, str(message), data.get("request_id"))
            )
        raise RuntimeError(f"火山视觉 {action} 失败 code={code}：{message}")
    return data


def _cv_submit(service: Any, form: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        submit = service.cv_submit_task(form)
    except Exception as error:  # noqa: BLE001
        _raise_friendly_cv_error(error, action)
        raise  # pragma: no cover
    if not isinstance(submit, dict):
        raise RuntimeError(f"{action}返回异常：{submit}")
    return _assert_cv_ok(submit, action)


def _poll_cv_task(service: Any, req_key: str, task_id: str, *, timeout: int, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            raw = service.cv_get_result({"req_key": req_key, "task_id": task_id})
        except Exception as error:  # noqa: BLE001
            _raise_friendly_cv_error(error, "查询任务")
            raise  # pragma: no cover
        if not isinstance(raw, dict):
            raise RuntimeError(f"火山视觉查询返回异常：{raw}")
        _assert_cv_ok(raw, "查询任务")
        last = raw
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        status = str(data.get("status") or "").lower()
        logger.info("Volc CV task_id=%s status=%s", task_id, status)
        if status == "done":
            return raw
        if status in {"not_found", "expired"}:
            raise RuntimeError(f"火山视觉任务不可用 status={status}：{raw}")
        time.sleep(interval)
    raise TimeoutError(f"火山视觉任务超时：task_id={task_id} last={last}")


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _avatar_cache_path(fingerprint: str, mode: str) -> Path:
    settings = get_settings()
    return settings.output_dir / "avatars" / f"{mode}-{fingerprint}.json"


def _load_cached_resource_id(fingerprint: str, mode: str) -> str | None:
    path = _avatar_cache_path(fingerprint, mode)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        resource_id = data.get("resource_id")
        return str(resource_id) if resource_id else None
    except Exception:  # noqa: BLE001
        return None


def _save_cached_resource_id(fingerprint: str, mode: str, resource_id: str) -> None:
    path = ensure_parent(_avatar_cache_path(fingerprint, mode))
    path.write_text(
        json.dumps({"resource_id": resource_id, "mode": mode, "fingerprint": fingerprint}, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_resource_id(query_payload: dict[str, Any]) -> str:
    data = query_payload.get("data") if isinstance(query_payload.get("data"), dict) else {}
    resp_data = data.get("resp_data")
    if isinstance(resp_data, str) and resp_data.strip():
        try:
            nested = json.loads(resp_data)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"形象创建 resp_data 不是合法 JSON：{resp_data[:300]}") from error
        resource_id = nested.get("resource_id")
        if resource_id:
            return str(resource_id)
        if nested.get("code") not in (0, "0", None):
            raise RuntimeError(f"形象创建失败：{nested}")
    resource_id = data.get("resource_id")
    if resource_id:
        return str(resource_id)
    raise RuntimeError(f"形象创建完成但未返回 resource_id：{query_payload}")


def _parse_preview_url(query_payload: dict[str, Any]) -> str:
    data = query_payload.get("data") if isinstance(query_payload.get("data"), dict) else {}
    # loopyb may put video_url at top-level data
    for key in ("video_url", "preview_url"):
        value = data.get(key)
        if isinstance(value, str) and _is_http_url(value):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and _is_http_url(first):
                return first

    resp_data = data.get("resp_data")
    if isinstance(resp_data, str) and resp_data.strip():
        nested = json.loads(resp_data)
        if nested.get("code") not in (0, "0", None):
            raise RuntimeError(f"视频生成失败：{nested}")
        preview = nested.get("preview_url")
        if isinstance(preview, list) and preview and _is_http_url(str(preview[0])):
            return str(preview[0])
        if isinstance(preview, str) and _is_http_url(preview):
            return preview
        video_url = nested.get("video_url") or nested.get("url")
        if isinstance(video_url, str) and _is_http_url(video_url):
            return video_url
    raise RuntimeError(f"视频生成完成但未返回 preview_url/video_url：{query_payload}")


def _create_or_reuse_resource_id(service: Any, image_url: str, mode: str, local_image: Path | None) -> str:
    settings = get_settings()
    role_key = ROLE_REQ_KEYS[mode]
    fingerprint = _file_fingerprint(local_image) if local_image else hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:16]
    cached = _load_cached_resource_id(fingerprint, mode)
    if cached:
        logger.info("Reuse cached avatar resource_id=%s mode=%s", cached, mode)
        return cached

    submit = _cv_submit(service, {"req_key": role_key, "image_url": image_url}, "形象创建提交")
    task_id = ((submit.get("data") or {}) if isinstance(submit.get("data"), dict) else {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"形象创建未返回 task_id：{submit}")

    done = _poll_cv_task(
        service,
        role_key,
        str(task_id),
        timeout=settings.volc_cv_timeout_seconds,
        interval=settings.volc_cv_poll_interval_seconds,
    )
    resource_id = _parse_resource_id(done)
    _save_cached_resource_id(fingerprint, mode, resource_id)
    logger.info("Created avatar resource_id=%s mode=%s", resource_id, mode)
    return resource_id


def _generate_with_volc_cv(
    portrait_asset_id: str,
    audio_path: str,
    script: str,
    resolution: str,
    audio_source_url: str | None,
    volc_cv_mode: str | None = None,
) -> VideoGenerationResult:
    settings = get_settings()
    mode = (volc_cv_mode or settings.volc_cv_mode or "normal").strip().lower()
    if mode not in VIDEO_REQ_KEYS:
        raise RuntimeError(f"不支持的 VOLC_CV_MODE={mode}（可选 normal / loopy / loopyb）")

    local_image: Path | None = None
    portrait_raw = portrait_asset_id.strip()
    if not _is_http_url(portrait_raw):
        mapped_portrait = _local_path_from_output_url(portrait_raw)
        candidate = mapped_portrait or Path(portrait_raw)
        if candidate.is_file():
            local_image = candidate
            portrait_raw = str(candidate)

    image_url = _resolve_public_url(portrait_raw, kind="人像图片")

    # Prefer a real local file when the frontend sent a relative /output/... as audioUrl.
    audio_remote = (audio_source_url or "").strip()
    audio_local = (audio_path or "").strip()
    if audio_remote.startswith("/") and not _is_http_url(audio_remote):
        # Relative site path is not a public URL — fall back to local path / mapping.
        audio_candidate = audio_local or audio_remote
    elif audio_remote:
        audio_candidate = audio_remote
    else:
        audio_candidate = audio_local
    mapped_audio = _local_path_from_output_url(audio_candidate)
    if mapped_audio is not None:
        audio_candidate = str(mapped_audio)
    audio_url = _resolve_public_url(audio_candidate, kind="音频")

    service = _visual_service()
    resource_id = _create_or_reuse_resource_id(service, image_url, mode, local_image)

    video_key = VIDEO_REQ_KEYS[mode]
    submit = _cv_submit(
        service,
        {
            "req_key": video_key,
            "resource_id": resource_id,
            "audio_url": audio_url,
        },
        "视频生成提交",
    )
    task_id = ((submit.get("data") or {}) if isinstance(submit.get("data"), dict) else {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"视频生成未返回 task_id：{submit}")

    logger.info(
        "Volc CV video submitted task_id=%s mode=%s resolution=%s resource_id=%s",
        task_id,
        mode,
        resolution,
        resource_id,
    )
    done = _poll_cv_task(
        service,
        video_key,
        str(task_id),
        timeout=settings.volc_cv_timeout_seconds,
        interval=settings.volc_cv_poll_interval_seconds,
    )
    source_url = _parse_preview_url(done)
    try:
        local_path = _download_video(source_url, str(task_id))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to download Volc CV video task_id=%s", task_id)
        local_path = None

    return VideoGenerationResult(
        video_url=output_url(local_path, settings.output_dir) if local_path else source_url,
        local_video_path=local_path,
        task_id=str(task_id),
        source_video_url=source_url,
    )


def generate_digital_human(
    portrait_asset_id: str,
    audio_path: str,
    script: str,
    resolution: str = "720p",
    audio_source_url: Optional[str] = None,
    volc_cv_mode: Optional[str] = None,
) -> VideoGenerationResult:
    """
    portrait_asset_id: 人像图片公网 URL / 本地图片路径（需配合 PUBLIC_BASE_URL）
    audio_path: 本地音频路径或远程音频 URL
    script: 文案（元数据；口型由音频驱动）
    """
    settings = get_settings()
    if not settings.enable_real_video:
        return _create_placeholder(
            portrait_asset_id,
            audio_path,
            script,
            resolution,
            audio_source_url,
        )

    provider = (settings.video_provider or "volc_cv").strip().lower()
    if provider in {"volc_cv", "volc", "cv", "realman"}:
        return _generate_with_volc_cv(
            portrait_asset_id,
            audio_path,
            script,
            resolution,
            audio_source_url,
            volc_cv_mode=volc_cv_mode,
        )
    raise RuntimeError(
        f"不支持的 VIDEO_PROVIDER：{settings.video_provider}。"
        "请使用 volc_cv（火山单图音频驱动，文档 https://docs.volcengine.com/docs/86081/1804513 ）。"
    )
