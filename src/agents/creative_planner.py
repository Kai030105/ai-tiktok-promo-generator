"""创意策划师 + 视频导演：Claude 分析产品图，生成9个叙事连贯的场景。"""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

CLAUDE_MODEL: str = "claude-sonnet-4-6"
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    """获取 Anthropic 客户端（懒加载单例）。

    Returns:
        anthropic.Anthropic 实例

    Raises:
        RuntimeError: ANTHROPIC_API_KEY 未设置
    """
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 未设置")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _encode_image(image_path: str) -> tuple[str, str]:
    """将本地图片编码为 base64。

    Args:
        image_path: 图片文件路径

    Returns:
        (media_type, base64_data) 元组

    Raises:
        ValueError: 不支持的图片格式
    """
    ext = Path(image_path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_map.get(ext)
    if not media_type:
        raise ValueError(f"不支持的图片格式: {ext}")

    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return media_type, data


async def analyze_and_plan(
    product_image_path: str,
    product_name: str,
    promotion_info: str = "",
    template: str = "new_product",
) -> list[dict]:
    """分析产品图片，生成 9 个叙事连贯的分镜场景。

    Claude 扮演创意策划师 + 视频导演双重角色：
    1. 视觉分析产品特征和卖点
    2. 设计 9 个场景的叙事弧线（开场→高潮→行动号召）
    3. 为每个场景生成 Leonardo 提示词和 Kling 视频动作描述

    Args:
        product_image_path: 产品图片路径
        product_name: 产品名称（意大利语或中文均可）
        promotion_info: 促销信息（如 "限时8折"，可为空）
        template: 视频模板（new_product / flash_sale / holiday / luxury）

    Returns:
        9 个场景描述列表，每个包含：
        - id: 场景编号（1-9）
        - title: 场景标题
        - description: 场景描述（中文）
        - duration: 建议时长（秒）
        - prompt: Leonardo 图像生成提示词（英文）
        - video_prompt: Kling 视频动作提示词（英文）

    Raises:
        RuntimeError: Claude API 调用失败
        ValueError: 图片格式不支持
    """
    media_type, image_data = _encode_image(product_image_path)

    template_hints = {
        "new_product": "新品上市，强调新鲜感和产品亮点",
        "flash_sale": "限时折扣，制造紧迫感，突出价格优惠",
        "holiday": "节日促销，营造欢乐氛围，强调礼品属性",
        "luxury": "高端精品，强调品质、工艺和品牌价值",
    }
    hint = template_hints.get(template, template_hints["new_product"])

    system_prompt = (
        "你是一位专业的 TikTok 商业视频创意总监，擅长为意大利百货店设计爆款宣传视频。\n"
        "你需要同时扮演两个角色：\n"
        "1. 创意策划师：分析产品视觉特征，提炼核心卖点\n"
        "2. 视频导演：设计9个场景的完整叙事弧线\n\n"
        "重要原则：\n"
        "- 9个场景必须叙事连贯，像一个完整故事\n"
        "- Leonardo 提示词必须保持风格统一（同一色调、同一场景风格）\n"
        "- Kling 提示词描述具体的镜头运动（slow zoom, pan left, pull back 等）\n"
        "- 所有提示词用英文\n\n"
        "输出严格遵循 JSON 格式，不要有多余文字。"
    )

    promo_text = f"\n促销信息：{promotion_info}" if promotion_info else ""
    user_prompt = (
        f"产品名称：{product_name}{promo_text}\n"
        f"视频模板：{hint}\n\n"
        f"请分析上传的产品图片，设计一个完整的9镜头 TikTok 宣传视频分镜脚本。\n\n"
        f"返回格式（严格 JSON）：\n"
        f'{{"scenes": [\n'
        f'  {{"id": 1, "title": "开场吸引", "description": "场景描述", "duration": 3,\n'
        f'    "prompt": "Leonardo英文提示词，写实摄影风格，产品特写",\n'
        f'    "video_prompt": "Kling英文动作描述，如slow zoom in on product"}},\n'
        f'  ... (共9个场景)\n'
        f']}}'
    )

    def _call_claude() -> list[dict]:
        client = _get_client()
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.7,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }],
        )
        raw = message.content[0].text.strip()
        # 去掉可能的 markdown 代码块
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        scenes: list[dict] = result.get("scenes", [])
        if len(scenes) != 9:
            raise RuntimeError(f"[Creative] Claude 返回场景数量错误: {len(scenes)}，期望 9")
        logger.info(f"[Creative] ✅ 场景规划完成，共 {len(scenes)} 个场景")
        return scenes

    try:
        scenes = await asyncio.get_event_loop().run_in_executor(None, _call_claude)
        return scenes
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[Creative] Claude 返回格式无法解析: {e}")
    except Exception as e:
        raise RuntimeError(f"[Creative] Claude API 调用失败: {e}")
