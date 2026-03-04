# AI驱动TikTok宣传视频生成器

> 让AI帮你自动制作专业的TikTok宣传视频

---

## 📋 项目概述

### 项目名称
**AI TikTok Promo Video Generator**

### 项目目标
为意大利连锁百货店打造一个**完全自动化**的宣传视频生成系统，用户只需上传产品图片，AI自动完成：
- 分镜设计
- 场景描述生成
- 分镜图生成
- 视频合成
- 特效添加

### 核心价值

| 传统方式 | 我们的系统 |
|----------|------------|
| 需要设计师 | ❌ 不需要 |
| 需要视频剪辑师 | ❌ 不需要 |
| 需要写脚本 | ❌ AI自动生成 |
| 需要几天时间 | ✅ 几分钟完成 |
| 高成本 | ✅ 几乎零成本 |

---

## 🎬 工作流程

### 完整流程图

```
用户上传产品图片
    ↓
[1] AI分析图片
    → 子agent：创意策划师
    → 输出：产品特征、卖点、目标受众
    ↓
[2] 生成分镜脚本
    → 子agent：视频导演
    → 输出：9个场景的文字描述
    ↓
[3] 生成分镜图
    → 调用 Leonardo AI API
    → 输出：9张分镜图片
    ↓
[4] 生成详细提示词
    → 子agent：视频剪辑师
    → 输出：每个场景的镜头运动、文字、特效
    ↓
[5] 合成最终视频
    → 后端：MoviePy + FFmpeg
    → 输出：TikTok宣传视频（1080x1920）
```

### 9宫格分镜设计

```
┌─────────┬─────────┬─────────┐
│ 场景1   │ 场景2   │ 场景3   │
│ 开场吸引 │ 产品展示 │ 核心卖点 │
├─────────┼─────────┼─────────┤
│ 场景4   │ 场景5   │ 场景6   │
│ 价格优惠 │ 使用场景 │ 用户评价 │
├─────────┼─────────┼─────────┤
│ 场景7   │ 场景8   │ 场景9   │
│ 品牌展示 │ 行动号召 │ 结尾强化 │
└─────────┴─────────┴─────────┘
```

---

## 🏗️ 技术架构

### 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **前端** | Gradio | Web界面 |
| **后端** | Python + FastAPI | API服务 |
| **AI推理** | Claude Sonnet | 子agent协调 |
| **图像生成** | Leonardo AI | 分镜图生成 |
| **视频处理** | MoviePy + FFmpeg | 视频合成 |
| **存储** | 本地文件系统 | 临时文件管理 |

### 核心模块

```
src/
├── agents/              # 子agent模块
│   ├── creative_planner.py    # 创意策划师
│   ├── video_director.py      # 视频导演
│   └── video_editor.py        # 视频剪辑师
├── api/                 # API模块
│   ├── leonardo_client.py     # Leonardo AI客户端
│   └── video_api.py           # 视频生成API
├── core/                # 核心功能
│   ├── storyboard_generator.py  # 分镜生成器
│   ├── video_composer.py        # 视频合成器
│   └── prompt_builder.py        # 提示词构建器
├── utils/               # 工具函数
│   ├── image_processor.py
│   └── file_manager.py
└── app.py               # 主应用
```

---

## 📚 项目文档结构

```
.
├── README.md                    # 项目说明（本文件）
├── .cursor/
│   ├── project_rules.md         # 项目规则
│   └── behavior_guidelines.md   # 行为规范
├── docs/
│   ├── API.md                   # API文档
│   ├── WORKFLOW.md              # 工作流程详细说明
│   └── EXAMPLES.md              # 使用示例
├── src/                         # 源代码
├── tests/                       # 测试文件
├── assets/                      # 资源文件
│   ├── templates/               # 视频模板
│   ├── music/                   # 背景音乐
│   └── fonts/                   # 字体文件
└── output/                      # 输出目录
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 FFmpeg
apt-get install ffmpeg

# 配置API密钥
export LEONARDO_API_KEY="your_api_key"
```

### 2. 启动服务

```bash
python src/app.py
```

### 3. 使用界面

打开浏览器访问 `http://localhost:7860`

---

## 📊 功能特性

### ✅ 已实现

- [x] 项目架构设计
- [x] 文档结构规划
- [x] 工作流程定义

### 🔄 进行中

- [ ] Leonardo AI 集成
- [ ] 子agent系统
- [ ] 视频合成引擎

### 📅 计划中

- [ ] Web界面
- [ ] 模板系统
- [ ] 批量处理

---

## 🎯 里程碑

### 阶段1：基础架构（当前）
- ✅ 项目规划
- ⏳ 核心模块开发
- ⏳ API集成

### 阶段2：核心功能
- ⏸️ 分镜生成
- ⏸️ 视频合成
- ⏸️ 子agent协调

### 阶段3：用户体验
- ⏸️ Web界面
- ⏸️ 模板系统
- ⏸️ 优化性能

### 阶段4：扩展功能
- ⏸️ 批量处理
- ⏸️ 自定义模板
- ⏸️ 数据分析

---

## 🤝 贡献指南

### 代码规范
- Python 3.10+
- PEP 8 代码风格
- 类型注解
- 完善的错误处理

### 提交规范
```
feat: 添加新功能
fix: 修复bug
docs: 文档更新
refactor: 代码重构
test: 测试相关
```

---

## 📄 许可证

MIT License

---

## 📞 联系方式

- 项目维护者：慧慧（AI助手）
- 用户：意大利连锁百货店
- 平台：TikTok

---

**最后更新**：2026-03-04 22:00 UTC
