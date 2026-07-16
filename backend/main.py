from __future__ import annotations

import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .audio_generator import doubao_tts_create, doubao_tts_preview, list_available_voices
from .audio_history import list_audio_history, save_audio_history_meta
from .auto_publisher import auto_publish
from .config import get_settings
from .schemas import (
    AudioGenerateRequest,
    AudioGenerateResponse,
    AudioHistoryResponse,
    AudioPreviewRequest,
    CopywritingCreateRequest,
    CopywritingItem,
    CopywritingListResponse,
    CopywritingUpdateRequest,
    PortraitHistoryResponse,
    PortraitUploadResponse,
    ScriptProcessRequest,
    ScriptProcessResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoHistoryResponse,
    VideoStatusResponse,
    VoiceOption,
    WorkflowPayload,
    WorkflowResult,
)
from .copywriting_store import (
    create_copywriting,
    delete_copywriting,
    get_copywriting,
    init_db as init_copywriting_db,
    list_copywriting,
    update_copywriting,
)
from .script_processor import process_script
from .utils.file_utils import ensure_parent, output_url
from .utils.logger import get_logger
from .portrait_history import list_portrait_history, save_portrait_history_meta
from .video_generator import generate_digital_human, query_heygen_video_status, start_heygen_video
from .video_history import list_video_history, save_video_history_meta

logger = get_logger(__name__)
settings = get_settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
(settings.output_dir / "portraits").mkdir(parents=True, exist_ok=True)
init_copywriting_db()

ALLOWED_PORTRAIT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}

app = FastAPI(title="Digital Human Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, requests.HTTPError):
        response = error.response
        status_code = response.status_code if response is not None else 502
        detail = response.text if response is not None else str(error)
        return HTTPException(status_code=status_code, detail=detail)
    if isinstance(error, (RuntimeError, ValueError, TimeoutError, NotImplementedError)):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Digital Human Agent API",
        "health": "/api/health",
        "docs": "/docs",
        "frontend": "http://127.0.0.1:5173",
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _portrait_suffix(content_type: str, filename: str) -> str:
    suffix = ALLOWED_PORTRAIT_TYPES.get(content_type)
    if suffix:
        return suffix
    name = filename.lower()
    if name.endswith((".jpg", ".jpeg")):
        return ".jpg"
    if name.endswith(".png"):
        return ".png"
    if name.endswith(".webp"):
        return ".webp"
    if name.endswith(".gif"):
        return ".gif"
    if name.endswith(".bmp"):
        return ".bmp"
    raise ValueError("仅支持 JPG / PNG / WEBP / GIF / BMP 人像图片。")


@app.post("/api/portraits/upload", response_model=PortraitUploadResponse)
async def upload_portrait(file: UploadFile = File(...)) -> PortraitUploadResponse:
    """Save a local portrait image into output/portraits/ and return preview URL + path."""
    try:
        content_type = (file.content_type or "").lower().strip()
        suffix = _portrait_suffix(content_type, file.filename or "")

        raw = await file.read()
        if not raw:
            raise ValueError("上传文件为空。")
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError("人像图片不能超过 20MB。")

        portrait_id = str(uuid.uuid4())
        output_path = ensure_parent(settings.output_dir / "portraits" / f"{portrait_id}{suffix}")
        output_path.write_bytes(raw)
        portrait_url = output_url(output_path, settings.output_dir)
        if not portrait_url:
            raise RuntimeError("无法生成人像预览地址。")

        original_name = file.filename or output_path.name
        save_portrait_history_meta(
            portrait_path=output_path,
            portrait_url=portrait_url,
            file_name=original_name,
            portrait_id=portrait_id,
        )
        logger.info("Portrait uploaded path=%s bytes=%s", output_path, len(raw))
        return PortraitUploadResponse(
            portraitPath=str(Path(output_path).resolve()),
            portraitUrl=portrait_url,
            fileName=original_name,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Portrait upload failed")
        raise _http_error(error) from error


@app.get("/api/portraits/history", response_model=PortraitHistoryResponse)
def portrait_history(limit: int = 50) -> PortraitHistoryResponse:
    return PortraitHistoryResponse(items=list_portrait_history(limit=limit))


@app.get("/api/audio/voices", response_model=dict[str, list[VoiceOption]])
def audio_voices() -> dict[str, list[VoiceOption]]:
    return {"voices": list_available_voices()}


@app.get("/api/audio/history", response_model=AudioHistoryResponse)
def audio_history(limit: int = 50) -> AudioHistoryResponse:
    return AudioHistoryResponse(items=list_audio_history(limit=limit))


@app.get("/api/video/history", response_model=VideoHistoryResponse)
def video_history(limit: int = 50) -> VideoHistoryResponse:
    return VideoHistoryResponse(items=list_video_history(limit=limit))


@app.post("/api/audio/preview", response_model=AudioGenerateResponse)
def audio_preview(payload: AudioPreviewRequest) -> AudioGenerateResponse:
    try:
        audio_result = doubao_tts_preview(
            voice_id=payload.voiceId,
            speed_ratio=payload.speedRatio,
            volume_ratio=payload.volumeRatio,
            pitch_ratio=payload.pitchRatio,
            text=payload.text,
        )
        return AudioGenerateResponse(
            audioPath=audio_result.audio_path,
            audioUrl=audio_result.audio_url,
            requestId=audio_result.request_id,
            taskId=audio_result.task_id,
            sourceAudioUrl=audio_result.source_audio_url,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Audio preview failed")
        raise _http_error(error) from error


@app.post("/api/scripts/process", response_model=ScriptProcessResponse)
def process_script_endpoint(payload: ScriptProcessRequest) -> ScriptProcessResponse:
    try:
        script = process_script(
            payload.userInput,
            mode=payload.mode,
            extract_url=payload.extractUrl,
        )
        return ScriptProcessResponse(script=script)
    except Exception as error:  # noqa: BLE001
        logger.exception("Script processing failed")
        raise _http_error(error) from error


@app.get("/api/copywriting", response_model=CopywritingListResponse)
def copywriting_list(q: str = "", limit: int = 50, offset: int = 0) -> CopywritingListResponse:
    items, total = list_copywriting(q=q, limit=limit, offset=offset)
    return CopywritingListResponse(
        items=[CopywritingItem(**item) for item in items],
        total=total,
    )


@app.get("/api/copywriting/{item_id}", response_model=CopywritingItem)
def copywriting_get(item_id: str) -> CopywritingItem:
    item = get_copywriting(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="文案不存在。")
    return CopywritingItem(**item)


@app.post("/api/copywriting", response_model=CopywritingItem)
def copywriting_create(payload: CopywritingCreateRequest) -> CopywritingItem:
    try:
        item = create_copywriting(
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
            input_mode=payload.inputMode,
            notes=payload.notes,
        )
        return CopywritingItem(**item)
    except Exception as error:  # noqa: BLE001
        logger.exception("Copywriting create failed")
        raise _http_error(error) from error


@app.put("/api/copywriting/{item_id}", response_model=CopywritingItem)
def copywriting_update(item_id: str, payload: CopywritingUpdateRequest) -> CopywritingItem:
    try:
        item = update_copywriting(
            item_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
            input_mode=payload.inputMode,
            notes=payload.notes,
        )
        return CopywritingItem(**item)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        logger.exception("Copywriting update failed id=%s", item_id)
        raise _http_error(error) from error


@app.delete("/api/copywriting/{item_id}")
def copywriting_delete(item_id: str) -> dict[str, bool]:
    if not delete_copywriting(item_id):
        raise HTTPException(status_code=404, detail="文案不存在。")
    return {"ok": True}


@app.post("/api/audio/generate", response_model=AudioGenerateResponse)
def audio_generate(payload: AudioGenerateRequest) -> AudioGenerateResponse:
    try:
        audio_result = doubao_tts_create(
            payload.text,
            voice_id=payload.voiceId,
            output_file=payload.outputFile,
            speed_ratio=payload.speedRatio,
            volume_ratio=payload.volumeRatio,
            pitch_ratio=payload.pitchRatio,
        )
        save_audio_history_meta(
            audio_path=audio_result.audio_path,
            audio_url=audio_result.audio_url,
            source_audio_url=audio_result.source_audio_url,
            voice_id=payload.voiceId,
            text=payload.text,
            request_id=audio_result.request_id,
            task_id=audio_result.task_id,
        )
        return AudioGenerateResponse(
            audioPath=audio_result.audio_path,
            audioUrl=audio_result.audio_url,
            requestId=audio_result.request_id,
            taskId=audio_result.task_id,
            sourceAudioUrl=audio_result.source_audio_url,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Audio generation failed")
        raise _http_error(error) from error


def _heygen_options_from_payload(payload: VideoGenerateRequest) -> dict:
    return {
        "title": payload.title,
        "aspect_ratio": payload.aspectRatio,
        "fit": payload.fit,
        "remove_background": payload.removeBackground,
        "output_format": payload.outputFormat,
        "expressiveness": payload.expressiveness,
        "motion_prompt": payload.motionPrompt,
        "background_type": payload.backgroundType,
        "background_color": payload.backgroundColor,
        "burn_captions": payload.burnCaptions,
    }


@app.post("/api/video/generate", response_model=VideoGenerateResponse)
def video_generate(payload: VideoGenerateRequest) -> VideoGenerateResponse:
    """Start HeyGen job (fast return) or run full blocking generate for other providers."""
    try:
        provider = (settings.video_provider or "heygen").strip().lower()
        heygen_opts = _heygen_options_from_payload(payload)
        if provider in {"heygen", "hey_gen"} and settings.enable_real_video:
            started = start_heygen_video(
                payload.portraitAssetId,
                payload.audioPath,
                payload.script,
                resolution=payload.resolution,
                audio_source_url=payload.audioUrl,
                **heygen_opts,
            )
            return VideoGenerateResponse(
                taskId=started.task_id,
                status=started.status,
                message=started.message,
                progressPercent=started.progress_percent,
                videoPageUrl=started.video_page_url,
            )

        video_result = generate_digital_human(
            payload.portraitAssetId,
            payload.audioPath,
            payload.script,
            resolution=payload.resolution,
            audio_source_url=payload.audioUrl,
            volc_cv_mode=payload.volcCvMode,
            **heygen_opts,
        )
        save_video_history_meta(
            video_path=video_result.local_video_path,
            video_url=video_result.video_url,
            source_video_url=video_result.source_video_url,
            task_id=video_result.task_id,
            script=payload.script,
            title=payload.title,
            resolution=payload.resolution,
            portrait_path=payload.portraitAssetId,
        )
        return VideoGenerateResponse(
            videoUrl=video_result.video_url,
            localVideoPath=video_result.local_video_path,
            taskId=video_result.task_id,
            sourceVideoUrl=video_result.source_video_url,
            status="completed" if video_result.video_url or video_result.local_video_path else "placeholder",
            message="完成",
            progressPercent=100,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Video generation failed")
        raise _http_error(error) from error


@app.get("/api/video/status/{task_id}", response_model=VideoStatusResponse)
def video_status(task_id: str) -> VideoStatusResponse:
    """Poll HeyGen GET /v3/videos/{video_id} — status only, no percent from vendor."""
    try:
        snapshot = query_heygen_video_status(task_id)
        if snapshot.status == "completed" and snapshot.local_video_path:
            save_video_history_meta(
                video_path=snapshot.local_video_path,
                video_url=snapshot.video_url,
                source_video_url=snapshot.source_video_url,
                task_id=snapshot.task_id or task_id,
            )
        return VideoStatusResponse(
            taskId=snapshot.task_id,
            status=snapshot.status,
            message=snapshot.message,
            progressPercent=snapshot.progress_percent,
            videoUrl=snapshot.video_url,
            localVideoPath=snapshot.local_video_path,
            sourceVideoUrl=snapshot.source_video_url,
            videoPageUrl=snapshot.video_page_url,
            failureCode=snapshot.failure_code,
            failureMessage=snapshot.failure_message,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Video status query failed task_id=%s", task_id)
        raise _http_error(error) from error


@app.post("/api/workflows/generate", response_model=WorkflowResult)
def workflow_generate(payload: WorkflowPayload) -> WorkflowResult:
    job_id = str(uuid.uuid4())
    logger.info("Workflow started job_id=%s", job_id)

    try:
        script = process_script(
            payload.userInput,
            mode=payload.inputMode,
            extract_url=payload.extractUrl,
        )
        audio_result = doubao_tts_create(
            script,
            voice_id=payload.voiceId,
            output_file=f"output/audio/{job_id}.mp3",
            speed_ratio=payload.speedRatio,
            volume_ratio=payload.volumeRatio,
            pitch_ratio=payload.pitchRatio,
        )
        save_audio_history_meta(
            audio_path=audio_result.audio_path,
            audio_url=audio_result.audio_url,
            source_audio_url=audio_result.source_audio_url,
            voice_id=payload.voiceId,
            text=script,
            request_id=audio_result.request_id or job_id,
            task_id=audio_result.task_id,
        )
        video_result = generate_digital_human(
            payload.portraitAssetId,
            audio_result.audio_path,
            script,
            resolution=payload.resolution,
            audio_source_url=audio_result.source_audio_url or audio_result.audio_url,
        )
        save_video_history_meta(
            video_path=video_result.local_video_path,
            video_url=video_result.video_url,
            source_video_url=video_result.source_video_url,
            task_id=video_result.task_id or job_id,
            script=script,
            title=payload.title,
            resolution=payload.resolution,
            portrait_path=payload.portraitAssetId,
        )
        publish_results = []
        if payload.publishNow:
            publish_results = auto_publish(
                video_result.video_url or video_result.local_video_path or "",
                title=payload.title or "数字人口播短视频",
                description=payload.description,
                platforms=payload.platforms,
            )

        logger.info("Workflow finished job_id=%s", job_id)
        return WorkflowResult(
            jobId=job_id,
            script=script,
            audioPath=audio_result.audio_path,
            audioUrl=audio_result.audio_url,
            sourceAudioUrl=audio_result.source_audio_url,
            videoUrl=video_result.video_url,
            localVideoPath=video_result.local_video_path,
            videoTaskId=video_result.task_id,
            sourceVideoUrl=video_result.source_video_url,
            publishResults=publish_results,
        )
    except Exception as error:  # noqa: BLE001
        logger.exception("Workflow failed job_id=%s", job_id)
        raise _http_error(error) from error


# Mount after API routes so /api/* is never shadowed by static files.
app.mount("/output", StaticFiles(directory=settings.output_dir), name="output")
