# VST — ViralStructTransfer 爆款结构迁移引擎

> 剪映 / 字节跳动 AI 全栈挑战赛 · 项目提交文档

---

## 1. 项目概述

**一句话定位**：VST 是一个「学习剪辑方法论的 AI 系统」——输入爆款短视频，自动拆解结构配方，识别素材缺口，智能补全，输出多个变体成片。

**解决什么问题**：

短视频创作者面临一个核心困境：爆款视频的"好看"是结果，但"为什么好看"是黑盒。VST 把爆款视频的创作方法论显式抽象为可复用的结构配方（StructureTemplate），然后用 AI 按照配方把新内容组装成视频。不是"AI 生成视频"，而是"AI 学会了剪辑逻辑，然后帮你剪"。

**核心能力**：
- 6 维度视频结构定义（叙事/节奏/视觉/音频/文字/包装）
- VLM 驱动的结构提取（ASR + 规则推断 + 多帧视觉分析）
- 素材缺口自动识别 + 6 种补全策略
- 36 个 MG 组件 + Remotion props-driven 渲染
- 自然语言场景编辑（LLM 直接修改视频结构）
- 知识图谱自动沉淀（Pattern → Module → Atom 三层）

---

## 2. 演示视频

> [演示视频链接]
>
> 3~5 分钟录屏，展示完整操作流程：上传参考视频 → 管线自动分析 → 识别缺口 → 生成视频 → 自然语言编辑 → 重新渲染。配旁白讲解。

---

## 3. 产出视频

> [产出视频链接]
>
> VST 系统生成的成品视频。包含多个变体（紧凑 15s / 标准 22s / 舒展 30s），展示不同内容策略（标准 / 高点击 CTR / 高转化 / 高节奏 / 高质感）。

---

## 4. 整体 AI 架构

### 4.1 系统架构图

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
│  ├─ ScriptDrivenVideo 渲染                  │
│  │   (/api/render_script → render_script.ts)│
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
│  ├─ 知识图谱 (SurrealDB 嵌入式图+向量)      │
│  └─ 入图 Agent (LLM 决策 merge/create/split)│
└─────────────────────────────────────────────┘
```

### 4.2 核心数据流

```
输入视频 (mp4)
    │
    ▼
[S1] 视频分析 ── scenedetect + librosa + 多帧 VLM 运动感知
    │              + RAFT 光流能量曲线 + SAM2 元素追踪
    │              → shots + caption + audio + motion
    │
    ▼
[S2] 结构提取 ── 四步流水线 (各阶段独立降级):
    │              Stage A: faster-whisper ASR 提取
    │              Stage B: 规则 + ASR 候选推断
    │              Stage C: VLM 微调 (3 prompt 并发)
    │              Stage D: 模板组装
    │              → StructureTemplate JSON (6 维度)
    ▼
[S3] 缺口检测 ── 纯算法缺口识别 + VLM 素材标注 + 高光排序分配
    │              → 6 种补全策略 (A-F)
    │
    ▼
[S4] LLM 编排 ── Beat-Level 两步 LLM + 校验修复环
    │              → VideoSpec JSON (shots[] + globalStyle)
    │
    ▼
[S5] Remotion 渲染 ── ScriptDrivenVideo (18 组件 + crossfade)
    │                    → mp4
    ▼
[S6] NL 场景编辑 ── 自然语言 → LLM 直接修改 VideoSpec
                      → Pydantic 校验 + diff → 重新渲染
```

### 4.3 使用的 AI 模型

| 模型 | 用途 | 调用方式 |
|------|------|----------|
| **MiMo-V2.5-pro** | Beat-Level 编排、NL 场景编辑、创意推理 | OpenAI 兼容 API (httpx) |
| **MiMo-V2.5** | 多帧视觉理解、素材标注、布局分析 | OpenAI 兼容 API (httpx) |
| **faster-whisper** | ASR 语音识别 (多语言) | 本地推理 |
| **RAFT-Small** | 光流追踪 (torchvision) | 本地推理 |
| **SAM2.1-Small** | 元素分割 (Meta) | 本地推理 (HuggingFace auto-download) |
| **BGE-M3** | 知识图谱向量索引 (1024 维) | 本地推理 |
| **Gemini Imagen 3** | AIGC 生图 (支持 StyleProfile 风格注入) | Google API |

### 4.4 关键技术点

**① 6 维度视频结构定义（StructureTemplate）**

不是用自然语言描述视频结构，而是定义了一个 6 维度的结构化 Schema：
- **Narrative**：hook_type / build_pattern / cta_type（叙事骨架）
- **Temporal**：total_duration / phase_breakdown / energy_curve（节奏骨架）
- **Visual**：shot_size_distribution / color_palette / face_prominence（视觉骨架）
- **Audio**：bpm / beat_alignment / voice_music_ratio（音频骨架）
- **Text**：caption_density / font_style / position（文字骨架）
- **Packaging**：transition_types / sticker_density / 3d_elements（包装骨架）

这个 Schema 是 LLM 输出和渲染层之间的契约——LLM 只能填这个 DSL，不能生成任意代码。

**② 素材缺口识别 + 智能补全**

系统对比"配方需要什么"和"用户提供了什么"，自动识别缺口：
- **VLM 标注**：对每个用户素材调 MiMo-V2.5 分析镜头类型、质量分、适合的视频阶段
- **打分分配**：`score = quality + role_fit[phase] + motion + sharpness + duration_fit`
- **6 种策略**：结构重排 / 字幕补全 / 包装补全(KB 推荐组件) / AIGC 生成 / 素材重组 / Beat-Level 编排

**③ NL Scene Editor（自然语言场景编辑）**

不预定义编辑操作枚举，而是把完整 VideoSpec JSON 交给 LLM，让它直接输出修改后的 spec：
```
用户: "把开头文字改成限时秒杀，倒计时颜色改金色，节奏加快"
    ↓
LLM 拿到完整 VideoSpec JSON + 18 个组件的 Props Schema
    ↓
LLM 输出修改后的完整 shots[]
    ↓
Pydantic 校验 + 自动修复 → diff 预览 → 重新渲染
```
VLM 验证：修改前后的视频截图对比，确认文字/颜色/时长变更均生效。

---

## 5. 工具协议

### 5.1 recipe.json — LLM 与渲染层的契约

VST 的核心协议是 `recipe.json`，它是 LLM 输出和 Remotion 渲染层之间的契约：

```json
{
  "fps": 30,
  "globalStyle": { "bgColor": "#050510", "palette": "promo" },
  "shots": [
    {
      "id": "hook_0",
      "role": "hook",
      "component": "WordReveal",
      "props": { "text": "限时秒杀", "font_size": "display", "color": "#FFFFFF" },
      "start": 0,
      "duration": 120,
      "position": "center",
      "transition": "crossfade"
    }
  ]
}
```

**LLM 能控制什么**：组件选择、文字内容、时长、位置、转场、色板、背景色
**LLM 不能控制什么**：任意代码执行、CSS 值（受限于枚举）、组件 Props（受限于 Pydantic Schema）

### 5.2 VideoSpec Pydantic Schema — 运行时校验

每个组件的 Props 都有 Pydantic 模型定义：

```python
class KineticTextProps(BaseModel):
    text: str = Field(description="屏幕上显示的完整文字，不超过20字")
    mode: Literal["bounce", "slide", "typewriter", "shake"] = "bounce"
    font_size: Literal["display", "headline", "body", "caption"] = "headline"
    color: str = Field(default="#FFFFFF", description="文字颜色 hex")
```

LLM 输出的所有 Props 都经过 `model_validate()` 校验，非法值自动修复或拒绝。

### 5.3 catalog.json — 组件目录协议

27 个组件的元数据目录，定义了每个组件的：
- `props_schema`：Props 字段定义
- `when_to_use`：适用场景
- `when_not`：不适用场景
- `example_effect`：效果示例

LLM 编排时参考此目录选择组件，BGE-M3 语义检索 + 多因子排序。

### 5.4 AI 辅助开发工作流

开发全程使用 **Claude Code** 作为 AI 编程助手：
- **Spec-driven development**：先写完整 spec（docs/spec.md），Claude Code 直接读取执行
- **TDD 工作流**：先写测试 → 实现 → 重构
- **自动 code review**：每次提交前自动审查
- **Skill 系统**：自定义 Claude Code skills（composition-rules.md 等）作为运行时 system prompt

---

## 6. 安全边界

### 6.1 LLM 输出校验

- **Schema 约束**：LLM 输出必须通过 VideoSpec Pydantic Schema 校验才能进入渲染层
- **组件白名单**：只能使用 18 个注册组件，不能生成任意 React 组件
- **Props 枚举**：颜色用 hex、字号用枚举档位（display/headline/body/caption）、动画模式用枚举（bounce/slide/typewriter/shake）
- **自动修复**：未知组件回退默认、缺失字段填默认值、超出范围自动 clamp

### 6.2 渲染层防护

- **render_validator**：14 条 QA 规则（黑屏/重叠/碰撞/安全区/元素数量/文字 bbox/阅读时间/对比度）
- **aesthetic_linter**：7 条美感规则
- **确定性修复**：校验失败时自动修复而非报错崩溃

### 6.3 知识验证

- **DuckDuckGo 搜索**：LLM 生成内容后自动搜索验证事实准确性
- **Do No Harm 护栏**：只有 high confidence + 多来源一致才自动修正，medium/low 只报告不改

### 6.4 环境与权限

- **API Key 走环境变量**：`.env` 文件不进 git（`.gitignore` 排除）
- **素材文件访问范围限制**：只读取 `data/uploads/{jobId}/materials/` 目录
- **零外部视频生成 API**：全部本地渲染（Remotion），不依赖第三方视频生成服务

---

## 7. 代码仓库与运行说明

### 7.1 仓库地址

> [GitHub 仓库链接]
>
> 如果是 private 仓库，请在提交前转为 public，或提供评委账号的 collaborator 权限。

### 7.2 环境要求

- **Node.js** >= 18
- **Python** >= 3.11
- **Docker** + Docker Compose（推荐）
- macOS / Linux / Windows (WSL2)

### 7.3 快速开始（Docker）

```bash
# 1. 克隆仓库
git clone [仓库地址]
cd viral-video-engine

# 2. 环境变量
cp .env.example .env
# 编辑 .env 填入 MIMO_API_KEY

# 3. 构建镜像（首次约 5 分钟，含 BGE-M3 模型下载）
docker compose build

# 4. 初始化知识库
docker compose run --rm seed

# 5. 启动全部服务
docker compose up

# 访问前端: http://localhost:5173
# Node API:  http://localhost:3000
# Python API: http://localhost:8000
```

### 7.4 本地开发（不用 Docker）

```bash
# 依赖安装
pip install -r services/python/requirements.txt
cd services/node && npm install && cd ../..
cd web && npm install && cd ..

# 一键启动三个服务
./scripts/start.sh
```

### 7.5 使用流程

1. 打开 http://localhost:5173
2. 上传参考视频（爆款短视频）+ 用户素材（产品图片/视频）
3. 点击"开始生成"，等待管线完成（约 2-5 分钟）
4. 自动跳转编辑页 → 看到场景卡片条 + 视频预览
5. 用自然语言编辑场景（如"把开头文字改成限时秒杀"）
6. 重新渲染 → 下载 MP4

---

## 8. 已知限制与后续计划

### 已知限制

| 问题 | 原因 | 影响 |
|------|------|------|
| SAM2 元素数量 ≠ 原视频视觉元素数 | SAM2 检测每个小轮廓为独立元素 | 需 VLM 逐场景判断主体 |
| 部分场景布局与原视频不同 | 元素过多导致 Grid/Stage 排列差异 | 需每场景只保留 1-2 个主体元素 |
| VLM 调用偶尔超时 | API 限流/不稳定 | 已加重试+降级 |
| 视频风格迁移的色彩还原 | StyleProfile 提取但未完全应用到渲染 | FX 层已接，CSS filter 部分生效 |

### 后续计划

1. **实时预览**：接入 Remotion Player，编辑后即时预览不需等待渲染
2. **更多组件**：3D 元素（Three.js）、Lottie 动画、视频片段混合
3. **多语言支持**：ASR 已支持多语言，UI 和字幕模板待扩展
4. **批量处理**：支持一次输入多个主题，批量生成变体
5. **知识图谱增强**：更多种子数据、自动从爆款视频中提取 Pattern 入库
