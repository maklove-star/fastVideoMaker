# -*- coding: utf-8 -*-
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import get_settings

get_settings.cache_clear()

from backend.audio_generator import doubao_tts_create

text = "大家好，欢迎收听本期短视频口播内容。人工智能正在改变内容创作方式。"
result = doubao_tts_create(
    text,
    voice_id="zh_female_shuangkuaisisi_moon_bigtts",
    speed_ratio=1.1,
    volume_ratio=1.0,
    pitch_ratio=1.0,
)
size = Path(result.audio_path).stat().st_size
print("OK")
print("path=", result.audio_path)
print("url=", result.audio_url)
print("bytes=", size)
print("request_id=", result.request_id)
