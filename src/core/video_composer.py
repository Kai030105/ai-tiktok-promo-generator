"""视频合成：下载 9 段 Kling 视频并拼接为完整 TikTok 视频"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import aiohttp
import aiofiles
from moviepy import VideoFileClip, concatenate_videoclips

logger = logging.getLogger(__name__)

VIDEO_FPS: int = 30
VIDEO_CODEC: str = "libx264"
VIDEO_BITRATE: str = "5000k"
AUDIO_CODEC: str = "aac"


async def _download_video(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: str,
) -> bool:
    """异步下载单段视频到本地文件。

    Args:
        session: aiohttp 会话
        url: 视频 URL
        dest_path: 本地保存路径

    Returns:
        下载成功返回 True，失败返回 False
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            resp.raise_for_status()
            async with aiofiles.open(dest_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 64):
                    await f.write(chunk)
        logger.info(f"[Composer] ✅ 视频下载完成: {Path(dest_path).name}")
        return True
    except Exception as e:
        logger.error(f"[Composer] ❌ 视频下载失败: {url[:60]}... | {e}")
        return False


async def download_all_videos(
    video_urls: list[Optional[str]],
    temp_dir: str,
) -> list[Optional[str]]:
    """并行下载所有视频片段。

    Args:
        video_urls: 视频 URL 列表（None 表示跳过）
        temp_dir: 临时文件目录

    Returns:
        本地文件路径列表（下载失败或 URL 为 None 的对应 None）
    """
    os.makedirs(temp_dir, exist_ok=True)

    async def _safe_download(idx: int, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        dest = os.path.join(temp_dir, f"scene_{idx+1:02d}.mp4")
        async with aiohttp.ClientSession() as session:
            success = await _download_video(session, url, dest)
        return dest if success else None

    tasks = [_safe_download(i, url) for i, url in enumerate(video_urls)]
    results = await asyncio.gather(*tasks)
    success_count = sum(1 for r in results if r)
    logger.info(f"[Composer] 视频下载完成: {success_count}/{len(video_urls)} 成功")
    return list(results)


def concat_videos(
    local_paths: list[Optional[str]],
    output_path: str,
) -> str:
    """将多段视频拼接为一个完整视频（同步，在线程池中调用）。

    跳过路径为 None 或文件不存在的片段。

    Args:
        local_paths: 本地视频文件路径列表
        output_path: 输出文件路径

    Returns:
        输出文件路径

    Raises:
        RuntimeError: 无有效视频片段或写入失败
    """
    valid_paths = [p for p in local_paths if p and os.path.exists(p)]
    if not valid_paths:
        raise RuntimeError("[Composer] 无有效视频片段可拼接")

    logger.info(f"[Composer] 开始拼接 {len(valid_paths)} 段视频...")
    clips = []
    try:
        for path in valid_paths:
            try:
                clip = VideoFileClip(path)
                clips.append(clip)
            except Exception as e:
                logger.warning(f"[Composer] 跳过损坏片段 {path}: {e}")

        if not clips:
            raise RuntimeError("[Composer] 所有视频片段均损坏")

        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        final.write_videofile(
            output_path,
            fps=VIDEO_FPS,
            codec=VIDEO_CODEC,
            bitrate=VIDEO_BITRATE,
            audio_codec=AUDIO_CODEC,
            logger=None,
        )
        logger.info(f"[Composer] ✅ 视频拼接完成: {output_path}")
        return output_path

    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass


async def compose_final_video(
    video_urls: list[Optional[str]],
    output_path: str,
    temp_dir: str,
) -> str:
    """完整视频合成流程：下载 → 拼接。

    Args:
        video_urls: 9 段视频的 URL 列表（None 表示跳过）
        output_path: 最终视频输出路径
        temp_dir: 临时文件目录

    Returns:
        最终视频路径

    Raises:
        RuntimeError: 合成失败
    """
    # 并行下载
    local_paths = await download_all_videos(video_urls, temp_dir)

    # 在线程池中拼接（moviepy 是同步的）
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: concat_videos(local_paths, output_path),
    )

    # 清理临时文件
    for path in local_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    return result
