# GitHub Unwrapped 架构模式 — VST 可复用清单

> 来源: https://github.com/remotion-dev/github-unwrapped
> 分析日期: 2026-05-28

## 一、核心架构决策

### 1. 数据注入: Zod Schema 作为 Composition 契约

Unwrapped 用 Zod schema 定义 Remotion composition 的所有 props，形成"数据→视频"的强类型契约：

```typescript
// src/config.ts
export const compositionSchema = z.object({
  topLanguages: topLanguagesSchema.or(z.null()),
  login: z.string(),
  planet: PlanetEnum,           // "Ice"|"Silver"|"Gold"|"Leafy"|"Fire"
  contributionData: z.array(z.number()),  // 365+ 条日贡献数据
  graphData: z.array(productivityPerHourSchema),  // 24 元素小时级数据
  // ...
});

// 转换函数: 原始数据 → composition 参数
function computeCompositionParameters(stats: ProfileStats, rocket: Rocket) {
  return {
    planet: computePlanet(stats.totalContributions),  // 阈值映射
    topLanguages: stats.topLanguages.map(parseTopLanguage),
    // ...
  };
}
```

**VST 对齐**: `video_spec_schema.py` 已用 Pydantic，可加 Zod 到 TS 端做前端校验。

### 2. 两条数据注入路径

| 路径 | 用途 | 数据流 |
|------|------|--------|
| 浏览器预览 | Remotion Player | `window.__USER__` → context → `computeCompositionParameters()` → `<Player inputProps={}>` |
| Lambda 渲染 | MP4 导出 | `/api/render` → `getProfileStatsFromCache()` → `computeCompositionParameters()` → `renderMediaOnLambda()` |

**VST 对齐**: 当前只有本地渲染路径。未来可加 Lambda/Cloud Run 批量渲染。

### 3. 场景编排: Series + TransitionSeries

```tsx
// remotion/Main.tsx — 6 个场景用 Series 串联
<Series>
  <Series.Sequence durationInFrames={130} offset={-15}>
    <OpeningScene login={login} rocket={rocket} />
  </Series.Sequence>
  <Series.Sequence durationInFrames={dynamic} offset={-10}>
    <AllPlanets topLanguages={topLanguages} ... />
  </Series.Sequence>
  // ... 共 6 个场景
</Series>

// TransitionSeries 做场景间转场 (slide/fade)
<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={90}>
    <PlanetScaleOut />
  </TransitionSeries.Sequence>
  <TransitionSeries.Transition
    presentation={slide({ direction: 'from-left' })}
    timing={springTiming({ damping: 200, durationInFrames: 15 })}
  />
  <TransitionSeries.Sequence durationInFrames={90}>
    <PlanetScaleSpiral />
  </TransitionSeries.Sequence>
</TransitionSeries>
```

**VST 对齐**: `ScriptDrivenVideo.tsx` 用的是 `<Sequence>` 硬切。可升级到 `<Series>` + `TransitionSeries`。

## 二、动画技术清单

### 1. SVG 路径动画 — 运动轨迹

核心工具函数 (`remotion/move-along-line.ts`):
```typescript
import { getLength, getPointAtLength, getTangentAtLength } from '@remotion/paths';

export function moveAlongLine(path: string, progress: number) {
  const length = getLength(path);
  const point = getPointAtLength(path, progress * length);
  const tangent = getTangentAtLength(path, progress * length);
  return {
    offset: { x: point.x, y: point.y },
    angleInDegrees: Math.atan2(tangent.y, tangent.x) * (180 / Math.PI),
    angleInRadians: Math.atan2(tangent.y, tangent.x),
  };
}
```

用例: 火箭沿弧线飞行、元素沿路径入场、装饰性轨迹动画。

### 2. 速度重映射 — 加速/减速感

```typescript
// remap-speed.tsx — 积分帧映射
export function remapSpeed(frame: number, speedFn: (f: number) => number): number {
  let acc = 0;
  for (let i = 0; i < frame; i++) {
    acc += speedFn(i);
  }
  return acc;
}
// 用法: remapSpeed(f, (i) => interpolate(i, [0, 100], [1, 7])) → 先慢后快
```

### 3. 噪声驱动有机运动

```typescript
import { noise2D } from '@remotion/noise';
// 火箭抖动
const shakeX = noise2D('shake', frame * 0.1, 0) * 5;
const shakeY = noise2D('shake', 0, frame * 0.1) * 3;
// 星星闪烁
const twinkle = interpolate(noise2D('star', frame * 0.05, 0), [-1, 1], [0.3, 1]);
```

### 4. 缩放穿越效果 (Zoom-Through)

```typescript
// Opening 退出: 从正常缩放到"穿越"效果
const distance = interpolate(frame, [exitStart, exitEnd], [1, 0.001], {
  extrapolateRight: 'clamp',
});
const scale = 1 / distance;  // 趋近无穷大
```

### 5. 预渲染素材 + OffthreadVideo

- 火箭喷焰: 预渲染 `.mp4` 视频，用 `<OffthreadVideo>` 播放
- 星球/火箭: 预渲染 PNG，用 `<Img>` 显示
- 好处: 复杂动画离线渲染，运行时零计算

## 三、渲染管线

### Lambda 批量渲染

```typescript
// deploy.ts
const functionInfo = await deployFunction({
  ram: 1200,           // MB
  disk: 10240,         // MB
  timeout: 120,        // seconds
  siteName: 'unwrapped2025',
});

// render.ts
const result = await renderMediaOnLambda({
  functionName: functionInfo.functionName,
  composition: 'Main',
  inputProps: compositionParameters,  // ← 数据在这里注入
  codec: 'h264',
  downloadBehavior: { type: 'delete-after-download' },
});
```

### 渲染池 + 缓存

```typescript
// render-pool.ts — 限制并发 100
const renderPool = new RenderPool({ maxConcurrent: 100 });

// db.ts — MongoDB 缓存
await insertRender(username, { status: 'rendering', progress: 0 });
// 完成后
await updateRenderStatus(username, 'video-available', downloadUrl);
```

## 四、VST 直接可用的积木

| 积木 | Unwrapped 文件 | VST 改造 |
|------|----------------|----------|
| `moveAlongLine()` | `remotion/move-along-line.ts` | 复制到 VST，用于 BeforeAfter/PriceReveal 入场 |
| `remapSpeed()` | `remotion/TopLanguages/remap-speed.tsx` | 复制到 VST，让所有动画有加速感 |
| `TransitionSeries` | `@remotion/transitions` | 升级 ScriptDrivenVideo 的场景切换 |
| `prefetch()` | `@remotion/preload` | 预加载场景图片，避免渲染时加载延迟 |
| Zod schema | `src/config.ts` | 在 TS 端加 Zod 校验 VideoSpec |
| `noise2D` | `@remotion/noise` | 已在 motion.ts 中使用，可扩展 |
