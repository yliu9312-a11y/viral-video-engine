# Web 管线流程分析 + 视频质量根因 + 解决方案

> 分析日期: 2026-06-12。基于 README、全量代码走读、`data/output/` 真实产物(d521fb92 武汉 / 9282c5fe 中国历史 / decomp_ski_*)和成片抽帧取证。

---

## 一、Web 管线实际流程(代码级)

### 管线 A — 结构迁移(首页"开始生成")

```
HomePage.runPipeline()
  POST /api/upload          → Node 落盘 data/uploads/{job}/
  POST /api/extract         → Py /extract: S1(scenedetect+VLM+光流) + S2(ASR+规则+VLM) → structure_template.json
  POST /api/gap             → Py /gap: 缺口检测 → gap_report.json
  POST /api/assign          → Py /assign: A-F 策略分配 → material_assignment.json
  POST /api/render          → Node execFileSync render.ts ×3 变体(ViralVideo, 旧渲染)
  POST /api/orchestrate     → Py /orchestrate:
                                template 有 beat_sheet → orchestrate_from_beats (beat-level)
                                否则 → orchestrate_animation ×3 phase (phase-level) ← S2 模板无 beat_sheet,web 实际走这条
  POST /api/render_script   → Node execFileSync render_script.ts (ScriptDrivenVideo) → 覆盖预览
  之后: /api/edit/scene (NL编辑) → /api/render_script 重渲
```

### 管线 B — 风格迁移(首页"开始风格迁移")

```
HomePage.runStyleMigrate()
  POST /api/upload
  POST /api/style_migrate (Node 代理, 40min 超时) → Py /style_migrate:
    [线程池阻塞段 _style_migrate_blocking]
      1. decompose_video()        PySceneDetect → 逐场景: SAM2+RAFT 窗口追踪 + EasyOCR + 元素融合
                                  + VLM 布局分析(6 家族) + _apply_parametric_layout 参数化布局
                                  + VLM 文字风格 + 转场检测
      2. extract_style_profile()  CV 取色/亮度/对比 + VLM 判风格家族 → StyleProfile
      3. _vlm_analyze_motion()    仅采样 ~4 个场景,两帧 VLM,关键词匹配 → effects
      4. _generate_scene_images() Gemini 逐张串行生图(2-3 张/场景),替换 image 元素 content_src
      5. generate_motion_paths_for_decomp()  VLM 动效类型 → motion_path 关键帧
      6. _inject_text_and_effects(d, {}, motions)  注入默认动效(此时无 LLM 文案)
      6.5 safe-zone clamp + MAX_EL=4 截断 + validate_and_fix_decomposition QA
      7. 重算场景边界, 存 decomposition.json, 生成图复制到 web/public/
    [async 段]
      orchestrate_from_beats(decomposition→template, topic)  LLM 按 phase 产文案
      _inject_text_and_effects(d, llm_texts, [])             文案回填(按 phase 顺序分配)
  POST /api/render_scene → Node execFileSync `npx remotion render ... MultiSceneVideo --fps=30`
                            → StyleDrivenVideo.tsx 里的 MultiSceneVideo (Stage/Grid + FX 层 + TextOverlayLayer)
```

关键观察:渲染层 MultiSceneVideo 每帧只渲染"当前场景",场景内图片走 `SceneStage/SceneGrid → AnimatedInner`,文字走 `TextOverlayLayer`(1.4s/条串行焦点),整体套 StyleProfile 的 CSS filter + FX 层。

---

## 二、质量糟糕的根因(按严重度排序,均有代码/产物证据)

### P0 — 直接毁掉画面

| # | 问题 | 位置 | 证据 |
|---|------|------|------|
| 1 | **StyleProfile.grade 单位语义错误:测量值被当 CSS 倍数用**。`brightness = np.mean(gray)/255`(参考视频绝对亮度,暗片≈0.08)直接存进 `grade.brightness`,而 schema 注释和渲染端都按 CSS `brightness()` 倍数(1.0=不变)使用。渲染端 clamp 到 0.5 后仍是 `brightness(0.5) contrast(0.5) saturate(0.63)` 全片叠加 | `scene_description.py:853-858` ↔ `StyleDrivenVideo.tsx:994-1003` | d521fb92 `grade.brightness=0.08, contrast=0.28`;成片 render_1e112a7e 抽帧 5 帧全部近黑,只剩灰色残影 |
| 2 | **生图 prompt 与主题完全脱钩**:`_generate_scene_images(topic,...)` 的 `topic` 参数从未被使用,PROMPTS 是硬编码列表(且明显武汉特化:轮渡/樱花/双层桥/塔楼) | `main.py:987-1049` | 9282c5fe 主题"中国历史"(文案:秦始皇/万里长城),s3_gen_0.png 实际是通用"黄金时刻航拍海岛城堡",与长城毫无关系 |
| 3 | **Gemini 生图无重试/无限流/串行,失败即空图;空 src 元素被渲染器直接丢弃** → 场景空洞或纯色块。13 场景×2-3 张串行(60s 硬超时/张)也是 30+ 分钟时长的主因 | `gemini_imager.py`(无 429 退避)、`main.py:1036-1046`、`StyleDrivenVideo.tsx:763,814`(filter 掉空 src) | d521fb92: 50 个 image 元素仅 34 个有图;decomp_ski_stage: 120/120 全空 → 整片只剩背景+字 |
| 4 | **fps 不匹配**:`render_scene` 硬编码 `--fps=30`,而 decomposition 的帧数/边界按参考视频 fps 计算 | `services/node/src/index.ts:332` | decomp_ski: fps=60、total_frames=1871(31s),按 30fps 渲出 62s,整体 2 倍慢放 |
| 5 | **成片无声**:全管线没有任何音轨注入(librosa 只测 BPM 没下文),Remotion 输出静音轨 | 全部合成 `.tsx` 无 `<Audio>` | ffmpeg volumedetect: mean/max −91dB(纯静音);短视频无 BGM 基本不成立 |

### P1 — 动效/编排断裂("看起来廉价"的来源)

| # | 问题 | 位置 |
|---|------|------|
| 6 | **motion_path 没接进最终渲染**:MultiSceneVideo 的 Stage/Grid 路径用 `AnimatedInner`,只读 entrance/exit/effect_type,完全不读 `motion_path`。SAM2+RAFT 追踪、VLM 运动分析、`generate_motion_paths_for_decomp` 的产出在 web 管线里全是死数据(只有单场景 StyleDrivenVideo 用了)。且生成的关键帧硬编码 `x:50,y:50`,真接上反而会把所有元素叠到画面中心 | `StyleDrivenVideo.tsx:664-754` vs `scene_decomposer.py:2015-2137` |
| 7 | **动效靠 `i % len(pool)` 轮转随机分配**:入场 7 选一、idle 8 选一、方向 4 选一、旋转 `(i*7-n*3.5)%30-15`——和参考视频无关,同屏元素动效互相打架。README 宣传的"LLM 作曲家" `compose_scene_animations` 在 web 管线从未被调用(死代码) | `scene_decomposer.py:1073-1084`、`main.py:1094-1105`;grep 确认无调用方 |
| 8 | **转场单一且消耗时长**:`_detect_transition`(cut/fade/slide)的结果存在 `entrance_transition`,渲染端只读 `transition_out`(默认 fade,只有从未被调用的 compose_scene_animations 会写)→ 每个场景固定 15 帧淡入+15 帧淡出,节奏拖沓;场景之间也没有真 crossfade(每帧只渲一个场景) | `scene_decomposer.py:40,1907` ↔ `StyleDrivenVideo.tsx:967-979` |
| 9 | **碎场景无合并**:PySceneDetect 产出 0.5s/0.8s/1.2s 碎片直接成场景 → 闪屏;叠加每场景 1s 的淡入淡出,碎场景基本全程半透明 | d521fb92 durations: [4.0, 3.1, **0.8**, 2.8, **1.2**, 4.3, **1.4**, **1.5**, ...] |
| 10 | **文案覆盖率低 + 暴力截断**:`decomposition_to_orchestrator_template` 把 13 个场景压成 ≤3 个 beat(hook/build/cta,每 beat ≤4 组件),LLM 只产几条文案,再按 phase 顺序往 13 个场景里塞,塞完即空;>14 字直接 `[:14]` 截断 | `scene_decomposer.py:1959-1992`、`main.py:1064-1092`;d521fb92 仅 4/14、9282c5fe 仅 6/14 文字元素有内容 |
| 11 | **文字停留固定 1.4s**:焦点串行排程 holdSec=1.4,4s 场景后 2.6s 无字;打字机入场叠加后,抽帧正好抓到只显示"黄"一个字 | `TextOverlayLayer.tsx:83-119` |

### P2 — 结构性短板

| # | 问题 | 位置 |
|---|------|------|
| 12 | SAM2 过检:8-21 元素/场景(README 已自知),`MAX_EL=4` 按列表顺序截前 4 个而非按重要性 | `main.py:823-827` |
| 13 | "保留原视频布局"未实现:参数化布局直接丢弃 SAM2 实测坐标,6 模板硬排;VLM 判家族单帧单词,错判无兜底验证 | `scene_decomposer.py:1061-1226` |
| 14 | 管线 A:`/orchestrate` 调 `orchestrate_animation(phase, gap, kb_atoms, **[]**, template)`——**用户上传素材永远不进编排成片**;且只编排 C/D/F 策略的 phase,A/B/E/PASS 的 phase 整段缺失 | `main.py:463,474` |
| 15 | QA 修复环对 decomposition 很浅:空文字填 "—"(会真渲染出一个破折号)、延长阅读时长,14 条规则主要服务管线 A 的 VideoSpec | `render_validator.py:631-655` |
| 16 | 工程性:渲染用 `execFileSync` 阻塞 Node 事件循环;前端进度条是 setInterval 假进度;`_crop_and_save` 的参考帧裁剪图不复制到 web/public(只复制 generated),走 /decompose 路径时 staticFile 必然 404 | `index.ts:227,276,328`、`HomePage.tsx:420-422`、`main.py:851-858` |

**一句话总结**:分析端(SAM2/RAFT/VLM/StyleProfile)做得很重,但测量结果在三个断点上没接到渲染端——①调色参数单位错了、②运动数据没人消费、③生图 prompt 没人注入主题;再叠加无声、慢放、空图、碎场景,成片必然糟糕。

---

## 三、解决方案(按投入产出排序)

### 立即可做(1-2 天,答辩前止血)

1. **修 grade 语义**(P0-1,半天)
   - `extract_style_profile` 改为存"目标倍数":`grade.brightness = clamp(0.85, 1.15, target/measured)` 或干脆只存 `mood`,渲染端按 mood 选预设 filter(dark → `brightness(1.0) contrast(1.05) saturate(0.9)` 级别的轻调)。
   - 原则:CSS filter 是"再调色",不是"复刻参考片亮度"。参考片暗 ≠ 把新素材压暗,风格已经通过 `to_aigc_prompt` 在生图阶段注入了,渲染端二次叠加是重复施加。
   - 快速验证:临时把 `cssFilter` 置空渲一版对比。

2. **生图 prompt 接入主题 + 场景语义**(P0-2,半天)
   - 让 `orchestrate_from_beats` 顺带为每个场景产出 `image_prompt`(主题+场景角色+文案对应物),`_generate_scene_images` 用 `f"{llm_image_prompt}, {topic}"`,硬编码 PROMPTS 只留作 LLM 失败兜底(且要在兜底里拼上 `{topic}`)。

3. **Gemini 健壮化**(P0-3,半天)
   - 429/5xx 指数退避+jitter 重试(官方推荐,见下方资料);并发 2-3 张(`asyncio.gather` + semaphore)替代纯串行;在 `generationConfig` 加 `imageConfig.aspectRatio: "16:9"`(gemini-2.5-flash-image 已正式支持 10 种比例,现在传的 width/height 实际被忽略)。
   - 失败兜底链:生成失败 → 用 `_crop_and_save` 已裁好的参考帧图(注意同步复制到 web/public)→ 再不行才留色块,保证"画面永远有东西"。

4. **fps 透传**(P0-4,15 分钟):HomePage/render_scene 把 `--fps=${decomposition.fps}` 传下去;或在 Python 端把 decomposition 统一重采样到 30fps。

5. **加 BGM**(P0-5,1 天)
   - 库里放 5-6 首 CC0 音轨(按 style_family × BPM 桶),librosa 已测参考片 BPM → 选最近的;MultiSceneVideo 加 `<Audio src={...} volume={...}/>`,结尾 1s 淡出。Remotion 官方有现成的转场配音/音频文档(见资料)。无声→有声是观感提升最大的单点改动。

6. **碎场景合并**(P1-9,2 小时):`detect_shots` 后处理——`duration < 1.5s` 的 shot 并入相邻较长 shot;或 AdaptiveDetector `min_scene_len` 提到 `fps*1.5`。

### 中期(约 1 周)

7. **把动效决策交还给已写好的 LLM 作曲家**(P1-6/7):web 管线调用 `compose_scene_animations`(它会写 transition_out、entrance/idle 命名预设),删除 `i % len(pool)` 轮转;`_vlm_analyze_motion` 的结果作为作曲家输入而不是直接关键词匹配。同屏元素动效统一(同 entrance 不同 stagger),而不是各玩各的——这是 MG 设计"编排>随机"的基本纪律(项目自己的 motion_design_guide 也是这么写的)。
8. **motion_path 二选一**:要么(a)在 `AnimatedInner` 外层读 motion_path 做相对位移(关键帧改存 Δx/Δy,叠加在 spatial 上,避免现在的 x=50 硬编码);要么(b)承认 Stage 模式不需要连续位移,删掉 `generate_motion_paths_for_decomp` 死代码,把 VLM 运动分析的产出只用于 entrance/idle 选择。半成品状态最伤质量。
9. **真转场**:渲染端消费 `_detect_transition` 结果,用 `@remotion/transitions` 的 `TransitionSeries`(官方组件,支持 fade/slide/wipe + 时序预设,转场期两场景同时渲染)替换"每场景对背景淡入淡出"。
10. **逐场景文案**:`decomposition_to_orchestrator_template` 不再压成 3 个 beat——每个场景一个 beat(或每场景让 LLM 产 `title/subtitle`),prompt 里硬性要求 ≤14 字并校验重试,废除 `[:14]` 截断;文字 hold 改为 `min(场景时长-出场, max(1.4s, 字数*0.15s))`。
11. **SAM2 过检治理**:提高 mask 质量阈值与最小面积(画面 2-4%),NMS 合并重叠 mask,然后按 `面积×中心度×运动能量` 取 top-K(K=层叠上限);SAM2 官方 AutomaticMaskGenerator 的 `pred_iou_thresh/stability_score_thresh/min_mask_region_area` 就是为此设计的(见资料)。比"截前 4 个"合理得多。
12. **渲染异步化**:`execFileSync` → 任务队列(`bull` 已经在 node 依赖里)+ 真实进度(Remotion `onProgress` 回调写 redis/内存,前端轮询或 SSE),替换假进度条;顺带解决 40 分钟 HTTP 长连接超时脆弱性。

### 长期(质量护城河)

13. **VLM 评审闭环(LLM-as-a-Judge)**:渲染 360p 预览 → 均匀抽 6-8 帧 → VLM 按 rubric 打分(亮度/文字可读性/主题相关性/空洞画面/元素打架)→ 不达标自动定位问题场景回修(改 filter、换图、删元素)再渲。这是 OpusClip 等业界团队对生成视频质量最有效的工程闭环(见资料),也正好复用项目已有的 MiMo VLM 通道。把现有 14 条静态规则升级成"静态规则 + 视觉评审"双层。
14. **数据驱动转场/节奏**:参考 ByteDance 的 AutoTransition(ECCV 2022):音乐 beat + 相邻镜头视觉特征 → 转场推荐;项目已有 BPM 和镜头特征,可以先做规则版(beat 对齐切点),后续再上模型。
15. **回归测试门槛**:每次管线改动用 `measure_structure.py` 的 ΔM + VLM 评审分跑固定测试集(武汉/历史/滑雪三个 case),低于阈值 CI 拒绝——防止"修一处坏三处"。

---

## 四、参考资料

- Remotion 转场官方文档(TransitionSeries): https://www.remotion.dev/docs/transitioning 、转场配音: https://www.remotion.dev/docs/transitions/audio-transitions 、画质指南: https://www.remotion.dev/docs/quality 、LLM 生成 Remotion 代码指南: https://www.remotion.dev/docs/ai/generate
- Gemini 2.5 Flash Image 正式版支持 aspectRatio(imageConfig): https://developers.googleblog.com/en/gemini-2-5-flash-image-now-ready-for-production-with-new-aspect-ratios/ 、官方限流文档(指数退避建议): https://ai.google.dev/gemini-api/docs/rate-limits 、串行生图 429 案例讨论: https://discuss.ai.google.dev/t/gemini-2-5-flash-image-frequent-429-resource-exhausted-during-sequential-image-generation-seeking-clarity-on-rate-limits/118691
- AutoTransition(ECCV 2022, ByteDance, 转场推荐): https://link.springer.com/chapter/10.1007/978-3-031-19839-7_17 、代码与数据集: https://github.com/acherstyx/AutoTransition
- OpusClip 工程团队 LLM-as-a-Judge 视频质量评估框架: https://medium.com/opus-engineering/a-scalable-llm-as-a-judge-framework-for-video-quality-evaluation-74612034bd1e
- SAM2 AutomaticMaskGenerator 参数(过检过滤): https://github.com/facebookresearch/sam2/blob/main/notebooks/automatic_mask_generator_example.ipynb
- OpenMontage(开源 agentic 视频管线,自动配 CC0 BGM 的参考实现): https://github.com/calesthio/OpenMontage
