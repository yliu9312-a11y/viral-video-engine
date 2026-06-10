# 通用视频风格迁移系统 — 最终方案

## 核心洞察

**问题不是"组件不够"，而是"组件不读 token"。**

现有组件硬编码了 ProductPromo 风格。解决方案：让所有组件从 StyleToken 读取样式，而不是硬编码。

**22 个原子 token = 任何短视频的视觉 DNA。**

## 架构：3 层分离

```
参考视频 → [VLM 提取] → StyleToken JSON (22 个值)
                              ↓
新主题   → [LLM 生成] → Content JSON (文字/图片)
                              ↓
              StyleToken + Content → [StyleDrivenVideo] → MP4
```

**关键：Style 和 Content 完全分离。同一套 Content 换 StyleToken 就是不同风格。同一套 StyleToken 换 Content 就是不同主题。**

## StyleToken Schema (22 个原子值)

```typescript
interface StyleToken {
  // ── 颜色 (5) ──
  color: {
    background: string;     // "#F5F5F5" 或 "#050510"
    text: string;           // "#000000" 或 "#FFFFFF"
    textSecondary: string;  // "#666666" 或 "#888888"
    accent: string;         // "#0000FF" 或 "#3B82F6"
    accentGlow: string;     // "rgba(0,0,255,0.3)" 或 "rgba(59,130,246,0.3)"
  };

  // ── 排版 (5) ──
  typography: {
    headingFont: string;    // "serif" | "sans-serif" | "monospace" | "cursive"
    bodyFont: string;
    headingSize: number;    // 48-96
    bodySize: number;       // 16-32
    headingWeight: number;  // 400-900
  };

  // ── 布局 (4) ──
  layout: {
    type: 'centered' | 'diagonal' | 'grid' | 'asymmetric' | 'stacked';
    rotation: number;       // -45 到 45 度
    textDirection: 'horizontal' | 'vertical' | 'mixed';
    alignment: 'left' | 'center' | 'right';
  };

  // ── 动画 (5) ──
  motion: {
    textEntrance: 'fade' | 'slide' | 'scale' | '3d-emerge' | 'typewriter' | 'clip-reveal';
    entranceDirection: 'from-left' | 'from-right' | 'from-bottom' | 'from-top' | 'from-center';
    easing: 'linear' | 'ease-out' | 'ease-in-out' | 'spring' | 'bounce';
    stagger: number;        // 0-10 帧，元素交错间隔
    duration: number;       // 入场动画帧数
  };

  // ── 形状 (3) ──
  shape: {
    borderRadius: number;   // 0-9999
    shadowIntensity: number; // 0-1 (0=无阴影, 1=强阴影)
    borderStyle: 'none' | 'solid' | 'dashed' | 'glow';
  };
}
```

## VLM 提取流程

```python
# services/python/style_extractor.py

def extract_style_tokens(video_path: str) -> StyleToken:
    """用 VLM 分析参考视频，提取 22 个原子 token。"""

    # 1. 提取 5 个关键帧（均匀分布）
    frames = extract_key_frames(video_path, n=5)

    # 2. VLM 分析（一次调用，返回结构化 JSON）
    prompt = """
    分析这些视频帧的视觉风格，返回 JSON：
    {
      "color": {
        "background": "十六进制背景色",
        "text": "主文字色",
        "textSecondary": "次要文字色",
        "accent": "强调色",
        "accentGlow": "rgba 发光色"
      },
      "typography": {
        "headingFont": "serif/sans-serif/monospace/cursive",
        "bodyFont": "...",
        "headingSize": 72,
        "bodySize": 18,
        "headingWeight": 800
      },
      "layout": {
        "type": "centered/diagonal/grid/asymmetric/stacked",
        "rotation": 30,
        "textDirection": "horizontal/vertical/mixed",
        "alignment": "left/center/right"
      },
      "motion": {
        "textEntrance": "fade/slide/scale/3d-emerge/typewriter/clip-reveal",
        "entranceDirection": "from-left/from-right/from-bottom/from-top/from-center",
        "easing": "linear/ease-out/ease-in-out/spring/bounce",
        "stagger": 3,
        "duration": 20
      },
      "shape": {
        "borderRadius": 0,
        "shadowIntensity": 0.3,
        "borderStyle": "none/solid/dashed/glow"
      }
    }
    """

    return vlm_call(frames, prompt)
```

## 组件如何读取 Token

```tsx
// 所有组件通过 context 读取 StyleToken
const StyleContext = React.createContext<StyleToken>(DEFAULT_TOKENS);

// 文字揭示组件 — 根据 token 自动选择变体
function TextReveal({ text, delay = 0 }) {
  const style = useContext(StyleContext);
  const frame = useCurrentFrame();
  const f = Math.max(0, frame - delay);

  // 根据 layout.rotation 决定旋转
  const rotation = style.layout.rotation;

  // 根据 motion.textEntrance 决定入场方式
  const entrance = getEntranceAnimation(
    style.motion.textEntrance,
    style.motion.entranceDirection,
    f,
    style.motion.duration,
    style.motion.easing
  );

  // 根据 color 决定颜色
  const textColor = style.color.text;

  // 根据 typography 决定字体
  const font = style.typography.headingFont;
  const size = style.typography.headingSize;

  return (
    <div style={{
      transform: `rotate(${rotation}deg) ${entrance.transform}`,
      opacity: entrance.opacity,
      color: textColor,
      fontFamily: font,
      fontSize: size,
      fontWeight: style.typography.headingWeight,
    }}>
      {text}
    </div>
  );
}

// 入场动画工厂函数
function getEntranceAnimation(type, direction, frame, duration, easing) {
  const progress = easeMap[easing](frame / duration);

  switch (type) {
    case 'fade':
      return { opacity: progress, transform: '' };
    case 'slide':
      const slideMap = {
        'from-left': `translateX(${(1-progress) * -100}px)`,
        'from-right': `translateX(${(1-progress) * 100}px)`,
        'from-bottom': `translateY(${(1-progress) * 100}px)`,
        'from-top': `translateY(${(1-progress) * -100}px)`,
      };
      return { opacity: progress, transform: slideMap[direction] };
    case 'scale':
      return { opacity: progress, transform: `scale(${0.5 + progress * 0.5})` };
    case '3d-emerge':
      return { opacity: progress, transform: `perspective(800px) translateZ(${(1-progress) * -200}px)` };
    case 'clip-reveal':
      return { opacity: 1, transform: '', clipPath: `inset(0 ${(1-progress)*100}% 0 0)` };
    default:
      return { opacity: progress, transform: '' };
  }
}
```

## 布局如何读取 Token

```tsx
// 根据 layout.type 自动选择布局模式
function StyleLayout({ children, segments }) {
  const style = useContext(StyleContext);

  switch (style.layout.type) {
    case 'diagonal':
      return <DiagonalLayout rotation={style.layout.rotation}>{children}</DiagonalLayout>;
    case 'grid':
      return <GridLayout alignment={style.layout.alignment}>{children}</GridLayout>;
    case 'asymmetric':
      return <AsymmetricLayout>{children}</AsymmetricLayout>;
    case 'stacked':
      return <StackedLayout>{children}</StackedLayout>;
    case 'centered':
    default:
      return <CenteredLayout>{children}</CenteredLayout>;
  }
}

// 斜角布局 — 文字按指定角度排列
function DiagonalLayout({ rotation, children }) {
  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: '100%',
      overflow: 'hidden',
    }}>
      {React.Children.map(children, (child, i) => (
        <div style={{
          position: 'absolute',
          top: `${20 + i * 25}%`,
          left: '50%',
          transform: `translateX(-50%) rotate(${rotation}deg)`,
          transformOrigin: 'center',
        }}>
          {child}
        </div>
      ))}
    </div>
  );
}
```

## 背景如何读取 Token

```tsx
function StyleBackground() {
  const style = useContext(StyleContext);
  const isLight = isLightColor(style.color.background);

  return (
    <AbsoluteFill style={{ background: style.color.background }}>
      {/* 浅色背景：加微妙纹理 */}
      {isLight && (
        <AbsoluteFill style={{
          backgroundImage: `radial-gradient(circle at 50% 50%, ${style.color.accentGlow} 0%, transparent 50%)`,
          opacity: 0.1,
        }} />
      )}
      {/* 深色背景：加粒子 */}
      {!isLight && (
        <ParticleBg count={20} color={style.color.accent} opacity={0.2} />
      )}
    </AbsoluteFill>
  );
}
```

## Content 结构（与 Style 分离）

```typescript
interface VideoContent {
  topic: string;
  segments: Segment[];
}

interface Segment {
  type: 'title' | 'cards' | 'quote' | 'grid' | 'marquee' | 'logo';
  duration: number; // 帧数
  data: {
    text?: string;
    items?: { icon: string; title: string; desc: string }[];
    marquee?: string;
    logoText?: string;
  };
}
```

## StyleDrivenVideo 合成

```tsx
function StyleDrivenVideo({ styleToken, content }: { styleToken: StyleToken; content: VideoContent }) {
  return (
    <StyleContext.Provider value={styleToken}>
      <StyleBackground />
      <AbsoluteFill>
        <StyleLayout>
          {content.segments.map((seg, i) => {
            const startFrame = content.segments.slice(0, i).reduce((s, seg) => s + seg.duration, 0);
            return (
              <Sequence key={i} from={startFrame} durationInFrames={seg.duration}>
                <SegmentRenderer segment={seg} />
              </Sequence>
            );
          })}
        </StyleLayout>
      </AbsoluteFill>
    </StyleContext.Provider>
  );
}

function SegmentRenderer({ segment }) {
  switch (segment.type) {
    case 'title':
      return <TextReveal text={segment.data.text} />;
    case 'cards':
      return <CardGroup items={segment.data.items} />;
    case 'quote':
      return <TextReveal text={segment.data.text} />;
    case 'grid':
      return <GridGroup items={segment.data.items} />;
    case 'marquee':
      return <MarqueeText text={segment.data.marquee} />;
    case 'logo':
      return <LogoDisplay text={segment.data.logoText} />;
  }
}
```

## 完整流程

```
输入: 55702300.mov + 主题"中国古代史发展"
    │
    ▼
[1] VLM 提取 StyleToken
    → { bg: #F5F5F5, text: #000, accent: #0000FF, layout: diagonal, rotation: 30, ... }
    │
    ▼
[2] LLM 生成 Content
    → { topic: "中国古代史发展", segments: [
         { type: "title", text: "五千年文明长河", duration: 120 },
         { type: "cards", items: [{icon:"🏛️", title:"秦汉", desc:"大一统"}, ...], duration: 150 },
         { type: "quote", text: "以史为鉴，可以知兴替", duration: 90 },
         ...
       ] }
    │
    ▼
[3] 知识验证（可选）
    → DuckDuckGo 搜索验证事实准确性
    │
    ▼
[4] StyleDrivenVideo 渲染
    → StyleToken 控制视觉风格（浅灰底、30° 斜角、slide 入场）
    → Content 控制内容（中国古代史的文字和卡片）
    → 输出 MP4
```

## 优势

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| 风格支持 | 只有 ProductPromo 深色风格 | 任意风格（由 StyleToken 决定） |
| 组件复用 | 每种风格要新组件 | 同一组组件，换 token 就换风格 |
| 迁移能力 | 不存在 | VLM 提取 token → 自动迁移 |
| 扩展性 | 加风格=加组件 | 加风格=加 token 预设 |

## 实施步骤

1. **定义 StyleToken schema** — 22 个原子值
2. **实现 style_extractor.py** — VLM 提取 token
3. **创建 StyleContext** — React context 传递 token
4. **改造现有组件** — 从 context 读取 token（不硬编码）
5. **新建布局组件** — DiagonalLayout / GridLayout / AsymmetricLayout
6. **创建 StyleDrivenVideo** — 新合成
7. **集成 pipeline** — extract_style → generate_content → render

## 文件清单

### 新建
| 文件 | 功能 |
|------|------|
| `services/python/style_extractor.py` | VLM 提取 StyleToken |
| `web/src/styles/StyleContext.tsx` | React Context + StyleToken 类型 |
| `web/src/styles/defaultTokens.ts` | 7 个预设族的默认 token |
| `web/src/components/mg/TextReveal.tsx` | 通用文字揭示（读 token） |
| `web/src/components/mg/CardGroup.tsx` | 通用卡片组（读 token） |
| `web/src/components/mg/GridGroup.tsx` | 通用网格组（读 token） |
| `web/src/components/mg/LogoDisplay.tsx` | 通用 logo（读 token） |
| `web/src/components/layout/DiagonalLayout.tsx` | 斜角布局 |
| `web/src/components/layout/GridLayout.tsx` | 网格布局 |
| `web/src/components/layout/AsymmetricLayout.tsx` | 不对称布局 |
| `web/src/remotion/compositions/StyleDrivenVideo.tsx` | 风格驱动合成 |

### 修改
| 文件 | 改动 |
|------|------|
| `services/python/main.py` | 新增 /extract_style endpoint |
| `web/src/remotion/root.tsx` | 注册 StyleDrivenVideo |
