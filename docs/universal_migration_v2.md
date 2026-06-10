# 通用视频风格迁移系统 v2 — 基于真实复杂度的方案

## 22 Token 方案的致命缺陷

| 缺陷 | 说明 |
|------|------|
| **只有全局，没有逐元素** | 22 token 控制整场风格，但每个元素可以有自己的入场/出场/颜色/位置 |
| **无法描述时间编排** | 元素 A 退出的同时 B 入场、交错、级联、同步节拍 — 这些需要逐元素时间轴 |
| **无法描述空间关系** | 元素之间的对齐、分组、层级、负空间 — 需要完整的场景图 |
| **无法描述复合效果** | 粒子跟随文字、位移贴图、运动模糊 — 需要跨层引用 |

**真实数据**：一个 10 元素场景最少需要 ~132 个属性，是 22 token 的 6 倍。专业级别需要 50-100 倍。

## 正确的架构：两层分离

```
参考视频 → [VLM 分析] → SceneDescription (完整场景结构)
                              │
                    ┌─────────┴─────────┐
                    │                   │
              Structure 层          Style 层
           (布局/时序/元素类型)    (颜色/字体/缓动)
                    │                   │
                    └─────────┬─────────┘
                              │
新主题 → [LLM 填内容] → Content (文字/数据)
                              │
              Structure + Content + Style → [渲染] → MP4
```

**关键洞察**：
- **Structure** = 参考视频的"骨架"（布局模式、时序编排、元素类型）— **迁移这个**
- **Style** = 参考视频的"皮肤"（颜色、字体、缓动曲线）— **迁移这个**
- **Content** = 具体的文字和数据 — **替换这个**

## SceneDescription 结构

```typescript
interface SceneDescription {
  // 全局
  canvas: { width: number; height: number; fps: number; duration: number };
  background: { color: string; gradient?: string; pattern?: string };

  // 元素列表（按时间顺序）
  elements: Element[];

  // 转场
  transitions: Transition[];

  // 全局效果
  effects: GlobalEffect[];
}

interface Element {
  // ── 身份 ──
  id: string;
  type: 'text' | 'image' | 'shape' | 'group' | 'particle' | 'video';

  // ── 内容（可替换）──
  content: {
    text?: string;           // 文字内容
    src?: string;            // 图片/视频路径
    shapeType?: 'rect' | 'circle' | 'line' | 'path';
    children?: Element[];    // 子元素（group 类型）
  };

  // ── 空间属性（逐元素）──
  spatial: {
    x: number | string;      // 绝对 px 或百分比
    y: number | string;
    width: number | string;
    height: number | string;
    anchorX: number;         // 锚点 0-1
    anchorY: number;
    rotation: number;        // 度
    scaleX: number;
    scaleY: number;
    skewX: number;
    skewY: number;
    zIndex: number;
  };

  // ── 外观属性（逐元素）──
  appearance: {
    opacity: number;         // 0-1
    fill: string;            // 颜色/渐变
    stroke: string;
    strokeWidth: number;
    borderRadius: number;
    shadow: { color: string; x: number; y: number; blur: number; spread: number };
    blendMode: string;
    blur: number;
    mask?: { type: 'rect' | 'circle' | 'path'; shape: string };
  };

  // ── 排版属性（text 类型）──
  typography?: {
    fontFamily: string;
    fontSize: number;
    fontWeight: number;
    lineHeight: number;
    letterSpacing: number;
    textAlign: 'left' | 'center' | 'right';
    color: string;
    gradient?: string;
    textShadow?: string;
    textTransform?: 'uppercase' | 'lowercase' | 'none';
  };

  // ── 时间属性（逐元素）──
  timing: {
    inPoint: number;         // 入场帧
    outPoint: number;        // 出场帧
    entrance: AnimationSpec; // 入场动画
    exit: AnimationSpec;     // 出场动画
    staggerIndex: number;    // 在兄弟元素中的交错序号
    staggerDelay: number;    // 交错延迟帧数
  };
}

interface AnimationSpec {
  type: 'none' | 'fade' | 'slide' | 'scale' | 'rotate' | 'clip' | '3d' | 'blur' | 'custom';
  direction?: 'left' | 'right' | 'top' | 'bottom' | 'center';
  duration: number;          // 帧数
  easing: EasingSpec;
  properties: Record<string, [number, number]>; // 属性名 → [起始值, 结束值]
}

interface EasingSpec {
  type: 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out' | 'spring' | 'bounce' | 'cubic-bezier';
  params?: number[];         // cubic-bezier 的 4 个值，spring 的 damping/stiffness/mass
}

interface Transition {
  type: 'cut' | 'fade' | 'wipe' | 'morph' | 'slide' | 'zoom' | 'parallax' | 'glitch' | 'particle';
  fromElement: string;
  toElement: string;
  duration: number;
  easing: EasingSpec;
  params: Record<string, number>; // 方向、距离、角度等
}

interface GlobalEffect {
  type: 'vignette' | 'grain' | 'color-grade' | 'particle-bg' | 'scanline';
  params: Record<string, number | string>;
}
```

## 迁移策略：Structure 迁移 + Style 替换

### 什么是 Structure（必须迁移）

| 维度 | 例子 | 迁移方式 |
|------|------|---------|
| 元素类型序列 | text → cards → quote → logo | 保持不变 |
| 布局模式 | 元素在 (50%, 30%) 居中 | 按画布比例缩放 |
| 时序编排 | A 入场→B 入场→A 出场→C 入场 | 保持相对时间关系 |
| 空间关系 | A 在 B 上方 50px | 保持相对距离 |
| 动画模式 | A 从左滑入，B 从右滑入 | 保持动画类型和方向 |
| 交错模式 | 元素依次入场，间隔 5 帧 | 保持交错间隔 |

### 什么是 Style（可以替换）

| 维度 | 参考视频 | 新视频 | 替换方式 |
|------|---------|--------|---------|
| 颜色 | #F5F5F5 底 + #000 字 + #0000FF 强调 | #050510 底 + #FFF 字 + #3B82F6 强调 | Token 映射 |
| 字体 | serif 标题 + sans 正文 | sans 标题 + mono 正文 | Token 映射 |
| 缓动 | spring 弹性 | ease-out 平滑 | Token 映射 |
| 阴影 | 无阴影 | 强阴影 | Token 映射 |
| 圆角 | 0px 直角 | 16px 圆角 | Token 映射 |

### 什么是 Content（必须替换）

| 维度 | 参考视频 | 新视频 | 替换方式 |
|------|---------|--------|---------|
| 文字 | "造物 逐空 焕新" | "中国古代史发展" | LLM 生成 |
| 图片 | 展览海报 | 历史图片 | 用户提供/AIGC |
| Logo | 小红书 | 用户品牌 | 用户提供 |

## StyleToken v2（分层 token）

```typescript
interface StyleTokenV2 {
  // ── 全局 mood（22 个）──
  global: {
    // 颜色
    bgColor: string;
    textColor: string;
    textSecondaryColor: string;
    accentColor: string;
    accentGlow: string;
    // 排版
    headingFont: string;
    bodyFont: string;
    headingSize: number;
    bodySize: number;
    headingWeight: number;
    // 动画
    globalEasing: EasingSpec;
    globalDuration: number;
    globalStagger: number;
    // 形状
    borderRadius: number;
    shadowIntensity: number;
    borderStyle: string;
    // 布局
    layoutMode: 'centered' | 'diagonal' | 'grid' | 'asymmetric' | 'stacked';
    rotation: number;
    textDirection: 'horizontal' | 'vertical' | 'mixed';
    alignment: 'left' | 'center' | 'right';
    // 节奏
    pacing: 'fast' | 'medium' | 'slow';
  };

  // ── 逐元素覆盖（可选）──
  elementOverrides?: Record<string, Partial<ElementOverride>>;

  // ── 逐类型覆盖（可选）──
  typeOverrides?: {
    text?: Partial<ElementOverride>;
    image?: Partial<ElementOverride>;
    shape?: Partial<ElementOverride>;
  };
}

interface ElementOverride {
  entranceType: string;
  entranceDirection: string;
  entranceDuration: number;
  entranceEasing: EasingSpec;
  exitType: string;
  exitDirection: string;
  exitDuration: number;
  exitEasing: EasingSpec;
  fill: string;
  stroke: string;
  opacity: number;
  scale: number;
  rotation: number;
  blur: number;
  shadow: boolean;
}
```

## VLM 提取 SceneDescription

```python
def extract_scene_description(video_path: str) -> SceneDescription:
    """用 VLM 分析参考视频，提取完整的 SceneDescription。"""

    # 1. 提取关键帧（每秒 2 帧）
    frames = extract_frames(video_path, fps=2)

    # 2. VLM 分析：逐帧识别元素、位置、颜色、文字
    elements = vlm_analyze_elements(frames)

    # 3. 光流分析：追踪元素运动轨迹
    motions = optical_flow_track(frames)

    # 4. 合并：VLM 识别的元素 + 光流追踪的运动 → 完整 SceneDescription
    scene = merge_elements_and_motions(elements, motions)

    return scene
```

**VLM prompt 示例**：
```
分析这些视频帧，识别每个可见元素：
1. 元素类型（text/shape/image）
2. 精确位置（x%, y% 相对于画布）
3. 尺寸（width%, height%）
4. 文字内容（逐字抄录）
5. 颜色（十六进制）
6. 字体（serif/sans/mono）
7. 字号（相对于画布高度的百分比）
8. 旋转角度
9. 入场方向（从哪出现）
10. 出场方向（往哪消失）

返回 JSON 数组，每个元素一个对象。
```

## 完整迁移流程

```
输入: 任意参考视频 + 新主题
    │
    ▼
[Step 1] VLM 提取 SceneDescription
    → 完整场景结构（元素、位置、时序、动画）
    │
    ▼
[Step 2] 分离 Structure 和 Style
    → Structure: 元素类型序列、布局模式、时序编排
    → Style: 颜色、字体、缓动、阴影
    │
    ▼
[Step 3] LLM 生成 Content
    → 根据新主题填充文字/数据
    │
    ▼
[Step 4] Style 替换（可选）
    → 用户可以调整颜色/字体/缓动
    │
    ▼
[Step 5] 渲染
    → 用 Structure + Content + Style 生成新视频
```

## 与之前方案的对比

| 维度 | v1 (22 token) | v2 (SceneDescription) |
|------|---------------|----------------------|
| 精度 | 只能描述全局 mood | 描述每个元素的每个属性 |
| 迁移质量 | 丢失大部分视觉语言 | 完整保留布局/时序/动画 |
| 复杂度 | 低（22 个值） | 高（~132+ 个值） |
| VLM 覃度 | 简单（颜色/字体） | 深度（逐元素识别+光流追踪） |
| 适用场景 | 快速原型 | 真正的风格迁移 |

## 实施优先级

| Phase | 内容 | 工作量 |
|-------|------|--------|
| 1 | 定义 SceneDescription schema | 小 |
| 2 | 实现 VLM SceneDescription 提取 | 中 |
| 3 | 实现 Structure/Style 分离 | 中 |
| 4 | 实现 StyleToken 映射 | 小 |
| 5 | 实现 StyleDrivenVideo 渲染 | 大 |
| 6 | 集成 pipeline | 中 |
