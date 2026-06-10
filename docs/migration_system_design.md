# VST 视觉风格迁移系统 — 可行方案

## 问题诊断

当前系统的核心问题不是"组件数量不够"，而是**组件不支持风格变体**。

现有组件（WordReveal/GlassCard/GradientText...）全部硬编码了 ProductPromo 的深色背景+英文风格。无论输入什么参考视频，输出都是同一个模板。

## 研究结论

| 领域 | 结论 |
|------|------|
| 学术界 | 没有现成的 motion graphics 风格迁移方案（研究空白） |
| 工业界 | After Effects MOGRT / Lottie / CapCut 都是手动模板，不自动迁移 |
| 可行路径 | 组件变体化（Variant Props）+ 风格提取 → 设计令牌映射 |

## 架构设计

### 核心思路：风格 = 设计令牌 + 布局模式 + 动画模式

```
参考视频
    │
    ▼
[S1] 视频分析 → 视觉语言 JSON
    │
    ▼
[StyleExtractor] → StyleProfile (设计令牌 + 布局 + 动画)
    │
    ▼
[StyleMapper] → 组件变体选择 + 参数配置
    │
    ▼
[Composer] → 用变体组件渲染新视频
```

### StyleProfile 结构

```typescript
interface StyleProfile {
  // 设计令牌
  tokens: {
    bg: string;           // "#F5F5F5" 或 "#050510"
    textPrimary: string;  // "#000000"
    textSecondary: string;// "#666666"
    accent: string;       // "#0000FF"
    fontHeading: string;  // "serif" | "sans-serif" | "display"
    fontBody: string;
  };

  // 布局模式
  layout: {
    type: 'centered' | 'diagonal' | 'grid' | 'asymmetric' | 'editorial';
    textDirection: 'horizontal' | 'vertical' | 'mixed';
    rotation: number;     // 0, 15, 30, -15, -30
    alignment: 'left' | 'center' | 'right';
  };

  // 动画模式
  animation: {
    textEntrance: 'fade' | 'slide' | 'scale' | '3d-emerge' | 'typewriter';
    textDirection: 'from-left' | 'from-right' | 'from-bottom' | 'from-top';
    transition: 'cut' | 'fade' | 'wipe' | 'morph';
    stagger: 'char' | 'word' | 'line' | 'none';
    easing: 'linear' | 'ease-out' | 'ease-in-out' | 'spring' | 'bounce';
  };

  // 节奏模式
  rhythm: {
    segmentPattern: 'fast-slow-fast' | 'steady' | 'crescendo' | 'custom';
    avgShotDuration: number;
    beatCount: number;
  };
}
```

### 组件变体化方案

**当前**（硬编码风格）：
```tsx
<WordReveal text="Hello" fontSize={48} />
// 永远是深色背景、英文、从下往上 slide
```

**目标**（变体化）：
```tsx
<TextReveal
  text="中国古代史"
  variant="diagonal"      // centered | diagonal | grid | asymmetric
  styleProfile={profile}  // 从参考视频提取的 StyleProfile
  fontSize={72}
  rotation={30}
/>
// 根据 profile 自动选择：浅灰背景、中文黑体、30° 斜角、从右滑入
```

### 需要的新组件（不是增加数量，而是增加变体）

| 现有组件 | 需要的变体 | 说明 |
|----------|-----------|------|
| WordReveal | +diagonal, +vertical, +3d-emerge | 支持斜排、竖排、3D 浮现 |
| GradientText | +minimal, +serif, +mixed-lang | 支持极简、衬线、中英混排 |
| GlassCard | +light-bg, +outline-only | 支持浅色背景、线框风格 |
| Background | +light, +gradient-light, +paper | 支持浅色背景、纸张质感 |
| MarqueeText | +vertical, +diagonal | 支持竖排、斜排跑马灯 |

### 新增布局组件

| 组件 | 功能 |
|------|------|
| DiagonalLayout | 30° 斜角文字布局，支持中英混排 |
| VerticalTextLayout | 竖排文字布局 |
| MixedLayout | 横排+竖排+斜排混合布局 |
| RibbonTransition | 条带卷入转场效果 |

## 实施计划

### Phase 1: StyleExtractor（从参考视频提取 StyleProfile）

扩展现有的 S1 VLM 分析，提取结构化的 StyleProfile。

**文件**: `services/python/style_extractor.py`

```python
def extract_style_profile(video_path: str) -> StyleProfile:
    """用 VLM 分析参考视频，提取 StyleProfile。"""
    # 1. 提取关键帧
    # 2. VLM 分析：布局/色彩/排版/动画/转场
    # 3. 结构化为 StyleProfile JSON
```

### Phase 2: 组件变体化

给现有组件增加 `variant` 和 `styleProfile` props。

**修改文件**:
- `web/src/components/mg/TextReveal.tsx` — 新建，合并 WordReveal + 斜排/竖排变体
- `web/src/components/mg/DiagonalText.tsx` — 新建，30° 斜角文字
- `web/src/components/mg/VerticalText.tsx` — 新建，竖排文字
- `web/src/design-tokens/index.ts` — 增加风格变体令牌

### Phase 3: StyleMapper（风格 → 组件参数映射）

**文件**: `services/python/style_mapper.py`

```python
def map_style_to_components(profile: StyleProfile, content: dict) -> list[ComponentSpec]:
    """将 StyleProfile 映射为组件参数列表。"""
    # 根据 profile.layout.type 选择布局组件
    # 根据 profile.animation.textEntrance 选择动画变体
    # 根据 profile.tokens 选择配色
```

### Phase 4: 新 Composition — StyleDrivenVideo

**文件**: `web/src/remotion/compositions/StyleDrivenVideo.tsx`

```tsx
export function StyleDrivenVideo({ styleProfile, content }) {
  return (
    <Background variant={styleProfile.tokens.bg === '#F5F5F5' ? 'light' : 'dark'}>
      {content.segments.map((seg, i) => (
        <Sequence key={i} from={seg.start} durationInFrames={seg.duration}>
          <SegmentRenderer
            segment={seg}
            styleProfile={styleProfile}
          />
        </Sequence>
      ))}
    </Background>
  );
}
```

## 文件清单

### 新建
| 文件 | 功能 |
|------|------|
| `services/python/style_extractor.py` | VLM 提取 StyleProfile |
| `services/python/style_mapper.py` | StyleProfile → 组件参数映射 |
| `web/src/components/mg/TextReveal.tsx` | 通用文字揭示（支持多变体） |
| `web/src/components/mg/DiagonalText.tsx` | 斜角文字组件 |
| `web/src/components/mg/VerticalText.tsx` | 竖排文字组件 |
| `web/src/components/mg/RibbonTransition.tsx` | 条带卷入转场 |
| `web/src/remotion/compositions/StyleDrivenVideo.tsx` | 风格驱动合成 |

### 修改
| 文件 | 改动 |
|------|------|
| `services/python/main.py` | 新增 /extract_style endpoint |
| `services/python/s1_analyzer.py` | VLM prompt 增加动画/转场分析 |
| `web/src/design-tokens/index.ts` | 增加风格变体令牌 |
| `web/src/remotion/root.tsx` | 注册 StyleDrivenVideo |

## 验证方案

1. 用 55702300.mov 提取 StyleProfile（浅灰+黑蓝+斜排+条带动画）
2. 用 StyleProfile + "中国古代史发展" 内容生成新视频
3. 对比：新视频应具有参考视频的视觉语言（浅灰底、30° 斜角文字、条带转场）

## 与学术界的区别

| 学术方案 | VST 方案 |
|----------|---------|
| 像素级风格迁移（CNN/Diffusion） | 设计令牌级风格迁移（JSON → CSS） |
| 需要训练模型 | 零训练，纯规则+VLM |
| 适用于自然图像 | 专为 motion graphics 设计 |
| 不处理布局/排版 | 核心就是布局/排版迁移 |
