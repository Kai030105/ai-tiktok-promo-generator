"""TikTok 宣传视频生成器 — Gradio 主应用"""

import asyncio
import logging
import os
import time
from pathlib import Path

import gradio as gr

from agents.creative_planner import analyze_and_plan
from api.leonardo_client import generate_storyboard_images
from api.kling_client import generate_videos_parallel
from core.storyboard import compose_storyboard_async
from core.video_composer import compose_final_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

TEMPLATES = {
    "🆕 新品上市": "new_product",
    "⚡ 限时折扣": "flash_sale",
    "🎉 节日促销": "holiday",
    "💎 高端精品": "luxury",
}


async def _run_pipeline(
    product_image_path: str,
    product_name: str,
    promotion_info: str,
    template_label: str,
    video_duration: int,
    progress: gr.Progress,
) -> tuple[str, str, str]:
    """完整生成流水线（异步）。

    Args:
        product_image_path: 产品图本地路径
        product_name: 产品名称
        promotion_info: 促销信息
        template_label: 模板显示名称
        video_duration: 每段视频时长（秒）
        progress: Gradio 进度条

    Returns:
        (storyboard_path, video_path, status_msg) 三元组
    """
    template = TEMPLATES.get(template_label, "new_product")
    ts = int(time.time())

    try:
        # 阶段 1: Claude 分析 + 场景规划
        progress(0.05, desc="🧠 Claude 分析产品中…")
        logger.info("[Pipeline] 阶段1: 创意分析")
        scenes = await analyze_and_plan(
            product_image_path=product_image_path,
            product_name=product_name,
            promotion_info=promotion_info,
            template=template,
        )

        # 阶段 2: Leonardo 生成分镜图（串行）
        progress(0.15, desc="🎨 生成分镜图（共9张，约5分钟）…")
        logger.info("[Pipeline] 阶段2: 分镜图生成")
        image_urls = await generate_storyboard_images(
            scenes=scenes,
            product_image_path=product_image_path,
        )

        # 阶段 3: 拼九宫格
        progress(0.55, desc="🖼 合成九宫格分镜图…")
        logger.info("[Pipeline] 阶段3: 九宫格合成")
        storyboard_path = str(OUTPUT_DIR / f"storyboard_{ts}.jpg")
        await compose_storyboard_async(image_urls, scenes, storyboard_path)

        # 阶段 4: 为每个场景注入图片 URL，然后并行生成视频
        progress(0.60, desc="🎬 Kling 生成视频片段（并行，约3-5分钟）…")
        logger.info("[Pipeline] 阶段4: 视频生成")
        for i, (scene, url) in enumerate(zip(scenes, image_urls)):
            scene["image_url"] = url or ""
        scenes_with_imgs = [s for s in scenes if s.get("image_url")]

        video_urls = await generate_videos_parallel(
            scenes=scenes_with_imgs,
            duration=video_duration,
        )

        # 阶段 5: 下载 + 拼接视频
        progress(0.90, desc="✂️ 拼接最终视频…")
        logger.info("[Pipeline] 阶段5: 视频合成")
        final_video_path = str(OUTPUT_DIR / f"tiktok_{ts}.mp4")
        await compose_final_video(
            video_urls=video_urls,
            output_path=final_video_path,
            temp_dir=str(TEMP_DIR / str(ts)),
        )

        progress(1.0, desc="✅ 完成！")
        success_count = sum(1 for u in video_urls if u)
        status = (
            f"✅ 生成完成！\n"
            f"- 分镜图：{sum(1 for u in image_urls if u)}/9 成功\n"
            f"- 视频片段：{success_count}/{len(scenes_with_imgs)} 成功\n"
            f"- 最终视频：{Path(final_video_path).name}"
        )
        return storyboard_path, final_video_path, status

    except Exception as e:
        logger.exception(f"[Pipeline] 流水线失败: {e}")
        return "", "", f"❌ 生成失败：{e}"


def run_pipeline_sync(
    product_image,
    product_name: str,
    promotion_info: str,
    template_label: str,
    video_duration: int,
    progress: gr.Progress = gr.Progress(),
) -> tuple:
    """Gradio 同步入口，包装异步流水线。

    Args:
        product_image: Gradio 上传的图片文件
        product_name: 产品名称
        promotion_info: 促销信息
        template_label: 模板显示名称
        video_duration: 每段视频时长
        progress: Gradio 进度条对象

    Returns:
        (storyboard_image, video_file, status_text) 三元组
    """
    if product_image is None:
        return None, None, "⚠️ 请先上传产品图片"
    if not product_name.strip():
        return None, None, "⚠️ 请输入产品名称"

    image_path = product_image if isinstance(product_image, str) else product_image.name
    storyboard, video, status = asyncio.run(
        _run_pipeline(
            product_image_path=image_path,
            product_name=product_name.strip(),
            promotion_info=promotion_info.strip(),
            template_label=template_label,
            video_duration=video_duration,
            progress=progress,
        )
    )
    return (storyboard or None), (video or None), status


def build_ui() -> gr.Blocks:
    """构建 Gradio 界面。

    Returns:
        gr.Blocks 实例
    """
    with gr.Blocks(title="🎬 TikTok 宣传视频生成器") as demo:
        gr.Markdown("# 🎬 TikTok 宣传视频生成器\n> 上传产品图 → AI 自动生成专业宣传视频")

        with gr.Row():
            with gr.Column(scale=1):
                product_image = gr.Image(
                    label="📸 产品图片",
                    type="filepath",
                    height=300,
                )
                product_name = gr.Textbox(
                    label="产品名称",
                    placeholder="如：意大利手工皮包 / Scarpe Nike",
                )
                promotion_info = gr.Textbox(
                    label="促销信息（可选）",
                    placeholder="如：限时8折 / Offerta Lampo -30%",
                )
                template = gr.Radio(
                    choices=list(TEMPLATES.keys()),
                    value="🆕 新品上市",
                    label="视频模板",
                )
                video_duration = gr.Slider(
                    minimum=5,
                    maximum=10,
                    step=5,
                    value=5,
                    label="每段视频时长（秒）",
                )
                generate_btn = gr.Button("🚀 一键生成", variant="primary", size="lg")

            with gr.Column(scale=2):
                status_box = gr.Textbox(label="状态", lines=4, interactive=False)
                storyboard_out = gr.Image(label="🖼 九宫格分镜图", height=600)
                video_out = gr.Video(label="🎥 最终视频")

        generate_btn.click(
            fn=run_pipeline_sync,
            inputs=[product_image, product_name, promotion_info, template, video_duration],
            outputs=[storyboard_out, video_out, status_box],
        )

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        theme=gr.themes.Soft(),
    )
