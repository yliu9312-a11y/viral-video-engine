# ProductPromo 组件体系修订方案

## 原始批评分析

### 一、确实缺的组件

| 缺失组件 | 是否必须有 | 理由 |
|----------|-----------|------|
| Background/AmbientLayer | ✅ 必须 | 9 个原子组件没有一个管背景层。原视频有微光粒子/渐变氛围，不是纯黑 |
| ParticleField | ✅ 必须 | Beat 0 发光弧线、Beat 6 蓝色辉光需要粒子系统。GlowTrail 是 SVG 路径粒子，背景光点是另一回事 |
| TransitionManager | ✅ 必须 | 7 个 beat 之间的过渡（fade/cut/wipe）需要统一管理，Sequence 只管时间不管视觉过渡 |
| 3DMockup/PerspectiveFrame | ⚠️ 部分需要 | FloatingMockup 用 CSS perspective 可以做 3D 透视，不需要 Three.js。但需要明确参数 |
| HeroTitle | ❌ 不需要 | GradientText + WordReveal 的组合可以覆盖，不需要独立组件 |
| Typography 组件 | ❌ 不需要 | 所谓"标题排版"就是 GradientText 的不同 props（fontSize/fontWeight），不需要新组件 |

### 二、组件定义模糊点

**GradientText.tsx** — 需要明确：
- shimmer = 横向扫光（background-position 动画，从左到右循环）
- 支持多色渐变（通过 `colors: string[]` props）
- 通过 `variant: "hero" | "body"` 控制字号

**GlowTrail.tsx** — 需要明确：
- 路径通过 `pathData: string` props 传入（SVG path d 属性）
- 与 Background 光点的区别：GlowTrail 是路径上的运动粒子，Background 是随机漂浮的静态光点

**GlassCard.tsx** — 关键问题：
- `backdrop-filter: blur()` 在 headless Chrome 渲染有边缘差异（Remotion #5126 已确认）
- **解决方案**：用 `filter: blur()` + 克隆元素替代，或用半透明背景 + 边框发光模拟玻璃效果
- 内容通过 `children` 传入（灵活），同时提供 `title`/`description`/`icon` 便捷 props

**FloatingMockup.tsx** — 澄清：
- 是平面浮动 + CSS perspective tilt（不是 Three.js 3D）
- 与"3DMockup"是同一个东西，名字统一为 FloatingMockup

### 三、架构层问题

**组件层级**（修订后）：

```
├── atoms/          ← 原子组件（单一职责）
│   ├── GradientText      — 渐变文字 + shimmer
│   ├── WordReveal        — 逐词动画
│   ├── TypewriterPrompt  — 搜索栏打字机
│   ├── MarqueeText       — 水平滚动文字
│   ├── GlowTrail         — SVG 路径粒子
│   ├── ParticleField     — [新增] 背景漂浮光点
│   └── IconButton        — [新增] 带辉光的图标
│
├── molecules/      ← 分子组件（原子组合）
│   ├── GlassCard         — 玻璃卡片（半透明 + 边框发光）
│   ├── FeatureGrid       — 功能标签网格（内含 GlassCard×N）
│   ├── FloatingMockup    — 浮动 UI 截图 + perspective tilt
│   ├── LogoReveal        — Logo spring 弹入 + 辉光
│   ├── HeroTitle         — [新增] 大字标题（GradientText + 居中布局 + z-index）
│   └── TransitionFX      — [新增] beat 间过渡效果（fade/wipe/cut）
│
├── organisms/      ← 有机体（一个 beat 的完整布局）
│   ├── HookBeat          — [新增] Beat 0 完整布局
│   ├── TypewriterBeat    — [新增] Beat 1 完整布局
│   ├── FeaturesBeat      — [新增] Beat 2 完整布局
│   ├── PayoffBeat        — [新增] Beat 3 完整布局
│   ├── GridBeat          — [新增] Beat 4 完整布局
│   ├── ClosingBeat       — [新增] Beat 5 完整布局
│   └── LogoBeat          — [新增] Beat 6 完整布局
│
├── layout/         ← 布局层
│   ├── Background        — [新增] 背景层（渐变 + 粒子）
│   ├── Section           — [新增] beat 容器（管理入场/出场/z-index）
│   └── Stage             — [新增] 全局舞台（背景层 + 内容层 + 前景层）
│
└── compositions/
    └── ProductPromo.tsx  — 最终合成（用 Stage + Section 串联 7 个 beat）
```

## 修订后的实现方案

### Phase 1: 设计系统补全

#### 1.1 配色系统 (`design-tokens/index.ts`)

```typescript
export const PALETTE_PROMO = {
  bg: '#050510',           // 深黑底
  bgGradient: 'radial-gradient(ellipse at 50% 50%, #0a0a2e 0%, #050510 70%)',
  text: '#FFFFFF',          // 主文字
  textMuted: '#8888AA',     // 次要文字
  accent: '#3B82F6',        // 蓝色强调
  accentGlow: 'rgba(59, 130, 246, 0.4)',
  glass: 'rgba(255,255,255,0.05)',  // 玻璃背景
  glassBorder: 'rgba(255,255,255,0.1)',
  gradient: ['#3B82F6', '#8B5CF6', '#EC4899'], // 渐变色组
};
```

#### 1.2 字体层级

```typescript
export const TYPOGRAPHY_PROMO = {
  hero: { fontSize: 72, fontWeight: 800, letterSpacing: -2, lineHeight: 1.1 },
  h1: { fontSize: 48, fontWeight: 700, letterSpacing: -1, lineHeight: 1.2 },
  h2: { fontSize: 32, fontWeight: 600, letterSpacing: 0, lineHeight: 1.3 },
  body: { fontSize: 18, fontWeight: 400, letterSpacing: 0.5, lineHeight: 1.6 },
  caption: { fontSize: 14, fontWeight: 400, letterSpacing: 1, lineHeight: 1.4 },
  label: { fontSize: 12, fontWeight: 600, letterSpacing: 2, lineHeight: 1.0 },
};
```

#### 1.3 间距系统

```typescript
export const SPACING_PROMO = {
  section: { padding: '60px 80px' },
  card: { padding: 24, gap: 16, borderRadius: 16 },
  grid: { columns: 4, gap: 20 },
  beatMargin: 0, // beat 之间无间距，靠过渡衔接
};
```

### Phase 2: 新增原子组件

#### 2.1 ParticleField.tsx — 背景漂浮光点

```typescript
interface ParticleFieldProps {
  count?: number;           // 光点数量，默认 30
  color?: string;           // 光点颜色，默认 accent
  speed?: number;           // 漂浮速度，默认 0.5
  sizeRange?: [number, number]; // 大小范围，默认 [2, 6]
  opacity?: number;         // 透明度，默认 0.3
}
```

实现：多个绝对定位的圆形 div，用 CSS animation 做随机漂浮运动。每个粒子的起始位置、大小、动画延迟随机生成（用 index 做 seed，保证帧一致性）。

#### 2.2 IconButton.tsx — 带辉光的图标

```typescript
interface IconButtonProps {
  icon: string;           // emoji 或 SVG 路径
  label?: string;
  glowColor?: string;
  size?: number;
}
```

### Phase 3: 新增分子组件

#### 3.1 HeroTitle.tsx — 大字标题

```typescript
interface HeroTitleProps {
  text: string;
  variant?: 'hero' | 'h1' | 'h2';
  gradient?: boolean;
  align?: 'left' | 'center' | 'right';
  enterDelay?: number;    // 入场延迟（帧数）
}
```

内部用 GradientText 渲染，管理居中布局和 z-index。

#### 3.2 TransitionFX.tsx — Beat 间过渡

```typescript
interface TransitionFXProps {
  type: 'fade' | 'wipe' | 'cut' | 'zoom';
  duration?: number;      // 过渡帧数，默认 15 (0.5s @30fps)
  direction?: 'left' | 'right' | 'up' | 'down';
}
```

实现：用 Remotion 的 `interpolate` + `useCurrentFrame` 控制 clip-path / opacity / transform。

### Phase 4: 新增布局组件

#### 4.1 Background.tsx — 背景层

```typescript
interface BackgroundProps {
  variant?: 'gradient' | 'particles' | 'both';
  gradient?: string;
  particleProps?: ParticleFieldProps;
  children?: React.ReactNode; // 叠加在背景上的内容
}
```

实现：
- 渐变层：radial-gradient 背景
- 粒子层：ParticleField 组件
- 两层用 `position: absolute` + `z-index` 叠加

#### 4.2 Section.tsx — Beat 容器

```typescript
interface SectionProps {
  enter?: 'fadeIn' | 'slideUp' | 'scaleIn' | 'none';
  exit?: 'fadeOut' | 'slideDown' | 'scaleOut' | 'none';
  enterDuration?: number;   // 入场帧数
  exitDuration?: number;    // 出场帧数
  zIndex?: number;
  children: React.ReactNode;
}
```

实现：用 `useCurrentFrame` + `useVideoConfig` 计算当前 beat 内的相对帧号，驱动入场/出场动画。

#### 4.3 Stage.tsx — 全局舞台

```typescript
interface StageProps {
  background: React.ReactNode;   // Background 组件
  children: React.ReactNode;     // Section×7
  foreground?: React.ReactNode;  // 可选前景层（logo 水印等）
}
```

### Phase 5: Beat 有机体

每个 Beat 有机体封装一个 beat 的完整布局和动画逻辑：

```typescript
// 示例：HookBeat.tsx
interface HookBeatProps {
  text: string;
  enterFrame: number;  // 在全局时间线中的起始帧
  exitFrame: number;   // 在全局时间线中的结束帧
}

function HookBeat({ text, enterFrame, exitFrame }: HookBeatProps) {
  return (
    <Section enter="fadeIn" exit="fadeOut">
      <HeroTitle text={text} variant="hero" gradient enterDelay={enterFrame} />
      <GlowTrail pathData="M0,300 Q200,100 400,300" />
    </Section>
  );
}
```

### Phase 6: GlassCard 背景模糊方案

基于 Remotion #5126 的研究，`backdrop-filter: blur()` 在 headless Chrome 有边缘差异。

**推荐方案：半透明背景 + 边框发光（不依赖 backdrop-filter）**

```css
.glass-card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow:
    0 0 20px rgba(59, 130, 246, 0.15),   /* 外发光 */
    inset 0 0 20px rgba(255, 255, 255, 0.02); /* 内发光 */
  border-radius: 16px;
}
```

**备选方案（如需真实模糊）：** 用 `filter: blur()` + 克隆元素
```typescript
// 在 GlassCard 内部
<div style={{ filter: 'blur(20px)', position: 'absolute', inset: -20 }}>
  {/* 克隆背景内容 */}
</div>
<div style={{ position: 'relative', zIndex: 1 }}>
  {/* 实际卡片内容 */}
</div>
```

### Phase 7: 合成重构

ProductPromo.tsx 用新的布局组件重构：

```tsx
export function ProductPromo() {
  return (
    <Stage
      background={<Background variant="both" gradient={PALETTE_PROMO.bgGradient} />}
    >
      <Sequence from={0} durationInFrames={180}>
        <HookBeat text="What if one prompt could build your side hustle" ... />
      </Sequence>
      <Sequence from={180} durationInFrames={90}>
        <TypewriterBeat prompt="Create a high-end online sneaker marketplace" ... />
      </Sequence>
      {/* ... 5 more beats */}
    </Stage>
  );
}
```

## 修订后的文件清单

### 新增（12 文件）
| 文件 | 类型 | 功能 |
|------|------|------|
| `components/mg/ParticleField.tsx` | atom | 背景漂浮光点 |
| `components/mg/IconButton.tsx` | atom | 带辉光的图标 |
| `components/mg/HeroTitle.tsx` | molecule | 大字标题（GradientText + 布局） |
| `components/mg/TransitionFX.tsx` | molecule | Beat 间过渡效果 |
| `components/mg/Background.tsx` | layout | 背景层（渐变 + 粒子） |
| `components/mg/Section.tsx` | layout | Beat 容器（入场/出场管理） |
| `components/mg/Stage.tsx` | layout | 全局舞台（三层叠加） |
| `components/mg/HookBeat.tsx` | organism | Beat 0 完整布局 |
| `components/mg/TypewriterBeat.tsx` | organism | Beat 1 完整布局 |
| `components/mg/FeaturesBeat.tsx` | organism | Beat 2 完整布局 |
| `components/mg/PayoffBeat.tsx` | organism | Beat 3 完整布局 |
| `components/mg/GridBeat.tsx` | organism | Beat 4 完整布局 |

### 修改（4 文件）
| 文件 | 改动 |
|------|------|
| `design-tokens/index.ts` | 新增 PALETTE_PROMO、TYPOGRAPHY_PROMO、SPACING_PROMO |
| `components/mg/GlassCard.tsx` | 移除 backdrop-filter，改用半透明 + 边框发光 |
| `components/mg/index.ts` | 新增 12 个导出 |
| `remotion/compositions/ProductPromo.tsx` | 用 Stage + Section + Beat 有机体重构 |

## 优先级

| 优先级 | 内容 | 工作量 |
|--------|------|--------|
| P0 | 设计系统（配色/字体/间距） | 小 |
| P0 | Background + ParticleField | 中 |
| P0 | GlassCard 修复（去掉 backdrop-filter） | 小 |
| P1 | Section + Stage 布局层 | 中 |
| P1 | HeroTitle + TransitionFX | 中 |
| P1 | 7 个 Beat 有机体 | 大 |
| P2 | IconButton | 小 |
| P2 | 合成重构 | 中 |

---

## 实施状态 (2026-06-05)

| Phase | 内容 | 状态 | 说明 |
|-------|------|------|------|
| 1.1 | TYPOGRAPHY_PROMO + SPACING_PROMO | ✅ 完成 | design-tokens/index.ts |
| 1.2 | GlassCard 去掉 backdrop-filter | ✅ 完成 | 改用 rgba 半透明 + box-shadow 外发光 |
| 2.1 | ParticleField | ⏭️ 跳过 | ParticleBg 已存在，功能完全匹配 |
| 2.2 | IconButton | ✅ 完成 | 新建 IconButton.tsx |
| 3.1 | HeroTitle | ✅ 完成 | 新建 HeroTitle.tsx（GradientText wrapper） |
| 3.2 | TransitionFX | ✅ 完成 | 新建 TransitionFX.tsx（fade/wipe/cut/zoom） |
| 4.1 | Background | ✅ 完成 | 新建 Background.tsx（渐变 + ParticleBg） |
| 4.2 | Section | ✅ 完成 | 新建 Section.tsx（入场/出场动画管理） |
| 4.3 | Stage | ✅ 完成 | 新建 Stage.tsx（三层叠加） |
| 5 | 7 个 Beat 有机体 | ✅ 完成 | HookBeat/TypewriterBeat/FeaturesBeat/PayoffBeat/GridBeat/ClosingBeat/LogoBeat |
| 6 | 合成重构 | ✅ 完成 | ProductPromo.tsx 用 Stage + Background 重构 |

**新建文件**: 11 个 (IconButton, HeroTitle, TransitionFX, Background, Section, Stage, HookBeat, TypewriterBeat, FeaturesBeat, PayoffBeat, GridBeat, ClosingBeat, LogoBeat)
**修改文件**: 4 个 (design-tokens, GlassCard, index.ts, ProductPromo.tsx)
**验证**: `npx tsc --noEmit` 通过（0 错误，16 个预存 unused variable 警告）
