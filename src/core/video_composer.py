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
import requests
import numpy as np
from PIL import Image
from moviepy import VideoFileClip, concatenate_videoclips, ImageClip, CompositeVideoClip

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


def _download_image_to_array(url: str, width: int = 1080, height: int = 1920) -> Optional[np.ndarray]:
    """下载图片并调整为 TikTok 竖屏尺寸，返回 numpy 数组。"""
    try:
        from io import BytesIO
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        # 保持宽高比裁剪填充
        img_w, img_h = img.size
        scale = max(width / img_w, height / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        img = img.crop((left, top, left + width, top + height))
        return np.array(img)
    except Exception as e:
        logger.warning(f"[Composer] 图片下载失败 {url[:60]}: {e}")
        return None


def create_slideshow_from_images(
    image_urls: list[Optional[str]],
    output_path: str,
    duration_per_scene: float = 3.0,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """用 Leonardo 静态图片制作幻灯片兜底视频（Ken Burns 缩放效果）。

    当 Kling 全部失败时调用此函数，至少给用户一个可用的视频产出。

    Args:
        image_urls: 图片 URL 列表（None 跳过）
        output_path: 输出文件路径
        duration_per_scene: 每张图停留时长（秒）
        width: 视频宽度
        height: 视频高度

    Returns:
        输出文件路径

    Raises:
        RuntimeError: 无可用图片
    """
    valid_urls = [u for u in image_urls if u]
    if not valid_urls:
        raise RuntimeError("[Composer] 幻灯片兜底：无可用图片 URL")

    logger.info(f"[Composer] 幻灯片模式：处理 {len(valid_urls)} 张图片")
    clips = []
    for i, url in enumerate(valid_urls):
        arr = _download_image_to_array(url, width, height)
        if arr is None:
            continue
        # Ken Burns：轻微放大 + 慢慢缩回，制造动感
        zoom_start, zoom_end = 1.08, 1.0

        def make_frame(t, _arr=arr, _dur=duration_per_scene, _zs=zoom_start, _ze=zoom_end):
            progress = t / _dur
            zoom = _zs + (_ze - _zs) * progress
            h, w = _arr.shape[:2]
            new_w = int(w / zoom)
            new_h = int(h / zoom)
            x1 = (w - new_w) // 2
            y1 = (h - new_h) // 2
            cropped = _arr[y1:y1 + new_h, x1:x1 + new_w]
            return np.array(Image.fromarray(cropped).resize((w, h), Image.BILINEAR))

        clip = ImageClip(_arr, duration=duration_per_scene).with_make_frame(make_frame)
        clips.append(clip)
        logger.info(f"[Composer] 幻灯片 {i+1}/{len(valid_urls)} 准备完成")

    if not clips:
        raise RuntimeError("[Composer] 幻灯片兜底：所有图片下载失败")

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
    for clip in clips:
        try:
            clip.close()
        except Exception:
            pass
    logger.info(f"[Composer] ✅ 幻灯片视频保存至: {output_path}")
    return output_path


async def create_slideshow_async(
    image_urls: list[Optional[str]],
    output_path: str,
    duration_per_scene: float = 3.0,
) -> str:
    """异步版幻灯片合成（线程池中运行）。"""
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: create_slideshow_from_images(image_urls, output_path, duration_per_scene),
    )


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
