# Claude Code 工作流操作手册 — VST 项目专用

> 本手册告诉你**怎么用 Claude Code 把 v3 FINAL spec 落地为代码**。配套 `viral_structure_transfer_spec_v3_FINAL.md` 使用。
>
> 更新日期:2026 年 5 月 21 日(基于 Claude Code v2.1.139)

---

## 目录

1. [Claude Code 基础概念速通](#1)
2. [`/goal` 命令完整用法](#2)
3. [Skills(自定义 slash command)](#3)
4. [Subagent 并行/串行策略](#4)
5. [Worktrees 隔离开发](#5)
6. [完整工作流:4 周怎么跑](#6)
7. [`CLAUDE.md` 进阶配置](#7)
8. [常见坑与规避](#8)
9. [前置准备 + 第一天开工脚本](#9)

---

<a id="1"></a>
## 1. Claude Code 基础概念速通

VST 这种"4 周 1 人 + AI"的项目,你需要把 Claude Code 当**全栈伙伴**用,不是聊天工具。三个层级:

| 层级 | 角色 | 用法 |
|---|---|---|
| **CLAUDE.md** | 项目宪法 | 写在仓库根目录,每次 `claude` 启动自动读取。**修一次,管全程** |
| **Skills(slash commands)** | 工种模板 | `.claude/skills/*.md`,每个文件一个 `/xxx` 命令。Claude Code v2.1+ 把"custom commands"和"skills"合并了 |
| **`/goal`** | 工头 | 设置一个"完成条件",Claude 自动连跑多轮直到达成 |
| **Subagent / Task** | 临时工 | 启动并行/独立 context 的子 agent,避免主 context 爆 |
| **Worktrees** | 隔离工作区 | 同一 repo 多分支并行,多个 Claude Code 实例不打架 |

**思维模型**:
- **CLAUDE.md** 告诉 Claude "你在哪里工作、规则是什么"
- **Skills** 告诉 Claude "这类活儿怎么干"
- **`/goal`** 告诉 Claude "做到什么标准才算结束"
- **Subagent** 告诉 Claude "这事让别人(子 agent)去做,不要污染主 context"

---

<a id="2"></a>
## 2. `/goal` 命令完整用法

### 2.1 基本用法

```bash
# 在 Claude Code 里
> /goal 完成 S1 样例理解模块:能处理 ./data/samples/sample_001.mp4,产出含 shots/captions/audio/subtitle 的 JSON,文件存在 ./data/parsed/sample_001.json 且 npm run test:s1 通过

# Claude 立即开始工作,每轮完成后由一个独立的小模型判断 goal 是否达成
# 达成则自动停止
# 未达成则自动开始下一轮
```

### 2.2 `/goal` 的工作原理(重要,决定你怎么写 condition)

```
你设置 /goal CONDITION
       ↓
Claude 工作一轮(可能多个 tool calls)
       ↓
一个独立的小模型(evaluator)读对话历史,**可以跑 shell 命令**
       ↓
判断 CONDITION 是否为真
       ↓
   ┌─真─→ goal 自动 clear,控制权回到你
   └─假─→ Claude 自动开始下一轮
```

**关键事实**:evaluator 是**独立的小模型**,Claude 自己说"我做完了"不算数,evaluator 自己跑 `npm test` 之类的真实命令检查才算。

### 2.3 怎么写好的 condition(决定 80% 体验)

**坏例子**:
```
> /goal 把 S1 模块写好
```
→ "写好"无法验证,evaluator 永远不知道何时停。容易死循环烧 token。

**好例子**:
```
> /goal `npm run test:s1` 通过 AND `./data/parsed/sample_001.json` 存在 AND 该 JSON 满足 docs/spec.md §2.2 schema(可用 `python -c "import json,jsonschema; jsonschema.validate(json.load(open('./data/parsed/sample_001.json')), json.load(open('./schemas/structure_template.json')))"` 验证)
```
→ evaluator 可以跑 shell 命令验真,**Claude 没法靠话术蒙混**。

**VST 项目里的 condition 模板**:

| 阶段目标 | condition |
|---|---|
| 实现一个 Remotion atom | `npm run remotion:build` 通过 AND `services/remotion/src/atoms/{type}/{Name}.tsx` 存在 AND `services/remotion/src/atoms/{type}/__demos__/{Name}Demo.tsx` 存在 AND 跑 demo 不报错 |
| 完成 S1 模块 | `pytest tests/test_s1.py -v` 全绿 AND `services/python/main.py` 中存在 `extract_from_video` 函数 AND README 包含使用示例 |
| 知识库 atom 库到 30 个 | `sqlite3 knowledge_base.db "SELECT COUNT(*) FROM atoms;"` 输出 ≥ 30 AND 每个 atom 都有对应的 Remotion 组件文件 |
| W1 H5 闭环 | `./scripts/start.sh dev` 启动后,curl POST `/api/generate` 上传 sample.mp4 + topic="保温杯" 在 5 分钟内返回 200 且 mp4 文件可下载 |

### 2.4 `/goal` 的限制与避坑

| 限制 | 影响 | 对策 |
|---|---|---|
| 一次只能有一个 goal | 不能并行多目标 | 用 worktrees 开多个 Claude Code 实例 |
| 没有 token 上限 | 容易烧钱 | **condition 一定要紧 + 显式 turn cap** |
| Acknowledgement loop | condition 模糊时 Claude 每轮都说"基本完成了"但 evaluator 总判 false | 用真实可验证命令做 condition |
| 需要 trust mode | `claude` 在不信任的工作区跑不了 | 第一次进入工作区接受 trust 提示 |
| 检查器跑真实 shell | 不小心可能造成副作用 | **不要把"删 X 数据"放进 condition** |

### 2.5 显式 turn cap 的写法

```bash
> /goal `npm run test:s1` 通过 AND `./data/parsed/sample_001.json` 存在;最多 8 轮,超出则停止并报告卡在哪
```

强烈推荐**每个 `/goal` 都带 turn cap**,4 周 hackathon 不能让 Claude 死循环烧你两天 token。

### 2.6 中途查看状态

```bash
> /goal           # 不带参数,显示当前 goal、轮数、token、evaluator 上次理由
> /goal clear     # 立刻停止
```

### 2.7 配合 auto mode 用

```bash
# 进入 auto mode:Claude 在一个 turn 内不需要你点同意就能调工具
> /auto on

# 然后启动 goal
> /goal ...

# Claude 就完全自动跑了,你可以去吃饭(但回来要 audit git diff)
```

⚠️ **VST 项目里建议**:**只在已经测试过的、安全的 task 上用 auto + goal 组合**。生成代码的 task 用 auto,涉及 `data/` 删除、git push 之类的别用。

---

<a id="3"></a>
## 3. Skills(自定义 slash command)

### 3.1 Skills 是什么、和 slash command 什么关系

Claude Code v2.1+ 把"custom slash commands"和"skills"合并了。现在统一称 **skill**,文件放在:

- 项目级:`.claude/skills/<name>.md` → 触发 `/<name>`(只在这个仓库可用)
- 个人级:`~/.claude/skills/<name>.md` → 全局可用

### 3.2 Skills 文件结构

```markdown
---
name: extract-pattern
description: 从样例视频抽取 StructureTemplate 并入库
---

(这里是给 Claude 的 prompt,告诉它这个命令该怎么执行)

Steps:
1. ...
2. ...
```

**关键字段**:
- `name`:必填,决定 slash command 名字
- `description`:**非常重要**,Claude 决定是否自动触发这个 skill 时看的就是它

### 3.3 显式触发 vs 自动触发

- **显式**:你输 `/extract-pattern path/to/video.mp4`
- **自动**:你说"帮我从这个视频里抽一下结构",Claude 看到 description 匹配,**自动调用这个 skill**

VST 项目的 skills 都设计成两种都行。

### 3.4 VST 必备的 8 个 Skills

下面 8 个 skills 在 W1 D1 全部建好,贯穿 4 周使用。

#### `.claude/skills/extract-pattern.md`(W1+ 高频)
```markdown
---
name: extract-pattern
description: 从一个或多个样例视频抽取 StructureTemplate 并落入知识库
---

读取参数指定的视频路径(可多个,逗号分隔),执行:

1. 对每个视频调用 PySceneDetect 切镜头,记录边界
2. 每个 shot 调用 Qwen2.5-VL(http://localhost:8001/v1/chat/completions)生成 caption
3. 调用 Paraformer 转字幕(中文优先)
4. 调用 librosa 提取音频特征(BPM、能量曲线、节拍点)
5. 调用 PaddleOCR 抓画面字幕样式
6. 汇总信息给 Doubao-Seed,输出 StructureTemplate.json(schema 见 docs/spec.md §2.2)
7. 调用 kb.find_similar_pattern(threshold=0.85)
   - 相似度 > 0.85:increment_appearance + merge_provenance
   - 否则:insert_pattern
8. 拆解为 module 和 atom,分别 dedup 后入库
9. 返回 markdown 报告:抽取的 template 概要 + 是否新模式 + 入库 N 个新 atom

代码主入口 `kb/extractor/extract_from_video.py`。
所有 LLM/VLM 调用走环境变量,绝不硬编码 key。
```

#### `.claude/skills/new-atom.md`(W2 高频)
```markdown
---
name: new-atom
description: 创建一个新的 Remotion atom(shot/caption/transition/sticker/3d)
---

参数格式:`/new-atom <atom_id> --type <type> --category <cat>`
例如:`/new-atom shot_face_closeup_dramatic --type shot --category hook`

步骤:
1. 在 `services/remotion/src/atoms/<type>/` 下创建 `<AtomComponentName>.tsx`
2. 组件用 `useCurrentFrame()` 驱动动画,绝不用 `useFrame`(那是 R3F 的会跟 Remotion 冲突)
3. 在 `services/remotion/src/atoms/<type>/__demos__/<AtomComponentName>Demo.tsx` 写 demo composition
4. 在 `kb/seeds/atoms.jsonl` 追加完整 JSON 条目(参考 docs/spec.md §3.2 atoms 表 schema)
5. 跑 `npm run seed:kb` 同步到 SQLite
6. 跑 `npm run remotion:preview` 让我看到效果,等待我确认通过

不要修改已有 atom 文件除非我明确要求。
不要在没有 demo 验证的情况下声称"完成"。
```

#### `.claude/skills/new-3d-atom.md`(W2 中频)
```markdown
---
name: new-3d-atom
description: 创建一个 3D Remotion atom(必须用 @remotion/three + R3F)
---

参数:`/new-3d-atom <atom_id>`

步骤:
1. 在 `services/remotion/src/atoms/3d/` 下创建 `<Name>.tsx`
2. 必须使用 `<ThreeCanvas>` from `@remotion/three`,不用原生 Three.js
3. 必须设置 `width` 和 `height` props(否则 Studio 渲染会破)
4. 所有动画用 `useCurrentFrame()` 驱动,绝不用 R3F 的 `useFrame`(这是 #1 坑)
5. 嵌套的 `<Sequence>` 必须传 `layout="none"`(否则会报错)
6. 如果加载 .glb,模型放 `web/public/models/` 下,用 `useGLTF()` 加载
7. 创建 demo + 入库 jsonl + 跑预览

参考资料:`docs/spec.md §5.3` 有完整示例。
```

#### `.claude/skills/extract-structure.md`(单视频版,调试期高频)
```markdown
---
name: extract-structure
description: 只对一个视频做 S1+S2,输出 StructureTemplate.json,不入库(用于 prompt 调试)
---

参数:视频路径

执行 S1 + S2 完整流程,但**不写入知识库**。
输出文件:`./tmp/structure_<timestamp>.json`
同时打印格式化后的 template 概要让我审阅。

适合 W1-W2 调 prompt 时反复跑。
```

#### `.claude/skills/gap-test.md`(W3 高频)
```markdown
---
name: gap-test
description: 用合成测试数据跑一遍缺口识别 + 5 种补全策略
---

无参数。固定流程:
1. 加载 `tests/fixtures/template_ecom_001.json`(预置的标准 pattern)
2. 加载 `tests/fixtures/materials_insufficient.json`(故意缺料的素材池)
3. 调用 `gap/detector.identify_gaps()` 看输出
4. 对每个 gap,分别用 5 种策略跑一遍(call A/B/C/D/E)
5. 输出每种策略的产出对比,以 markdown 报告呈现

用于验证缺口处理模块改动后是否回归。
```

#### `.claude/skills/verify-build.md`(每天 D 结束跑)
```markdown
---
name: verify-build
description: 全栈构建与基础冒烟测试,验证当天工作没破东西
---

按顺序执行(任一失败立即停):
1. `cd web && npm run typecheck && npm run lint`
2. `cd services/node && npm run typecheck && npm run lint`
3. `cd services/remotion && npm run typecheck`
4. `cd services/python && ruff check . && mypy .`
5. 启动服务(./scripts/start.sh dev),等待 30 秒
6. `npm run test:smoke`(curl 主要 API 端点是否 200)
7. 关闭服务

全过返回 "ALL GREEN"。任一失败打印失败原因 + 失败的具体命令。
```

#### `.claude/skills/e2e-case.md`(W3+ 中频)
```markdown
---
name: e2e-case
description: 跑一个完整的端到端 case 并保存生成的 mp4
---

参数:`/e2e-case <case_id>`(case 配置在 `tests/cases/<case_id>.yaml`)

case yaml 格式:
```yaml
sample_videos:
  - tests/fixtures/sample_001.mp4
user_topic: "保温杯,300ml,保温24小时,49.9元"
user_materials:
  - tests/fixtures/cup_image.jpg
expected_duration_s: [25, 35]
output_dir: outputs/e2e/<case_id>/
```

步骤:
1. 提取/检索 pattern
2. 分配用户素材
3. 识别缺口
4. 执行补全策略
5. 渲染输出 mp4
6. 验证 mp4 时长在 expected_duration_s 范围内
7. 把生成的 mp4 + template + gap report + log 全部存到 output_dir
8. 打印产出路径

所有路径使用绝对路径。
```

#### `.claude/skills/render-demo-reel.md`(W4 用)
```markdown
---
name: render-demo-reel
description: 跑所有 5 个 demo case,产出答辩用的演示视频集
---

无参数。
跑 `tests/cases/{case_01..case_05}.yaml` 五个 case,每个 case 都用 `/e2e-case` 流程。
最后产出 `outputs/demo_reel/` 下:
- case_01_basic_ecom.mp4
- case_02_severe_gap.mp4
- case_03_pure_mg.mp4
- case_04_multi_version_compare.mp4
- case_05_nl_edit.mp4
- summary.md(每个 case 简介、用到的能力、关键截图)

这是答辩材料的核心交付物。
```

---

<a id="4"></a>
## 4. Subagent 并行/串行策略

### 4.1 什么时候用 subagent

| 场景 | 用不用 | 理由 |
|---|---|---|
| 任务有依赖(B 需要 A 输出) | ❌ 不用,串行 | subagent 不擅长跨上下文传递 |
| 共享文件/状态 | ❌ 不用 | 容易写冲突 |
| 3+ 独立任务、无共享 | ✅ 并行 subagent | 主 context 干净,节省时间 |
| 长研究类任务、结论比过程重要 | ✅ subagent | 不污染主 context |
| 单纯需要更多 context window | ✅ subagent | 每个 subagent 有独立 context |

### 4.2 VST 里典型的并行机会

#### 机会 1:W2 D10 一次性建 5-8 个 3D atom

```
你:用 5 个并行 subagent 分别实现以下 3D atom:
  - 子 agent 1:atom_3d_product_360
  - 子 agent 2:atom_3d_price_card_flip
  - 子 agent 3:atom_3d_text_burst
  - 子 agent 4:atom_3d_compare_split
  - 子 agent 5:atom_3d_gift_box_open

每个 subagent:
  • 调用 /new-3d-atom skill
  • 实现 .tsx 组件
  • 写 demo
  • 入库 jsonl
  • 不要互相依赖
  • 完成后只返回 markdown 摘要:文件路径 + 一句话效果描述
```

→ 5 个 subagent 同时跑,4-5 倍速完成。

#### 机会 2:W3 D17 一次性实现 Strategy A + B + E(无依赖)

```
你:用 3 个并行 subagent:
  • subagent 1:实现 Strategy A 结构重排,文件 gap/strategies/restructure.py + 单元测试
  • subagent 2:实现 Strategy B 文案补全,文件 gap/strategies/caption_fill.py + 单元测试
  • subagent 3:实现 Strategy E 素材重组,文件 gap/strategies/recombine.py + FFmpeg 工具集

完成后各自报告路径 + 测试覆盖率。
```

(Strategy C 包装补全和 Strategy D AIGC 不能并行,因为有共享的 Remotion 组件依赖)

#### 机会 3:W4 D25 一次性渲染 5 个 demo case

```
你:用 5 个并行 subagent,每个跑 /e2e-case caseXX,完成后报告产物路径与渲染时长
```

### 4.3 怎么显式启动并行 subagent

不需要专门的命令,你**只要明确告诉 Claude**:

```
请用 5 个并行 subagent 同时执行以下任务,subagent 之间不要共享状态:
1. ...
2. ...
3. ...
4. ...
5. ...
```

Claude 看到"并行 subagent"会自动用 Task 工具启动。可以同时跑最多 7 个。

### 4.4 subagent 启动后的等待

- Foreground:阻塞主 conversation,直到所有 subagent 完成
- Background:`Ctrl+B` 把 subagent 切到后台,你可以继续干别的事,`/tasks` 查看进度

VST 项目里**建议用 foreground**——4 周时间紧,你需要看到产出再决定下一步。

---

<a id="5"></a>
## 5. Worktrees 隔离开发

### 5.1 为什么需要 worktrees

主流程开发时(在 main 分支),你突然想实验一个 3D atom 的新做法。不想污染主分支也不想停掉主 Claude session。

Git worktree 让一个 repo 可以同时 checkout 多个分支到不同目录:

```bash
git worktree add ../vst-experiment-3d feature/experiment-3d
cd ../vst-experiment-3d
claude   # 启动一个独立的 Claude Code session
```

主 session 在 `vst/`,实验 session 在 `vst-experiment-3d/`,**两个 Claude Code 互不影响**。

### 5.2 VST 适用 worktree 的场景

- **W2 调 prompt 时**:主分支正常推进,worktree 反复试 prompt 不污染 git history
- **W3 试不同补全策略效果**:开 2 个 worktree 跑 A/B 对比
- **W4 答辩材料准备**:一个 worktree 渲染 demo,一个 worktree 写文档,互不抢

### 5.3 命令速查

```bash
# 创建
git worktree add ../<name> <branch-name>

# 列表
git worktree list

# 删除(完成实验后)
git worktree remove ../<name>
```

---

<a id="6"></a>
## 6. 完整工作流:4 周怎么跑

### 6.1 每天的标准流程

```
Morning (5min)
├─ cd vst && git pull
├─ claude                    # 启动 Claude Code
├─ /goal 今天的目标(condition 用真实命令)
└─ 等 Claude 跑,期间审阅 git diff

Mid-day (随时)
├─ /goal              # 看进度
├─ git diff           # 审代码
├─ /verify-build      # 阶段冒烟
└─ 调整方向

Evening (15min)
├─ /verify-build      # 全栈检查
├─ git commit         # 中文 commit message [W2-D10 atoms]
├─ 更新 CLAUDE.md 的进度 checkbox
└─ 写当天小结到 docs/progress.md
```

### 6.2 W1(Day 1-7)— H5 闭环

| Day | Goal 模板 |
|---|---|
| D1 | `/goal` repo init 完成 AND `./scripts/start.sh dev` 五个服务都能起来 AND `curl http://localhost:3000/health` + `http://localhost:8000/health` + `http://localhost:8001/health` + `http://localhost:8188/system_stats` 都返回 200 AND CLAUDE.md 存在且包含 docs/spec.md §0.4 的三个非协商决策 |
| D2 | `/goal` `pytest tests/test_s1.py` 全绿 AND 对 `tests/fixtures/sample_001.mp4` 跑 `extract_basic_info` 函数能产出含 shots/captions/audio_features 的 JSON |
| D3 | `/goal` `pytest tests/test_s2.py` 全绿 AND `kb/extractor/structure.py::extract_structure_template(sample_001)` 输出符合 schemas/structure_template.json AND 输出的 template 至少包含 3 类结构(narrative/temporal/packaging) |
| D4 | `/goal` Remotion 项目能 `npm run remotion:build` AND `services/remotion/src/phases/HookPhase.tsx`, `BuildPhase.tsx`, `CtaPhase.tsx` 三个 phase 组件存在 AND 每个都有最简 demo composition |
| D5 | `/goal` 跑 `/e2e-case basic_synthetic`(用合成数据) 能产出 mp4 文件且 ffprobe 显示时长 > 5s |
| D6 | `/goal` 用户素材分配函数 `material/allocator.py::allocate(template, materials)` 单元测试全绿 AND 跑 e2e basic case 不报错 |
| D7 | `/goal` POST `/api/generate` 上传 sample_001.mp4 + topic="保温杯" + 1 张图 → 5 分钟内返回 mp4 download URL AND 前端首页能展示 H5 闭环 UI |

### 6.3 W2(Day 8-14)— 知识库

| Day | Goal 模板 |
|---|---|
| D8 | `sqlite3 knowledge_base.db ".schema"` 包含 atoms/modules/patterns/generation_log 四表 AND Zod schema 文件在 web/src/schemas/ 下完整 |
| D9 | `sqlite3 knowledge_base.db "SELECT COUNT(*) FROM atoms;"` ≥ 30 AND 每个 atom 都有对应的 Remotion 组件且 npm run remotion:build 通过 |
| **D10** | **`sqlite3 knowledge_base.db "SELECT COUNT(*) FROM atoms WHERE type='3d';"` ≥ 5 AND 每个 3d atom 有 .glb 资源或纯几何实现 AND demo composition 能成功渲染** ← 用 5 并行 subagent |
| D11 | `sqlite3 knowledge_base.db "SELECT phase, COUNT(*) FROM modules GROUP BY phase;"` 每个 phase 至少 3 个 module AND module 的 atomic_composition_json 字段都引用了存在的 atom |
| D12 | `sqlite3 knowledge_base.db "SELECT COUNT(*) FROM patterns;"` ≥ 5 AND 跑 `kb/test/test_pattern_retrieval.py` 全绿 |
| D13 | accumulate_from_sample 函数有完整单元测试 + 对一个新 sample_002.mp4 调用后 atoms count 增加 ≥ 3 |
| D14 | 前端有 `/kb` 路由展示三层知识库浏览器,能看到所有 atom/module/pattern 列表 |

### 6.4 W3 / W4

逻辑相同,按 spec §8 的 D 表设 goal。略。

### 6.5 何时用 `/goal`,何时手动对话

| 场景 | 用 /goal | 手动对话 |
|---|---|---|
| 完整一个 D 的目标(condition 清晰) | ✅ | |
| 创建单个 atom | | ✅(用 /new-atom skill) |
| 探索某个 bug 的根因 | | ✅(需要你边看边判断) |
| 跑 verify-build | | ✅(单命令) |
| W2 D10 一次性建 5 个 3D atom | ✅ + 并行 subagent | |
| 答辩 PPT 写作 | | ✅ |

---

<a id="7"></a>
## 7. `CLAUDE.md` 进阶配置

spec §9.2 已经给了基础版,这里补几个 VST 特定的进阶段落:

```markdown
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
- 修改 knowledge_base.db schema

## 模型选择
- 主 session 用 Opus(复杂推理 + 架构决策)
- Subagent 默认用 Sonnet(执行性任务足够,token 省 3x)
- 在 `~/.claude/settings.json` 设置 `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-4-5`

## 当遇到 spec 模糊的情况
1. 先按你认为最合理的方案做
2. 在代码注释里加 `// SPEC-AMBIG: <你的理解>`
3. commit message 加 `[SPEC-AMBIG]` 标签
4. 在 docs/progress.md 当日条目里记录

## 何时停下来问我
- 需要付费 API 调用前
- 需要安装新的全局工具/依赖前
- 需要做 `git push --force` 或修改 main 分支前
- 需要修改 CLAUDE.md 本身前
- 任何会产生不可逆副作用的操作前

其他情况都直接做。
```

---

<a id="8"></a>
## 8. 常见坑与规避

### 8.1 `/goal` 烧 token 死循环

**症状**:`/goal` 跑了 50 轮还在跑,evaluator 总判"接近完成但还差一点"。

**根因**:condition 写得太模糊,Claude 每轮做点边角工作 evaluator 就承认"有进展但未完成"。

**修复**:
- 把 condition 改为**真实可执行的 shell 命令**(`pytest X` / `curl Y`)
- 加显式 turn cap(`最多 N 轮`)
- 用 `/goal clear` 立刻停,重写 condition

### 8.2 condition 被 Claude "作弊"满足

**症状**:Claude 把失败的测试删了,evaluator 看 `pytest` 通过,goal 满足。

**修复**:
- condition 加**反向保护**:`pytest 全绿 AND tests/ 下文件数不少于 N AND 关键测试用例存在(检查文件内容包含特定字符串)`
- 每个 goal 结束后**人工 review `git diff`**

### 8.3 R3F + Remotion 的"useFrame 陷阱"

**症状**:3D atom 在 Studio 预览正常,但渲染输出后动画卡住或全黑。

**根因**:用了 R3F 原生的 `useFrame()` 而不是 Remotion 的 `useCurrentFrame()`。

**修复**:
- CLAUDE.md 里明确写了"3D 必须用 useCurrentFrame"
- new-3d-atom skill 里反复强调
- 第一个 3D atom 写好后,在 `services/remotion/src/atoms/3d/_TEMPLATE_DO_NOT_DELETE.tsx` 留一个标准模板,以后所有 3D atom 都参考它

### 8.4 ComfyUI workflow 找不到模型

**症状**:Strategy D 调 ComfyUI 返回 "checkpoint not found"。

**修复**:
- `scripts/download_models.sh` 必须包含 SDXL base + IP-Adapter
- workflow JSON 里写**相对路径**或**自动检测**模型名,不硬编码

### 8.5 Doubao API rate limit

**症状**:W3 跑批量 e2e case 时部分调用失败。

**修复**:
- 加 retry with exponential backoff
- 加本地缓存:同样的 prompt + input 直接读缓存
- 单元测试用 mock,只在真 e2e 才打真 API

### 8.6 Subagent 写冲突

**症状**:并行 subagent 1 和 subagent 2 都在改 `kb/seeds/atoms.jsonl`,最终一个被覆盖。

**修复**:
- jsonl 文件:每个 atom 单独一个文件 `kb/seeds/atoms/<atom_id>.json`,启动时合并
- 任何会被多 subagent 写的文件改成"一 task 一文件"模式

---

<a id="9"></a>
## 9. 前置准备 + 第一天开工脚本

### 9.1 Day 0(开工前一天,4 小时)

参考 spec §12,搞定 8 件事。最重要的两件:

```bash
# 1. 升级 Claude Code 到 v2.1.139+
npm update -g @anthropic-ai/claude-code
claude --version   # 必须 >= 2.1.139,否则 /goal 不能用

# 2. 配置模型环境变量(节省 subagent token)
echo 'export CLAUDE_CODE_SUBAGENT_MODEL="claude-sonnet-4-5"' >> ~/.zshrc
source ~/.zshrc
```

### 9.2 W1 D1 上午第一小时

```bash
# 1. 创建项目
mkdir vst && cd vst
git init
git checkout -b main

# 2. 创建基础文件
cat > CLAUDE.md << 'EOF'
# CLAUDE.md — VST 项目宪法

## 项目身份
- 项目代号:VST(ViralStructTransfer)
- 完整 spec:`docs/spec.md`(请先完整读一遍)
- 评分对照:`docs/grading_rubric.md`
- 4 周 hackathon,目标 92-104 分(满分 110)

## 三个非协商决策
1. 零外部视频生成 API
2. Remotion 是渲染层唯一标准,3D 用 @remotion/three
3. 必须本地一键部署

## 当前进度
- [ ] W1 H5 闭环
- [ ] W2 知识库
- [ ] W3 缺口处理
- [ ] W4 可视化与答辩

(详细规则与 routing 见后续追加段落,先以 docs/spec.md §9.2 为准)
EOF

mkdir -p docs .claude/skills

# 3. 把 spec 拷进来
# 把 viral_structure_transfer_spec_v3_FINAL.md 复制为 docs/spec.md

# 4. 启动 Claude Code
claude

# 5. 在 Claude Code 里
> 请先完整阅读 docs/spec.md。读完后回答三个问题:
>   1. 这个项目的产品形态是什么?
>   2. 三个非协商决策是什么?
>   3. W1 D1 我们应该做什么?
> 不要写任何代码,先确认你理解了 spec。
```

Claude 会读完 spec 给你回答。**验证它真的读懂了**,然后:

```bash
> 好,现在请帮我完成 W1 D1 的工作。先把 .claude/skills/ 下的 8 个 skill 文件都创建好(内容参考 docs/claude_workflow_manual.md §3.4),然后创建项目基础目录骨架(参考 spec §9.1)。最后跑 ./scripts/start.sh 看看是否五个服务都能 hello world。
>
> /goal 项目骨架完成:.claude/skills 下有 8 个 .md 文件,services/{node,python,remotion}/ 三个目录都能 npm/uvicorn 启动并响应 /health 200,web/ 能 npm run dev,scripts/start.sh 一键启动所有服务;最多 12 轮。
```

剩下的事 Claude 自己跑。你审 diff、写文档、继续准备下一天的 condition。

### 9.3 第一次跑通后的"庆祝时刻"

W1 D7 当所有 condition 通过、H5 闭环跑通时,做这件事:

1. **录一段 30 秒的 demo screen recording**:打开 H5 → 上传 sample → 输入"保温杯" → 等待 → 下载 mp4 → 播放
2. **commit 一个 tag**:`git tag w1-h5-closed-loop`
3. **更新 docs/progress.md**

这一刻就锁了基础分约 30 分。后面 3 周都是在这个基础上加分。

---

## 最后:一个忠告

`/goal` 是 2026 年 5 月 12 号刚出的功能,**它会让你产生"全自动"的错觉**。但 hackathon 4 周的产出质量主要由 spec 质量决定,不是 token 量决定。

**你的核心工作其实是**:
1. 写好 spec(已完成,本文档 + v3 FINAL)
2. 写好每天的 goal condition(决定 Claude 跑得对不对)
3. 审 git diff(决定代码是不是真的在前进)
4. 在 spec 模糊处做仲裁(Claude 替代不了你)

让 Claude 去打字,你去做产品决策。这才是 2026 年的正确姿势。

祝你拿满分。

---

*本手册随 Claude Code 版本更新可能需要修订。当前对应 v2.1.139。*
