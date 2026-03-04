"""项目配置"""

# Leonardo AI
LEONARDO_API_KEY = "b5ea37ca-3016-40fe-b0cd-f32b405be54e"
LEONARDO_BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
LEONARDO_MODEL_ID = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"  # Phoenix 1.0

# Kling AI
KLING_ACCESS_KEY = "AkhHCmpn4CFFRmtdD8BtKFCpp9GEyTRn"
KLING_SECRET_KEY = "8FgeKAJYGag3yR48mF3DhJN9ygmn8T9Q"
KLING_BASE_URL = "https://api.klingai.com"

# Claude (Anthropic)
ANTHROPIC_API_KEY = ""  # 从环境变量读取，OpenClaw 已注入
CLAUDE_MODEL = "claude-sonnet-4-6"

# 视频规格
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# 分镜图规格
STORYBOARD_WIDTH = 1024
STORYBOARD_HEIGHT = 1024

# 九宫格拼图参数
GRID_COLS = 3
GRID_ROWS = 3
GRID_BORDER = 8       # 格子间距（黑色）
GRID_OUTER = 16       # 外边框宽度
GRID_BG_COLOR = (0, 0, 0)  # 黑色边框

# 输出目录
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
