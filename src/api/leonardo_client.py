"""Leonardo AI 分镜图生成客户端（同步串行，避免并发限制）"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

LEONARDO_API_KEY: str = os.environ.get("LEONARDO_API_KEY", "b5ea37ca-3016-40fe-b0cd-f32b405be54e")
LEONARDO_BASE_URL: str = "https://cloud.leonardo.ai/api/rest/v1"
LEONARDO_MODEL_ID: str = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"  # Phoenix 1.0

_RETRY_TIMES: int = 3
_RETRY_DELAY: float = 5.0
_ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}
_MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB


def _headers() -> dict[str, str]:
    """返回 Leonardo API 请求头。

    Returns:
        HTTP 请求头字典
    """
    return {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json",
    }


def _request_with_retry(
    method: str,
    url: str,
    retries: int = _RETRY_TIMES,
    delay: float = _RETRY_DELAY,
    **kwargs,
) -> dict:
    """带重试的 HTTP 请求。

    Args:
        method: HTTP 方法（GET / POST）
        url: 请求 URL
        retries: 最大重试次数
        delay: 重试间隔秒数
        **kwargs: 透传给 requests

    Returns:
        响应 JSON 字典

    Raises:
        RuntimeError: 所有重试均失败
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, headers=_headers(), timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            logger.warning(f"[Leonardo] {method} 第 {attempt}/{retries} 次失败: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"[Leonardo] 请求全部失败: {last_err}")


def validate_image(image_path: str) -> None:
    """验证上传图片的格式和大小。

    Args:
        image_path: 图片文件路径

    Raises:
        ValueError: 格式不支持或文件过大
    """
    path = Path(image_path)
    if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的文件格式: {path.suffix}，仅支持 {_ALLOWED_EXTENSIONS}")
    if path.stat().st_size > _MAX_FILE_SIZE:
        raise ValueError(f"文件过大: {path.stat().st_size / 1024 / 1024:.1f}MB，上限 10MB")


def upload_image(image_path: str) -> str:
    """上传本地图片到 Leonardo，返回 image_id（用于 Image Guidance）。

    Args:
        image_path: 本地图片路径（JPG/PNG，≤10MB）

    Returns:
        Leonardo image_id

    Raises:
        ValueError: 文件格式或大小不合规
        RuntimeError: 上传失败
    """
    validate_image(image_path)
    ext = Path(image_path).suffix.lstrip(".")

    # Step 1: 获取上传凭证
    data = _request_with_retry("POST", f"{LEONARDO_BASE_URL}/init-image", json={"extension": ext})
    upload_info = data.get("uploadInitImage", {})
    upload_url: str = upload_info.get("url", "")
    fields_raw = upload_info.get("fields", "{}")
    image_id: str = upload_info.get("id", "")

    if not upload_url or not image_id:
        raise RuntimeError(f"[Leonardo] 上传初始化失败: {data}")

    fields: dict = json.loads(fields_raw) if isinstance(fields_raw, str) else fields_raw

    # Step 2: 上传到 S3
    with open(image_path, "rb") as f:
        s3_resp = requests.post(upload_url, data=fields, files={"file": f}, timeout=30)

    if s3_resp.status_code not in (200, 204):
        raise RuntimeError(f"[Leonardo] S3 上传失败: HTTP {s3_resp.status_code}")

    logger.info(f"[Leonardo] 图片上传成功: {image_id}")
    return image_id


def _poll_generation(gen_id: str, timeout: int = 180, interval: int = 3) -> str:
    """轮询直到图片生成完成，返回图片 URL。

    Args:
        gen_id: Leonardo 生成任务 ID
        timeout: 最长等待秒数
        interval: 轮询间隔秒数

    Returns:
        图片公开 URL

    Raises:
        RuntimeError: 超时
    """
    url = f"{LEONARDO_BASE_URL}/generations/{gen_id}"
    deadline = time.time() + timeout

    while time.time() < deadline:
        data = _request_with_retry("GET", url)
        images = data.get("generations_by_pk", {}).get("generated_images", [])
        if images:
            img_url: str = images[0]["url"]
            logger.info(f"[Leonardo] 生成完成: {img_url}")
            return img_url
        time.sleep(interval)

    raise RuntimeError(f"[Leonardo] 生成超时（{timeout}s）: {gen_id}")


def generate_image(
    prompt: str,
    negative_prompt: str = "blurry, low quality, watermark, text, logo, inconsistent style",
    width: int = 1024,
    height: int = 1024,
    init_image_id: Optional[str] = None,
    init_strength: float = 0.35,
) -> str:
    """生成单张分镜图（同步）。

    Args:
        prompt: 场景描述（英文）
        negative_prompt: 负向提示词
        width: 图片宽度
        height: 图片高度
        init_image_id: 参考图 ID（用于风格一致性）
        init_strength: 参考图影响强度（0~1）

    Returns:
        生成图片的公开 URL

    Raises:
        RuntimeError: 生成失败
    """
    body: dict = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "modelId": LEONARDO_MODEL_ID,
        "width": width,
        "height": height,
        "num_images": 1,
        "guidance_scale": 7,
        "num_inference_steps": 40,
        "alchemy": True,
        "presetStyle": "PHOTOGRAPHY",
        "contrastRatio": 0.5,
    }

    if init_image_id:
        body["controlnets"] = [{
            "initImageId": init_image_id,
            "initImageType": "UPLOADED",
            "preprocessorId": 67,
            "strengthType": "Mid",
        }]

    data = _request_with_retry("POST", f"{LEONARDO_BASE_URL}/generations", json=body)
    gen_id: str = data.get("sdGenerationJob", {}).get("generationId", "")
    if not gen_id:
        raise RuntimeError(f"[Leonardo] 提交失败: {data}")

    logger.info(f"[Leonardo] 任务已提交: {gen_id}")
    return _poll_generation(gen_id)


async def generate_storyboard_images(
    scenes: list[dict],
    product_image_path: Optional[str] = None,
) -> list[Optional[str]]:
    """串行生成 9 张分镜图（Leonardo 有并发限制，必须串行）。

    Args:
        scenes: 9 个场景描述列表，每个包含 'title' 和 'prompt' 字段
        product_image_path: 产品参考图路径（用于 Image Guidance 保持风格一致）

    Returns:
        9 张图片 URL 列表（失败的场景对应 None）
    """
    # 上传参考图
    init_image_id: Optional[str] = None
    if product_image_path:
        try:
            init_image_id = await asyncio.get_event_loop().run_in_executor(
                None, upload_image, product_image_path
            )
            logger.info(f"[Leonardo] 产品参考图已上传: {init_image_id}")
        except Exception as e:
            logger.warning(f"[Leonardo] 参考图上传失败，不使用 Image Guidance: {e}")

    urls: list[Optional[str]] = []
    for i, scene in enumerate(scenes):
        logger.info(f"[Leonardo] 生成分镜图 {i+1}/9: {scene['title']}")
        try:
            # 在线程池里跑同步函数，不阻塞事件循环
            url = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda s=scene, iid=init_image_id: generate_image(
                    prompt=s["prompt"],
                    init_image_id=iid,
                    init_strength=0.35,
                ),
            )
            urls.append(url)
            logger.info(f"[Leonardo] ✅ 分镜图 {i+1} 完成")
        except Exception as e:
            logger.error(f"[Leonardo] ❌ 分镜图 {i+1} 失败: {e}")
            urls.append(None)

    success = sum(1 for u in urls if u)
    logger.info(f"[Leonardo] 分镜图生成完成: {success}/9 成功")
    return urls
