from __future__ import annotations

from typing import Iterable

from .schemas import Platform, PublishResult
from .utils.logger import get_logger


logger = get_logger(__name__)


def auto_publish(
    video_path: str,
    title: str,
    description: str = "",
    platforms: Iterable[Platform] = ("douyin", "xiaohongshu"),
) -> list[PublishResult]:
    """
    自动发布视频到指定平台。

    当前为 Playwright/social-auto-upload 接入占位：后续接入账号 Cookie、平台差异化标题、
    上传按钮定位和发布确认后，将 status 改为 success/failed。
    """
    results: list[PublishResult] = []
    for platform in platforms:
        logger.info("Publish skipped platform=%s video=%s", platform, video_path)
        results.append(
            PublishResult(
                platform=platform,
                status="skipped",
                message="自动发布模块待接入 Playwright/social-auto-upload。",
            )
        )
    return results
