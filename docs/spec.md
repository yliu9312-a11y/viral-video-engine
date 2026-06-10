# 爆款结构迁移引擎 — 系统完整设计规范 v3 FINAL

> **本文档定位**:这是一份**可被 Claude Code 直接读取并执行**的完整 spec。它合并了 v1/v2/v3 补丁的所有有效内容,补充了基于课题讲解会议的修订、Three.js 3D 增强、Claude Code 工作流适配。**v1/v2/v3-patch 三份历史文档已废弃,以本文档为准**。
>
> 项目代号:**ViralStructTransfer**(以下简称 VST)
> 团队规模:1 人(你)+ Claude Code 协助
> 周期:4 周
> 目标分数:92-104(满分 110,含加分项)
> 出题方:剪映 / 字节跳动 AI 全栈挑战赛

---

## 目录

0. [项目要旨与立项依据](#0)
1. [系统总体架构](#1)
2. [视频结构的形式化定义](#2)
3. [剪辑技巧知识库(三层)](#3)
4. [素材缺口处理(P0 / 20 分)](#4)
5. [Remotion 渲染层与 3D 能力](#5)
6. [本地部署架构](#6)
7. [完整技术栈清单](#7)
8. [4 周路线图(逐天对齐评分)](#8)
9. [Claude Code 协作工作流](#9)
10. [评分对照表 + 加分项设计](#10)
11. [AI 工具使用说明文档(官方强制)](#11)
12. [立即可执行的 Day 0 清单](#12)

---

<a id="0"></a>
## 0. 项目要旨与立项依据

### 0.1 一句话定义

VST 不是一个"AI 视频生成器",而是一个**"学习剪辑方法论的 AI 系统"**——给它几个爆款样例视频,它把这些视频的"创作配方"显式抽象为可复用的协议;给它一个新主题/商品/素材,它按配方生成全新短视频。

### 0.2 出题方与产品对位

| 维度 | 信息 |
|---|---|
| 出题方 | 剪映团队(字节跳动) |
| 直接产品对位 | **Pippit AI 的"爆款一键复刻"**(原 CapCut Commerce Pro) |
| 评分四维度 | ① 系统完成度 ② 最终视频效果 ③ **沉淀的剪辑技巧知识库** ④ 可解释/可调整/可展示 |
| 技术建议(官方明确) | React/TypeScript/Node.js + LLM/VLM/ASR + FFmpeg/OpenCV + **Remotion/HyperFrames** |
| 资源(官方提供) | Doubao-Seed-2.0-lite EP + APIKEY(`ep-20260508213828-7ntjl`)+ 算力 |
| 资源(官方不提供) | **视频生成模型 token**(关键约束) |

### 0.3 课题问的 4 个核心问题(官方原文)

> 1. 你如何定义视频的"结构"
> 2. 你如何把样例结构迁移到新内容
> 3. **当素材不足时,你如何识别缺口并做合理补全**
> 4. 你的结果是否可解释、可调整、可展示

这 4 个问题决定 75 分。VST 全部回应了:

| 问题 | VST 的回答 | 对应模块 |
|---|---|---|
| Q1 结构定义 | **6 维度 StructureTemplate Schema**(narrative/temporal/visual/audio/text/packaging) | §2 |
| Q2 结构迁移 | **三层知识库**(原子/模块/模式)+ 检索式生成 | §3 |
| Q3 缺口处理 | **5 步识别 + 5 种补全策略**(含本地 ComfyUI + Remotion 动画化路径) | §4 |
| Q4 可解释 | **迁移过程可视化 + 决策卡片 + 知识库 stats 仪表盘** | §5 + §8 W4 |

### 0.4 三个非协商核心立项决策

| 决策 | 内容 | 理由 |
|---|---|---|
| **方向** | 营销带货短视频为主,剪辑/MG 动画能力做嵌入 | 评委是 Pippit 团队,直接对位;5 种缺口在营销场景最自然出现 |
| **渲染层** | **Remotion + @remotion/three**(React + R3F)+ FFmpeg | 生态成熟、与 React 前端同栈、官方 3D 支持、可嵌入 Player 实时预览;HyperFrames 在答辩里作为"调研过的备选"提及 |
| **生成路径** | 零外部视频生成 API,**全部本地**:Remotion 出片段 + ComfyUI 生静态图 + Remotion 动画化 + FFmpeg 拼接 | 官方不给视频 token + 必须可本地部署 + 评分不考核速度 |

### 0.5 v1/v2/v3-patch → v3 FINAL → 当前 关键变更

| 维度 | v3 FINAL | 当前实际 |
|---|---|---|
| LLM | Doubao-Seed-2.0-lite | **MiMo-V2.5-pro(编排) + MiMo-V2.5(视觉)** |
| VLM | Qwen2.5-VL-7B (本地 vLLM) | **MiMo-V2.5(代理 API)** |
| ASR | Paraformer / Whisper | **faster-whisper (多语言)** |
| AIGC 生图 | ComfyUI + SDXL | **Gemini Imagen 3** |
| 数据库 | SQLite | **SurrealDB (嵌入式图+向量) + BGE-M3** |
| 渲染层 | Remotion + 3D 原子库 | **Remotion + recipe.json + 36 MG 组件 + props-driven 合成 + MultiSceneVideo** |
| 配方系统 | 无 | **recipe.json (VST schema 单一真相源)** |
| 动效工程 | 无 | **design-tokens + motion/primitives.ts (纯函数)** |
| MG 组件 | ~10 个 | **36 个 (扁平结构, 18 注册到 ScriptDrivenVideo)** |
| 合成 | ViralVideo + ScriptDriven | **+ ProductPromo + SparkPromo + StyleDrivenVideo + MultiSceneVideo** |
| 结构验证 | 无 | **measure_structure.py (6 指标 × 18 检查点)** |
| 补全策略 | 5 种 (A-E) | **6 种 (A-F, +LLM 编排)** |

---

<a id="1"></a>
## 1. 系统总体架构

### 1.1 官方四步法 → VST 五阶段

PPT 给出的官方技术路径:**结构解析与定义 → 经验沉淀与协议化 → 原子化拆解与重组 → 新视频生成**。VST 映射为五阶段,中间两步加重笔墨:

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  S1 样例    │ → │  S2 结构    │ → │  S2.5 知识  │ → │  S3 素材    │ → │  S4 结果    │
│  理解       │   │  抽取       │   │  库沉淀⭐   │   │  适配 ⭐    │   │  生成       │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
                                          │              ↑
                              自动积累原子/模块/模式      │
                                          │       (含缺口识别 & 6 种补全)
                                          ▼
                                   ┌──────────────┐
                                   │  Knowledge   │
                                   │  Base        │
                                   │ (SurrealDB)  │
                                   └──────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │ recipe.json │ ← VST schema 单一真相源
                                    │ (结构配方)   │
                                    └─────────────┘
─────────────────────────────────────────────────────────────────────
横向能力 A: 迁移过程可视化(10 分)
横向能力 B: 多版本生成(4 分)
横向能力 C: 人机协同(降级版,8 分主线 + 加分项)
```

### 1.2 模块职责清单

| 模块 | 输入 | 输出 | 关键技术 | 评分对位 |
|---|---|---|---|---|
| S1 样例理解 | 样例视频(文件) | shot 列表 + 场景描述 + 音频特征 | scenedetect + librosa + MiMo-V2.5 | 任务 1 (5 分) |
| S2 结构抽取 | S1 输出 | `StructureTemplate.json` | 三步流水线: ASR(faster-whisper) + 规则推断 + VLM 微调(3 prompt 并发) | 任务 2 (10 分) |
| **S2.5 知识库沉淀** | S2 输出 | 累积式 atom/module/pattern 库 | LLM 归纳 + SurrealDB + 入图 Agent | 加分项核心 |
| S3 素材适配 | 用户素材 + Pattern | 缺口报告 + 补全方案 | VLM 素材标注 + 5 步识别 + 6 种策略(A-F) | 任务 5 + 6 (20 分) + 任务 11 (8 分) |
| S4 结果生成 | recipe.json + config + 素材 | mp4 | Remotion props-driven 合成 + FFmpeg | 任务 4 (10 分) + 任务 10 (4 分) |
| 横向 A 可视化 | 全流程数据 | React 可视化界面 | React + force-graph | 任务 7 (10 分) |
| 横向 B 多版本 | 同输入 | 多种风格视频 | recipe.json theming + 不同 config | 任务 10 (4 分) |
| 横向 C 协同 | 自然语言指令 | template patch + 重渲染 | LLM 编排 | 任务 12-13 (8 分 + 加分) |

### 1.3 H5 极简闭环(官方明确的最低标准)

```
[H5 UI]
 ① 用户上传 1-N 个样例视频
 ② 系统解析样例结构(自动)
 ③ 用户输入新主题/商品/素材
 ④ 系统生成新视频(自动)
 ⑤ 用户下载 mp4
```

**全自动,无人工微调环节**。W1 末必须达到这个最低标准。

---

<a id="2"></a>
## 2. 视频结构的形式化定义

### 2.1 六维度映射

| 官方层级 | VST 维度 | 字段示例 |
|---|---|---|
| 脚本/段落结构 | Narrative | hook_type, build_pattern, cta_type |
| 节奏结构 | Temporal | total_duration, phase_breakdown_pct, shots_per_second, energy_curve |
| 节奏结构 | Visual | avg_shot_length, shot_size_distribution, face_prominence, color_palette |
| 节奏结构 | Audio | bpm, beat_alignment_strength, voice_music_ratio, energy_envelope |
| 包装结构 | Text/Caption | caption_density_per_sec, font_style, color, position, emoji_pattern |
| 包装结构 | Packaging | transition_types, sticker_density, title_bar_style, b_roll_density, 3d_elements |

### 2.2 `StructureTemplate.json` 完整 Schema

```typescript
// types/StructureTemplate.ts
import { z } from "zod";

export const HookType = z.enum([
  "悬念_反问句", "利益_直接", "反转_期待落差",
  "冲突_对立", "否定_常识", "数字_震惊", "故事_钩子"
]);

export const BuildPattern = z.enum([
  "痛点列举_方案展示_效果对比",
  "对比展示_揭示原因",
  "教程演示_步骤拆解",
  "故事推进_悬念加深",
  "数据论证_权威背书"
]);

export const CtaType = z.enum([
  "限时优惠", "社会认同", "直接索取", "紧迫感_库存",
  "免费试用", "比较取胜"
]);

export const PhaseSchema = z.object({
  phase: z.enum(["hook", "build", "payoff_cta"]),
  duration_pct: z.tuple([z.number(), z.number()]),
  shot_count_range: z.tuple([z.number(), z.number()]),
  avg_shot_length_s: z.number(),
  required_shot_types: z.array(z.string()),
  caption_style: z.object({
    font: z.string(),
    color: z.string(),
    size: z.enum(["small", "medium", "large", "xlarge"]),
    position: z.enum(["top", "center", "bottom_third", "center_with_box"]),
    animation: z.enum(["typewriter_fast", "fade_in", "slide_up", "bounce", "static"])
  }),
  audio_energy: z.enum(["low", "medium", "medium_rising", "high", "peak_to_resolution"]),
  bgm_role: z.string()
});

export const StructureTemplateSchema = z.object({
  template_id: z.string(),
  source_videos: z.array(z.string()),
  category: z.string(),
  duration_range: z.tuple([z.number(), z.number()]),
  
  narrative: z.object({
    hook_type: HookType,
    build_pattern: BuildPattern,
    cta_type: CtaType
  }),
  
  timeline: z.array(PhaseSchema),
  
  audio_template: z.object({
    bpm_range: z.tuple([z.number(), z.number()]),
    beat_align_strength: z.enum(["weak", "medium", "strong"]),
    energy_curve: z.enum(["flat", "rising", "rising_then_climax", "wave"])
  }),
  
  packaging: z.object({
    transitions: z.array(z.string()),
    sticker_density_per_sec: z.number(),
    title_bar: z.object({
      style: z.string(),
      appears_at_phases: z.array(z.string())
    }),
    cover_style: z.string(),
    use_3d_elements: z.boolean().optional()
  }),
  
  transferability: z.object({
    best_for_verticals: z.array(z.string()),
    avoid_verticals: z.array(z.string())
  }),
  
  provenance: z.object({
    extracted_from: z.array(z.string()),
    extraction_date: z.string(),
    version: z.number(),
    times_used: z.number()
  })
});

export type StructureTemplate = z.infer<typeof StructureTemplateSchema>;
```

`provenance` 字段是**知识库可追溯性**的关键——每个 pattern 知道自己从哪儿来、被用了几次。

---

<a id="3"></a>
## 3. 剪辑技巧知识库(三层)

> 这是 VST 拿下"沉淀的知识库"评分线 + 多个加分项的核心模块。

### 3.1 三层结构与对应粒度

```
┌──────────────────────────────────────────────────────────┐
│  Pattern Library  (模式库) — 完整爆款配方                  │
│  ─ StructureTemplate.json (§2.2 schema)                    │
│  ─ 5-10 个验证过的爆款模式:                                │
│      美妆带货 / 数码评测 / 家居种草 / 食品 / 知识口播       │
└──────────────────────────────────────────────────────────┘
                          ▲
                          │ 由多个 module 组合而成
                          │
┌──────────────────────────────────────────────────────────┐
│  Module Library  (模块库) — phase 级别可复用单元           │
│  ─ hook_modules:    悬念反问 / 利益直接 / 反转开场 ...     │
│  ─ build_modules:   痛点列举 / 对比展示 / 教程演示 ...     │
│  ─ cta_modules:     限时优惠 / 社会认同 / 直接索取 ...     │
│  目标 W2 末:每类 module 3-5 个,总计 ~15 个                │
└──────────────────────────────────────────────────────────┘
                          ▲
                          │ 由多个 atom 组合而成
                          │
┌──────────────────────────────────────────────────────────┐
│  Atomic Library  (原子库) — 最小可复用单元                 │
│  ─ shot_atoms:      face_closeup / product_zoom_in /      │
│                     hand_demonstrate / before_after ...    │
│  ─ caption_atoms:   typewriter_yellow / bouncing_red /    │
│                     slide_in_white / handwriting ...      │
│  ─ transition_atoms:whip_pan / match_cut / speed_ramp /   │
│                     glitch / flash ...                    │
│  ─ sticker_atoms:   countdown / price_tag / arrow_pop /   │
│                     sparkle / focus_circle ...            │
│  ─ 3d_atoms:        product_360_rotation / price_card_flip│
│                     text_burst_3d / gift_box_open ...     │
│  目标 W2 末:30-50 个 atom,其中 5-8 个 3D atom             │
└──────────────────────────────────────────────────────────┘
```

### 3.2 数据库表结构(原始设计, 已迁移到 SurrealDB)

> **注意**: 实际实现使用 SurrealDB (嵌入式图+向量) + BGE-M3 embedding, 通过 `kb/graph_backend.py` 抽象层访问。
> 以下 SQLite schema 为原始设计文档, 保留供参考。

```sql
-- knowledge_base.db

CREATE TABLE atoms (
  atom_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,                 -- shot/caption/transition/sticker/3d
  category TEXT,                       -- hook/build/payoff
  description TEXT,
  remotion_component TEXT NOT NULL,    -- 对应的 React 组件名
  required_inputs_json TEXT,
  fallback_strategy TEXT,
  compatible_phases_json TEXT,
  duration_range_json TEXT,
  energy_level TEXT,
  visual_impact_score REAL,
  tech_stack_json TEXT,                -- ["@remotion/three"] 等
  examples_from_json TEXT,
  appearance_count INTEGER DEFAULT 0,
  engagement_correlation REAL,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE modules (
  module_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,                  -- phase_module
  phase TEXT NOT NULL,                 -- hook/build/cta
  narrative_pattern TEXT,
  duration_range_json TEXT,
  atomic_composition_json TEXT,        -- [{"atom_id":..., "weight":...}]
  script_template TEXT,
  examples_json TEXT,
  best_for_verticals_json TEXT,
  appearance_count INTEGER DEFAULT 0,
  created_at TEXT
);

CREATE TABLE patterns (
  template_id TEXT PRIMARY KEY,
  category TEXT,
  full_json TEXT NOT NULL,             -- 完整 StructureTemplate.json
  best_for_verticals_json TEXT,
  appearance_count INTEGER DEFAULT 1,
  engagement_correlation REAL,
  provenance_videos_json TEXT,
  created_at TEXT
);

CREATE TABLE generation_log (
  log_id TEXT PRIMARY KEY,
  template_id_used TEXT,
  user_input_json TEXT,
  gap_report_json TEXT,
  output_video_path TEXT,
  created_at TEXT,
  FOREIGN KEY (template_id_used) REFERENCES patterns(template_id)
);
```

### 3.3 知识库的累积机制(每次处理样例自动写库)

```python
# kb/accumulator.py 伪代码
def accumulate_from_sample(video_url: str, kb: KnowledgeBase):
    # 1. S1 理解
    shots = pyscenedetect_split(video_url)
    captions = [mimo_vlm_caption(s) for s in shots]
    audio = librosa_analyze(video_url)

    # 2. S2 抽取
    template = mimo_extract_structure(shots, captions, audio)
    
    # 3. 检查 Pattern Library:这个 pattern 是新的还是已有的?
    similar = kb.find_similar_pattern(template, threshold=0.85)
    if similar:
        kb.increment_appearance(similar.template_id)
        kb.merge_provenance(similar.template_id, video_url)
    else:
        kb.insert_pattern(template)
    
    # 4. 拆解到 module 级
    for phase in template.timeline:
        module = identify_or_create_module(phase, kb)
        kb.upsert_module(module)
        
        # 5. 拆解到 atom 级
        for shot_idx, shot in enumerate(phase.shots):
            atoms = decompose_to_atoms(shot, captions[shot_idx], audio)
            for atom in atoms:
                if not kb.has_atom_similar(atom):
                    kb.insert_atom(atom)
                    # 同时生成 Remotion 组件骨架
                    generate_remotion_component_skeleton(atom)
                kb.increment_atom_appearance(atom.atom_id)
```

**这套机制做出来 = "沉淀的剪辑技巧知识库"的实体证据**。答辩时打开 SurrealDB 前端可视化给评委看图谱内容,直接锁定加分项。

### 3.4 知识库检索(新视频生成时使用)

```python
# kb/template_store.py 伪代码
def retrieve_pattern_for_topic(topic: str, vertical: str, kb: KnowledgeBase):
    # SurrealDB 向量搜索 + 结构化查询
    candidates = kb.search_patterns(
        query=topic,
        vertical=vertical,
        limit=3,
        order_by="appearance_count DESC, engagement_correlation DESC",
    )

    # LLM 二次排序(综合 topic 语义相似度)
    return mimo_rerank(candidates, topic)
```

---

<a id="4"></a>
## 4. 素材缺口处理(P0 / 20 分)

### 4.1 缺口识别:5 步算法

```python
# gap/detector.py 伪代码
def identify_gaps(template: StructureTemplate, user_materials: List[Material]) -> List[Gap]:
    gaps = []
    for phase in template.timeline:
        required_types = set(phase.required_shot_types)
        required_duration_s = (phase.duration_pct[1] - phase.duration_pct[0]) / 100 \
                              * template.duration_range[1]
        
        # Step 1: 类型覆盖检查
        candidate_materials = [m for m in user_materials 
                               if set(m.tagged_types) & required_types]
        available_types = set().union(*[m.tagged_types for m in candidate_materials])
        missing_types = required_types - available_types
        
        # Step 2: 时长覆盖检查
        available_duration = sum(m.usable_duration for m in candidate_materials)
        duration_shortfall = max(0, required_duration_s - available_duration)
        
        # Step 3: 镜头数检查
        shot_count_shortfall = max(0, phase.shot_count_range[0] - len(candidate_materials))
        
        # Step 4: 质量检查(模糊/分辨率/构图)
        low_quality = [m for m in candidate_materials if m.quality_score < 0.6]
        
        # Step 5: 输出结构化 gap 报告(含 LLM 影响说明)
        if missing_types or duration_shortfall > 0 or shot_count_shortfall > 0:
            gaps.append({
                "phase": phase.phase,
                "missing_shot_types": list(missing_types),
                "duration_shortfall": duration_shortfall,
                "shot_count_shortfall": shot_count_shortfall,
                "low_quality_count": len(low_quality),
                "severity": compute_severity(missing_types, duration_shortfall, shot_count_shortfall),
                "impact_on_video": doubao_explain_impact(phase, missing_types)
            })
    return gaps
```

**`impact_on_video` 字段**是评分点 5 从 4-5 分晋升 6-8 分的关键——用 LLM 自然语言生成"**缺少商品特写,会让中段卖点缺乏说服力,预估完播率下降 ~15%**"。

### 4.2 补全策略:全做 5 种 + 决策树自动选

```
缺口出现 → 判断 gap 类型与严重度
│
├─ severity=HIGH & missing_shot_types={hook_attention_grabber}
│      └→ Strategy A: 结构重排
│            LLM 输入 (gap + template),输出 patched template
│            (跳过 hook,直接 build 开场;或 hook 改纯字幕)
│
├─ missing_shot_types ⊆ packagable_types & 有商品图
│      └→ Strategy C: 包装补全 (优先,因为视觉冲击力强)
│            Remotion 卖点卡片 / 标题条 / 贴纸组件库
│
├─ missing_shot_types = {usage_scenario}, 用户完全无场景图
│      └→ Strategy D: AIGC 生成补全(本地)
│            Gemini Imagen 3 生图 + Remotion 动画化
│
├─ shot_count_shortfall ≥ 2 & 用户素材质量好
│      └→ Strategy E: 现有素材重组复用
│            FFmpeg 变换工具集(crop / Ken Burns / 反向 / 变速)
│
└─ low_quality 占多数
       └→ Strategy B: 文案/字幕补全
            画面表达不够,加大字幕信息密度
```

### 4.3 五种策略的实现细节

#### Strategy A: 结构重排
```python
def strategy_a_restructure(template, gap):
    prompt = f"""原模板:{template}
    缺口:{gap}
    请输出修改后的 timeline,跳过强依赖缺失类型的 phase,
    并相应调整其他 phase 的 duration_pct。
    返回纯 JSON。"""
    return doubao_call(prompt)
```

#### Strategy B: 文案/字幕补全
- 利用 Remotion 大字字幕组件承载缺失画面的语义
- 例:缺产品特写 → 满屏出一行"水洗 3 万次不掉色"+ 商品名

#### Strategy C: 包装补全(最常用)
- Remotion 组件库:`<TitleBar>`, `<PriceCard>`, `<SellingPointCard>`, `<Sticker>`
- LLM 选择哪个模板填进哪个 phase

#### Strategy D: AIGC 生成补全(本地)
```python
def strategy_d_aigc(gap, product_image):
    # 1. ComfyUI 生静态场景图
    workflow = load_comfyui_workflow("product_in_scene.json")
    workflow.set_input("product_image", product_image)
    workflow.set_input("prompt", "保温杯在办公桌上,清晨阳光,极简风格")
    scene_image = comfyui_run(workflow)
    
    # 2. Remotion 动画化
    return {
        "remotion_component": "KenBurnsScene",
        "props": {
            "image_url": scene_image,
            "zoom_start": 1.0, "zoom_end": 1.15,
            "duration_s": 2.5,
            "overlay": "light_leak"
        }
    }
```

#### Strategy E: 素材重组复用
```python
def strategy_e_recombine(material, needed_count):
    """同一段素材生出 N 个不同 "镜头" """
    variants = []
    variants.append({"transform": "original"})
    variants.append({"transform": "crop_60_center"})        # 中景版
    variants.append({"transform": "crop_30_subject_zoom"})  # 特写版 + Ken Burns
    variants.append({"transform": "slow_motion_0.5x"})      # 变速版
    variants.append({"transform": "mirror_horizontal"})     # 镜像版
    return variants[:needed_count]
```

### 4.4 决策卡片 UI(评委必看的可视化)

每个 gap 在前端展示一张可交互的决策卡片:

```
┌──────────────────────────────────────────────┐
│ 缺口 #1                                       │
│ phase: hook  |  severity: HIGH               │
│ ─────────────────────────────────────────── │
│ 🔍 检测:缺少"高吸引力开场镜头"               │
│                                              │
│ 💡 影响:开头无法快速建立悬念,                │
│      预估完播率下降 12-18%                    │
│                                              │
│ ✅ 已采用策略:Strategy C (包装补全)           │
│  → 生成"满屏大字 + 商品定格放大"开场          │
│                                              │
│ 🔄 备选策略:                                   │
│  ○ Strategy A 结构重排(改用 build 开场)      │
│  ○ Strategy D AIGC 生成(ComfyUI 生场景图)   │
│ [切换为其他策略]                              │
└──────────────────────────────────────────────┘
```

**这种卡片** = 任务 6 补全(12 分) + 任务 7 可视化(10 分) + 加分项可解释性 + 任务 12 人工可调 8 分**四连击**。

---

<a id="5"></a>
## 5. Remotion 渲染层与 3D 能力

### 5.1 为什么选 Remotion(不选 HyperFrames)

| 维度 | Remotion ✅ | HyperFrames |
|---|---|---|
| 生态成熟度 | 2021 年发布,数百万用户 | 2026 年发布,早期 |
| React 同栈 | 完美(你前端就是 React) | 需要 iframe 嵌入 |
| 3D 支持 | **官方 `@remotion/three`** + R3F + `useVideoTexture` + Spline 集成 | 需手动接 Three.js + `__hfThreeTime` |
| 实时预览 | `<Player>` 组件可嵌入 React 编辑器 | 独立 preview server |
| 文档与示例 | 极丰富 | 较少 |
| License | 个人/3 人内免费 | Apache 2.0 完全免费 |

**HyperFrames 在答辩里这么讲**:"我们调研过 HTML-native 路线,选择 Remotion 是因为 React 生态成熟度更高、官方 3D 支持更完善、`<Player>` 可实时嵌入我们的编辑器做无缝预览。HTML-native 路线的优势在 AI 自动写作场景,但我们的核心创新在显式的知识库与原子组件抽象,这与 React 组件的对齐更天然。"

### 5.2 recipe.json — VST schema 单一真相源

recipe.json 是 VST 的核心抽象：把一个视频的完整配方编码为一个 JSON 文件，同时作为：
- **手工样例**：证明 VST 能自动生成这类 schema
- **Remotion 合成的输入**：props-driven，换 config 即出不同视频
- **结构保真度实验的基准**：measure_structure.py 从中提取 6 个指标

```jsonc
{
  "meta":    { "fps", "width", "height", "durationFrames" },
  "tokens":  { "colors", "glass", "fonts", "spacing", "shadows" },
  "motion":  { /* 命名原语库 — 对应 motion/primitives.ts */ },
  "components": { /* 组件 → props 映射 */ },
  "timeline": [ /* 每段 = {component, startFrame, durationFrames, props} */ ],
  "theming": { /* 换题材只需替换此节 */ }
}
```

### 5.3 Motion Primitives — 纯函数动效库

`web/src/motion/primitives.ts` 导出纯动画函数，与 recipe.json.motion 一一对应：

| 原语 | 函数签名 | 用途 |
|------|---------|------|
| wordReveal | `(frame, fps, wordIndex, params) → {opacity, transform}` | 逐词揭示 |
| typewriterState | `(frame, textLength, params) → {charsVisible, cursorVisible}` | 打字机状态 |
| glassCardStyle | `(frame, fps, params) → {opacity, transform}` | 玻璃卡片入场 |
| floatingEntryStyle | `(frame, fps, delay, preset) → {opacity, scale, translateY, rotate}` | 浮动 mockup |
| marqueeOffset | `(frame, textWidth, params) → number` | 水平跑马灯 |
| gradientShimmerPosition | `(frame, params) → string` | 渐变光泽扫描 |
| logoRevealStyle | `(frame, fps, params) → {scale, glowBlur}` | Logo 弹入 |
| glowTrailProgress | `(frame, delay, params) → number` | 发光粒子路径进度 |
| perspectiveTiltStyle | `(frame, fps, delay) → {scale, rotateY}` | 3D 透视倾斜 |

### 5.4 MG 组件库 (23 个)

组件分三层：原始通用组件(10) → Promo 产品宣传片系列(9) → Spark Magnific 风格系列(4)。所有组件遵循 design-tokens 约束，无硬编码颜色/字号。

### 5.5 Props-driven 合成

ProductPromo 和 SparkPromo 均为 props-driven：
```tsx
interface ProductPromoProps { config?: ProductPromoConfig; }
// DEFAULT_PROMO_CONFIG 是 WriteFlow 主题
// 换 config 即生成不同品牌/题材的视频
```

### 5.6 结构保真度实验

`scripts/measure_structure.py` 从 recipe.json 提取 6 个结构指标（18 个检查点），用于量化"recipe 是否捕获了爆款结构"：
- beatTimingDistribution (7)
- motionDensity (1)
- attentionCurve (7)
- motionDiversity (1)
- transitionInterval (1)
- headTailRatio (1)

判定标准：A(<10%偏差) / B(<20%) / C(<30%) / D(不可迁移)

### 5.7 核心数据流:recipe.json + Config → Remotion → MP4

```tsx
// ProductPromo — props-driven 合成
import { ProductPromo, DEFAULT_PROMO_CONFIG } from './compositions/ProductPromo';

// 方式 1: 使用默认 WriteFlow 配置
<Composition id="ProductPromo" component={ProductPromo} defaultProps={{ config: DEFAULT_PROMO_CONFIG }} />

// 方式 2: 换 config 生成不同视频
const customConfig: ProductPromoConfig = {
  brand: 'Layout.dev',
  hookText: 'What if one prompt could build your side hustle?',
  featuresPhase1: [{ label: 'Nike', icon: '👟', description: 'Premium collection' }],
  // ...
};
<Composition id="ProductPromo" component={ProductPromo} defaultProps={{ config: customConfig }} />
```

```tsx
// SparkPromo — 60fps 横版，Magnific 风格
// 12 beats: intro → stepping up → level up → pro workflows → photo wall
//           → feature list → geometric → headlines → expanding lines → logo
<Composition id="SparkPromo" component={SparkPromo}
  durationInFrames={1860} fps={60} width={1280} height={720} />
```

### 5.3 3D Atom 示例:商品 360° 旋转展示

```tsx
// atoms/3d/ProductRotation360.tsx
import { ThreeCanvas } from '@remotion/three';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { useGLTF } from '@react-three/drei';

export const ProductRotation360: React.FC<{
  glbUrl: string;
  durationS: number;
}> = ({ glbUrl, durationS }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  
  const totalFrames = durationS * fps;
  const rotation = (frame / totalFrames) * Math.PI * 2;  // 完整 360°
  
  return (
    <ThreeCanvas width={width} height={height}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 7.5]} intensity={1.2} />
      <Product3D url={glbUrl} rotation={rotation} />
    </ThreeCanvas>
  );
};

function Product3D({ url, rotation }: { url: string; rotation: number }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} rotation={[0, rotation, 0]} />;
}
```

### 5.4 3D 资源策略:不自己建模,用 CC0 资源

- [Sketchfab](https://sketchfab.com)(筛 CC0)
- [Poly Haven](https://polyhaven.com)
- [Quaternius](https://quaternius.com)
- 在线建简单 3D:[Spline](https://spline.design) → 导出 R3F 代码

**自建 Blender 模型不在 4 周内做**。如果用户上传的商品在 .glb 库里找不到对应,自动降级 `fallback_strategy` → 2D Ken Burns。

### 5.5 5-8 个 3D 原子规划

| atom_id | 用途 | 资源需求 |
|---|---|---|
| `atom_3d_product_360` | 商品 360° 旋转 | .glb 模型(杯/瓶/盒/手机) |
| `atom_3d_price_card_flip` | 3D 价格牌翻转 | 纯几何,无外部资源 |
| `atom_3d_text_burst` | 3D 立体大字爆出 | troika-three-text |
| `atom_3d_compare_split` | 左右 3D 对比 | 两个 .glb 模型 |
| `atom_3d_gift_box_open` | 礼盒开盒(节日大促) | .glb 礼盒模型 |
| `atom_3d_camera_flythrough` | 相机环绕飞跃 | R3F + drei OrbitControls |
| `atom_3d_data_viz_bar` | 3D 柱状图卖点 | 纯几何 |
| `atom_3d_phone_with_video` | 3D 手机嵌入用户视频 | `useVideoTexture` |

**最后一个 `atom_3d_phone_with_video` 价值极高**——用 `useVideoTexture()` 把用户上传的视频贴到 3D 手机屏幕上,做出"商品测评展示"效果,**直接复用 Remotion React Three Fiber 官方模板**。

---

<a id="6"></a>
## 6. 本地部署架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend  (React + TypeScript + Vite)                   │
│  - 知识库浏览器 (force-graph) + RemotionPlayer 预览       │
│  端口:5173                                                │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP
┌────────────────────┴────────────────────────────────────┐
│  Backend Orchestrator  (Node.js + Express)               │
│  - 流水线编排 + KB 代理                                   │
│  端口:3000                                                │
└──────┬──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  Python FastAPI  (端口 8000)                              │
│  ├─ S1 视频分析 (scenedetect + librosa + MiMo-V2.5)     │
│  ├─ S2 结构提取 (ASR + 规则推断 + VLM 微调)              │
│  ├─ S3 缺口检测 + 6 种补全策略                            │
│  ├─ LLM 动画编排 (两步 LLM + ScriptDriven)               │
│  └─ 知识图谱 (SurrealDB 嵌入式)                           │
└─────────────────────────────────────────────────────────┘
       │
       ├──> MiMo-V2.5-pro (代理 API, 动画编排/创意推理)
       ├──> MiMo-V2.5 (代理 API, 图片/视频理解)
       └──> Gemini Imagen 3 (生图)

┌─────────────────────────────────────────────────────────┐
│  SurrealDB  (嵌入式, ./data/graph.db)                     │
│  - 4 节点: Pattern / Module / Atom / Vertical             │
│  - 3 边: composed_of / built_from / best_for              │
│  - BGE-M3 1024 维 HNSW 向量索引                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  File Storage  (./data)                                  │
│  - uploads/      用户上传                                  │
│  - output/       渲染输出 (mp4)                            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Recipe Schema  (./recipe.json)                          │
│  - VST 单一真相源: meta/tokens/motion/components/timeline │
│  - props-driven → 换 config 出不同视频                    │
└─────────────────────────────────────────────────────────┘
```

### 6.1 一键启动脚本

```bash
# scripts/start.sh
#!/bin/bash
set -e

# 1. 启动 ComfyUI(假设已 git clone)
cd ./vendor/ComfyUI && python main.py --port 8188 &
COMFY_PID=$!

# 2. 启动 vLLM with Qwen2.5-VL-7B
vllm serve Qwen/Qwen2.5-VL-7B-Instruct --port 8001 &
VLLM_PID=$!

# 3. 启动 Python FastAPI
cd ./services/python && uvicorn main:app --reload --port 8000 &
PY_PID=$!

# 4. 启动 Node.js Orchestrator
cd ./services/node && npm run dev &
NODE_PID=$!

# 5. 启动前端
cd ./web && npm run dev &
WEB_PID=$!

echo "All services started."
echo "Frontend: http://localhost:5173"
echo "Node API: http://localhost:3000"
echo "Python API: http://localhost:8000"
echo "vLLM: http://localhost:8001"
echo "ComfyUI: http://localhost:8188"

wait $WEB_PID
```

### 6.2 README 必须提供的部署步骤

```markdown
# VST 本地部署

## 前置依赖
- Node.js >= 22
- Python >= 3.10
- FFmpeg
- CUDA 12.x + GPU >= 24GB(运行 Qwen2.5-VL-7B 与 ComfyUI)

## 一键部署
git clone <repo>
cd vst
./scripts/install.sh      # 装所有依赖
./scripts/download_models.sh   # 下 Qwen2.5-VL + SDXL
./scripts/start.sh        # 启动全部服务
```

---

<a id="7"></a>
## 7. 完整技术栈清单

| 层 | 选型 | 用途 |
|---|---|---|
| **主 LLM + VLM** | **MiMo-V2.5-pro**(代理 API) | 动画编排/创意推理 (文本) |
| **VLM (图片/视频)** | **MiMo-V2.5**(代理 API) | S1 场景分析 + S2 结构提取 + S3 素材标注 |
| **图片生成** | **Gemini Imagen 3** | 策略 D AIGC 生图 |
| **镜头切分** | PySceneDetect + scenedetect | AdaptiveDetector |
| **ASR** | faster-whisper (多语言) | 字幕转写 (Stage A) |
| **音频分析** | librosa | BGM 节拍、能量曲线 |
| **视频渲染** | **Remotion v4 + @remotion/three + GSAP + Lottie** | MG 动画 + 3D + 参数化合成 |
| **配方系统** | **recipe.json** + motion primitives | VST schema 单一真相源 + 纯函数动效库 |
| **MG 组件库** | **23 个 Remotion 组件** | Promo(9) + Spark(4) + 原始(10) |
| **前端** | React + TypeScript + Vite + Zustand + react-force-graph-2d | 知识库浏览器 + RemotionPlayer |
| **后端 Orchestrator** | Node.js + Express + tsx | 任务编排 |
| **后端 Heavy Lifting** | Python FastAPI + Pydantic | 视频理解、LLM 调度、知识库 |
| **数据库** | **SurrealDB**(嵌入式, 图+向量) + BGE-M3 (1024 维 HNSW) | 知识图谱 4 节点 3 边 |
| **打包** | Docker Compose (3 服务 + 1 seed job) | 一键部署 |

---

<a id="8"></a>
## 8. 4 周路线图(逐天对齐评分)

### Week 1 — H5 极简闭环(对齐官方最低标准)

| Day | 任务 | 评分锁定 |
|---|---|---|
| **D1** | 项目骨架:repo init + Node/Python/前端三服务跑通 hello world + Doubao API 跑通 | — |
| **D2** | S1 样例理解:PySceneDetect 切镜头、Qwen2.5-VL caption、Paraformer 转字幕 | 任务 1 (5 分) |
| **D3** | S2 结构抽取:LLM few-shot 输出 `StructureTemplate.json`,3 类结构全覆盖 | 任务 2 (10 分) |
| **D4** | Remotion 项目 init + 基础 phase 组件(Hook/Build/Cta 各 1 个最简版) | — |
| **D5** | S4 简单生成:Remotion + FFmpeg 输出 MP4 | 任务 4 (10 分) |
| **D6** | S3 基础素材分配(无缺口处理,假设素材完整) | — |
| **D7** | 端到端跑通 H5 闭环:上传→解析→输入主题→生成→下载 | 任务 4 + 8 (10+6 分) |

**W1 末状态**:H5 极简闭环已通,基础分约 30 分锁定

---

### Week 2 — 知识库构建(v3 核心差异化)⭐

| Day | 任务 | 评分锁定 |
|---|---|---|
| **D8** | SQLite schema 设计 + 3 层 JSON Schema (Zod) + CRUD 包装层 | — |
| **D9** | Atom 库构建:抽样 20 个爆款视频,手工 + LLM 提取 30 个 atom,每个对应 Remotion 组件骨架 | 任务 9 部分 |
| **D10** | 3D Atom 库:实现 5-8 个 3D 原子(Product 360 / Price Card Flip / Text Burst / Compare Split / Gift Box) | 任务 9 + 加分项视觉完成度 |
| **D11** | Module 库:基于 atom 组合 hook/build/cta 各 3-5 个 module | — |
| **D12** | Pattern 库:沉淀 5-10 个完整 pattern,验证可被新主题复用 | — |
| **D13** | 自动累积机制(`accumulate_from_sample`)+ 知识库浏览器 UI | 加分项"沉淀知识库" |
| **D14** | 检索机制(`retrieve_pattern_for_topic`)+ 集成到主流程 | — |

**W2 末状态**:**这是 v3 的核心差异化模块**,答辩里"我们的系统有沉淀的剪辑技巧知识库"这一段最让评委印象深刻

---

### Week 3 — 素材缺口处理 + 多版本

| Day | 任务 | 评分锁定 |
|---|---|---|
| **D15** | 缺口识别 5 步算法 + `impact_on_video` LLM 影响说明 | 任务 5 (8 分) |
| **D16** | 决策卡片 UI(前端 + 后端 socket) | 任务 7 部分 + 加分 |
| **D17** | Strategy A (结构重排) + Strategy B (字幕补全) | 任务 6 部分 |
| **D18** | Strategy C (Remotion 包装补全:标题条/卖点卡/贴纸 ~10 个组件) | 任务 6 + 任务 9 |
| **D19** | Strategy D (本地 ComfyUI 集成 + Remotion 动画化) | 任务 6 满分 (12 分) + 加分 AIGC 融合 |
| **D20** | Strategy E (FFmpeg 素材重组工具集) | 任务 6 |
| **D21** | 多版本生成:高点击/高转化/高节奏/**高质感 3D 版**(4 个版本) | 任务 10 (4 分) |

**W3 末状态**:核心差异化模块完成,核心评分项几乎全部到位

---

### Week 4 — 可视化 + 真实素材 + 答辩材料

| Day | 任务 | 评分锁定 |
|---|---|---|
| **D22** | 迁移过程可视化完整版:样例侧栏 + 映射线 + 缺口高亮 + 结果右栏 | 任务 7 (10 分) |
| **D23** | 真实素材适配深化:景别分类 + 高光筛选 + 槽位推荐 | 任务 11 (8 分) |
| **D24** | 自然语言改片(简单版):输入框 + Doubao patch template | 任务 13 (加分) |
| **D25** | 录 5 个 Demo Case 视频 | — |
| **D26** | 写项目文档(AI 架构图 + 工具协议 + 安全边界 + AI 使用说明) | 必交付物 |
| **D27** | 仓库整理 + Docker Compose + README | 加分项工程质量 |
| **D28** | 压测 + bug 修复 + 答辩 PPT | — |

### 总分预算

| 维度 | 分数预期 |
|---|---|
| 基础闭环 25 分 | 23-25 |
| 素材缺口 20 分 | 18-20 |
| 结果展示 20 分 | 16-18 |
| 进阶能力 20 分 | 16-18 |
| 人机协同+完成度 15 分 | 11-13 |
| 加分项(知识库、可解释性、AIGC 融合、包装链路、工程质量) | **8-10** |
| **总计** | **92-104** |

---

<a id="9"></a>
## 9. Claude Code 协作工作流

> 见单独的《Claude Code 工作流操作手册》,本节只给最关键的项目内文件配置。

### 9.1 项目根目录必备文件

```
vst/
├── CLAUDE.md                   # 项目宪法,Claude Code 自动读取
├── .claude/
│   ├── skills/                 # 自定义 slash command (skills)
│   │   ├── new-atom.md         # /new-atom 创建新原子
│   │   ├── new-module.md       # /new-module 创建新模块
│   │   ├── extract-pattern.md  # /extract-pattern 从样例抽 pattern
│   │   ├── verify-build.md     # /verify-build 验证当前构建
│   │   └── e2e-test.md         # /e2e-test 端到端测试
│   └── settings.local.json
├── docs/
│   ├── spec.md                 # 就是本文档
│   ├── architecture.md         # §6 拆分版
│   └── grading_rubric.md       # §10 完整评分对照
├── services/
│   ├── node/                   # Express orchestrator
│   ├── python/                 # FastAPI heavy lifting
│   └── remotion/               # Remotion 项目
├── web/                        # React 前端
├── kb/                         # 知识库代码
├── scripts/                    # 部署脚本
└── data/                       # 运行时数据
```

### 9.2 `CLAUDE.md` 模板

> 以下是模板。实际 CLAUDE.md 在项目根目录，Claude Code 每次会话自动读取。

```markdown
# CLAUDE.md — VST 项目宪法

## 项目身份
- 项目代号:ViralStructTransfer (VST)
- 完整 spec:见 `docs/spec.md`
- 评分对照:见 `docs/grading_rubric.md`
- 4 周 hackathon,目标 92-104 分(满分 110)

## 三个非协商决策
1. **零外部视频生成 API**:不调用即梦/Seedance/可灵/Sora
2. **Remotion 是渲染层唯一标准**:不引入 Manim、MoviePy 等
3. **必须本地一键部署**

## 技术栈强约束
- LLM + VLM:MiMo-V2.5-pro(编排) + MiMo-V2.5(视觉理解)
- 图片生成:Gemini Imagen 3
- 数据库:SurrealDB(嵌入式,图+向量) + BGE-M3
- 前端:React + TS + Vite + Zustand + Konva.js + RemotionPlayer
- 后端:Node Express(:3000) + Python FastAPI(:8000)
- 渲染:Remotion v4 + @remotion/three + GSAP + Lottie
- 配方:recipe.json (VST schema 单一真相源)

## 编码规范
- TypeScript strict mode,无 `any`
- Python 用类型注解 + Pydantic
- 所有新组件先看 `web/src/components/mg/` 是否已有同类
- Remotion 组件:atom 用 `Atom*`,phase 用 `Phase*`,完整视频 `Renderer*`
- Design Tokens 优先:颜色→PALETTES,字号→FONT_SIZES,间距→SPACING,动效→SPRING/EASE

## 当前进度
- [x] W1 H5 闭环 (D1-D7)
- [x] W2 知识库 (D8-D14)
- [x] W3 缺口处理 + 视觉质量 + 动画编排
- [x] W4 S2 增强 + Docker 部署 + recipe.json schema + 结构保真度实验
```

### 9.3 项目级 skills(`.claude/skills/*.md`)

#### `.claude/skills/extract-pattern.md`
```markdown
---
name: extract-pattern
description: 从一个样例视频抽取 StructureTemplate.json 并落入知识库
---

读取参数指定的视频路径,执行以下步骤:

1. 调用 PySceneDetect 切镜头,记录 shot 边界
2. 对每个 shot 调用 Qwen2.5-VL(http://localhost:8001)生成 caption
3. 调用 Paraformer 转字幕
4. 调用 librosa 提取音频特征
5. 把以上信息汇总,调用 Doubao-Seed 输出 StructureTemplate.json(schema 见 docs/spec.md §2.2)
6. 调用 kb.find_similar_pattern,如果相似度 > 0.85 则 increment_appearance,否则 insert_pattern
7. 把 pattern 拆解为 module 和 atom,分别检查后入库
8. 返回:抽取的 template + 是否新模式 + 入库的 atom 数量

代码组织放在 `kb/extractor/` 下,主入口 `kb/extractor/extract_from_video.py`。
```

#### `.claude/skills/new-atom.md`
```markdown
---
name: new-atom
description: 创建一个新的 atom(含 Remotion 组件骨架 + DB 条目)
---

参数:atom_id, type, category, description

要做的事:
1. 在 `services/remotion/src/atoms/{type}/` 下创建组件文件
2. 组件需要遵循 §5.2 模板,使用 `useCurrentFrame()` 驱动动画
3. 在 `kb/seeds/atoms.jsonl` 追加一条 JSON
4. 跑 `npm run seed:kb` 把新条目同步到 SQLite
5. 在 `services/remotion/src/atoms/{type}/__demos__/` 下创建一个 demo composition 用于预览
6. 运行 `npm run remotion:preview` 让我看到效果

不要修改已有的 atom 文件除非我明确要求。
```

#### `.claude/skills/verify-build.md`
```markdown
---
name: verify-build
description: 验证当前构建状态(tsc / lint / 关键路径 e2e)
---

按顺序执行:
1. `cd web && npm run typecheck`
2. `cd services/node && npm run typecheck`
3. `cd services/remotion && npm run typecheck`
4. `cd services/python && ruff check . && mypy .`
5. 启动所有服务(./scripts/start.sh dev)
6. 调用 e2e 测试脚本 `npm run test:e2e:basic`:上传一个测试样例 → 解析 → 用 mock 商品输入 → 生成视频 → 验证 mp4 存在且时长 > 5s

任何一步失败就打印失败原因并停止。全部通过返回 "ALL GREEN"。
```

更多 skills 见单独《Claude Code 工作流操作手册》。

---

<a id="10"></a>
## 10. 评分对照表 + 加分项设计

### 10.1 评分对照(100 分主体)

| 评分项 | 满分 | VST 设计 | 预期得分 |
|---|---|---|---|
| 1. 样例输入与基础解析 | 5 | S1 + 多样例支持 | 4-5 |
| 2. 结构拆解能力 | 10 | 6 维度全覆盖,3 类结构清晰 | 9-10 |
| 3. 结构迁移生成能力 | 10 | 脚本+分镜+时间线+成片 全 4 项 | 9-10 |
| 4. 素材缺口识别 | 8 | 5 步算法 + LLM 影响说明 | 7-8 |
| 5. 素材缺口补全 | 12 | 5 种策略全做 + 决策树 | 10-12 |
| 6. 迁移过程可视化 | 10 | 完整四区域 UI + 决策卡片 | 8-10 |
| 7. 最终效果展示 | 10 | 5 个 Demo Case + 前后对比 | 8-10 |
| 8. 画面包装能力 | 8 | 字幕+标题条+卖点卡+转场+封面+贴纸 全 6 项 | 7-8 |
| 9. 多版本生成 | 4 | 4 个版本(含 3D 质感版) | 3-4 |
| 10. 真实素材适配 | 8 | 景别+高光+槽位推荐 | 6-8 |
| 11. 人工可调能力 | 8 | 决策卡片切换 + 简单 NL 改片 | 5-7 |
| 12. 创意与产品完成度 | 7 | 知识库 + 3D + Docker | 5-7 |
| **小计** | **100** | | **81-99** |

### 10.2 加分项(上限 10 分)

| 加分项 | VST 设计 | 预期 |
|---|---|---|
| 自然语言改片 | D24 简单版 | +1-2 |
| 真实素材 + AIGC 融合 | Strategy D + E 混用 | +1-2 |
| 结构迁移可解释性 | 知识库浏览器 + 决策卡片 + Pattern provenance | +2-3 |
| 完整画面包装链路 | 6 项包装能力全做 | +1-2 |
| 工程质量/视觉完成度 | Docker + 测试 + 文档 + 3D atom | +2-3 |
| **小计** | | **+7-10** |

**总分预算:88-109**(高位接近满分上限)

---

<a id="11"></a>
## 11. AI 工具使用说明文档(官方强制交付物)

```markdown
# AI 工具使用说明

## 1. 使用的 AI 工具
| 工具 | 用途 | 阶段 |
|---|---|---|
| MiMo-V2.5-pro | 动画编排/创意推理 (文本 LLM) | S2/S3/S4 |
| MiMo-V2.5 | 图片/视频理解 (VLM) | S1/S2/S3 |
| Gemini Imagen 3 | AIGC 生图 (策略 D) | S3 |
| faster-whisper | 多语言 ASR 字幕转写 | S1 (S2 Stage A) |
| Claude Code | 开发期代码辅助 | 全程 |

## 2. 自主设计与实现
- **recipe.json** VST schema 单一真相源 + **motion/primitives.ts** 纯函数动效库
- **6 维度 StructureTemplate Schema** 及三步 S2 流水线(ASR+规则+VLM 微调)
- **三层知识库**(原子/模块/模式, SurrealDB 图+向量)与自动累积机制
- **5 步缺口识别算法** + **6 种补全策略**(A-F)及决策树
- **23 个 Remotion MG 组件**(Promo 9 + Spark 4 + 原始 10)
- **Props-driven 合成**(ProductPromo + SparkPromo)，换 config 出不同视频
- **Design Tokens** 工程化(字号/配色/间距/easing/spring 预设)
- **结构保真度实验**(measure_structure.py, 6 指标 × 18 检查点)
- 缺口决策卡片 UI 与交互
- 迁移过程可视化
- 本地一键部署架构(Docker Compose)

## 3. 工具协议与安全边界
- API Key 全部走环境变量,不入仓
- 用户素材仅在 ./data/uploads 临时存储,任务结束 24h 后清理
- AIGC 生成内容标注水印(Strategy D 输出添加可见水印)
- ComfyUI workflow 限制使用通用 SDXL 基础模型,不引入定制风格 LoRA
- 不调用任何可能涉及违规内容的生成提示词
- 涉及人脸的素材生成需用户明确确认,不持久化人脸特征
```

---

<a id="12"></a>
## 12. 立即可执行的 Day 0 清单

**在 W1 D1 开工前的准备工作**(预计 4 小时):

1. **跑通 Doubao API**(15 分钟)
   ```bash
   curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $DOUBAO_API_KEY" \
     -d '{"model":"ep-20260508213828-7ntjl","messages":[{"role":"user","content":"返回 JSON: {\"ok\":true}"}]}'
   ```

2. **跑通 Remotion**(30 分钟)
   ```bash
   npx create-video@latest --template=blank
   cd my-video && npm start
   ```

3. **跑通 Remotion + React Three Fiber**(45 分钟)
   ```bash
   npx create-video@latest --template=three
   cd my-video && npm start
   # 看到 3D 手机视频,把官方模板的 .glb 换成 Quaternius 下载的杯子
   ```

4. **本地装 ComfyUI**(60 分钟)
   ```bash
   git clone https://github.com/comfyanonymous/ComfyUI
   cd ComfyUI && pip install -r requirements.txt
   # 下 SDXL base 模型到 models/checkpoints/
   python main.py --port 8188
   ```

5. **下载 10 个抖音爆款样例**(30 分钟)
   - 5 个营销带货(美妆/数码/家居)
   - 3 个剪辑炫酷(Vlog/旅行)
   - 2 个 MG 动画

6. **下载 5 个 CC0 .glb 模型**(15 分钟)
   - Quaternius: 杯子、瓶子、礼盒、手机、耳机

7. **本地装 vLLM + 下 Qwen2.5-VL-7B**(60 分钟,可异步)
   ```bash
   pip install vllm
   vllm serve Qwen/Qwen2.5-VL-7B-Instruct --port 8001
   ```

8. **更新 Claude Code 到 v2.1.139+**(2 分钟)
   ```bash
   npm update -g @anthropic-ai/claude-code
   claude --version
   ```

做完以上,W1 D1 直接开工 0 阻力。

---

## 附录:废弃文档说明

以下早期文档已被本文档完全替代,**请勿混用**:
- `viral_structure_transfer_report.md` (v1) — 思路探索,产品方向不对
- `viral_structure_transfer_report_v2.md` (v2) — 部分内容仍正确但被本文档合并
- `viral_structure_transfer_report_v3_patch.md` (v3 补丁) — 增量内容已并入本文档

如果你在 Claude Code 中工作,**只参考本文档 + CLAUDE.md + 项目级 skills**。

---

*v3 FINAL 完成于 2026 年 5 月 21 日。本文档是项目唯一权威 spec。*
