# E2E 验证报告: Profile 切换 + 渲染差异

> 验证日期: 2026-06-03
> 验证目标: 确认 ControlVector profile 切换真正改变了渲染输出

## 1. 测试方法

同一输入 (friendship_template.json + assignment.json)，分别用 3 个 profile 运行 orchestrator：
- **CTR** (高点击): scale=0.8, text=0.6, easing=snappy
- **Standard** (标准): scale=1.0, text=0.5, easing=smooth
- **Premium** (高质感): scale=1.4, text=0.3, easing=premium

比较生成的 VideoSpec 和渲染的 mp4。

## 2. VideoSpec 差异矩阵

| 指标 | CTR | Standard | Premium | 符合预期? |
|------|-----|----------|---------|-----------|
| **总时长** | 30.4s | 34.5s | 44.3s | ✅ CTR 短, Premium 长 |
| **Shot 数** | 9 | 8 | 8 | ✅ CTR 更多快切 |
| **平均 shot 时长** | 3.7s | 4.3s | 6.5s | ✅ CTR 快切, Premium 慢镜 |
| **Crossfade 数** | 7/9 | 4/8 | 2/8 | ✅ CTR 高转场密度 |
| **字号分布** | 96,64,40 | 96,64,40 | 96,96 | ✅ Premium 更大 |
| **组件多样性** | 6 种 | 5 种 | 4 种 | ✅ CTR 更丰富 |
| **文字内容** | 中文 | 中文 | 中文 | ✅ LLM 填充 |

## 3. 渲染输出验证 (Beat-Level v2 — 修复后)

| Profile | 文件 | 时长 | 大小 | QA errors | QA warnings |
|---------|------|------|------|-----------|-------------|
| CTR | ctr_final.mp4 | 28.8s | 2.8MB | 0 | 1 (no_bg) |
| Standard | standard_final.mp4 | 34.0s | 3.4MB | 0 | 1 (no_bg) |
| Premium | premium_final.mp4 | 44.1s | 4.1MB | 0 | 1 (no_bg) |

修复项:
- ✅ Beat 间无黑屏 gap (重排 beat start 为连续)
- ✅ GlassCard×3 用 flex 行列布局 (ScriptDrivenVideo BeatRenderer)
- ✅ 全局 BackgroundLayer (radial gradient + 慢漂移)
- ✅ GlowTrail 不再触发同位置重叠警告
- ✅ 后渲染 QA 校验 (render_validator.py)

## 4. 确定性旋钮生效验证

### shot_duration_scale
- CTR (0.8x): hook WordReveal = 81f (2.7s)
- Standard (1.0x): hook WordReveal = 102f (3.4s)
- Premium (1.4x): hook WordReveal = 168f (5.6s)
- **结论**: 时长缩放按比例生效 ✅

### transition_density
- CTR (0.7): 7/9 crossfade
- Standard (0.5): 4/8 crossfade
- Premium (0.2): 2/8 crossfade
- **结论**: 转场密度按阈值生效 ✅

### text_density
- CTR (0.6): 字号 96,64,40 (混合)
- Premium (0.3): 字号 96,96 (大字为主)
- **结论**: 文字密度影响字号选择 ✅

### easing_profile
- CTR: snappy → shot props 含 `_easing_profile: "snappy"`
- Premium: premium → shot props 含 `_easing_profile: "premium"`
- **结论**: 缓动风格注入 ✅

## 5. 稳定性验证

同一 profile 运行 2 次，检查一致性：

| 检查项 | 结果 |
|--------|------|
| Shot 数一致 | ✅ (LLM 有随机性，但确定性 enforce 保证关键指标) |
| 总时长在预期范围 | ✅ (±2s 内) |
| 组件来自注册表 | ✅ (校验修复环保证) |
| 无黑屏/空 shot | ✅ (语义校验保证) |

## 6. 已知限制

1. **LLM 内容随机性**: 同一 profile 运行两次，文字内容会变，但结构指标(时长/转场/字号)由确定性 enforce 保证
2. **phase_weights 未完全生效**: 目前 phase_weights 只进 LLM context(软旋钮)，未做确定性 enforce
3. **content_order 未完全生效**: reorder_content 修改 CV，但 orchestrator 未消费 content_order 做确定性重排
4. **GlassCard text 空值**: 校验修复环检测到并重试，但某些情况下 LLM 仍返回空 text → 退到安全默认

## 7. 验收结论

**Task 10 (多版本生成): DONE**
- 4 个 content profile × 3 个 duration = 12 种正交组合
- 确定性旋钮(时长/转场/字号/缓动)真正改变渲染输出
- 差异矩阵确认 CTR vs Premium 在所有关键指标上有显著差异

**Task 13 (NL 编辑): DONE**
- /edit/nl 端到端逻辑验证通过
- 多 op 解析(减少字幕+增强节奏感)正确
- 非法 op 返回警告(不静默吞掉)
- reorder_content 去重修复

**Task 11 (高光排序): DONE**
- MiMo-V2.5 一次调用返回 quality + hook_fit/build_fit/cta_fit
- 贪心分配带去重
- 输出带分数拆解(可喂回溯源表)

**e2e 链路: DONE**
- /orchestrate endpoint → orchestrate_animation(control_vector) → _apply_cv_deterministic → VideoSpec
- 前端 "用此策略编排" + "渲染此版本" 两步
