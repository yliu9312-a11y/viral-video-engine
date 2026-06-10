# Video Recipe: Layout.dev Product Promo (Studio Both Sides)

> 来源: 小红书 @StudioBothSides — Layout.dev 宣传片
> 分析日期: 2026-05-28
> 用途: VST 知识库 pattern 种子 + ProductPromo 合成参考

## 一、Beat Sheet (7 beats, 39s, 1080×640 @30fps)

| # | Beat | 时间 | 帧范围 | 时长 | 核心元素 |
|---|------|------|--------|------|----------|
| 0 | Hook | 0-6s | 0-180 | 6s (180f) | 逐词渐变揭示 "What if one prompt could build your side hustle" |
| 1 | Typewriter | 6-9s | 180-270 | 3s (90f) | 发光弧线 → 圆角搜索栏 → 打字机输入 prompt |
| 2 | Features | 9-22s | 270-660 | 13s (390f) | 玻璃拟态卡片 ×3-4 + 浮动 UI mockup + 底部跑马灯 |
| 3 | Payoff | 22-28s | 660-840 | 6s (180f) | 渐变大字 "From prompt to production" + 3D 透视网站截图 |
| 4 | Feature Grid | 28-32s | 840-960 | 4s (120f) | 大字标签 (Auth/Database/Payments/UI) + 网格布局 |
| 5 | Closing | 32-37s | 960-1110 | 5s (150f) | "Stop prompting, start shipping" 渐变滚动文字 |
| 6 | Logo | 37-39s | 1110-1170 | 2s (60f) | Logo spring 弹入 + 蓝色辉光 backdrop |

**节奏规律**: 快(6s) → 快(3s) → 慢(13s,核心展示) → 中(6s) → 快(4s) → 中(5s) → 快(2s)

## 二、Design Tokens

### 2.1 色彩体系

| Token | 值 | 用途 |
|-------|-----|------|
| `bg.primary` | `#050510` | 近黑背景(带蓝调) |
| `accent.primary` | `#3B82F6` | 电光蓝(主强调) |
| `accent.light` | `#60A5FA` | 浅蓝(次强调) |
| `text.primary` | `#FFFFFF` | 白色文字(100% 不透明) |
| `text.secondary` | `#6B7280` | 灰色文字(40-60% 不透明) |
| `text.gradient` | `linear-gradient(90deg, #9CA3AF, #FFFFFF, #3B82F6)` | 渐变文字(灰→白→蓝) |
| `glow.color` | `rgba(59, 130, 246, 0.4)` | 蓝色辉光 |
| `glow.blur` | `60-80px` | 辉光模糊半径 |

### 2.2 玻璃拟态参数

```css
background: rgba(15, 23, 42, 0.6);           /* 半透明深蓝底 */
border: 1px solid rgba(59, 130, 246, 0.3);    /* 蓝色边框 */
backdrop-filter: blur(20px);                   /* 背景模糊 */
box-shadow: 0 0 30px rgba(59, 130, 246, 0.15); /* 内发光 */
border-radius: 16px;                           /* 圆角 */
```

### 2.3 字体层级

| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| Display | 80-100px | 900 (Black) | Feature 标签 (Auth/Database) |
| Headline | 50-60px | 700-800 | Hook 文案, Payoff 文案 |
| Body | 30-40px | 500-600 | 跑马灯文字, Typewriter 内容 |
| Caption | 16-20px | 400-500 | 卡片内文字, 价格, 标签 |

**对比规则**: 关键词 100% 白色 + 粗体, 其余文字降透明度到 40-60%

### 2.4 间距网格

基于 8px 网格:
- 卡片内边距: 24px
- 卡片间距: 32px
- 文字与卡片间距: 16px
- 安全区: 上 40px, 下 40px, 左 40px, 右 40px (横版)

## 三、Motion Vocabulary (10 种动效原语)

### M1: Word-by-Word Reveal (逐词揭示)
```
动画: opacity 0→1 + translateY(20→0)
时序: 每词间隔 3 帧 (100ms @30fps)
Easing: expo-out bezier (0.16, 1, 0.3, 1)
Spring: { damping: 12, stiffness: 200, mass: 0.8 }
用于: Hook beat, Closing beat
```

### M2: Typewriter + Cursor (打字机 + 光标)
```
动画: 字符逐个出现, 间隔 1 帧 (~33ms)
光标: "|" 字符, opacity 每 15 帧切换 (500ms 闪烁)
容器: 圆角搜索栏, 发光边框
用于: Typewriter beat
```

### M3: Glow Trail on Path (路径发光粒子)
```
动画: 小圆点沿 SVG 弧线移动, 带发光拖尾
粒子: 4-6px 白色圆, box-shadow 发光
拖尾: 3-5 个前序点, 递减 opacity
路径: M 100,320 Q 200,100 540,100 (抛物线弧)
用于: Typewriter beat 入场
```

### M4: Floating Mockup Parallax (浮动视差)
```
动画: translateY 缓慢上升 (-20px/3s) + 轻微 rotateY(2-5deg)
驱动: noiseOffset() 有机微动, amplitude 5px
阴影: 跟随高度, blur 随 translateY 增大
入场: spring({ damping: 15, stiffness: 100 }) scale 0.8→1
用于: Features beat
```

### M5: Glass Card Entrance (玻璃卡片入场)
```
动画: scale 0.8→1 + opacity 0→1
Spring: { damping: 15, stiffness: 100 }
交错: 每卡间隔 6 帧 (STAGGER.card)
用于: Features beat, Feature Grid beat
```

### M6: Horizontal Marquee (水平跑马灯)
```
动画: translateX 线性滚动, 速度 ~100px/s (3.3px/frame)
循环: 文字渲染两次, modulo 实现无缝
边缘: mask-image 渐变遮罩, 两端 fade to transparent
用于: Features beat 底部, Closing beat
```

### M7: Gradient Text Shimmer (渐变文字光泽)
```
动画: background-position 从左到右移动
渐变: linear-gradient(90deg, #9CA3AF, #FFFFFF, #3B82F6)
速度: 2s 完成一次完整扫描
入场: opacity 0→1 + translateY(20→0) spring
用于: Payoff beat, Closing beat
```

### M8: Feature Grid Stagger (功能网格交错)
```
动画: 每个网格单元独立 spring 入场
交错: 6 帧间隔 (STAGGER.card)
布局: 2×2 CSS Grid, 每格含大标签 + 小描述
用于: Feature Grid beat
```

### M9: Logo Spring Bounce (Logo 弹入)
```
动画: scale 0→1
Spring: { damping: 8, stiffness: 150 } (弹跳感)
辉光: box-shadow pulse, blur 60→80→60px, 周期 1s
用于: Logo beat
```

### M10: Perspective Tilt (透视倾斜)
```
CSS: perspective(1000px) rotateY(5deg) on parent
动画: rotateY 从 0→5deg, 缓慢
阴影: 底部蓝色 ambient glow
用于: Payoff beat 网站截图
```

## 四、Component Mapping

| 视频元素 | Remotion 组件 | 复用/新建 |
|----------|---------------|-----------|
| 逐词揭示文字 | `WordReveal` | 新建 |
| 渐变文字 | `GradientText` | 新建 |
| 打字机搜索栏 | `TypewriterPrompt` | 新建 |
| 发光弧线粒子 | `GlowTrail` | 新建 |
| 玻璃拟态卡片 | `GlassCard` | 新建 |
| 浮动 UI 截图 | `FloatingMockup` | 新建 |
| 水平跑马灯 | `MarqueeText` | 新建 |
| 功能网格 | `FeatureGrid` | 新建 |
| Logo 弹入 | `LogoReveal` | 新建 |
| 背景辉光 | `GradientMesh` | 已有 (CinematicEffects) |
| 粒子背景 | `ParticleBg` | 已有 |
| 胶片噪点 | `FilmGrain` | 已有 (CinematicEffects) |

## 五、AI 写作助手题材映射 (WriteFlow)

| 原视频 (Layout.dev) | 新视频 (WriteFlow) |
|---|---|
| sneaker marketplace | AI writing assistant |
| "build your side hustle" | "build your content strategy" |
| "Create a high-end online sneaker marketplace" | "Write a compelling product launch email for..." |
| 产品卡片 (Nike ×3) | 功能卡片 (Email/Blog/Social ×3) |
| 搜索栏 "Search silhouettes..." | 分析面板 "Analyzing content performance..." |
| 用户评论卡 (Leticia Kutch) | 数据统计卡 (10K+ words generated) |
| 支付 UI (Apple Pay/Stripe) | 集成 UI (WordPress/Medium/Ghost) |
| "From prompt to production" | "From idea to published content" |
| 网站截图 (GRAIL) | 编辑器截图 (WriteFlow Editor) |
| Auth/Database/Payments/UI | Templates/SEO/Analytics/Scheduling |
| "Stop prompting, start shipping" | "Stop writing, start publishing" |
| Layout.dev logo | WriteFlow logo |
