# 短视频 Motion Graphics 设计指南

> 本文档整理爆款短视频的视觉设计原理、动效规范和实现指导。
> 目标：让 VST 渲染引擎（Remotion）输出的视频达到专业 MG 水准。

---

## 一、核心设计原则

### 1.1 动画 12 原则（Disney，适用于 MG）

| 原则 | MG 应用 | Remotion 实现 |
|------|---------|---------------|
| **Squash & Stretch** | 文字落地时短暂压缩再弹回 | `spring()` + scale 插值 |
| **Anticipation** | 元素入场前先微缩/微退 | 先 scale(0.95) 再 scale(1) |
| **Staging** | 每帧只有一个焦点，消灭竞争元素 | z-index 层级 + 淡入淡出 |
| **Slow In/Slow Out** | 所有属性变化都用 ease，不用 linear | `interpolate()` + easing |
| **Follow Through** | 主动画停后，次要元素继续微动 | 不同元素不同 delay |
| **Arcs** | 运动轨迹走弧线不走直线 | 贝塞尔曲线路径 |
| **Secondary Action** | 主动画下叠加微动背景/阴影 | 平行动画层 |
| **Timing** | 快=轻盈紧急，慢=庄重重要 | 帧数控制 |
| **Exaggeration** | 关键帧超出实际 10-25% | 放大 scale/位移 |
| **Solid Drawing** | 用阴影/透视创造深度 | box-shadow, transform3d |
| **Appeal** | 圆润、对称的形状更讨喜 | border-radius, 圆角 |

### 1.2 时间规范（30fps）

| 动作类型 | 帧数 | 秒数 | 场景 |
|---------|------|------|------|
| 文字快闪入场 | 4-8 帧 | 0.13-0.27s | 标题弹入 |
| 标题缓动入场 | 12-20 帧 | 0.4-0.67s | 主标题 |
| 转场 | 15-30 帧 | 0.5-1s | shot 之间 |
| 产品展示 | 60-90 帧 | 2-3s | 单个产品 |
| CTA 按钮 | 20-30 帧 | 0.67-1s | 行动号召 |
| 背景微动 | 持续循环 | — | 粒子/渐变 |

### 1.3 缓动曲线（Easing）

```
Sharp emphasis:    80-90% ease-out     → 文字弹入
Smooth entrance:   60-70% ease-out     → 元素滑入
Natural flow:      50% ease-in-out     → 位移
Dramatic reveal:   75% ease-in → 85% ease-out  → 产品登场
Bounce:            overshoot + elastic  → 强调
```

Remotion 实现：
```ts
import { spring, interpolate } from 'remotion';

// Spring bounce
const scale = spring({ frame, fps, config: { damping: 8, stiffness: 200 } });

// Custom easing
const opacity = interpolate(frame, [0, 20], [0, 1], {
  extrapolateRight: 'clamp',
  easing: (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, // easeInOutCubic
});
```

---

## 二、爆款短视频结构模式

### 2.1 Hook（前 3 秒）

**目标：** 0.5 秒内抓住注意力

| Hook 类型 | 视觉手法 | 文字策略 |
|----------|---------|---------|
| 痛点反问 | 黑屏→大字弹出 | "你还在XXX？" (shake 动画) |
| 数字冲击 | 数字滚动+发光 | "99%的人不知道" (NumberRoll) |
| 前后对比 | 分屏滑动 | Before → After (wipe 转场) |
| 悬念留白 | 模糊→清晰 | "结果你绝对想不到..." (typewriter) |
| 利益直接 | 产品+价格标签 | "只要39.9！" (bounce + 发光) |

**设计规范：**
- 文字 ≥ 64px（竖屏 1080×1920）
- 对比色：白字+黑描边 或 黄字+红底
- 动画：bounce 或 shake，不用 fade（太慢）
- 0.3s 内必须出现第一个视觉元素

### 2.2 Build（中间 10-20 秒）

**目标：** 展示产品价值，保持注意力

| 内容类型 | 视觉手法 | 动效 |
|---------|---------|-----|
| 产品展示 | 产品图+渐变背景+价格 | ProductShowcase 组件 |
| 功能演示 | 屏幕录制+标注箭头 | 箭头动画+文字说明 |
| 数据对比 | 柱状图/环形图 | BarChart/DonutChart |
| 使用场景 | B-roll + 文字叠加 | Ken Burns + 卖点卡片 |
| 成分解析 | 放大镜+标注线 | 逐个弹出动画 |

**设计规范：**
- 每 2-3 秒切一个视觉元素（保持节奏）
- 卖点用编号卡片（1. 2. 3.）逐个弹入
- 背景用暗色渐变，前景用亮色文字
- 数据用动画图表（数字从 0 滚到目标值）

### 2.3 Payoff / CTA（最后 3-5 秒）

**目标：** 驱动行动

| CTA 类型 | 视觉手法 | 文字 |
|---------|---------|-----|
| 限时优惠 | 倒计时+红色渐变 | "仅剩最后XX件！" |
| 社会认同 | 数字滚动+头像 | "10万人已购买" |
| 行动号召 | 脉冲按钮+箭头 | "立即抢购→" (shake) |
| 互动引导 | 手指点击动画 | "双击点赞❤️" |

**设计规范：**
- CTA 按钮：圆角 60px，渐变色（红→橙 或 紫→蓝）
- 脉冲动画：scale 1→1.05→1 循环
- 文字用 shake 模式强调
- 倒计时用 CountdownTimer 组件

---

## 三、视觉规范

### 3.1 配色方案

**短视频主色调（按品类）：**

| 品类 | 主色 | 辅色 | 背景 |
|------|------|------|------|
| 好物推荐 | #FF416C (红) | #FFD700 (金) | 渐变暗色 |
| 美妆 | #FF6B9D (粉) | #C084FC (紫) | 柔和渐变 |
| 美食 | #FF8C42 (橙) | #4ECDC4 (青) | 暖色 |
| 数码 | #3B82F6 (蓝) | #10B981 (绿) | 深色 |
| 健身 | #EF4444 (红) | #F59E0B (黄) | 黑色 |
| 知识 | #8B5CF6 (紫) | #06B6D4 (青) | 深蓝 |

**文字配色规则：**
- 主文字：白色 #FFFFFF + 黑色描边 3px
- 强调文字：品类主色 + 发光效果
- 次要文字：rgba(255,255,255,0.7)
- 背景文字：绝对不要用纯黑字，用半透明叠层

### 3.2 字体规范

| 用途 | 字号 | 字重 | 字体 |
|------|------|------|------|
| Hook 标题 | 72-96px | 900 (Black) | PingFang SC / 思源黑体 |
| Build 卖点 | 36-48px | 700 (Bold) | PingFang SC |
| 说明文字 | 28-32px | 400 (Regular) | PingFang SC |
| CTA 按钮 | 40-52px | 800 (ExtraBold) | PingFang SC |
| 数据数字 | 64-96px | 900 (Black) | DIN / Roboto Mono |

### 3.3 描边与阴影

```css
/* 文字描边（必加，保证可读性） */
text-shadow:
  -2px -2px 0 #000,
   2px -2px 0 #000,
  -2px  2px 0 #000,
   2px  2px 0 #000,
   0    4px 20px rgba(0,0,0,0.8);

/* 卡片阴影 */
box-shadow: 0 8px 32px rgba(0,0,0,0.3);

/* 发光效果 */
text-shadow: 0 0 20px rgba(255,65,108,0.8), 0 0 40px rgba(255,65,108,0.4);
```

### 3.4 布局网格（竖屏 1080×1920）

```
┌──────────────┐
│   Safe Zone  │  ← 顶部 120px：系统状态栏
│              │
│    Hook      │  ← 顶部 1/3：标题/Hook
│    Zone      │
│              │
├──────────────┤
│              │
│   Content    │  ← 中间 1/3：产品/内容
│    Zone      │
│              │
├──────────────┤
│              │
│    CTA       │  ← 底部 1/3：CTA/价格
│    Zone      │
│              │
│   Safe Zone  │  ← 底部 120px：系统手势区
└──────────────┘
```

---

## 四、转场设计

### 4.1 转场类型

| 转场 | 适用场景 | 实现 |
|------|---------|------|
| **Cut** | 快节奏切换 | 直接切，0 帧 |
| **Fade** | 场景过渡 | opacity 0→1 |
| **Wipe** | 前后对比 | clip-path 滑动 |
| **Zoom** | 产品放大 | scale 1→2 |
| **Glitch** | 科技/数码 | 随机位移+色差 |
| **Slide** | 内容列表 | translateX |
| **Blur** | 梦幻/回忆 | filter: blur |

### 4.2 转场节奏

- **快切**（0 帧）：每 1-2 秒切一次，适合 hook
- **缓动**（15-30 帧）：每 3-5 秒转场，适合 build
- **慢推**（30-60 帧）：产品展示，配合缩放

### 4.3 Glitch 转场实现

```tsx
// Remotion glitch effect
const glitch = (frame: number) => {
  const intensity = Math.sin(frame * 0.5) * 5;
  return {
    transform: `translate(${intensity}px, ${-intensity}px)`,
    filter: `hue-rotate(${frame * 10}deg)`,
    clipPath: `inset(${Math.random() * 10}% 0)`,
  };
};
```

---

## 五、文字动画模式

### 5.1 四种基础模式

| 模式 | 效果 | 适用 |
|------|------|------|
| **Bounce** | 从上落入，弹跳 2-3 次 | 标题入场 |
| **Slide** | 从左滑入，减速停止 | 副标题/说明 |
| **Typewriter** | 逐字出现 | CTA/长句 |
| **Shake** | 快速抖动 | 强调/促销 |

### 5.2 文字层级动画

```
标题 (72px, bounce, delay=0)
  └─ 副标题 (36px, slide, delay=15帧)
      └─ 说明 (28px, fade, delay=30帧)
          └─ CTA (40px, shake, delay=45帧)
```

### 5.3 数字滚动

```tsx
// 从 0 滚到 10000，2 秒
<NumberRoll value={10000} suffix="+" color="#FFD700" fontSize={80} />

// 价格显示
<NumberRoll value={39.9} prefix="¥" color="#FF416C" fontSize={64} />
```

---

## 六、背景与氛围

### 6.1 背景类型

| 类型 | 效果 | 适用 |
|------|------|------|
| **渐变** | 线性/径向渐变 | 万能 |
| **粒子** | 浮动光点/星星 | 科技/梦幻 |
| **万花筒** | 旋转几何图案 | 潮流/年轻 |
| **动态模糊** | 高斯模糊+移动 | 产品突出 |
| **噪点** | 静态噪点叠加 | 复古/质感 |

### 6.2 渐变配色

```css
/* 好物推荐 */
background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);

/* 美妆 */
background: linear-gradient(135deg, #2d1b69 0%, #11001c 50%, #1a0a2e 100%);

/* 数码 */
background: linear-gradient(135deg, #0c1445 0%, #0a1628 50%, #060d1f 100%);
```

### 6.3 叠层效果

```tsx
// 暗角效果
<AbsoluteFill style={{
  background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.7) 100%)',
}} />

// 噪点纹理
<AbsoluteFill style={{
  backgroundImage: 'url("data:image/svg+xml,...")', // SVG noise
  opacity: 0.05,
  mixBlendMode: 'overlay',
}} />
```

---

## 七、音乐与节奏同步

### 7.1 BPM 匹配

- 常见短视频 BGM：120-140 BPM
- 每拍 = 30fps / (BPM/60) = 12.86 帧
- 关键动画节拍对齐：文字弹入在拍点上

### 7.2 能量曲线

```
高 ┤   ████                    ████
   │  ██████                  ██████
中 ┤ ████████    ████████    ████████
   │██████████  ██████████  ██████████
低 ┤████████████████████████████████████
   └──hook──────build──────payoff──→
```

- Hook：高能量开头
- Build：中等能量，有起伏
- Payoff：能量回升，高潮结尾

---

## 八、从爆款视频中提取模式

### 8.1 提取维度

每个爆款视频应该提取以下结构化信息：

```json
{
  "template_id": "tpl_xxx",
  "category": "好物推荐",
  "engagement_score": 8.5,
  "structure": {
    "hook": {
      "duration_s": 3,
      "type": "痛点反问",
      "text_animation": "bounce",
      "bg_type": "渐变暗色",
      "energy": "high"
    },
    "build": {
      "duration_s": 15,
      "segments": [
        {"type": "产品展示", "component": "ProductShowcase", "duration_s": 5},
        {"type": "数据对比", "component": "BarChart", "duration_s": 5},
        {"type": "使用演示", "component": "KenBurns", "duration_s": 5}
      ],
      "transitions": ["wipe", "zoom"],
      "text_cards": 3
    },
    "payoff": {
      "duration_s": 5,
      "type": "限时优惠",
      "cta_component": "CountdownTimer",
      "text_animation": "shake"
    }
  },
  "visual_style": {
    "primary_color": "#FF416C",
    "bg_style": "渐变暗色",
    "font_weight": "Black",
    "stroke": true
  },
  "motion_patterns": [
    "bounce_in",
    "slide_up_cards",
    "number_roll",
    "pulse_button"
  ]
}
```

### 8.2 入图 Agent 扩展

入图 agent 应该从视频中提取的额外信息：
- `motion_patterns[]`：使用的动效模式
- `visual_style{}`：配色/字体/背景风格
- `engagement_score`：互动数据（如果有的话）
- `transition_types[]`：转场类型
- `text_animation_modes[]`：文字动画模式

### 8.3 推荐引擎增强

策略 C/D 推荐 atom 时，应该考虑：
- 动效匹配：同类视频常用哪些动效
- 视觉风格匹配：配色/背景是否一致
- 节奏匹配：快切 vs 慢推

---

## 九、Remotion 组件规范

### 9.1 组件 Props 标准

所有 MG 组件应支持：

```ts
interface MGComponentProps {
  // 内容
  text?: string;
  // 样式
  color?: string;
  bgColor?: string;
  fontSize?: number;
  fontFamily?: string;
  // 动画
  delay?: number;      // 帧数
  duration?: number;   // 帧数
  mode?: string;       // 动画模式
  // 通用
  style?: React.CSSProperties;
}
```

### 9.2 现有组件清单

| 组件 | 文件 | 动画模式 | 状态 |
|------|------|---------|------|
| KineticText | mg/KineticText.tsx | bounce/slide/typewriter/shake | ✅ |
| ProductShowcase | mg/ProductShowcase.tsx | 渐变背景+产品+价格 | ✅ |
| CountdownTimer | mg/CountdownTimer.tsx | 3-2-1-GO 倒计时 | ✅ |
| BarChart | mg/DataChart.tsx | 柱状图动画 | ✅ |
| DonutChart | mg/DataChart.tsx | 环形图动画 | ✅ |
| NumberRoll | mg/DataChart.tsx | 数字滚动 | ✅ |
| Transition | mg/CountdownTimer.tsx | fade/wipe/zoom/glitch | ✅ |

### 9.3 缺失组件（待开发）

| 组件 | 功能 | 优先级 |
|------|------|--------|
| **PriceReveal** | 原价划掉→现价弹出 | P0 |
| **BeforeAfter** | 分屏滑动对比 | P0 |
| **ParticleBg** | 浮动粒子背景 | P1 |
| **EmojiReaction** | emoji 弹出动画 | P1 |
| **ProgressBar** | 进度条+百分比 | P2 |
| **Testimonial** | 用户评价卡片 | P2 |
| **Badge** | 标签/徽章动画 | P2 |

---

## 十、渲染质量检查清单

渲染前检查：

- [ ] 文字都有描边（黑/白，3px）
- [ ] 文字 ≥ 36px（竖屏）
- [ ] 每 2-3 秒有视觉变化
- [ ] Hook 前 0.5 秒有元素出现
- [ ] CTA 有脉冲/shake 动画
- [ ] 背景不是纯黑/纯白
- [ ] 转场不是全部 cut
- [ ] 数字用 NumberRoll 动画
- [ ] 配色符合品类调性
- [ ] 音乐节奏与动画同步

---

## 参考资源

- Disney 12 Principles of Animation (1981)
- School of Motion - Motion Design Principles
- After Effects Motion Graphics Best Practices
- TikTok/Reels 爆款视频分析
- 抖音电商短视频制作规范
