"""Kling AI 图生视频客户端（JWT 认证，异步）"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

import aiohttp
import jwt

logger = logging.getLogger(__name__)

KLING_ACCESS_KEY: str = os.environ.get("KLING_ACCESS_KEY", "AkhHCmpn4CFFRmtdD8BtKFCpp9GEyTRn")
KLING_SECRET_KEY: str = os.environ.get("KLING_SECRET_KEY", "8FgeKAJYGag3yR48mF3DhJN9ygmn8T9Q")
KLING_BASE_URL: str = "https://api.klingai.com"

_RETRY_TIMES: int = 3
_RETRY_DELAY: float = 5.0


def _make_token() -> str:
    """生成 Kling JWT token，有效期 30 分钟。

    Returns:
        签名后的 JWT 字符串
    """
    now = int(time.time())
    payload = {
        "iss": KLING_ACCESS_KEY,
        "exp": now + 1800,
        "nbf": now - 5,
    }
    return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256")


def _headers() -> dict[str, str]:
    """返回带有最新 JWT token 的请求头。

    Returns:
        HTTP 请求头字典
    """
    return {
        "Authorization": f"Bearer {_make_token()}",
        "Content-Type": "application/json",
    }


async def _post_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    body: dict,
    retries: int = _RETRY_TIMES,
    delay: float = _RETRY_DELAY,
) -> dict:
    """带重试的 POST 请求。

    Args:
        session: aiohttp 会话
        url: 请求 URL
        body: 请求体
        retries: 最大重试次数
        delay: 重试间隔秒数

    Returns:
        响应 JSON 字典

    Raises:
        RuntimeError: 所有重试均失败
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            async with session.post(url, json=body, headers=_headers(), timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data
                raise RuntimeError(f"Kling API 错误: {data.get('message')} | {data}")
        except Exception as e:
            last_err = e
            logger.warning(f"[Kling] POST 第 {attempt}/{retries} 次失败: {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
    raise RuntimeError(f"[Kling] POST 全部失败: {last_err}")


async def _get_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    retries: int = _RETRY_TIMES,
    delay: float = _RETRY_DELAY,
) -> dict:
    """带重试的 GET 请求。

    Args:
        session: aiohttp 会话
        url: 请求 URL
        retries: 最大重试次数
        delay: 重试间隔秒数

    Returns:
        响应 JSON 字典

    Raises:
        RuntimeError: 所有重试均失败
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data
                raise RuntimeError(f"Kling 查询错误: {data.get('message')}")
        except Exception as e:
            last_err = e
            logger.warning(f"[Kling] GET 第 {attempt}/{retries} 次失败: {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
    raise RuntimeError(f"[Kling] GET 全部失败: {last_err}")


async def _submit_task(
    session: aiohttp.ClientSession,
    image_url: str,
    prompt: str,
    duration: int,
    aspect_ratio: str,
    model: str,
) -> str:
    """提交图生视频任务，返回 task_id。

    Args:
        session: aiohttp 会话
        image_url: 分镜图公开 URL
        prompt: 视频动作描述（英文）
        duration: 时长（5 或 10 秒）
        aspect_ratio: 宽高比（TikTok 用 9:16）
        model: Kling 模型版本

    Returns:
        task_id 字符串

    Raises:
        RuntimeError: 提交失败
    """
    url = f"{KLING_BASE_URL}/v1/videos/image2video"
    body = {
        "model_name": model,
        "image": image_url,
        "prompt": prompt,
        "duration": str(duration),
        "aspect_ratio": aspect_ratio,
        "cfg_scale": 0.5,
    }
    data = await _post_with_retry(session, url, body)
    task_id: str = data["data"]["task_id"]
    logger.info(f"[Kling] 任务已提交: {task_id}")
    return task_id


async def _poll_task(
    session: aiohttp.ClientSession,
    task_id: str,
    timeout: int = 600,
    interval: int = 10,
) -> str:
    """轮询任务直到完成，返回视频 URL。

    Args:
        session: aiohttp 会话
        task_id: Kling 任务 ID
        timeout: 最长等待秒数
        interval: 轮询间隔秒数

    Returns:
        视频下载 URL

    Raises:
        RuntimeError: 超时或任务失败
    """
    url = f"{KLING_BASE_URL}/v1/videos/image2video/{task_id}"
    deadline = time.time() + timeout

    while time.time() < deadline:
        data = await _get_with_retry(session, url)
        status: str = data["data"]["task_status"]
        logger.info(f"[Kling] 任务 {task_id}: {status}")

        if status == "succeed":
            videos = data["data"].get("task_result", {}).get("videos", [])
            if videos:
                return videos[0]["url"]
            raise RuntimeError(f"[Kling] 任务成功但无视频 URL: {task_id}")

        if status == "failed":
            msg = data["data"].get("task_status_msg", "未知原因")
            raise RuntimeError(f"[Kling] 任务失败: {msg}")

        await asyncio.sleep(interval)

    raise RuntimeError(f"[Kling] 任务超时（{timeout}s）: {task_id}")


async def generate_video_async(
    image_url: str,
    prompt: str,
    duration: int = 5,
    aspect_ratio: str = "9:16",
    model: str = "kling-v1-6",
) -> str:
    """异步生成单段视频（提交 + 轮询）。

    Args:
        image_url: 分镜图公开 URL
        prompt: 视频动作描述（英文）
        duration: 视频时长秒数（5 或 10）
        aspect_ratio: 宽高比
        model: Kling 模型版本

    Returns:
        视频下载 URL

    Raises:
        RuntimeError: 生成失败
    """
    async with aiohttp.ClientSession() as session:
        task_id = await _submit_task(session, image_url, prompt, duration, aspect_ratio, model)
        return await _poll_task(session, task_id)


async def generate_videos_parallel(
    scenes: list[dict],
    duration: int = 5,
) -> list[Optional[str]]:
    """并行生成多段视频（9 个场景同时提交，异步轮询）。

    Args:
        scenes: 场景列表，每个包含 'image_url' 和 'video_prompt' 字段
        duration: 每段视频时长秒数

    Returns:
        视频 URL 列表（失败的场景对应 None）
    """
    async def _safe_generate(scene: dict) -> Optional[str]:
        try:
            return await generate_video_async(
                image_url=scene["image_url"],
                prompt=scene["video_prompt"],
                duration=duration,
            )
        except Exception as e:
            logger.error(f"[Kling] 场景 {scene.get('id')} 视频生成失败: {e}")
            return None

    tasks = [_safe_generate(scene) for scene in scenes]
    results = await asyncio.gather(*tasks)
    logger.info(f"[Kling] 并行生成完成，成功 {sum(1 for r in results if r)} / {len(results)}")
    return list(results)
