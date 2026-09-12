# TiboWatch

[English](README.md)

一个轻量的自托管监控器，监测公开的 Codex 重置和额度信号，通过 Bark 向 iPhone 发送重要变化。

TiboWatch 轮询第三方 [SaveMeTibo](https://savemetibo.com/) JSON 数据源，关注 reset、quota、banked reset 和 team hint，复用现有 [Bark](https://github.com/Finb/Bark) 推送服务。它**不会查询个人 Codex 账号**。

## 架构

```mermaid
flowchart LR
    A[Public signal source] --> B[TiboWatch]
    B --> C[Semantic dedupe]
    C --> D[Bark]
    D --> E[iPhone]
```

SaveMeTibo → TiboWatch → Bark API → Apple Push Notification Service（APNs）→ iPhone。

systemd timer 每五分钟启动一次短生命周期 Python 进程，并带少量调度抖动。本地 JSON 状态分别记录已观察事件和已获服务接受的通知，不开放入站端口。

## 功能

- 有证据的重置观察线索，以及 confirmed、landed 状态。
- 对此前已通知事件的明确更正、撤回和观察结束提示。
- 同事件下的 `team_hint` 补充动向，保持主事件状态不变。
- 跨轮询、跨进程重启的语义去重。
- 首次健康运行只建立历史基线，不补发已有事件。
- 持久化待发队列、有限重试和 `Retry-After` 处理。
- 数据源陈旧检测、失效告警和恢复提示。
- 仅 Python 标准库：无数据库、Docker 依赖、Telegram、X API、浏览器自动化或 LLM。

通知使用固定中文标题和说明，配合截断的上游英文摘要。v1 尚未提供英文通知本地化。

## 环境要求

- 使用 systemd 的 Linux，例如较新的 Debian 或 Ubuntu。
- Python **3.11+**，含 `zoneinfo`，以及系统时区数据。
- 安装时可使用 `sudo`，具备常见系统工具 `useradd`、`runuser`、`install`。
- 能通过出站 HTTPS 访问 SaveMeTibo 和 `api.day.app`。
- iPhone 已安装 Bark，在 `api.day.app` 注册并允许通知。

默认安装脚本面向 Linux 系统级安装，不升级操作系统、不安装 Python、不修改网络，也不安装 Bark 服务端。CI 检查 Python 3.11 和 3.14，未穷举所有发行版组合。

## 快速开始

```sh
git clone https://github.com/hkwsg/tibowatch.git
cd tibowatch
python3 -m unittest discover -s tests -v
sudo sh deploy/install.sh
```

安装脚本创建独立的 `tibo-watch` 用户、代码目录和 systemd units。重复安装保留本任务已有状态和凭据；遇到无法确认归属的已有资源时拒绝覆盖。安装不会自动启用 timer。

在**自己的可信终端**配置 Bark：

```sh
sudo python3 /opt/tibo-watch/watcher.py configure-bark
```

按提示粘贴 Bark App 的基础设备推送地址，输入不回显。不要附加标题、正文路径或查询参数。仅接受 `https://api.day.app/` 作为服务来源。不要将地址写入命令行参数、Git、Issue 或截图。

然后激活：

```sh
sudo /opt/tibo-watch/activate.sh
```

激活会发送一条明确标记的安装测试，执行生产单轮检查，并在推送服务接受且健康基线通过后启用 timer。若已有真实待发提醒，该生产检查也可能发送它们；业务提醒与安装测试分别计数。

请检查 iPhone 是否实际收到通知。Bark 服务端接受请求不等于手机收到；CLI 无法观察手机，因此设备实收显示为未确认。

重复激活不会自动重发安装测试。若测试结果不确定，先检查状态，不要删除状态或连续重试来强行触发通知。确需重测时，应由维护者在持有状态锁的情况下审阅测试标记后处理。

## 状态与运维

```sh
# 最近执行、健康源、新鲜度、待重试数量与服务接受记录
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py status

# 检查公开源，不改状态
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py check-source

# 只读模拟，不写生产状态、不推送
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py dry-run

# 立即执行已配置的生产服务
sudo systemctl start tibo-watch.service

# 调度与日志
systemctl list-timers tibo-watch.timer
sudo journalctl -u tibo-watch.service -n 20 --no-pager
```

oneshot 执行完成后显示 `inactive` 属正常现象，应核对 `Result=success`、`ExecMainStatus=0`，以及 timer 是否 enabled/active。无通知也可能只是无新信号；排障时先看源年龄、`health.reason`、`push_status` 和 `pending_count`。

暂停：

```sh
sudo systemctl disable --now tibo-watch.timer
```

暂停 timer 不终止正在执行的单轮任务。需要时单独运行 `sudo systemctl stop tibo-watch.service`。已验收的安装可用 `sudo systemctl enable --now tibo-watch.timer` 恢复。

更换 Bark key 使用同一不回显配置命令，下一次服务运行读取新值。不要通过命令行参数编辑凭据。

## 默认参数与行为

| 参数 | v1 默认值 |
| --- | --- |
| 数据源 | `https://savemetibo.com/status.json` |
| Bark 接口 | `https://api.day.app/push` |
| 轮询 | 五分钟，timer 最多增加 15 秒抖动 |
| HTTP 超时 / 响应上限 | 10 秒 / 2 MiB |
| 陈旧 / 失效阈值 | 30 / 60 分钟；上游明确 outage 也适用 |
| 普通补发窗口 | 六小时 |
| 同状态普通更新冷却 | 30 分钟，保留最新待发版本 |
| 每轮发送上限 | 五条队列通知 |
| 消息时区 | `Asia/Shanghai`，不改变系统时区 |

`config.example.json` 仅记录固定默认值，**不是程序会读取的运行时配置**。修改这些默认值目前需要审阅源码或 unit 文件。

状态推进和明确纠错不受普通更新冷却限制。关联 hint 使用独立补充语义，不能使 confirmed/landed 主事件降级。同轮主事件有可通知更新时优先主事件。相同规范文本、纯时间刷新、概率变化或数组重排不会重复通知。文本比较是确定性规则，不是通用自然语言理解。

状态使用文件锁、原子写入和有效备份。发送失败保留待发，按 5/10/20/60 分钟退避，并遵守更长的 `Retry-After`。鉴权失败至少退避一天。主状态损坏时尝试备份，无法恢复则需要人工处理，不静默当作首次安装。

## 安全模型

Bark 设备 key 是**秘密**，绝不能提交到 Git。它保存在 root-only `/etc/tibo-watch/bark.env`（0600，目录 0700）。systemd 管理器读取 EnvironmentFile 后传给专用 `tibo-watch` 进程。watcher 日常运行不需要 root，专用用户本身不能读取受限配置目录。

代码位于 `/opt/tibo-watch`，服务仅能写入 `/var/lib/tibo-watch`。无需入站监听、反向代理、Telegram 会话或个人账号凭据。请求校验 TLS，Bark 使用 POST JSON、不跟随重定向，通知链接限制域名，日志不输出请求正文或 key。默认普通 `active` 通知，不启用自动复制。

公开消息会经过现有 Bark 服务中转，并非全部基础设施都由自己控制。安全问题处理方式见 [SECURITY.md](SECURITY.md)。

## 更新与卸载

更新前暂停 timer，必要时停止本任务 service，并安全备份旧代码和状态。检查新版本并运行测试，再执行安装脚本。确认状态兼容及源健康后恢复。重复安装保留凭据、状态和 timer 当前启用状态。

卸载时先禁用 timer、停止任务，仅删除 `/etc/systemd/system/` 下本任务两个 unit，执行 `sudo systemctl daemon-reload`，再删除本任务代码目录。默认保留状态、凭据和专用用户供恢复，只有明确需要丢弃时才单独删除。不要移除共享 Python 包或更改网络。

## 已知限制

- SaveMeTibo 是第三方数据源，不是 OpenAI 官方 API，不能保证覆盖 Tibo 在 X 的所有动态。
- 社区重置信号不代表个人 Codex 账号额度必然已重置。
- 五分钟是本机轮询周期，**不是从发帖到手机收到的端到端 SLA**。
- VPS、Bark 或上游故障无法保证通过同一条失效链路自报；没有独立心跳或备用源。
- 极端网络超时可能出现服务端已接受、本地却未知的情况，不能保证严格 exactly-once。
- 上游未来的 schema 或生命周期变化可能需要适配。未知核心结构会进入降级；事件消失本身不视为撤回。
- 去重历史持续保留，长期部署需观察本地状态大小。

## 开发与许可证

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
```

34 项离线测试使用合成数据、临时状态和 mock HTTP，无需真实设备 key。贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本记录见 [CHANGELOG.md](CHANGELOG.md)，使用 [MIT 许可证](LICENSE)。

## 免责声明

本项目不是 OpenAI 或 Tibo 官方项目，与 OpenAI、Tibo、X、Bark、SaveMeTibo 均无隶属关系。

This project is not affiliated with OpenAI, Tibo, X, Bark, or SaveMeTibo.
