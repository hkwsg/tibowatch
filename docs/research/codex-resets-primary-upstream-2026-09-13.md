# Codex Resets 作为 TiboWatch 第一上游：调研纪要

- 日期：2026-09-13
- 性质：架构研究纪要，不是实现计划，不自动授权修改生产代码或发布版本。
- 当前 owner 方向：**后续优先将 `codex-resets.com` 作为第一上游；SaveMeTibo 仅在第一上游失效时作为兜底源。**
- 当前运行实现仍以 SaveMeTibo RSS 为准，本文件只记录后续架构方向与调研证据。

## 1. 结论摘要

Codex Resets 适合成为 TiboWatch 的第一上游，原因不是“它有一个概率页面”，而是它已经提供结构化、公开、无需鉴权的 API，并且已有多个社区项目将它作为机器数据源使用。

当前公开 API：

- `GET https://codex-resets.com/api/v1/status`
- `GET https://codex-resets.com/api/v1/resets`
- OpenAPI：`https://codex-resets.com/api/openapi.json`
- 文档：`https://codex-resets.com/api/docs`

公开规范中没有 webhook；主流社区实现也是定时轮询，而不是等待 Codex Resets 主动回调。

后续推荐的数据流方向：

```text
Codex Resets API（第一上游）
        ↓
状态变化检测 / 去重 / 原始快照留档
        ↓
现有一次翻译 + 英文 fallback
        ↓
Bark
        ↓
iPhone

Codex Resets 明确失效
        ↓
SaveMeTibo（兜底上游）
```

注意：**“Codex Resets 失效”的严格定义、主源恢复后的 failback 规则、双源事件映射与去重尚未最终设计。** 后续必须单独设计，不能简单地两个源同时轮询后都推送。

## 2. API 的真实语义：不是一个概率数字，而是状态机

`/api/v1/status` 目前应理解为三个主要业务状态：

```text
active_watch
    ↓
scheduled_reset
    ↓
latest_reset
```

### `active_watch`

代表当前有效的预测/观察信号。主要字段：

- `level`: `elevated` / `strong`
- `reset_chance_percent`: 0–100 或 null
- `forecast_window`: 人类可读时间窗
- `observed_at`: 该 Watch 的观察时间
- `expires_at`: Watch 失效时间
- `text`: 上游公开文本
- `source`: 来源类型、作者、URL

### `scheduled_reset`

代表已经明确宣布、但还没有被确认执行的 reset。主要字段：

- `id`
- `status = scheduled`
- `reset_type = regular | banked`
- `announced_at`
- `scheduled_for`（可为 null）
- `text`
- `source`

公开规范明确：即使 `scheduled_for` 已经过时，也**不能**仅凭时间推断 reset 已完成。

### `latest_reset`

代表最近一次已记录的 reset announcement / observed reset：

- `id`
- `reset_type = regular | banked`
- `announced_at`
- `text`
- `source`

`id` 可能是 X post ID，也可能是 `observed-...`，因此不能假设它永远是纯数字。

## 3. 2026-09-13 当前 API 实测

在 2026-09-13 约 03:26（北京时间）读取：

`https://codex-resets.com/api/v1/status`

HTTP 200，业务状态为：

- `latest_reset.id = 2098685367058612394`
- `latest_reset.reset_type = regular`
- `latest_reset.text = "Reset all propagated. Sweet dreams. https://t.co/VgKVUixoJG"`
- `scheduled_reset = null`
- `active_watch = null`
- `stats.total = 53`
- `stats.avg_interval_days = 6.9`

说明 `active_watch = null` 是健康的空闲状态，不是接口错误。

## 4. 历史状态变化证据

### 证据等级

官方 API 没有发现可按时间回放 `/status` 的公开历史接口。因此历史状态证据分三类：

1. **高价值档案：** 独立项目 `AghDoo/codex-reset-benchmark` 定时读取公开 API，以 append-only NDJSON 保存规范化后的 Watch、采样时间、源更新时间及每次原始响应的 SHA-256。
2. **社区下游 fixture：** 真实下游项目在测试中保存与当时 API 时间线一致的 `/status` shape，可用于补充字段和文本，但不当作逐字 HTTP 抓包。
3. **Telegram / 原帖对照：** 用于核实相同时刻确实存在相应上游信号。

Benchmark 自己明确说明：它保存 as-issued 的规范化结果和 provenance hash，**不保存完整源网页/API 原文副本**。

### 已确认的历史 Watch 演化

| API source_updated_at (UTC) | level | 概率 | forecast_window | expires_at |
| --- | --- | ---: | --- | --- |
| 2026-08-27 06:31:31 | strong | 60% | `by end of thursday` | 2026-08-28 07:00 |
| 2026-08-29 05:38:31 | elevated | 80% | `by end of Saturday` | 2026-08-30 07:00 |
| 2026-08-29 21:23:38 | strong | 75% | `by end of sunday` | 2026-08-31 07:00 |
| 2026-09-06 20:09:56 | elevated | 45% | `within 24h` | 2026-09-07 20:09:56 |
| 2026-09-07 19:24:57 | strong | 85% | `around 6pm today` | 2026-09-08 02:00 |
| 2026-09-11 06:39:40 | elevated | 60% | `by end of this week` | 2026-09-14 07:00 |

关键结论：

- 概率会下降，例如 **80% → 75%**；不能只在概率上升时推送。
- `forecast_window` 会变化；概率和时间窗都属于事件状态。
- Watch 可能持续数小时，并在多次采样中完全相同；不能每次轮询都推送。
- Watch 会被新的 Watch 替代，也会进入 `scheduled_reset`，最后进入 `latest_reset`。

### 8 月 27 日：60% strong Watch

独立 benchmark 记录：

```text
level = strong
probability = 0.60
forecast_window = by end of thursday
observed_at = 2026-08-27T06:31:31Z
expires_at = 2026-08-28T07:00:00Z
raw_sha256 = a94a74d432f868fdf6c6a5c12b1e2e016f175bd2923499b4a3138cfc8cc9b842
```

另一个下游项目 `mathdevie/devie-ai-quota-tracker` 保存的测试样例还包含：

```text
text = Intrigued to see if I can find it tomorrow
source.author = thsottiaux
```

其 `meta.generated_at` 为 `2026-08-27T09:04:36.405Z`。

### 8 月 29–30 日：80% → 75%

第一轮：

```text
80%
elevated
by end of Saturday
observed_at = 2026-08-29T05:38:31Z
expires_at = 2026-08-30T07:00:00Z
```

该状态在独立 benchmark 的多次轮询中持续存在。

随后 API 进入新 Watch：

```text
75%
strong
by end of sunday
observed_at = 2026-08-29T21:23:38Z
expires_at = 2026-08-31T07:00:00Z
```

这证明通知触发条件不能写成“new_probability > old_probability”。

### 9 月 6–7 日：45% → 85%

第一轮：

```text
45%
elevated
within 24h
observed_at = 2026-09-06T20:09:56Z
expires_at = 2026-09-07T20:09:56Z
```

随后进入：

```text
85%
strong
around 6pm today
observed_at = 2026-09-07T19:24:57Z
expires_at = 2026-09-08T02:00:00Z
```

说明 API 会随着证据变化建立新的 Watch，而不是只更新一个固定百分比。

### 9 月 11–12 日：60% Watch → Scheduled Reset → Reset landed

先出现：

```text
60%
elevated
by end of this week
observed_at = 2026-09-11T06:39:40Z
expires_at = 2026-09-14T07:00:00Z
```

随后在 2026-09-12 出现明确 `scheduled_reset`。社区项目 `Javis603/token-monitor` 因此专门提交 `fix(codex): show scheduled resets (#679)`，保存的 API shape 包含：

```text
scheduled_reset.id = 2098612714704891959
scheduled_reset.status = scheduled
scheduled_reset.reset_type = regular
scheduled_reset.announced_at = 2026-09-12T03:20:36Z
scheduled_reset.scheduled_for = 2026-09-12T07:00:00Z
active_watch = null
```

随后当前 API 已进入新的 `latest_reset`，说明主流程应把 Watch、Scheduled 和 Landed/Reset 当成不同的上游事件状态。

## 5. 社区实际接入方式

### Zayrick/codex-worker

项目已实际实现：

```text
Cloudflare Cron（5 分钟）
  → GET codex-resets.com/api/v1/status
  → 解析 active_watch
  → 概率 + 时间组成标题
  → Bark / 钉钉
```

它证明 **Codex Resets → Bark** 已有真实开源实现。

但其旧实现用“`observed_at` 距当前不足 5 分钟才发”的窗口判断。这个做法对 TiboWatch 不应照搬，因为服务短暂中断超过 5 分钟可能漏掉刚发生的 Watch。

参考：
- `https://github.com/Zayrick/codex-worker`
- `worker-rs/src/application/reset_watch.rs`

### Javis603/token-monitor

它读取 `/api/v1/status`：

- 固定 endpoint
- 禁止重定向
- 6 秒请求超时
- 成功默认缓存约 15 分钟
- 错误约 30 秒后重试
- 保留 last-good，但仅在预测仍有效时使用
- Watch 到 `expires_at` 后自动转 inactive
- 2026-09-12 加入 `scheduled_reset` 支持

这套 last-good + expiry-aware cache 逻辑值得参考。

参考：
- `https://github.com/Javis603/token-monitor`

### AghDoo/codex-reset-benchmark

这是本轮最重要的历史证据源之一。

它把多个社区预测源公开采样并追加保存，`codex-resets-com` 使用：

```text
collector_type = status_watch_json
source_url = https://codex-resets.com/api/v1/status
```

保存：

- 采样时间
- source_updated_at
- level
- probability
- forecast_window
- observed_at
- expires_at
- 原始响应 `raw_sha256`

README 明确采用 append-only / as-issued 原则。

参考：
- `https://github.com/AghDoo/codex-reset-benchmark`

## 6. 对 TiboWatch 的后续设计约束

### 6.1 第一上游 / 兜底方向

owner 当前方向：

1. **Codex Resets = 第一上游**。
2. **SaveMeTibo = 第一上游失效后的兜底**。
3. 默认不把两个源当成同级广播源，避免同一件事双推。

但以下定义尚需后续设计：

- 何谓“Codex Resets 失效”：网络错误、超时、429、503、无效 JSON、schema 不兼容、数据长时间不更新分别如何处理？
- 主源短暂异常时是否立即切 SaveMeTibo，还是需要连续失败 / stale threshold？
- 从 SaveMeTibo 兜底恢复到 Codex Resets 时如何 failback？
- failback 时如何避免将同一事件重新推送？
- Codex Resets 自己健康但 `active_watch = null` 时绝不能错误触发兜底；这是正常 idle。

### 6.2 状态指纹，而不是只比较概率

建议未来 fingerprint 至少考虑：

```text
event/state type
level
reset_chance_percent
forecast_window
observed_at
expires_at
scheduled_for
reset_type
source identity / URL
text fingerprint
```

目标行为：

```text
同一状态重复读取 → 静默
状态真正变化 → 产生一个候选通知
80% → 75% → 可视为新 Watch 状态
watch → scheduled → 新状态
scheduled → reset landed → 新状态
```

最终是否对每一种状态变化都发 Bark，需要在实施前明确产品规则；不能仅因为 API 字段变化就默认骚扰用户。

### 6.3 第一轮只建立 baseline

沿用现有 TiboWatch 的好习惯：首次接入 Codex Resets 时只建立当前状态基线，不重放历史消息。

### 6.4 `/resets` 用于历史补漏，但不能替代完整状态历史

`/api/v1/resets` 支持分页和时间范围，可用于恢复部分“已确认 reset”历史。

但当前公开 API 没有发现历史 Watch / historical scheduled list，因此：

- 断线期间出现又消失的短期 Watch 可能无法通过 `/resets` 补回。
- 后续不能宣称 `/resets` 是 Telegram / `/status` 的完整历史消息档案。

### 6.5 TiboWatch 自己保存完整原始 JSON

这是本轮最明确的工程改进建议之一。

独立 benchmark 只保存规范化字段 + hash，导致今天想恢复历史原始正文时仍要 GitHub 考古。

未来 TiboWatch 接入后建议：

```text
每次真正观察到新的上游业务状态
        ↓
先保存完整原始 /status JSON 快照
        ↓
生成结构化 state / fingerprint
        ↓
选择翻译
        ↓
持久化最终 Bark payload
        ↓
发送 / 重试
```

只在业务状态变化时保存快照，不必每 5 分钟保存一份。文件很小，空间成本可忽略。

用途：

- 将来可逐字回答某次 85% Watch 的原始 API 返回。
- 便于诊断 parser/schema 演化。
- 便于处理双源去重与争议。
- 不依赖第三方未来继续保留历史。

### 6.6 API schema 要“已知字段严格 + 允许加字段”

2026-08 的社区下游结构主要只有 `latest_reset + active_watch`；2026-09-12 已出现 `scheduled_reset`。

因此 parser 应：

- 对业务必需字段做类型和范围验证；
- 对未知新增字段容忍；
- 对未知业务状态 fail closed，而不是错误推送；
- API 结构异常时不能把当前状态清空成“没有信号”。

## 7. 稳定性观察

现有历史证据显示：

- Watch 往往持续多个小时。
- 同一 Watch 在多次相隔数小时的采样中仍存在。
- 社区已有项目采用 5 分钟轮询，也有项目采用 10–15 分钟缓存。

因此对 TiboWatch 来说，**5 分钟轮询是合理的起始值**，没有必要秒级抓取。

但这不是上游 SLA：

- 公开 API 没有发现可用率承诺。
- 没有在公开规范中找到明确的固定 rate-limit 数值。
- 需要遵守 `429 Retry-After`。
- API 200 不等于上游 X 采集链一定最新；未来应设计 stale/health 判定。

## 8. Bark 与现有产品体验应保持不变

未来更换第一上游不等于推翻当前通知层。

应继续保留：

- Bark 为手机通知出口。
- 不附自动外跳 URL（按当前补丁方向）。
- 通知留在 Bark 历史。
- 文本如需中文，仍是一条新事件最多一次 Luna 翻译。
- 翻译失败使用英文原文。
- Bark retry 重用已选择的 payload，不重新翻译、不重新取概率。

Codex Resets 的概率和状态是**上游数据**，不交给模型自己推断。

## 9. 尚未解决的问题（下一阶段）

下一轮如果正式设计“Codex Resets 第一上游 + SaveMeTibo 兜底”，优先解决：

1. 主源健康 / stale / failure 的精确定义。
2. fallback 触发和 failback 恢复状态机。
3. Codex Resets 与 SaveMeTibo 的跨源事件 ID / 文本 / 时间映射。
4. 双源去重：兜底期间收到 SaveMeTibo 后，主源恢复时不能再推同一事件。
5. Watch、Scheduled、Reset landed 三类状态分别何时值得打扰用户。
6. `/resets` 在短期断线恢复中的补漏范围。
7. 上游 schema 变更时的 fail-closed 策略。
8. 原始 JSON 快照的保留周期和本地状态结构。
9. 是否保留 SaveMeTibo 当前概率/图片增强，还是 fallback 时只转其 RSS 已发布消息。

在这些问题解决前，不建议直接把两个源简单并联到生产 Bark。

## 10. 本轮决策状态

**已决定：**

- 下一阶段架构方向改为：Codex Resets 第一上游，SaveMeTibo 失效兜底。

**尚未决定：**

- fallback 的精确定义和等待时间。
- 双源去重合同。
- 每种 Codex Resets 状态的具体 Bark 产品文案/推送阈值。
- 是否以及何时开始代码实现。

因此本研究纪要应作为下一阶段设计输入，而不是直接开发指令。
