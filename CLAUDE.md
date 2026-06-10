# CLAUDE.md — VST 项目宪法

## 项目身份
- 项目代号:ViralStructTransfer (VST)
- 完整 spec:见 `docs/spec.md`
- 4 周 hackathon,目标 92-104 分(满分 110)
- 出题方:剪映 / 字节跳动 AI 全栈挑战赛

## 三个非协商决策(任何情况不可违反)
1. **零外部视频生成 API**:不调用即梦/Seedance/可灵/Sora。需要画面时:用户素材 → Remotion → Gemini Imagen 3 生图 → Remotion 动画化
2. **Remotion 是渲染层唯一标准**:不引入 Manim、MoviePy 等替代。3D 用 `@remotion/three`,不用原生 Three.js HTML
3. **必须本地一键部署**:任何不能本地跑的能力一律不引入

## 技术栈强约束
- 主 LLM + VLM:MiMo-V2.5-pro(通过 MiMo 代理 API `MIMO_API_KEY`,用于动画编排/创意推理)
- VLM(图片/视频输入):MiMo-V2.5(环境变量 `MIMO_VLM_MODEL`,S1 场景分析 + S2 结构提取 + S3 素材标注)
- 图片生成:Gemini Imagen 3(环境变量 `GEMINI_API_KEY`,策略 D AIGC 生图,支持 StyleProfile 风格注入)
- 完整 API 配置说明见 README "API 配置" 章节
- 数据库:SurrealDB(嵌入式,图+向量一体化)+ BGE-M3 embedding,通过 `kb/graph_backend.py` 抽象层访问。不直接 `from surrealdb import ...`,所有调用走抽象层
- 前端:React + TS + Vite + Zustand + Konva.js + RemotionPlayer
- 后端:Node.js Express(主编排,端口 3000) + Python FastAPI(重计算,端口 8000)
- 渲染:Remotion + @remotion/three + GSAP + Lottie
- 3D 资源:CC0 .glb 模型(Quaternius/Sketchfab),不自己建模

## 编码规范
- TypeScript strict mode,无 `any`
- Python 用类型注解 + Pydantic
- 所有新组件先看 `web/src/components/` 是否已有同类
- Remotion 组件命名:MG 组件用描述性名称(KineticText/GlassCard/HookBeat),合成用 `*Video`(ScriptDrivenVideo/MultiSceneVideo)

## SurrealDB 使用规则(必读)
1. SDK 用 `AsyncSurreal`,**绝不用** `Surreal` 同步版(性能差 + 抽象层乱)
2. 所有 SurrealDB 调用必须经过 `kb/graph_backend.py`,不直接 `from surrealdb import ...`
3. HNSW 索引语法:`DIST COSINE` 不是 `DISTANCE COSINE`,索引名加 `OVERWRITE` 防止重跑炸
4. KNN 操作符必带两个参数:无索引时 `<|k,COSINE|>`,有 HNSW 时 `<|k,ef|>`(ef 推荐 100-200)
5. `vector::distance::knn()` **不传参数**,它读取上面 KNN 操作符的距离
6. 嵌入式模式只允许一个进程连接同一个 file:// 数据库(只让 Python 连,Node 通过 HTTP API 间接访问)
7. 不在嵌入式模式下使用 Live Query(不支持)

## Git 习惯
- 每个 atom/module/pattern 单独 commit
- 提交 message 用中文,前缀 `[W1-D2 S1]` 标识周/天/阶段
- 不 commit `data/`, `node_modules/`, `dist/`, `*.mp4`, `.env`

## Subagent 路由规则

**Parallel dispatch**(全部满足才并行):
- 3+ 不相关的任务
- 任务间无共享状态(不改同一文件)
- 我明确说了"并行 / 同时 / parallel"

**Sequential dispatch**(任一触发就串行):
- 任务有依赖
- 改同一文件或状态
- 任务范围不明确

**永远不要并行的操作**:
- git 操作
- 改 CLAUDE.md
- 修改 SurrealDB graph.db schema

## 何时停下来问我
- 需要付费 API 调用前
- 需要安装新的全局工具/依赖前
- 需要做 `git push --force` 或修改 main 分支前
- 需要修改 CLAUDE.md 本身前
- 任何会产生不可逆副作用的操作前

其他情况都直接做。

## 当遇到 spec 模糊的情况
1. 先按你认为最合理的方案做
2. 在代码注释里加 `// SPEC-AMBIG: <你的理解>`
3. commit message 加 `[SPEC-AMBIG]` 标签
4. 在 docs/progress.md 当日条目里记录

## 与我协作时
- **不要问太多确认**,有 spec 就直接做
- 每个 Day 任务结束后跑一次 `/verify-build`
- 写完代码立刻写至少 1 个测试或一个 demo case
- 如果遇到 spec 模糊处,先按你认为合理的方案做,**然后在 commit message 里标记 `[SPEC-AMBIG]` 让我事后审查**

## Docker 部署(一键启动)

```bash
# 首次运行:构建镜像 + 初始化知识库
cp .env.example .env              # 填入 MIMO_API_KEY + GEMINI_API_KEY (可选)
docker compose build              # 构建 3 个服务镜像(含 BGE-M3 模型下载,首次较慢)
docker compose run --rm seed      # 初始化 SurrealDB schema + 加载 36 atoms + 6 modules + 1 pattern
docker compose up                 # 启动全部服务

# 访问地址
# 前端:    http://localhost:5173
# Node API: http://localhost:3000
# Python API: http://localhost:8000

# 后续重启(不需要重新 seed)
docker compose up

# 重新 seed(清除旧数据)
rm -rf data/graph.db && docker compose run --rm seed && docker compose up
```

## 当前进度
- [x] W1 H5 闭环 (D1-D7)
- [x] W2 知识库 (D8-D14) — 种子数据: 1 pattern / 6 modules / 36 atoms (运行时可扩展)
- [x] W3 缺口处理 (D15-D21) — KB-aware 策略 / 多版本 / 人工可调 / 入图 agent
- [x] W3 视觉质量 — Design Tokens / SafeZone / Aesthetic Linter / MG 组件库(35 .tsx + index.ts)
- [x] W3 动画编排 — LLM Orchestrator v3(两步 LLM) / ScriptDrivenVideo / 脚本驱动渲染
- [x] W4 S2 增强 — ASR(faster-whisper) + 规则推断 + VLM 微调(3 prompt 并发)
- [x] W4 Docker 部署 — docker-compose + 3 个 Dockerfile + nginx
- [x] W4 Beat-Level 编排 — 结构确定+LLM填内容 / 7-beat 层叠 / 18 组件注册 / 校验修复环
- [x] W4 场景级迁移 — scene_decomposer(shot→场景→元素融合→布局模板→beat_sheet) / motion_kinematics(20动效词表) / MultiSceneVideo 渲染
- [x] W4 动画系统升级 — 5层控制(生命周期/属性/缓动/编排/场景) / LLM作曲家(命名预设) / render_validator(14条规则+修复) / sustain idle / mask_reveal / anchor
- [x] W4 Kinetic Typography — TextOverlayLayer(Staging原则) / 顺序焦点排程 / 5种入场技法(word_stagger/char_pop/mask_reveal/blur_in/typewriter) / scrim可读性 / 文字专用校验
- [x] W4 VLM 驱动布局 + 参数化生成 — VLM 分析原视频帧判定布局(centered/radial/stack/full_bleed/grid/split) / 6 种参数化生成器 / 图片裁剪保存(多帧采样+低对比度过滤)
- [x] W4 组件目录系统 — catalog.json(27组件) + component_catalog.py(BGE-M3检索+多因子排序+运行时Pydantic) + build_registry.py(自动生成TS注册) + L1-L4选择质量层
- [x] W4 风格迁移 — StyleProfile(CV+VLM提取) + VLM动效分析(motion_path关键帧) + Gemini风格注入生图 + LLM文字编排 + MultiSceneVideo Stage渲染 + FX层(Vignette/FilmGrain/LightLeak/GradientMesh) + Web UI(上传+进度条+预览)
- [x] W4 知识验证 — knowledge_verifier.py(Do No Harm护栏 + 多来源一致 + 并行搜索 + 只改high confidence)
- [ ] W4 答辩 Demo — 多场景演示 + 前端 polish

## 关键文件速查
| 文件 | 功能 |
|------|------|
| `services/python/s1_analyzer.py` | S1 视频分析(scenedetect + 多帧 VLM + motion) — 含视觉语言提取 |
| `services/python/template_merger.py` | 多视频 template 合并(中位数边界/并集类型/众数分类) |
| `services/python/vision_analyzer.py` | CV 视觉分析(EasyOCR + 光流 + 运动模式 + 颜色提取) |
| `services/python/scene_description.py` | CV 测量驱动 SceneDescription + StyleProfile(CV+VLM提取6种风格家族, to_aigc_prompt/to_css_filter) + VLM 重试+压缩 |
| `services/python/knowledge_verifier.py` | 知识验证(DuckDuckGo 搜索 + LLM 事实核查 + Do No Harm 护栏: 仅 high confidence 多来源一致才改) |
| `services/python/gemini_imager.py` | Gemini Imagen 3 生图(支持 StyleProfile 风格注入, gemini-2.5-flash-image) |
| `services/python/scene_editor.py` | 自然语言场景编辑器(LLM 直接修改 VideoSpec shot 级别, 无预定义 op 枚举) |
| `services/python/motion_analyzer.py` | 光流能量曲线 + SAM2 元素追踪(RAFT/Farneback + SAM2.1-small) |
| `services/python/s2_extractor.py` | S2 结构提取 v2(ASR+规则+VLM 微调) |
| `services/python/s2/asr_extractor.py` | Stage A: faster-whisper ASR 提取 |
| `services/python/s2/structure_inferrer.py` | Stage B: 规则+ASR 候选推断 |
| `services/python/s2/vlm_refiner.py` | Stage C: VLM 微调(3 个并发 prompt) |
| `services/python/s2/schemas.py` | S2 数据结构(ASRSegment, PhaseDraft, VLMRefinement) |
| `services/python/video_spec_schema.py` | VideoSpec Pydantic schema(18 组件, 含 MG 高级组件) |
| `services/python/s3_gap_detector.py` | S3 缺口检测 + 高光排序(MiMo VLM 质量分+角色分+廉价信号) |
| `services/python/s3_strategist.py` | S3 策略引擎(A-F 六策略) |
| `services/python/animation_orchestrator.py` | LLM 动画编排 v3 + Beat-Level 编排(结构确定+LLM填内容) |
| `services/python/control_vector.py` | ControlVector 控制向量(Task 10/12/13 共用地基: 4 profiles + NL 编辑) |
| `services/python/aesthetic_linter.py` | 美感校验(7 条规则) |
| `services/python/atom_component_map.py` | KB atom → Remotion 组件映射 |
| `services/python/scene_decomposer.py` | 场景级视频分解(shot检测→窗口化提取→元素融合→beat_sheet抽取) |
| `services/python/motion_kinematics.py` | 运动学特征提取(散度/旋度/尺度)+ 闭集动效分类器(20个Tier A/B/C) |
| `services/python/visual_director.py` | 视觉导演(VLM分析视觉结构→LLM规划素材→Gemini生图) |
| `services/python/render_validator.py` | 渲染QA校验(14条规则+确定性修复: 覆盖率/居中性/出血/重叠/黑屏gap/碰撞/安全区/阅读时间/对比度) |
| `services/python/video_utils.py` | 视频格式检测+自动转码(15+格式) |
| `services/python/visual_gap_detector.py` | 视觉缺口检测(背景/前景/装饰/文字层分析) |
| `kb/template_store.py` | 知识图谱 CRUD + 向量搜索 |
| `kb/agent/ingestion_agent.py` | 入图 Agent(merge/create/split) |
| `web/src/design-tokens/index.ts` | Design Tokens(字号/配色/间距/easing) |
| `web/src/components/mg/` | MG 组件库(35 .tsx + 1 index.ts, 扁平结构: KineticText/GlassCard/HookBeat/PhotoStack/ImageOrbit 等) |
| `web/src/components/SafeZone.tsx` | 安全区组件 |
| `web/src/components/StandardCaption.tsx` | 标准字幕组件 |
| `web/src/components/MigrationMap.tsx` | 迁移溯源表(因果链+severity色+fallback徽章+钻取面板) |
| `web/src/remotion/compositions/ScriptDrivenVideo.tsx` | 脚本驱动渲染 |
| `catalog.json` | 统一组件目录(27 组件, 单一真相源) |
| `services/python/component_catalog.py` | 组件目录 + BGE-M3 检索 + 多因子排序 + 运行时 Pydantic |
| `scripts/build_registry.py` | catalog.json → 自动生成 TS COMPONENT_MAP |
| `fewshot_pairings.json` | few-shot 好搭配示例(L3 选择质量层) |
| `.claude/skills/composition-rules.md` | 组合纪律(运行时 system prompt) |
| `web/src/remotion/compositions/ProductPromo.tsx` | 产品宣传片合成(1080×640, 7 beats, props-driven config) |
| `web/src/remotion/compositions/StyleDrivenVideo.tsx` | 风格驱动渲染(CSS Grid/Stage 双模式 + MultiSceneVideo Stage绝对定位 + CinematicEffects FX层 + TextOverlayLayer 文字层) |
| `web/src/remotion/compositions/TextOverlayLayer.tsx` | Kinetic Typography 文字覆盖层(Staging 原则 + 顺序焦点 + 5种入场技法 + scrim + scroll_list_pointer) |
| `services/python/scene_decomposer.py` (_vlm_analyze_layout) | VLM 布局分析(分析原视频帧 → centered/radial/stack/full_bleed/grid/split) |
| `services/python/scene_decomposer.py` (_apply_parametric_layout) | 参数化布局生成器(6 种家族确定性生成) |
| `services/python/scene_decomposer.py` (_crop_and_save) | 图片裁剪保存(多帧采样选最亮+低对比度过滤) |
| `web/src/motion/primitives.ts` | 动效原语库(纯函数, recipe.json.motion 对应) |
| `recipe.json` | VST schema 单一真相源(meta/tokens/motion/components/timeline) |
| `scripts/measure_structure.py` | 结构指标集 M 测量(beat timing/motion density/attention curve/diversity) |
| `scripts/render_promo.ts` | ProductPromo 渲染脚本 |
| `scripts/render_spark.ts` | SparkPromo 渲染脚本(1280×720, 60fps) |
| `scripts/render_style.ts` | StyleDrivenVideo 渲染脚本 |
| `scripts/render_multi_scene.ts` | MultiSceneVideo 渲染脚本(场景级分解→MP4) |
| `scripts/test_wuhan.py` | 风格迁移完整管线测试(分解→StyleProfile→VLM动效→Gemini生图→LLM文字→渲染) |
| `web/src/pages/HomePage.tsx` | 前端主页(上传视频+主题→风格迁移→预览播放, 进度条) |
| `docs/video_recipe_layoutdev.md` | Layout.dev 视频配方(beat sheet + tokens + motion) |
| `scripts/e2e_test.py` | E2E 测试(完整流水线) |
| `scripts/e2e_demo.py` | E2E 演示(KB-aware 策略) |
| `scripts/e2e_orchestrated.py` | E2E 演示(LLM 编排版) |
| `docs/motion_design_guide.md` | MG 设计指南 |
| `docs/unwrapped_patterns.md` | GitHub Unwrapped 架构模式参考 |
| `docs/component_proportions.md` | 组件比例规范 |

## 风格迁移系统架构

**核心原则**: 场景级分解 + CV 测量运动学 + LLM 作曲家（在 DSL 内组合）+ CSS Grid 布局（构造性保证铺满/不出血/不变形）。

**数据流**:
```
参考视频
   → PySceneDetect shot 检测 (shot = scene)
   → 逐场景窗口化: SAM2 元素发现 + RAFT 光流追踪 + EasyOCR 文字
   → 元素融合去重 (SAM2 mask ∪ OCR box → card/graphic/caption)
   → VLM 布局分析 (分析原视频帧 → centered/radial/stack/full_bleed/grid/split)
   → 参数化布局生成 (_apply_parametric_layout, 6 种家族确定性生成)
   → 图片裁剪保存 (_crop_and_save, 多帧采样选最亮+低对比度过滤)
   → motion_path 接线 + motion_kinematics 动效分类
   → LLM 作曲家 (选 spring 预设 + idle + out + 转场)
   → 验证修复环 (14 条规则 + 确定性兜底修复)
   → MultiSceneVideo 渲染 (CSS Grid/Stage + AnimatedInner + TextOverlayLayer)
```

**布局系统**: VLM 驱动 + 参数化生成
- 6 种家族: centered(大图居中) / radial(环绕) / stack(堆叠) / full_bleed(全屏) / grid(平铺) / split(分割)
- VLM 分析原视频帧确定每个场景的目标布局（不靠 SAM2 坐标，因为天然是散开的）
- `_apply_parametric_layout` 根据家族名确定性生成坐标（参数→布局，没有自由坐标）
- grid 家族用 CSS Grid 命名区域 + `object-fit:cover`
- stage 家族(radial/stack/scatter)用绝对定位 + 旋转
- TextOverlayLayer 浮在图片层之上（Staging 原则：一次一焦点）

**动画控制 5 层** (对齐 12 原则 + Lottie 属性模型):
- 层 0 生命周期: entrance(~6帧) → sustain(idle: float/breathe/rotate/none) → exit(~3帧, 比入场快)
- 层 1 可动属性: position / scale / rotation / opacity / anchor / mask_reveal / blur
- 层 2 时间缓动: spring 预设(snappy/bouncy/smooth) / easing / duration / anticipation
- 层 3 编排: stagger(3-5帧) / direction / grouping
- 层 4 场景: camera / bg_motion / 转场

**动效词表 (20 个)**:
- Tier A (已有组件): pop_in / text_scroll / scale_pulse / slide_caption / logo_reveal / image_swap / logo_shrink
- Tier B (Remotion 友好): flip / scatter / gather / rotate_180 / line_split / emit_images / highlight_sel / 2_5d_push / spin_in / elastic_pop
- Tier C (媒体槽位): volumetric_3d / camera_fly / generated_vid

**LLM 作曲家输出**: 命名预设(不吐裸数值) — spring: snappy/bouncy/smooth, idle: float/breathe/rotate/none, out: fade/fade_scale/slide_*

**验证规则 (9 条)**: 黑屏gap / 同位置重叠 / 空文字 / 无背景 / 时长异常 / 单shot时长 / 散件≤2(编排内不限) / 文字bbox相交 / 必读文字安全区。每条配确定性修复动作。

**VLM 职责边界**: 只做 OCR 更正 + 语义角色标注 + 场景 layout/role 分类，不出坐标/帧号

**审计字段**: 每个元素有 `source` + `track_confidence` + `effect_type` + `effect_tier` + `idle_animation` + `exit_animation`

## Beat-Level 编排架构

**核心思路**: 结构确定 + LLM 作曲家。beat 结构由模板的 `beat_sheet` 字段定义，LLM 填内容 + 选动效参数 + 选转场。

**两种编排模式**:
1. **Phase-Level** (旧): `orchestrate_animation()` — 3 phases, LLM 决定组件+内容, 适合无 beat_sheet 的模板
2. **Beat-Level** (新): `orchestrate_from_beats()` — 7 beats, 结构确定, LLM 作曲家, 适合有 beat_sheet 的模板

**Beat-Level 流程**:
```
template.beat_sheet → _fill_beat_content(LLM填内容+选动效) → generate_video_spec_from_beats(组装+注入参数) → validate_and_fix(QA校验+修复)
```

**LLM 作曲家输出**: 每个 beat 的内容 + 动效参数(命名预设) + 转场选择

**层叠渲染**: 同一 beat 内的组件 `start` 相同、`position` 不同 → ScriptDrivenVideo 同时渲染。
例: beat 0 = WordReveal(center) + GlowTrail(center) 同时出现。

**组件注册表**: 18 个组件 (9 基础 + 9 MG 高级), 在 `ScriptDrivenVideo.tsx` COMPONENT_MAP 和 `video_spec_schema.py` _PROPS_MAP 中注册。MG 组件库共 35 文件, 四层架构 (atoms/molecules/organisms/layout)。

**校验修复环**: Pydantic 结构校验 → `_validate_spec_semantic` 语义校验 → 失败带错误重提示 → 仍失败退安全默认。

## 文本长度约束

组件对文字长度有硬性限制，超出会被截断。`_enforce_text_limits()` 在生成时预处理。

| 组件 | max_chars | 原因 |
|------|-----------|------|
| TypewriterPrompt | 25 | 搜索栏 700px, 单行 nowrap, 40px mono |
| GradientText | 35 | 64px 渐变大字, 单行 |
| WordReveal | 50 | 96px 逐词揭示, 可 wrap 但≤3行 |
| GlassCard text | 20 | 卡片 260px, 内部文字 |
| FeatureGrid label | 8 | 标签 ≤2词 |
| LogoReveal | 15 | Logo 文字, 短 |
| MarqueeText | 80 | 跑马灯滚动, 长度不限但要可读 |

组件层自适应: TypewriterPrompt/GradientText/WordReveal 内部会根据文字长度自动缩小 fontSize 防溢出。

## Props 命名规则

`_build_component_props()` 返回的 props 必须用 **snake_case** (与 Pydantic schema 一致)。
`_resolve_props()` 在 `to_render_input()` 时转为 camelCase 给 JS 组件。
错误示例: `fontSize` → 被 `_sanitize_props` 剥离 → Pydantic 用默认值。
正确示例: `font_size` → Pydantic 校验通过 → `_resolve_props` 转为 `fontSize`。
