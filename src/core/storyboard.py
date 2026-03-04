"""漫画风格九宫格分镜图生成器"""

import asyncio
import logging
import os
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiohttp
import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# 九宫格布局参数
_CELL_SIZE: int = 512       # 每格图片尺寸（像素）
_BORDER: int = 8            # 格子间距（黑色）
_OUTER: int = 20            # 外边框宽度
_LABEL_H: int = 48          # 场景标签高度
_BG_COLOR: tuple = (0, 0, 0)       # 边框颜色（黑）
_LABEL_BG: tuple = (20, 20, 20)    # 标签背景色
_LABEL_FG: tuple = (255, 255, 255) # 标签文字色
_GRID_COLS: int = 3
_GRID_ROWS: int = 3


def _download_image(url: str) -> Optional[Image.Image]:
    """下载图片 URL 并返回 PIL Image。

    Args:
        url: 图片公开 URL

    Returns:
        PIL Image 对象，下载失败返回 None
    """
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"[Storyboard] 图片下载失败: {url[:60]}... | {e}")
        return None


def _make_placeholder(scene_id: int, title: str) -> Image.Image:
    """为下载失败的场景生成占位图。

    Args:
        scene_id: 场景编号
        title: 场景标题

    Returns:
        灰色占位 PIL Image
    """
    img = Image.new("RGB", (_CELL_SIZE, _CELL_SIZE), color=(60, 60, 60))
    draw = ImageDraw.Draw(img)
    text = f"场景{scene_id}\n{title}"
    draw.multiline_text(
        (_CELL_SIZE // 2, _CELL_SIZE // 2),
        text,
        fill=(180, 180, 180),
        anchor="mm",
        align="center",
    )
    return img


def _add_scene_label(img: Image.Image, scene_id: int, title: str) -> Image.Image:
    """在图片底部添加场景编号和标题标签（漫画风格）。

    Args:
        img: 原始 PIL Image
        scene_id: 场景编号
        title: 场景标题

    Returns:
        添加标签后的 PIL Image
    """
    labeled = Image.new("RGB", (_CELL_SIZE, _CELL_SIZE + _LABEL_H), color=_BG_COLOR)
    labeled.paste(img.resize((_CELL_SIZE, _CELL_SIZE)), (0, 0))

    draw = ImageDraw.Draw(labeled)
    # 标签背景
    draw.rectangle([0, _CELL_SIZE, _CELL_SIZE, _CELL_SIZE + _LABEL_H], fill=_LABEL_BG)
    # 编号 badge
    draw.rectangle([0, _CELL_SIZE, 36, _CELL_SIZE + _LABEL_H], fill=(220, 50, 50))
    draw.text((18, _CELL_SIZE + _LABEL_H // 2), str(scene_id), fill=(255, 255, 255), anchor="mm")
    # 标题（截断过长文字）
    short_title = title[:12] + "…" if len(title) > 12 else title
    draw.text((44, _CELL_SIZE + _LABEL_H // 2), short_title, fill=_LABEL_FG, anchor="lm")

    return labeled


def compose_storyboard_grid(
    image_urls: list[Optional[str]],
    scenes: list[dict],
    output_path: str,
) -> str:
    """将 9 张分镜图拼成漫画风格九宫格。

    每个格子底部有场景编号和标题标签（红色编号 badge + 黑底白字标题），
    格子之间有黑色边框，整体像一页漫画分镜。

    Args:
        image_urls: 9 张图片 URL 列表（None 表示使用占位图）
        scenes: 9 个场景描述（含 id 和 title）
        output_path: 输出文件路径（.jpg 或 .png）

    Returns:
        实际输出文件路径

    Raises:
        ValueError: 图片数量不足 9 张
        RuntimeError: 合成失败
    """
    if len(image_urls) < 9:
        raise ValueError(f"需要 9 张分镜图，实际收到 {len(image_urls)} 张")

    cell_h = _CELL_SIZE + _LABEL_H

    # 计算画布总尺寸
    canvas_w = _OUTER * 2 + _GRID_COLS * _CELL_SIZE + (_GRID_COLS - 1) * _BORDER
    canvas_h = _OUTER * 2 + _GRID_ROWS * cell_h + (_GRID_ROWS - 1) * _BORDER
    canvas = Image.new("RGB", (canvas_w, canvas_h), color=_BG_COLOR)

    for idx in range(9):
        url = image_urls[idx]
        scene = scenes[idx] if idx < len(scenes) else {"id": idx + 1, "title": f"场景{idx+1}"}

        # 下载或生成占位图
        if url:
            img = _download_image(url)
            if img is None:
                img = _make_placeholder(scene["id"], scene["title"])
        else:
            img = _make_placeholder(scene["id"], scene["title"])

        # 加标签
        cell = _add_scene_label(img, scene["id"], scene.get("title", ""))

        # 计算在画布上的位置
        col = idx % _GRID_COLS
        row = idx // _GRID_COLS
        x = _OUTER + col * (_CELL_SIZE + _BORDER)
        y = _OUTER + row * (cell_h + _BORDER)

        canvas.paste(cell, (x, y))
        logger.debug(f"[Storyboard] 拼入场景 {idx+1} 在 ({x}, {y})")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path, quality=95)
    logger.info(f"[Storyboard] ✅ 九宫格保存至: {output_path}（{canvas_w}x{canvas_h}）")
    return output_path


async def compose_storyboard_async(
    image_urls: list[Optional[str]],
    scenes: list[dict],
    output_path: str,
) -> str:
    """异步版九宫格合成（在线程池中运行，不阻塞事件循环）。

    Args:
        image_urls: 9 张图片 URL 列表
        scenes: 9 个场景描述
        output_path: 输出文件路径

    Returns:
        实际输出文件路径
    """
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: compose_storyboard_grid(image_urls, scenes, output_path),
    )
