from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    ark_api_key: str = os.getenv("ARK_API_KEY", "")
    ark_api_url: str = os.getenv(
        "ARK_API_URL",
        "https://ark.cn-beijing.volces.com/api/v3/responses",
    )
    # Doubao Responses model; GLM_MODEL kept as legacy alias.
    ark_model: str = os.getenv("ARK_MODEL", os.getenv("GLM_MODEL", "doubao-seed-evolving"))
    glm_model: str = os.getenv("GLM_MODEL", os.getenv("ARK_MODEL", "doubao-seed-evolving"))
    ark_max_output_tokens: int = int(os.getenv("ARK_MAX_OUTPUT_TOKENS", "4096"))

    # Legacy seed-audio create endpoint (optional fallback).
    doubao_audio_api_key: str = os.getenv("DOUBAO_AUDIO_API_KEY", "")
    doubao_audio_url: str = os.getenv(
        "DOUBAO_AUDIO_URL",
        "https://openspeech.bytedance.com/api/v3/tts/create",
    )
    doubao_audio_model: str = os.getenv("DOUBAO_AUDIO_MODEL", "seed-audio-1.0")

    # Console service 10007: App ID + Access Token HTTP TTS.
    # Docs: https://www.volcengine.com/docs/6561/79820
    doubao_tts_app_id: str = os.getenv("DOUBAO_TTS_APP_ID", "")
    doubao_tts_access_key: str = os.getenv("DOUBAO_TTS_ACCESS_KEY", "")
    doubao_tts_secret_key: str = os.getenv("DOUBAO_TTS_SECRET_KEY", "")
    doubao_tts_http_url: str = os.getenv(
        "DOUBAO_TTS_HTTP_URL",
        "https://openspeech.bytedance.com/api/v1/tts",
    )
    doubao_tts_v3_url: str = os.getenv(
        "DOUBAO_TTS_V3_URL",
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
    )
    doubao_tts_cluster: str = os.getenv("DOUBAO_TTS_CLUSTER", "volcano_tts")
    doubao_tts_default_speaker: str = os.getenv(
        "DOUBAO_TTS_DEFAULT_SPEAKER",
        "zh_female_shuangkuaisisi_uranus_bigtts",
    )
    doubao_tts_uid: str = os.getenv("DOUBAO_TTS_UID", "digital-human-agent")
    doubao_tts_sample_rate: int = int(os.getenv("DOUBAO_TTS_SAMPLE_RATE", "24000"))
    doubao_tts_encoding: str = os.getenv("DOUBAO_TTS_ENCODING", "mp3")
    # Prosody defaults. V1 uses ratios around 1.0.
    doubao_tts_speed_ratio: float = float(os.getenv("DOUBAO_TTS_SPEED_RATIO", "1.0"))
    doubao_tts_volume_ratio: float = float(os.getenv("DOUBAO_TTS_VOLUME_RATIO", "1.0"))
    doubao_tts_pitch_ratio: float = float(os.getenv("DOUBAO_TTS_PITCH_RATIO", "1.0"))

    # Optional async long-text V3 (App ID + Access Key). Kept for long scripts.
    doubao_tts_submit_url: str = os.getenv(
        "DOUBAO_TTS_SUBMIT_URL",
        "https://openspeech.bytedance.com/api/v3/tts/submit",
    )
    doubao_tts_query_url: str = os.getenv(
        "DOUBAO_TTS_QUERY_URL",
        "https://openspeech.bytedance.com/api/v3/tts/query",
    )
    doubao_tts_resource_id: str = os.getenv(
        "DOUBAO_TTS_RESOURCE_ID",
        "volc.service_type.10029",
    )
    doubao_tts_poll_interval_seconds: float = float(
        os.getenv("DOUBAO_TTS_POLL_INTERVAL_SECONDS", "3")
    )
    doubao_tts_timeout_seconds: int = int(os.getenv("DOUBAO_TTS_TIMEOUT_SECONDS", "300"))
    doubao_tts_max_chunk_bytes: int = int(os.getenv("DOUBAO_TTS_MAX_CHUNK_BYTES", "900"))
    doubao_tts_prefer_async_over_chars: int = int(
        os.getenv("DOUBAO_TTS_PREFER_ASYNC_OVER_CHARS", "600")
    )

    # Douyin spoken-script extraction via flash ASR (same AppID/Token as TTS).
    # Docs: https://www.volcengine.com/docs/6561/1631584
    doubao_asr_flash_url: str = os.getenv(
        "DOUBAO_ASR_FLASH_URL",
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash",
    )
    doubao_asr_resource_id: str = os.getenv(
        "DOUBAO_ASR_RESOURCE_ID",
        "volc.bigasr.auc_turbo",
    )
    doubao_asr_timeout_seconds: int = int(os.getenv("DOUBAO_ASR_TIMEOUT_SECONDS", "180"))
    doubao_asr_max_bytes: int = int(os.getenv("DOUBAO_ASR_MAX_BYTES", str(20 * 1024 * 1024)))
    # Douyin transcript: model (Ark input_video) | asr (flash) | auto (model then asr)
    douyin_transcript_provider: str = os.getenv("DOUYIN_TRANSCRIPT_PROVIDER", "model").strip().lower()
    douyin_keep_transcript_files: bool = _env_bool("DOUYIN_KEEP_TRANSCRIPT_FILES", "false")
    ark_files_url: str = os.getenv(
        "ARK_FILES_URL",
        "https://ark.cn-beijing.volces.com/api/v3/files",
    )
    enable_real_video: bool = _env_bool("ENABLE_REAL_VIDEO")
    video_provider: str = os.getenv("VIDEO_PROVIDER", "heygen").strip().lower()

    # HeyGen Image-to-Video（音频驱动口型）
    # https://developers.heygen.com/image-to-video
    # https://developers.heygen.com/docs/quick-start
    heygen_api_key: str = os.getenv("HEYGEN_API_KEY", "")
    heygen_api_base: str = os.getenv("HEYGEN_API_BASE", "https://api.heygen.com").rstrip("/")
    heygen_create_path: str = os.getenv("HEYGEN_CREATE_PATH", "/v3/videos")
    heygen_query_path: str = os.getenv("HEYGEN_QUERY_PATH", "/v3/videos/{video_id}")
    heygen_assets_path: str = os.getenv("HEYGEN_ASSETS_PATH", "/v3/assets")
    heygen_aspect_ratio: str = os.getenv("HEYGEN_ASPECT_RATIO", "auto").strip() or "auto"
    heygen_poll_interval_seconds: float = float(
        os.getenv("HEYGEN_POLL_INTERVAL_SECONDS", "8")
    )
    heygen_timeout_seconds: int = int(os.getenv("HEYGEN_TIMEOUT_SECONDS", "900"))

    # Volcengine Visual「单图音频驱动」（可选备选 VIDEO_PROVIDER=volc_cv）
    # https://docs.volcengine.com/docs/86081/1804513
    volc_access_key: str = os.getenv("VOLC_ACCESS_KEY", os.getenv("VOLC_ACCESSKEY", ""))
    volc_secret_key: str = os.getenv("VOLC_SECRET_KEY", os.getenv("VOLC_SECRETKEY", ""))
    # normal | loopy | loopyb
    volc_cv_mode: str = os.getenv("VOLC_CV_MODE", "normal").strip().lower()
    volc_cv_poll_interval_seconds: float = float(
        os.getenv("VOLC_CV_POLL_INTERVAL_SECONDS", "5")
    )
    volc_cv_timeout_seconds: int = int(os.getenv("VOLC_CV_TIMEOUT_SECONDS", "900"))

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")
    # When PUBLIC_BASE_URL is empty: auto-upload local files to a temp host
    # (litterbox/catbox/0x0) so Volc can fetch them. Use off to disable.
    public_file_host: str = os.getenv("PUBLIC_FILE_HOST", "auto").strip().lower()
    public_upload_timeout_seconds: int = int(os.getenv("PUBLIC_UPLOAD_TIMEOUT_SECONDS", "120"))
    output_dir: Path = ROOT_DIR / "output"


@lru_cache
def get_settings() -> Settings:
    return Settings()
