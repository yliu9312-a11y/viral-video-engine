# VST — ViralStructTransfer

> 短视频结构迁移引擎 · 剪映/字节跳动 AI 全栈挑战赛

输入一段爆款短视频，自动拆解结构模板，识别素材缺口，智能补全策略，输出多个变体成片。支持风格迁移：输入参考视频 + 新主题 → 提取视觉风格 → 生成匹配视觉语言的新视频。

---

## 架构

```
浏览器 :5173
   │
   ▼
┌─────────────────────────────────────┐
│  nginx (web)                        │
│  ├─ 静态前端 (React + Vite)         │
│  └─ /api/* 反代 ──────────────────┐ │
└───────────────────────────────────┼─┘
                                    ▼
┌─────────────────────────────────────────────┐
│  Node Express (:3000)                       │
│  ├─ 流水线编排 (upload → extract → gap →    │
│  │      assign → render → orchestrate)      │
│  ├─ NL Scene Editor 代理 (/api/edit/scene)  │
│  ├─ NL ControlVector 代理 (/api/edit/nl)    │
│  ├─ ScriptDrivenVideo 渲染                  │
│  │   (/api/render_script → render_script.ts)│
│  ├─ 风格迁移代理 (/api/style_migrate → Py)  │
│  ├─ KB 代理 (/api/kb/* → Python)            │
│  └─ Remotion 渲染 (ProductPromo /           │
│       SparkPromo / ScriptDrivenVideo /       │
│       StyleDrivenVideo / MultiSceneVideo)    │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│  Python FastAPI (:8000)                     │
│  ├─ S1 视频分析 (scenedetect + librosa +    │
│  │    MiMo-V2.5 多帧运动感知 + RAFT 光流)   │
│  ├─ S2 结构提取 (ASR + 规则推断 + VLM 微调) │
│  ├─ S3 缺口识别 (纯算法) + 策略生成 (A-F)    │
│  ├─ NL Scene Editor (LLM 直接修改 VideoSpec) │
│  ├─ LLM 动画编排 (Beat-Level + 两步 LLM)     │
│  ├─ 风格迁移 (StyleProfile + VLM 动效 +      │
│  │    Gemini 生图 + MultiSceneVideo 渲染)    │
│  ├─ 知识图谱 (SurrealDB 嵌入式图+向量)      │
│  │   ├─ 4 节点: Pattern / Module / Atom /   │
│  │   │          Vertical                    │
│  │   ├─ 3 边: composed_of / built_from /    │
│  │   │         best_for                     │
│  │   └─ BGE-M3 1024 维 HNSW 向量索引        │
│  └─ 入图 Agent (LLM 决策 merge/create/split)│
└─────────────────────────────────────────────┘
```

---

## 快速开始 (Docker)

```bash
# 1. 环境变量
cp .env.example .env
# 编辑 .env 填入 MIMO_API_KEY + GEMINI_API_KEY (可选)

# 2. 构建镜像 (首次约 5 分钟，含 BGE-M3 模型下载)
docker compose build

# 3. 初始化知识库 (种子数据: 1 pattern / 6 modules / 36 atoms)
docker compose run --rm seed

# 4. 启动全部服务
docker compose up

# 访问前端: http://localhost:5173
# Node API:  http://localhost:3000
# Python API: http://localhost:8000

# 使用流程 (两条管线):
#
# 管线 A — 结构迁移:
#   1. 上传参考视频 + 用户素材 → 点击"开始生成"
#   2. 等待管线完成 (自动: 分析→缺口→分配→渲染→编排)
#   3. 自动跳转编辑页 → 场景卡片 + 视频预览
#   4. 用自然语言编辑场景 (如 "把开头文字改成限时秒杀")
#   5. 重新渲染 → 下载 MP4
#
# 管线 B — 风格迁移:
#   1. 上传参考视频 + 输入新主题 → 点击"开始风格迁移"
#   2. 等待管线完成 (分解→风格→动效→图片→文字→渲染)
#   3. 预览播放
```

```bash
# 后续重启 (不需要重新 seed)
docker compose up

# 重置知识库
rm -rf data/graph.db && docker compose run --rm seed && docker compose up
```

---

## 本地开发 (不用 Docker)

```bash
# 依赖安装
pip install -r services/python/requirements.txt
cd services/node && npm install && cd ../..
cd web && npm install && cd ..

# 一键启动三个服务
./scripts/start.sh

# 或手动分别启动:
cd services/python && PYTHONPATH=.. uvicorn main:app --reload --port 8000
cd services/node && npm run dev    # :3000
cd web && npm run dev              # :5173
```

---

## API 配置

### 需要提供的 API Key

项目依赖 **2 个外部 API**，在 `.env` 中配置：

```bash
# 必填 — MiMo API (LLM + VLM，所有智能推理的核心)
MIMO_API_KEY=your-mimo-api-key
MIMO_API_URL=https://token-plan-cn.xiaomimimo.com/v1/chat/completions

# 选填 — Gemini API (AIGC 图片生成，不填则跳过图片生成)
GEMINI_API_KEY=your-gemini-api-key
```

| API | 环境变量 | 是否必须 | 用途 |
|-----|---------|---------|------|
| **MiMo LLM** | `MIMO_API_KEY` + `MIMO_API_URL` | ✅ 必填 | 动画编排、内容生成、自然语言编辑、知识验证、知识库入图决策 |
| **MiMo VLM** | 同上 (同 endpoint) | ✅ 必填 | 视频帧分析、场景理解、风格提取、运动检测、素材标注 |
| **Gemini Imagen 3** | `GEMINI_API_KEY` | ⚠️ 选填 | AIGC 图片生成 (风格迁移 + 缺口补全策略 D) |

> **不填 Gemini 也能跑**：风格迁移管线会继续执行（文字+动效+FX 层正常，仅图片为空黑块）。

### 使用的模型

| 模型 | 环境变量 | 默认值 | 类型 | 用途 |
|------|---------|--------|------|------|
| `mimo-v2.5-pro` | `MIMO_MODEL` | `mimo-v2.5-pro` | LLM (文本推理) | 创意推理、VideoSpec 生成、NL 编辑解析、内容填充、知识验证评估 |
| `mimo-v2.5` | `MIMO_VLM_MODEL` | `mimo-v2.5` | VLM (图文理解) | 视频帧分析、OCR 更正、风格家族分类、运动模式识别、素材质量打分 |
| `gemini-2.5-flash-image` | `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | 图片生成 | 文本→图片 (支持 StyleProfile 风格注入) |

### MiMo API 使用详情

MiMo 是 OpenAI 兼容 endpoint，项目中通过两种方式调用：

| 调用方式 | 模型 | 用途 | 使用文件数 |
|---------|------|------|-----------|
| OpenAI SDK (`openai.OpenAI`) | `mimo-v2.5-pro` | 两步 LLM 编排 (thinking mode + json_object) | animation_orchestrator.py |
| Raw httpx POST | `mimo-v2.5` (VLM) | 视频帧多图分析 (压缩 640px + 3次重试) | scene_description.py, vlm_refiner.py, s1_analyzer.py 等 7 个文件 |
| Raw httpx POST | `mimo-v2.5-pro` (LLM) | 文本推理、NL 解析 | scene_editor.py, main.py, ingestion_agent.py 等 6 个文件 |

**MiMo 特殊能力**：
- `mimo-v2.5-pro` 支持 **thinking mode** (`extra_body={"thinking": {"type": "enabled"}}`)，用于创意推理
- `mimo-v2.5` 支持 **多图输入**，一次分析多帧视频画面
- 所有调用支持 **JSON mode** (`response_format={"type": "json_object"}`)

### Gemini API 使用详情

```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}
```

- 使用 Google 原生 REST API (非 OpenAI 兼容)
- `responseModalities: ["TEXT", "IMAGE"]` 获取图片输出
- 支持 StyleProfile 风格注入：`style_profile.to_aigc_prompt(base_prompt)` 在 prompt 前添加风格修饰词

### 本地模型 (无需 API Key)

以下模型全部在本地运行，不需要任何 API Key：

| 模型 | 用途 | 设备 | 自动下载 |
|------|------|------|---------|
| **SAM2.1-Small** (Meta) | 元素分割 — 自动发现视频中的视觉元素 | GPU/CPU | ✅ HuggingFace |
| **RAFT-Small** (torchvision) | 光流追踪 — 逐帧追踪元素运动轨迹 | GPU/CPU | ✅ torchvision |
| **BGE-M3** (BAAI) | 语义嵌入 — 组件目录 BGE-M3 检索 | CPU | ✅ sentence-transformers |
| **faster-whisper** | ASR 语音识别 — 提取视频语音文字 | CPU | ✅ CTranslate2 |
| **EasyOCR** | 文字检测 — 视频帧中的文字区域识别 | CPU | ✅ 自动下载 |
| **PySceneDetect** | 镜头检测 — 自动切分视频场景 | CPU | ✅ pip |
| **librosa** | 音频分析 — BPM 检测、音频特征提取 | CPU | ✅ pip |

> **GPU 推荐**：SAM2 和 RAFT 在 GPU (CUDA) 上运行更快，但 CPU 也能跑（会自动 fallback）。

### API 调用流程图

```
用户上传视频 + 输入主题
    │
    ├─ MiMo VLM (mimo-v2.5) ──────────────────────────────────────┐
    │   ├─ S1: 视频帧分析 → caption + 视觉语言                      │
    │   ├─ S2 Stage C: VLM 微调 → phase 分类                        │
    │   ├─ 场景分解: 元素角色标注 + 布局分析 + 运动检测               │ 共 ~20-40 次调用
    │   ├─ StyleProfile: 风格家族分类 + FX 检测                      │ (取决于场景数)
    │   └─ S3: 素材质量打分                                         │
    │                                                                │
    ├─ MiMo LLM (mimo-v2.5-pro) ──────────────────────────────────┤
    │   ├─ 动画编排: 两步 LLM (thinking + json)                     │
    │   ├─ Beat-Level: 内容填充 + 动效选择                           │ 共 ~5-10 次调用
    │   ├─ NL 编辑: 自然语言 → EditOp                                │
    │   └─ 知识验证: DuckDuckGo 搜索 + LLM 评估                     │
    │                                                                │
    ├─ Gemini Imagen 3 (gemini-2.5-flash-image) ───────────────────┤
    │   └─ 风格迁移: 主题图片生成 (注入 StyleProfile 风格)            │ 共 ~10-20 次调用
    │                                                                │ (取决于场景数)
    │                                                                │
    └─ 本地模型 ───────────────────────────────────────────────────┘
        ├─ SAM2 + RAFT: 元素分割 + 光流追踪
        ├─ EasyOCR: 文字检测
        ├─ faster-whisper: ASR 语音识别
        └─ BGE-M3: 组件语义检索
```

### 获取 API Key

| API | 获取方式 | 费用 |
|-----|---------|------|
| **MiMo** | [小米 MiMo 开放平台](https://open.xiaomimimo.com) 注册获取 | 按 token 计费 |
| **Gemini** | [Google AI Studio](https://aistudio.google.com/apikey) 免费获取 | 免费额度 (有频率限制) |

---

## 渲染视频

```bash
# ProductPromo (WriteFlow AI 写作助手, 1080×640, 30fps, 39s)
npx tsx scripts/render_promo.ts output/promo_ai_writing.mp4

# SparkPromo (Magnific 风格, 1280×720, 60fps, 31s)
npx tsx scripts/render_spark.ts output/spark_promo.mp4

# ScriptDrivenVideo (脚本驱动, CSS Grid 布局, 自动检测帧数)
npx tsx scripts/render_script.ts <script.json> <output.mp4>

# StyleDrivenVideo (单场景, SceneDescription → MP4)
npx tsx scripts/render_style.ts <scene.json> <output.mp4>

# MultiSceneVideo (场景级分解, Stage 绝对定位 + 转场 + FX 层)
npx tsx scripts/render_multi_scene.ts <decomposition.json> <output.mp4>

# Beat-Level 友谊视频示例 (1080×1920, 30fps, 38s)
npx tsx scripts/render_script.ts friendship_demo/output/beat_script.json friendship_demo/output/beat_final.mp4
```

### 渲染模式对比

| 合成 | 布局 | 用途 | 输入 |
|------|------|------|------|
| ScriptDrivenVideo | CSS Grid | LLM 编排生成内容 | VideoSpec (shots) |
| MultiSceneVideo | Stage 绝对定位 | **风格迁移**（保留原视频元素布局） | decomposition.json |
| StyleDrivenVideo | Grid/Stage 双模式 | 单场景风格渲染 | SceneDescription |
| ProductPromo | props-driven | 产品宣传片 | config props |
| SparkPromo | 1280×720 60fps | Magnific 风格 | config props |

## E2E 测试

```bash
# 设置环境变量
export MIMO_API_KEY="your-mimo-api-key"
export MIMO_API_URL="https://token-plan-cn.xiaomimimo.com/v1/chat/completions"

# 运行完整 E2E 测试 (S1→S2→S3→S4渲染→S5入图)
python scripts/e2e_test.py

# 跳过渲染 (更快)
python scripts/e2e_test.py --skip-render
```

## 结构保真度实验

```bash
# 测量单个 recipe 的结构指标
python scripts/measure_structure.py recipe.json

# 对比两个 recipe 的 ΔM 保真度
python scripts/measure_structure.py recipe1.json recipe2.json --threshold 0.2
```

---

## 项目目录

```
viral-video-engine/
├── CLAUDE.md                    # 项目宪法 (编码规范 + 技术栈约束)
├── catalog.json                 # 统一组件目录 (27 组件, 单一真相源)
├── fewshot_pairings.json        # few-shot 好搭配示例 (L3 选择质量层)
├── recipe.json                  # VST schema 单一真相源 (meta/tokens/motion/components/timeline)
├── docker-compose.yml           # Docker 服务编排
├── .env.example                 # 环境变量模板
│
├── services/
│   ├── python/                  # Python FastAPI 服务
│   │   ├── control_vector.py    #   ControlVector 控制向量 (Task 10/12/13 共用地基)
│   │   ├── main.py              #   入口: /extract /extract_style /gap /assign /orchestrate /profiles /edit/nl /edit/scene /decompose /style_migrate /kb/*
│   │   ├── s1_analyzer.py       #   S1: 视频分析 (scenedetect + 多帧 VLM + motion + 视觉语言)
│   │   ├── motion_analyzer.py   #   光流能量曲线 + 元素轨迹追踪 (RAFT/Farneback)
│   │   ├── s2_extractor.py      #   S2: 结构提取 v2 (ASR+规则+VLM 微调, 含 visual/text/rhythm)
│   │   ├── template_merger.py   #   多视频 template 合并
│   │   ├── vision_analyzer.py   #   CV 视觉分析 (EasyOCR + 光流 + 运动模式检测)
│   │   ├── scene_description.py #   CV+VLM 融合提取 SceneDescription (逐元素属性)
│   │   ├── knowledge_verifier.py #  知识验证 (DuckDuckGo 搜索 + LLM 事实核查)
│   │   ├── scene_decomposer.py  #   场景级视频分解 (shot→场景→元素融合→beat_sheet)
│   │   ├── motion_kinematics.py #   运动学特征 (散度/旋度/尺度) + 闭集动效分类 (20 Tier A/B/C)
│   │   ├── visual_director.py   #   视觉导演 (VLM分析→LLM规划→Gemini生图)
│   │   ├── render_validator.py  #   渲染QA校验 (黑屏/重叠/空文字/时长异常)
│   │   ├── video_utils.py       #   视频格式检测+自动转码
│   │   ├── s2/
│   │   │   ├── asr_extractor.py   # Stage A: faster-whisper ASR
│   │   │   ├── structure_inferrer.py # Stage B: 规则推断
│   │   │   ├── vlm_refiner.py     # Stage C: VLM 微调 (3 prompt 并发)
│   │   │   └── schemas.py         # S2 数据结构
│   │   ├── s3_gap_detector.py   #   S3: 缺口识别 (纯算法) + VLM 素材标注
│   │   ├── s3_strategist.py     #   S3: 6 种补全策略 (A-F)
│   │   ├── animation_orchestrator.py # Beat-Level 编排 + LLM v3 (两步 LLM + 校验修复环)
│   │   ├── component_catalog.py   #   组件目录 (BGE-M3 检索 + 多因子排序 + 运行时 Pydantic)
│   │   ├── gemini_imager.py       #   Gemini Imagen 3 生图 (支持 StyleProfile 风格注入)
│   │   ├── scene_editor.py        #   自然语言场景编辑器 (LLM 直接修改 VideoSpec shot)
│   │   ├── aesthetic_linter.py  #   美感校验 (7 条规则)
│   │   ├── atom_component_map.py#   KB atom → Remotion 组件映射
│   │   ├── video_spec_schema.py #   VideoSpec Pydantic schema (18 组件 + snake_case)
│   │   └── Dockerfile
│   │
│   ├── node/                    # Node.js 编排服务
│   │   └── src/index.ts
│   │
│   └── remotion/                # Remotion 渲染服务
│       └── src/
│
├── kb/                          # 知识图谱 (种子: 1 pattern / 6 modules / 36 atoms)
│   ├── graph_backend.py         #   SurrealDB 抽象层 (AsyncSurreal)
│   ├── template_store.py        #   4 节点 3 边 CRUD + 向量搜索
│   ├── agent/
│   │   └── ingestion_agent.py   #   入图 Agent (merge/create/split)
│   └── seeds/                   #   种子数据 (43 JSON)
│       ├── atoms/               #     原子组件
│       ├── modules/             #     模块
│       └── patterns/            #     模式 (含 promo pattern)
│
├── web/                         # React 前端
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── HomePage.tsx        #   流水线首页 (上传 + 进度)
│   │   │   ├── EditorPage.tsx      #   视频编辑页 (场景卡片 + NL 编辑 + 渲染)
│   │   │   └── KnowledgeBase.tsx   #   知识图谱可视化
│   │   ├── design-tokens/       #   Design Tokens
│   │   │   ├── index.ts         #   字号/配色/间距/easing/palettes (含 promo)
│   │   │   └── motion.ts        #   Spring/EASE/STAGGER 预设 + 工具函数
│   │   ├── motion/
│   │   │   └── primitives.ts    #   动效原语库 (纯函数, recipe.json.motion 对应)
│   │   ├── components/
│   │   │   ├── SafeZone.tsx
│   │   │   ├── StandardCaption.tsx
│   │   │   ├── MigrationMap.tsx  #   Task 7 迁移溯源表 (因果链 + severity 色 + fallback 徽章 + 钻取)
│   │   │   └── mg/              #   MG 组件库 (35 .tsx + 1 index.ts, 扁平结构)
│   │   │       ├── index.ts     #   统一导出
│   │   │       ├── KineticText.tsx / GlassCard.tsx / HookBeat.tsx / ...
│   │   │       └── (共 35 个 .tsx 组件文件)
│   │   ├── stores/pipeline.ts
│   │   └── remotion/
│   │       ├── root.tsx         #   6 个 Composition 注册
│   │       └── compositions/
│   │           ├── ViralVideo.tsx       # 传统渲染 (1080×1920)
│   │           ├── ScriptDrivenVideo.tsx # 脚本驱动渲染 (18 组件 + crossfade + calculateMetadata)
│   │           ├── ProductPromo.tsx     # 产品宣传片 (1080×640, props-driven)
│   │           ├── SparkPromo.tsx       # Magnific 风格 (1280×720, 60fps)
│   │           ├── StyleDrivenVideo.tsx # 风格驱动 + 双模式渲染 (Grid/Stage) + MultiSceneVideo + TextOverlayLayer
│   │           └── TextOverlayLayer.tsx # Kinetic Typography 文字覆盖层 (顺序焦点 + 5 种入场技法)
│   ├── Dockerfile
│   └── nginx.conf
│
├── scripts/
│   ├── start.sh                 #   本地一键启动
│   ├── build_registry.py        #   catalog.json → 自动生成 TS COMPONENT_MAP
│   ├── test_wuhan.py            #   风格迁移测试 (武汉文化主题)
│   ├── render.ts                #   ViralVideo 渲染
│   ├── render_script.ts         #   ScriptDrivenVideo 渲染
│   ├── render_promo.ts          #   ProductPromo 渲染 (1080×640, 30fps)
│   ├── render_spark.ts          #   SparkPromo 渲染 (1280×720, 60fps)
│   ├── render_style.ts          #   StyleDrivenVideo 渲染
│   ├── render_multi_scene.ts    #   MultiSceneVideo 渲染 (场景级分解→MP4)
│   ├── measure_structure.py     #   结构指标集 M 测量 (保真度实验)
│   ├── e2e_test.py              #   E2E 测试
│   ├── e2e_demo.py              #   E2E 演示 (KB-aware)
│   ├── e2e_orchestrated.py      #   E2E 演示 (LLM 编排)
│   ├── seed_kb.py               #   知识库初始化
│   └── ...
│
├── data/                        # 运行时数据 (不入 git)
│   ├── graph.db                 #   SurrealDB 嵌入式数据库
│   ├── uploads/
│   └── output/                  #   渲染输出 (mp4)
│
├── .claude/skills/
│   ├── composition-rules.md     #   组合纪律 (运行时 system prompt 常驻)
│   └── ...                      #   其他 skills
│
├── docs/
│   ├── spec.md                  #   完整系统设计 spec
│   ├── motion_design_guide.md   #   MG 设计指南 (8 条铁律)
│   ├── video_recipe_layoutdev.md #  Layout.dev 视频配方
│   ├── component_proportions.md #   组件比例规范
│   ├── unwrapped_patterns.md    #   GitHub Unwrapped 架构参考
│   ├── product_promo_revision.md # ProductPromo 组件体系修订方案
│   ├── migration_system_design.md # 场景级迁移系统设计 (v1)
│   ├── universal_migration_system.md # 通用迁移系统设计 (v2)
│   └── universal_migration_v2.md # 迁移系统 v2 修订
│
├── output/
│   ├── promo_ai_writing.mp4     #   ProductPromo 输出 (39s, 4.7MB)
│   └── spark_promo.mp4          #   SparkPromo 输出 (31s, 2.9MB)
│
├── friendship_demo/             # Beat-Level 友谊视频示例
│   ├── friendship_template.json #   含 7-beat beat_sheet
│   ├── materials/               #   Gemini 生成的友谊主题图片
│   └── output/
│       ├── beat_script.json     #   Beat-Level 生成的动画脚本
│       └── beat_final.mp4       #   最终渲染 (38s, 3.2MB)
│
├── types/                       # TypeScript 类型
├── tests/                       # 测试用例
└── e2e_demo/                    # E2E 测试数据
```

---

## 前端流程

项目有两条独立的前端流程，共享同一个 Python 后端。

### 流程 A — 结构迁移（首页"开始生成"）

```
上传参考视频 + 用户素材
    │
    ▼
[S1] 视频分析 ── scenedetect + librosa + 多帧 VLM
    │              + RAFT 光流 + SAM2 元素追踪
    │              → shots + caption + audio + motion
    │
    ▼
[S2] 结构提取 ── ASR + 规则推断 + VLM 微调
    │              → StructureTemplate JSON
    ▼
[S3] 缺口检测 + 策略生成 (A-F 六策略)
    │
    ▼
[S3.5] 美感校验 (7 条规则)
    │
    ▼
[S4] Beat-Level 编排 ── LLM 填内容 + 选动效 → VideoSpec
    │
    ▼
[S5] 渲染 ── ScriptDrivenVideo (CSS Grid, 18 组件)
    │
    ▼
[S6] NL 场景编辑 ── 自然语言修改 VideoSpec → 重新渲染 → 下载
```

### 流程 B — 风格迁移（首页"开始风格迁移"）

```
上传参考视频 + 输入新主题
    │
    ▼
[1] 场景分解 ── PySceneDetect + SAM2 + OCR + VLM
    │              → VideoDecomposition (多场景 + beat_sheet)
    │
    ▼
[2] StyleProfile ── CV 取色 + VLM 判风格家族 (6 种)
    │
    ▼
[3] VLM 运动分析 ── 逐场景帧对 → motion_path 关键帧
    │
    ▼
[4] Gemini 图片生成 ── 主题 prompt + StyleProfile 风格注入
    │
    ▼
[5] LLM 文字编排 ── 主题相关文案 (≤14字, 不重复)
    │
    ▼
[6] 注入 ── 文字动画 + idle 动画 + 入场/出场动效
    │
    ▼
[7] MultiSceneVideo 渲染 ── Stage 绝对定位 + FX 层 + 转场
    │
    ▼
预览播放
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Zustand + react-force-graph-2d |
| 编排 | Node.js + Express + tsx |
| 计算 | Python 3.11 + FastAPI + Pydantic |
| 知识库 | SurrealDB (嵌入式, 图+向量) + BGE-M3 (1024 维) — 种子: 1 pattern / 6 modules / 36 atoms |
| LLM + VLM | MiMo-V2.5-pro (文本推理, thinking mode) + MiMo-V2.5 (多图理解) — OpenAI 兼容 endpoint, 13 个文件共用 |
| 光流追踪 | RAFT-Small (torchvision) + OpenCV Farneback fallback |
| 元素分割 | SAM2.1-Small (Meta, HuggingFace auto-download) + contour fallback |
| 图片生成 | Gemini Imagen 3 (gemini-2.5-flash-image, 支持 StyleProfile 风格注入) |
| ASR | faster-whisper (多语言) |
| 渲染 | Remotion v4 + @remotion/three + GSAP + Lottie |
| 动效工程 | Design Tokens + motion primitives (纯函数) + 35 个 MG 组件 (18 个注册到 ScriptDrivenVideo) |
| 动效词表 | 20 个动效分类 (Tier A/B/C) + 运动学特征 (散度/旋度/尺度) + 闭集分类器 |
| 场景分解 | scene_decomposer (shot→场景→元素融合→CSS Grid 布局→beat_sheet) + MultiSceneVideo 渲染 |
| 布局系统 | VLM 驱动布局分析 + 6 种参数化家族 (centered/radial/stack/full_bleed/grid/split) + CSS Grid + Stage 绝对定位 + AnimatedInner |
| 文字系统 | TextOverlayLayer (Staging 原则) + 顺序焦点排程 + 5 种入场技法 + scrim 可读性 |
| 动画引擎 | 5 入场 × 5 持续 × 4 出场 = 100 种组合 + Per-element 随机化 + stagger |
| 组件目录 | `catalog.json` (27 组件) + `component_catalog.py` (BGE-M3 检索 + 多因子排序 + 运行时 Pydantic) |
| 选择质量 | L1 结构化查询 + L2 多因子排序 + L3 few-shot 好搭配 + L4 选择校验器 |
| 风格迁移 | StyleProfile (palette/grade/fx/overlay/typography) → Gemini prompt 注入 + 渲染 FX 层 |
| 知识验证 | DuckDuckGo 搜索 + LLM 事实核查 + Do No Harm 护栏 (high confidence 才改) |
| 图片提取 | 多帧采样选最亮 + SAM2 bbox 裁剪 + 低对比度过滤 |
| 配方系统 | recipe.json (VST schema 单一真相源) + 参数化合成 |
| 美感 | Aesthetic Linter (7 条规则) + render_validator (14 条 QA 规则 + 确定性修复) + SafeZone + Design Tokens |
| NL 场景编辑 | scene_editor.py (LLM 直接修改 VideoSpec JSON) + Pydantic 校验 + 自动 diff + 场景卡片可视化 |
| 编辑页面 | EditorPage (左右分栏: 视频预览 + 场景时间线 + NL 编辑器 + 编辑历史) |
| 部署 | Docker Compose (3 服务 + 1 seed job) |

---

## MG 组件库 (35 .tsx + 1 index.ts, 扁平结构)

`web/src/components/mg/` 下所有组件平铺存放，无子目录。

### 原子组件
KineticText · GradientText · WordReveal · TypewriterPrompt · MarqueeText · GlowTrail · IconButton · ParticleBg · BeforeAfter · PriceReveal · CountdownTimer · ProductShowcase

### 数据组件
DataChart (含 BarChart / NumberRoll / DonutChart) · CinematicEffects (LightLeak / GlitchTransition / GradientMesh / FilmGrain / Vignette)

### 分子组件
GlassCard · FloatingMockup · FeatureGrid · FeatureScroller · LogoReveal · HeroTitle · TransitionFX · ImageOrbit · GeometricLines · PhotoStack · LottiePlayer

### Beat 有机体
HookBeat · TypewriterBeat · FeaturesBeat · PayoffBeat · GridBeat · ClosingBeat · LogoBeat

### 布局组件
Background · Section · Stage

### 合成层
ScriptDrivenVideo · ProductPromo · SparkPromo · ViralVideo · StyleDrivenVideo (含 MultiSceneVideo)

### 注册到 ScriptDrivenVideo COMPONENT_MAP (18)
KineticText · ProductShowcase · CountdownTimer · BarChart · NumberRoll · DonutChart · PriceReveal · BeforeAfter · ParticleBg · GradientText · WordReveal · TypewriterPrompt · GlassCard · FloatingMockup · MarqueeText · FeatureGrid · LogoReveal · GlowTrail

---

## 组件目录系统 (Catalog-Driven Orchestration)

> 单一真相源 `catalog.json` → 自动生成注册 → BGE-M3 语义搜索 → LLM 选择 + 校验

### 架构

```
catalog.json (27 组件, 含 props_schema/when_to_use/when_not/example_effect)
    │
    ├─ build_registry.py → _generated_component_map.ts (TS 注册)
    ├─ component_catalog.py → 运行时 Pydantic (create_model, 不 codegen)
    │
    └─ 编排器:
        L1: build_need() 结构化查询 (phase/kind/role/content_len/style_family)
        L2: rank() 多因子排序 (0.35×cosine + 0.2×phase + 0.15×style + 0.1×impact + 0.1×char + 0.1×kind)
        L3: few-shot 好搭配 + 富候选卡 (when_to_use/when_not/example_effect) + 要求 why
        L4: validate_choice() 选择校验器 (must_read/phase_blacklist/kind/char_limits)
```

### 使用

```bash
# 生成 TS 注册文件
python scripts/build_registry.py

# 校验（CI 模式）
python scripts/build_registry.py --check
```

### 添加新组件

1. 在 `catalog.json` 添加一条 CatalogEntry
2. 创建 `.tsx` 组件文件
3. 运行 `python scripts/build_registry.py`
4. 完成（不需要改其他文件）

---

## 风格迁移系统 (StyleProfile)

> 输入任意参考视频 + 新主题 → 提取视觉风格 → 生成新视频（匹配原视频视觉语言）

### 设计原则

**几何与时序用 CV 测量，语义与模式用 VLM 分类。** VLM 不负责坐标/帧号（已知短板），只负责"这是什么"。

- SAM2 + RAFT 光流 → 逐元素运动轨迹（不是 VLM 编造的"左滑"）
- VLM → OCR 更正 + 语义角色标注 + 风格家族分类
- motion_path 关键帧 → 连续运动（不是只有入场/出场）

### 完整管线

```
参考视频 + 新主题
    │
    ▼
[1] 场景分解 ─ PySceneDetect shot → SAM2+OCR+VLM 元素融合 → beat_sheet
    │
    ▼
[2] StyleProfile ─ CV 取色 (palette/grade) + VLM 判风格家族 (6 种)
    │                 → to_aigc_prompt() 注入 Gemini / to_css_filter() 注入渲染
    │
    ▼
[3] VLM 运动分析 ─ 逐场景帧对分析 → 平移/旋转/缩放/淡入淡出/弹性/级联
    │                 → generate_motion_paths_for_decomp() 生成 motion_path 关键帧
    │
    ▼
[4] Gemini 图片生成 ─ 主题相关 prompt + StyleProfile 风格修饰词 → 1280×720 图片
    │
    ▼
[5] LLM 文字编排 ─ orchestrate_from_beats() → 主题相关文案（不重复，≤14字）
    │
    ▼
[6] 注入 ─ 文字 (typewriter/blur_in 入场) + idle 动画 (float/breathe/rotate/elastic_pop)
    │         + 入场/出场动效 + motion_path 连续运动
    │
    ▼
[7] MultiSceneVideo 渲染 ─ Stage 绝对定位 + FX 层 (Vignette/FilmGrain/LightLeak/GradientMesh)
                             + CSS filter (调色) + 场景转场 (15帧 crossfade)
```

### Web UI 入口

```
http://localhost:5173 → 上传参考视频 → 输入主题 → "开始风格迁移"
    → 进度条 (分解→风格→动效→图片→文字→渲染)
    → 预览播放
```

### API 端点

```
POST /api/style_migrate  { videoPath, topic } → decomposition JSON + job_id
POST /api/render_scene   { composition, props } → MP4 base64
```

### StyleProfile 字段

```python
@dataclass
class StyleProfile:
    style_family: str    # dark_neon_ui / bright_airy / retro_film / minimal_tech / vibrant_social / dark_cinematic
    palette: dict        # bg_color, bg_gradient, accent, accent2, text_color
    grade: dict          # brightness, contrast, saturate, hue_rotate, temperature, mood
    fx: dict             # vignette, film_grain, light_leak, glow, gradient_mesh (0-1)
    overlay: dict        # has_logo, logo_pos, has_frame, ui_chrome
    typography: dict     # font_style, weight, case, text_color, glow_text
```

### 应用点

1. **AIGC 生成时**: `style_profile.to_aigc_prompt(base_prompt)` → 注入风格修饰词 + 调色板颜色
2. **渲染时**: CSS filter (调色) + Vignette/FilmGrain/LightLeak/GradientMesh FX 层 + 背景色

### 渲染图层栈

```
z:0   内容层 (Stage 绝对定位, 保留原视频元素布局)
z:5   FX 层: Vignette / FilmGrain / LightLeak / GradientMesh (按 StyleProfile.fx 开关)
z:10  文字层 (TextOverlayLayer, 顺序焦点, VLM分析的入场技法)
z:-1  背景 (palette bg_color/bg_gradient)
```

### 运行

```bash
# 完整管线: 分解 → 风格提取 → VLM动效分析 → LLM文字 → 渲染
python scripts/test_wuhan.py
```

### 已知限制

| 问题 | 原因 | 状态 |
|------|------|------|
| SAM2 元素过检 | 每个小轮廓为独立元素，数量远超视觉元素数 | 需 VLM 逐场景判断主体，或提高 contour 面积阈值 |
| Gemini 429 限流 | API 配额限制 | 图片生成会失败，管线继续（空图+文字+动效） |
| VLM 超时 | MiMo API 不稳定 | 已加重试 (3次) + 指数退避 + 图片压缩 640px |
| 布局匹配度 | 元素过多导致 Stage 排列与原视频不同 | 需每场景只保留 1-2 个主体元素 |
| 文字动画匹配 | VLM 分析原视频文字入场风格 | typewriter/blur_in 已接入，效果可接受 |
| 色彩调性 | StyleProfile 提取但未完全应用 | FX 层已接，CSS filter 部分生效 |

---

## 知识验证系统 (KnowledgeVerifier)

> LLM 生成内容后自动搜索验证，Do No Harm 护栏

### 流程

1. 提取事实性声明 (过滤主观内容，只保留含数字/日期的硬事实)
2. DuckDuckGo 搜索 (带重试 + 优雅降级)
3. 多来源一致性检查 (数字重叠验证)
4. LLM 评估 (批处理，注入一致检查结果)
5. 仅 high confidence + 一致矛盾 → 自动修正；其余保留原文

### 原则

- **默认保留原文**。只有多来源一致 + high 置信才覆盖。
- medium/low → 只报告不改。
- 搜不到/冲突 → 不改，标记 unverifiable。

---

## 亮点

1. **迁移溯源表 (MigrationMap)**: 因果链可视化——源结构→缺口→策略→产出，severity 上色 + fallback 暴露 + 钻取面板
2. **recipe.json + Beat-Level 编排**: VST schema 单一真相源，beat_sheet 自动生成 + LLM 作曲家填内容/动效/转场
3. **GraphRAG 知识图谱**: 4 节点 3 边 + SurrealDB HNSW 向量搜索 + 前端可视化
4. **Agentic Ingestion**: LLM 决策 merge/create/split，不是简单 INSERT
5. **20 个动效词表 + 运动学分类器**: 散度/旋度/尺度→闭集分类→Tier A/B/C，参数化组件库
6. **Props-driven 合成**: 换 config 即出不同视频，证明模板化可复用
7. **场景级视频分解**: PySceneDetect shot→SAM2+OCR 元素融合→CSS Grid 布局(layout_type+slot)→beat_sheet
8. **5 层动画控制**: 生命周期(entrance/sustain idle/exit) + 可动属性(position/scale/rotation/opacity/anchor/mask_reveal/blur) + 时间缓动(spring 预设) + 编排(stagger/direction) + 场景(camera/bg_motion)
9. **LLM 作曲家 + 验证修复环**: 命名预设(snappy/bouncy/smooth)不吐裸数值 + 9 条规则配确定性兜底修复
10. **零外部 API**: SurrealDB 嵌入式 + 本地 BGE-M3 + MiMo 代理，一键 docker compose up
11. **运动提取管线**: SAM2 元素发现 + RAFT 光流追踪 + RDP 关键帧化 + motion_path 接线到渲染器
12. **ControlVector 统一控制**: 类型化旋钮——预设 profile / 人工可调 / NL 编辑，三任务一套地基
13. **NL Scene Editor**: 自然语言直接修改 VideoSpec——LLM 拿到完整 spec JSON + 用户指令 → 输出修改后的 spec → Pydantic 校验 + 自动修复 → diff 预览 → 重新渲染。不限预定义操作，LLM 自由理解任意编辑意图
24. **场景可视化编辑页**: 管线完成后自动跳转独立编辑页——场景卡片条(组件图标/文字/时长/phase 徽章) + 变更高亮 + NL 编辑 + 一键渲染 + 编辑历史
14. **高光排序 (Task 11)**: MiMo-V2.5 VLM 零训练打分——质量分 + 角色匹配分 + 廉价信号 → 贪心分配
15. **结构保真度 ΔM**: measure_structure.py 量化迁移前后 beat timing / motion density / attention curve / diversity
16. **CSS Grid 布局系统**: 6 个模板(centered_hero/grid_2x2/split_lr/full_bleed/three_row/hero_side) + 命名区域自动铺满 + object-fit:cover 不变形 + AnimatedInner 动画解耦
17. **渲染 QA 校验**: 14 条规则(黑屏/重叠/碰撞/安全区/元素数量/文字bbox/阅读时间/对比度) + 确定性兜底修复
18. **诚实边界**: Tier C 效果(体积3D/生成视频)标为媒体槽位 MigrationMap 暴露 fallback，不假装克隆
19. **Kinetic Typography 文字系统**: Staging 原则(一次一焦点) + TextOverlayLayer(文字浮在 Grid 之上) + 顺序焦点排程 + 5 种入场技法(word_stagger/char_pop/mask_reveal/blur_in/typewriter) + scrim 可读性底衬 + 文字专用校验(阅读时间/对比度)
20. **VLM 驱动布局 + 参数化生成**: VLM 分析原视频帧判定布局(centered/radial/stack/full_bleed/grid/split) → 6 种参数化生成器确定性产出 + 图片裁剪保存(多帧采样选最亮+低对比度过滤) + 中文布局识别
21. **风格迁移管线**: StyleProfile(CV取色+VLM判风格) → Gemini 风格注入生图 → VLM 动效分析 → motion_path 关键帧生成 → MultiSceneVideo Stage 渲染 + FX 层
22. **组件目录 + L1-L4 选择质量**: catalog.json(27组件) → BGE-M3 语义检索 → 多因子排序(0.35cosine+0.2phase+0.15style+0.1impact+0.1char+0.1kind) → few-shot 好搭配 → 选择校验器
23. **知识验证 Do No Harm**: DuckDuckGo 搜索 + LLM 事实核查 + 多来源一致性检查 → 仅 high confidence 才自动修正，其余保留原文
