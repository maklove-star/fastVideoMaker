from __future__ import annotations

import json
import re
from typing import Literal

import requests
from bs4 import BeautifulSoup

from .config import get_settings
from .douyin_transcript import extract_douyin_spoken_script
from .utils.logger import get_logger


logger = get_logger(__name__)
ScriptMode = Literal["generate", "polish", "direct"]


SYSTEM_PROMPT = """你是短视频口播文案专家。请输出适合数字人口播的中文短视频文案，时长约 60 秒，控制在 200-300 字。
要求：
1. 口语化、节奏清晰、有感染力；
2. 开头 3 秒给出明确钩子；
3. 中段给出信息增量或观点；
4. 结尾自然收束，可带轻度行动引导；
5. 不要输出标题、分镜、编号、Markdown，只输出可直接朗读的正文。"""


URL_PATTERN = re.compile(r"https?://[^\s，。！？；、<>'\"）)】》]+", re.IGNORECASE)
DOUYIN_HOST_PATTERN = re.compile(
    r"(?:^|\.)(?:douyin\.com|iesdouyin\.com)\b",
    re.IGNORECASE,
)
DOUYIN_SHARE_TAIL_PATTERN = re.compile(
    r"(复制此链接[，,]\s*打开(?:Dou音|抖音)搜索[，,]\s*直接观看视频[！!。.]*)",
    re.IGNORECASE,
)
# Examples:
#   3.58 07/20 :6pm h@O.xF Fhb:/
DOUYIN_SHARE_PREFIX_PATTERN = re.compile(
    r"^\s*"
    r"(?:[\d.]+\s+)?"
    r"(?:\d{1,2}/\d{1,2}\s+)?"
    r"(?::\s*\d{1,2}\s*(?:am|pm)\s+)?"
    r"(?:[A-Za-z0-9@._\-/:]+\s*)*",
    re.IGNORECASE,
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip("，。！？；、,.!?;:'\"<>)]}）】》")


def is_douyin_url(url: str) -> bool:
    try:
        host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/", 1)[0]
    except Exception:  # noqa: BLE001
        return False
    return bool(DOUYIN_HOST_PATTERN.search(host))


def _decode_js_string(raw: str) -> str:
    return json.loads(f'"{raw}"')


def clean_share_text(text: str, url: str | None = None) -> str:
    """Strip Douyin share boilerplate; keep the caption itself unchanged."""
    cleaned = text.strip()
    if url:
        cleaned = cleaned.replace(url, " ")
    # Also drop any leftover short links in the text.
    cleaned = URL_PATTERN.sub(" ", cleaned)
    cleaned = DOUYIN_SHARE_TAIL_PATTERN.sub(" ", cleaned)
    cleaned = DOUYIN_SHARE_PREFIX_PATTERN.sub("", cleaned, count=1)
    cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
    return cleaned.strip(" \t\r\n")


def extract_web_text(url: str, timeout: int = 15) -> str:
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding

    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()

    candidates = soup.find_all(["article", "main"])
    text_source = candidates[0] if candidates else soup.body or soup
    lines = [line.strip() for line in text_source.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if len(line) >= 8)
    return text[:6000]


def extract_douyin_desc(url: str, timeout: int = 20) -> str:
    """Fetch Douyin share/video page and return the original video desc verbatim."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    html = response.text

    for key in ("desc", "share_desc", "caption", "title", "content"):
        match = re.search(rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"', html)
        if not match:
            continue
        try:
            value = _decode_js_string(match.group(1)).strip()
        except Exception:  # noqa: BLE001
            value = match.group(1).encode("utf-8").decode("unicode_escape").strip()
        # Skip generic boilerplate snippets.
        if not value or value in {"抖音", "Dou音", "请打开抖音"}:
            continue
        if "投资有风险" in value and len(value) < 40:
            continue
        logger.info("Extracted Douyin field=%s chars=%s", key, len(value))
        return value

    raise RuntimeError("已打开抖音链接，但未找到视频文案（desc）。")


def resolve_input_text(user_input: str, extract_url: bool = False) -> str:
    raw_text = user_input.strip()
    if not raw_text:
        return ""
    if not extract_url:
        return raw_text

    url = extract_first_url(raw_text)
    if not url:
        raise ValueError("未从输入内容中识别到 http/https 链接，请粘贴完整链接或分享口令。")

    fallback_text = clean_share_text(raw_text, url)

    # Douyin: download video audio and ASR the spoken script (口播全文).
    if is_douyin_url(url):
        settings = get_settings()
        try:
            script = extract_douyin_spoken_script(
                url,
                keep_files=settings.douyin_keep_transcript_files,
            )
            if script:
                return script
        except Exception as error:  # noqa: BLE001
            logger.exception("Douyin spoken-script extraction failed url=%s", url)
            raise RuntimeError(
                f"抖音口播文案提取失败：{error}"
            ) from error

    try:
        web_text = extract_web_text(url)
    except requests.RequestException as error:
        logger.warning("Failed to extract web text url=%s error=%s", url, error)
        web_text = ""

    # Prefer a single clean source so the result stays verbatim.
    if fallback_text and (not web_text or len(fallback_text) >= len(web_text)):
        return fallback_text
    if web_text:
        return web_text
    if fallback_text:
        return fallback_text

    raise RuntimeError("已识别链接，但未能提取网页正文；如果是短视频平台链接，请同时粘贴分享标题或视频简介。")


def _extract_response_text(data: dict) -> str:
    """Parse text from Ark/OpenAI-style Responses API payload."""
    output = data.get("output") or []
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {None, "message"} and item.get("role") != "assistant":
            # Prefer assistant message blocks; skip reasoning-only items.
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
            part_type = part.get("type")
            if part_type in {"output_text", "text", "input_text"}:
                text = part.get("text") or ""
                if text.strip():
                    texts.append(text.strip())
            elif isinstance(part.get("text"), str) and part["text"].strip():
                texts.append(part["text"].strip())

    if texts:
        return "\n".join(texts).strip()

    # Fallback shapes used by some adapters.
    for key in ("output_text", "text", "content"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def call_doubao(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    if not settings.ark_api_key:
        raise RuntimeError("缺少 ARK_API_KEY，请在 .env 中配置火山方舟 API Key。")

    model = settings.ark_model or settings.glm_model
    input_items: list[dict] = []
    for message in messages:
        role = message.get("role") or "user"
        text = (message.get("content") or "").strip()
        if not text:
            continue
        # Responses API uses system/user/assistant + input_text parts.
        mapped_role = "system" if role == "system" else role
        input_items.append(
            {
                "role": mapped_role,
                "content": [{"type": "input_text", "text": text}],
            }
        )

    if not input_items:
        raise ValueError("文案模型请求内容为空。")

    payload = {
        "model": model,
        "input": input_items,
        "max_output_tokens": settings.ark_max_output_tokens,
    }
    response = requests.post(
        settings.ark_api_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.ark_api_key}",
        },
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    content = _extract_response_text(data)
    if not content:
        status = data.get("status")
        incomplete = data.get("incomplete_details") or {}
        if status == "incomplete":
            raise RuntimeError(
                "豆包输出被截断（思考占用过多 token）。"
                f"请增大 ARK_MAX_OUTPUT_TOKENS（当前 {settings.ark_max_output_tokens}），"
                f"原因：{incomplete.get('reason') or status}。"
            )
        raise RuntimeError(f"豆包未返回文案内容：{data}")
    return content


# Backward-compatible alias.
def call_glm(messages: list[dict[str, str]]) -> str:
    return call_doubao(messages)


def process_script(user_input: str, mode: ScriptMode = "generate", extract_url: bool = False) -> str:
    """
    user_input: 用户输入的内容、链接或关键词
    mode: "generate"、"polish" 或 "direct"
    extract_url: 是否提取链接正文；为 True 时始终返回提取结果，不做 LLM 改写
    return: 处理后的文案文本
    """
    source_text = resolve_input_text(user_input, extract_url=extract_url)
    if not source_text:
        raise ValueError("文案输入不能为空。")

    # Link extraction must stay verbatim — never rewrite with the LLM.
    if extract_url or mode == "direct":
        return source_text

    if mode == "generate":
        user_prompt = f"请围绕这个主题生成一段口播文案：{source_text}"
    elif mode == "polish":
        user_prompt = f"请将下面内容润色为更适合短视频数字人口播的文案：\n{source_text}"
    else:
        raise ValueError(f"不支持的文案处理模式：{mode}")

    logger.info("Calling Doubao Responses model for script mode=%s", mode)
    return call_doubao(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
