# TiboWatch

[English](README.md)

轻量转发 [SaveMeTibo 已发布的 RSS 提醒](https://savemetibo.com/feed.xml)，可选翻译成简体中文，再通过 Bark 推送到 iPhone。

**SaveMeTibo 发布 → TiboWatch 可选翻译 → Bark 投递。** 不再二次解读事件。RSS `title` 和 `description` 是可见内容的唯一依据，不附加时间、来源标签、警告、说明或内部 ID。

> v1.1 正在等待评审。已有 v1 安装在升级获批前继续运行；v1.0.0 发布版仍可单独获取。

## 架构与环境

```mermaid
flowchart LR
    A[SaveMeTibo RSS] --> B[GUID 与正文去重]
    B --> C[可选的一次 Codex 翻译]
    C --> D[持久化精确标题与正文]
    D --> E[Bark API]
    E --> F[APNs → iPhone]
```

翻译出现任何错误，立即选择原始英文。没有更大模型回退、翻译重试循环、翻译服务或额外队列；Bark 重试沿用本地待发项保存的可见内容。

需要使用 systemd 的 Linux（例如较新 Debian/Ubuntu）、Python 3.11+，以及常见 sudo/useradd/runuser/install 工具；允许出站 HTTPS 到 SaveMeTibo 和 api.day.app，iPhone 已在 Bark 注册。无入站端口、数据库、Docker、Telegram、X API、浏览器自动化或 Python 第三方依赖。

翻译可选：需有**服务运行用户可访问、已登录的本地 Codex CLI**，并支持下列参数。CLI、登录、模型或额度不可用时直接回退英文。安装器不安装或登录 Codex、不复制凭据、不改变网络或其他服务。

## 新安装

审阅拟安装版本后执行：

```sh
git clone https://github.com/hkwsg/tibowatch.git
cd tibowatch
python3 -m unittest discover -s tests -v
sudo sh deploy/install.sh
sudo python3 /opt/tibo-watch/watcher.py configure-bark
sudo /opt/tibo-watch/activate.sh
```

在自己的可信终端按提示输入 Bark 基础设备地址，不回显，仅接受 HTTPS api.day.app，不能附加标题、正文路径或查询参数。不要将地址写入命令参数、Issue、截图或 Git。

激活发送一条明确的安装测试，健康基线通过后才启用 timer。首次健康 RSS 只建历史基线，不回放、不调用 Codex。已有测试尝试标记时重复激活不自动重发；结果不确定需人工审阅。生产单轮可能另行发送真实待发消息。

## 一次尽力翻译

每条真正新增或内容变化的提醒，最多启动一个子进程，**固定使用 gpt-5.6-luna**。无新提醒的轮询不探测模型、不调用 Codex：

```sh
codex exec --ephemeral --ignore-user-config --ignore-rules \
  --skip-git-repo-check --sandbox read-only --model gpt-5.6-luna \
  -c 'approval_policy="never"' -c features.shell_tool=false \
  -c features.unified_exec=false -c 'web_search="disabled"' \
  -c project_doc_max_bytes=0 --output-schema <临时-schema> \
  --output-last-message <临时输出> -
```

程序使用参数数组，通过 stdin 传入 JSON 数据，不拼接 shell 命令。使用独立临时目录、**8 秒超时**、丢弃 stdout/stderr、不把 Bark key 传给 CLI；严格解析只有 title/body 两个字符串字段的最终 JSON，超时杀死进程组。提示词要求完整翻译、不概括、不遗漏、不解释、不加标签或审查，保留 Codex、Astra、ChatGPT 等名称。结构校验不能证明语义准确性。

调用前先落盘英文回退和尝试标记；若翻译期间进程崩溃，下次发送保存的英文而非重译。成功后原子保存译文。Bark 重试绝不再调用 Codex，即使之后登录或模型恢复。每轮最多处理五条内容选择和五条发送，其余保留在同一个持久队列。

systemd 可加载非敏感 `/etc/tibo-watch/runtime.env`，样例见 [deploy/runtime.env.example](deploy/runtime.env.example)：

- `TIBOWATCH_TRANSLATE=0` 关闭翻译（默认开启）。
- `TIBOWATCH_CODEX_BIN` 指定可访问的已有可执行文件，默认使用 PATH 中的 codex。
- 可选 `CODEX_HOME` 需指向服务用户可用的已有 CLI 登录环境。

其他账号的登录不会自动共享给 `tibo-watch`，且 `ProtectHome=true` 会阻止服务访问 home 目录内的 CLI/登录文件。不要放宽秘密权限、以 root 运行 watcher 或复制其他用户凭据来绕过。没有适当的已有 CLI 环境就使用英文回退。TiboWatch 不读取登录文件，由 CLI 自行处理认证。

参数依据：[OpenAI 非交互文档](https://developers.openai.com/codex/noninteractive/)和[配置参考](https://developers.openai.com/codex/config-reference/)。旧 CLI 不支持参数时同样回退英文。

## 去重与内容规则

- 首次健康 RSS：只建基线，零通知、零翻译。
- 新 GUID 或相同 GUID 的 title/description 变化：生成一条新候选。
- title/description 相同：无论顺序、pubDate、link 如何变化都不重复。
- pubDate 仅用于候选按时间排序；GUID 仅作内部身份。
- 点击目标采用有效 HTTPS RSS link：禁止用户信息和空白（允许合法端口），否则回退 https://savemetibo.com/。程序不会抓取点击目标。
- 保留 XML 实体解码后的文本/CDATA；嵌入 HTML 原样保留，不渲染、不剥离。不概括、审查或静默截断原文。
- 出站 JSON 采用保守的 **3000 UTF-8 字节预算**（含 key 和包装字段）。超限的已选内容原样留在 pending，状态显示 payload_too_large，不缩短、不在选择后换成另一版。
- 网络、XML、冲突重复 GUID、异常空 RSS 等错误保留状态，仅记录本地状态/日志，不额外生成 Bark 源异常或解读通知。没有新发布并不意味着 RSS 陈旧。

## 可靠性与运维

文件锁、原子替换、fsync 和滚动备份保护状态。已观察与已接受分开记录，先持久化再发送。Bark 成功要求 HTTP 200 和整数 JSON code=200。失败按 5/10/20/60 分钟退避，遵守更长 Retry-After，鉴权失败至少退避一天。源获取失败时暂停队列处理直到健康抓取；待发没有六小时过期丢弃机制。

```sh
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py status
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py check-source
sudo -u tibo-watch python3 /opt/tibo-watch/watcher.py dry-run
sudo systemctl start tibo-watch.service
systemctl list-timers tibo-watch.timer
sudo journalctl -u tibo-watch.service -n 20 --no-pager
sudo systemctl disable --now tibo-watch.timer
```

dry-run 不写状态、不翻译、不推送。status 显示抓取年龄、失败原因、待发错误及待发项翻译结果，不输出正文。oneshot 完成后 inactive 正常，核对 Result=success、ExecMainStatus=0 和 timer。已验收安装可通过 `sudo systemctl enable --now tibo-watch.timer` 恢复；暂停 timer 不终止正在运行的任务。

config.example.json 只说明固定默认值，不是运行时配置文件。timer 仍为五分钟，最多 15 秒抖动；HTTP 超时 10 秒、输入上限 2 MiB。

## 从 v1 升级：评审通过后再执行

不要通过安装测试入口迁移。使用已审发布版的升级工具：

```sh
sudo sh deploy/upgrade.sh
```

它仅暂停本任务 timer；若 oneshot 仍活动或有任何未解决 pending 就拒绝继续。安装前保存受限状态快照，再安装代码、执行两次新服务，并在健康 RSS/状态检查通过后恢复 timer。失败时 timer 保持暂停供检查。不要为升级删除 v1 pending，先处理其真实投递结果。

首次健康新运行将 version=1 迁移到 2，另存 v1 备份，保留安装测试标记并建立 RSS 基线，不历史重播。有 v1 pending 则拒绝迁移，Bark 凭据不动。保留旧代码和受限快照供回滚：v1 无法读取 v2 状态；回滚需停本任务并恢复匹配的旧代码/状态，同时核对快照之后已接受的通知。

## 安全与限制

Bark key 是秘密，位于 root-only /etc/tibo-watch/bark.env（0600，目录 0700），由 systemd 管理器读取。日常运行用户为非 root 的 tibo-watch，代码只读，仅本任务状态可写。校验 TLS、禁止 POST 重定向，不记录请求正文或 key。只有安装需要 root。安全问题见 [SECURITY.md](SECURITY.md)。

SaveMeTibo 是第三方，不是 OpenAI 官方 API，不保证 Tibo 所有动态，也不代表个人 Codex 额度生效。五分钟不是端到端 SLA。VPS、Bark 或上游失效不能保证同路径自报；极端超时可能重复，不能保证 exactly-once。翻译可用性与语义准确性均不保证。历史指纹长期保留，需观察状态文件大小。

卸载先暂停 timer，必要时停本服务，只移除其 units/代码并 daemon-reload。默认保留凭据、状态和专用用户，明确需要丢弃时才删除。不删除共享软件、不改网络。

## 开发

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile watcher.py
sh -n deploy/install.sh
sh -n deploy/activate.sh
sh -n deploy/upgrade.sh
git diff --check
```

测试仅用合成 RSS、临时状态和 mock CLI/Bark，CI 检查 Python 3.11/3.14。参见 [CONTRIBUTING.md](CONTRIBUTING.md)、[CHANGELOG.md](CHANGELOG.md)和 [LICENSE](LICENSE)。

本项目与 OpenAI、Tibo、X、Bark、SaveMeTibo 均无隶属关系。
