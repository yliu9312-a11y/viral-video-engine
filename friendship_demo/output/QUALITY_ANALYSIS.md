# 视觉质量分析: 渲染问题诊断

> 分析日期: 2026-06-03
> 分析对象: CTR / Standard / Premium 三个 profile 的渲染输出

---

## 问题 1: 同位置重叠 — 文字叠在文字上

**现象**: GlassCard/FeatureGrid(居中) 和 GradientText(居中) 在同一时间段、同一 position 渲染，视觉上互相遮挡。

**根因**: Phase-level orchestrator 为每个 shot 独立生成 start/duration/position，**没有位置冲突检测**。LLM 不知道"center 已经被占了"。

| Profile | 重叠 | 时长 | 位置 |
|---------|------|------|------|
| CTR | GlassCard + GradientText | 2.4s | center+center ❌ |
| Standard | FeatureGrid + GradientText | 2.0s | center+center ❌ |
| Premium | GlassCard + GradientText | 4.0s | center+center ❌ |
| Premium | GlowTrail + ParticleBg | 2.4s | center+center ❌ |

**修复方向**:
- 方案 A: Orchestrator 生成后加 **position 冲突检测** — 同时间段内不允许两个 shot 都是 center
- 方案 B: 同时间段的 shot 自动分配位置 — 第一个 center, 第二个 lower, 第三个 upper
- 方案 C (根本): 用 beat-level orchestrator (`orchestrate_from_beats`)，beat 内组件已预设不同 position

---

## 问题 2: 第一帧后有长黑屏

**现象**: CTR 的 WordReveal(0-2.7s) 结束后，GlowTrail 从 2.7s 才开始，中间有 **1.3s 黑屏**。

**根因**: Phase-level orchestrator 把 beat 0 的两个组件 (WordReveal + GlowTrail) 当成**两个独立 shot**，顺序排列。
- 正确做法 (beat-level): 两个组件 start=0，同时渲染
- 实际做法 (phase-level): shot[0] dur=81f, shot[1] start=81f → 中间有 gap

**同样的问题在 Premium**:
- GlowTrail start=168f, 但 ParticleBg 从 180f 开始 → 12f (0.4s) 微小 gap
- 不如 CTR 严重，但仍然是不必要的硬切

**根因**: Phase-level orchestrator 不知道"这些组件应该同时出现"。它把所有 shot 当成**顺序排列**的独立单元。

**修复方向**: 这正是 beat-level orchestrator 解决的问题。`orchestrate_from_beats()` 让同一 beat 内的组件 start 相同。

---

## 问题 3: 背景空旷 — 只有深蓝黑

**现象**: ParticleBg 的 opacity=0.15-0.3，粒子极淡。大部分时间背景就是纯色 `#050510`。

**根因**:
1. ParticleBg 的 opacity 被 CV 的 text_density 或默认值压低了
2. 原版 Layout.dev 视频有 **BackgroundLayer** (radial gradient + noiseOffset 缓慢移动)，但 ScriptDrivenVideo 没有这个全局背景层
3. 原版有 **GlowTrail 弧线** 作为装饰性视觉引导，但 phase-level 把它当成独立 shot 而非贯穿性装饰

**对比原版 (ProductPromo.tsx)**:
```tsx
// 原版有独立的 BackgroundLayer，始终渲染
<BackgroundLayer frame={frame} />  // radial gradient + noise + ParticleBg

// 然后 beats 在上面叠加
<Sequence from={BEATS[0].start}>
  <HookBeat />  // WordReveal + GlowTrail 同时
</Sequence>
```

**ScriptDrivenVideo.tsx** 没有全局背景层 — 每个 shot 独立渲染，ParticleBg 只是一个普通 shot。

**修复方向**:
- 方案 A: ScriptDrivenVideo 加一个**全局 BackgroundLayer** (radial gradient + 慢漂移)，始终渲染
- 方案 B: ParticleBg 的 opacity 提高到 0.4-0.5
- 方案 C: 加一个不可见的 "background" shot 类型，始终在底层渲染

---

## 问题 4: Shot 顺序不符合 beat 结构

**现象 (CTR)**:
```
[0] WordReveal     0-2.7s   ← hook
[1] GlowTrail      2.7-4.7s  ← 应该和 WordReveal 同时！
[2] ParticleBg     6-12.4s   ← build 背景
[3] FloatingMockup 12.4-17.2s ← build 内容
[4] GlassCard      17.2-22s   ← build 内容
[5] FeatureGrid    22-26.8s   ← build 内容
[6] MarqueeText    26.8-30.4s ← build 底部
[7] GradientText   18-20.4s   ← cta? 但和 build 重叠!
[8] KineticText    20.4-22s   ← cta? 但和 build 重叠!
```

**问题**: CTA 组件 (GradientText, KineticText) 的 start 在 540f/612f，**和 build 组件重叠**。这是因为 `_apply_cv_deterministic` 的 shot_duration_scale 缩放了时长，但没有重新计算 start 位置。

**根因**: `_apply_cv_deterministic` 只改 duration_frames，**没有重排 start**。缩放后 shot 变短了，但下一个 shot 的 start 没变 → 出现 gap 或重叠。

**修复**: `_apply_cv_deterministic` 在缩放时长后，**必须重排所有 shot 的 start**，保证无缝衔接。

---

## 问题 5: 每个组件都是 center — 缺乏视觉层次

**现象**: 18 个组件中大部分 position=center，只有 MarqueeText 用了 lower。

**原版 Layout.dev 的视觉层次**:
```
Beat 0 (hook):  WordReveal(center) + GlowTrail(center, 装饰) → 同时
Beat 2 (build): GlassCards(center, 上半) + MarqueeText(lower, 底部) → 同时
Beat 3 (payoff): GradientText(center, 上半) + Mockup(center, 下半) → 同时
Beat 5 (closing): GradientText(center) + MarqueeText(lower) → 同时
```

**关键**: 原版用的是 **flex 布局** (上下排列)，不是 absolute position。GlassCards 在上半部分，MarqueeText 在底部。这不是 position=center/lower 能表达的。

**ScriptDrivenVideo 的 position 系统太粗糙**:
- center: top=200, bottom=200 (中间大区域)
- upper: top=250, height=40%
- lower: bottom=370, height=40%

两个 center 组件会完全重叠。需要更精细的布局系统。

---

## 修复优先级

| 优先级 | 问题 | 修复方案 | 工作量 |
|--------|------|---------|--------|
| **P0** | 同位置重叠 | position 冲突检测 + 自动分配 | 小 |
| **P0** | start 重排缺失 | `_apply_cv_deterministic` 缩放后重排 start | 小 |
| **P1** | 黑屏 gap | beat-level orchestrator (已有，需切换) | 中 |
| **P1** | 背景空旷 | 加全局 BackgroundLayer | 小 |
| **P2** | 视觉层次粗糙 | 更精细的布局系统 (flex-based) | 大 |
