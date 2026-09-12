# TiboWatch — 把 Codex 额度重置提醒推送到 iPhone

[English](README.md) · [交给 Codex 部署](DEPLOY_WITH_CODEX.md) · [工程与运维说明](docs/ENGINEERING.md)

**不用盯着 X，也不用在手机上挂 Telegram，有 Codex 重置消息就收 Bark 通知。**

TiboWatch 是一个部署在 Linux 服务器上的轻量转发器：读取 [SaveMeTibo 已发布的 RSS 提醒](https://savemetibo.com/feed.xml)，通过 [Bark](https://github.com/Finb/Bark) 发到 iPhone。它还可以复用你已有的 Codex CLI 登录，把新消息翻译成简体中文；翻译暂时不可用时，就发送英文原文。

本文对应基于 RSS 的 v1.1.2 正式版本。部署提示词会先核对所选代码版本，再执行安装。

## 一句话交给 Codex 部署

在服务器上的 Codex，或已经获准通过 SSH 操作服务器的 Codex 会话里，粘贴：

```text
请在我授权的 Linux 服务器上部署 https://github.com/hkwsg/tibowatch 的 v1.1.2 正式版本。
先读取所选版本的 DEPLOY_WITH_CODEX.md，按其中流程执行。
环境信息请自行检查，需要时引导我提供 Bark 推送地址，
然后完成配置、手机测试和定时运行。
翻译优先复用我已有的 Codex 登录。
```

固定版本入口：[v1.1.2 部署提示词](https://github.com/hkwsg/tibowatch/blob/v1.1.2/DEPLOY_WITH_CODEX.md)。

完整、独立的部署提示词在 **[DEPLOY_WITH_CODEX.md](DEPLOY_WITH_CODEX.md)**。已经下载项目的话，直接让 Codex“读取根目录这个文件并开始部署”即可。

服务器环境准备好后，你主要配合两件事：粘贴一次 Bark 地址，以及确认手机收到测试。其余配置由 Codex 处理。只有 ChatGPT 对话、尚未连接服务器时，也可以先让它读懂项目，再把同一份部署提示词交给有服务器操作权限的 Codex。

## 需要准备什么

| 准备项 | 用途 |
| --- | --- |
| 一台支持 systemd 的 Linux 服务器、Python 3.11+ 和安装权限 | 每约五分钟检查一次 RSS |
| iPhone 已安装 Bark、允许通知 | 通过 `api.day.app` 收提醒 |
| 可选：已有且兼容的 Codex CLI 与登录 | 将新的英文提醒译成简体中文 |

不需要 X API Key、Telegram 账号、数据库或 Docker。翻译使用现有 CLI 账号的可用权限和额度，不是每轮检查都调用模型。

## 手机会收到什么

假设上游发布：

```text
Codex — Watch

A major quota incident puts another Codex reset in play.
```

匹配到发布时的 86% 概率并完成中文翻译后，可能显示为：

```text
Codex — 重置观察：86%

一次重大额度故障，使 Codex 再次重置成为可能。
```

这里只展示内容示例。实际通知就是上游标题和正文，或它们的译文；不附加来源标签、时间或解释。通知请求保存在 Bark 历史中，不再附带点击外跳 URL。可靠匹配到的发布概率直接放标题末尾；无可靠数据就不加后缀。文字路径保留原有 emoji，翻译提示也要求保留。匹配的上游 PNG 可作为尽力提供的图标，不是完整大图附件，手机裁切效果不保证。

可通过 `TIBOWATCH_ICON_URL` 配置固定的仓库托管图标，详见工程说明。

## 它怎样工作

```text
SaveMeTibo RSS → 发现新增或改动 → 可选的一次翻译 → Bark → iPhone
```

SaveMeTibo 负责发布社区提醒。TiboWatch 每约五分钟读取一次，以条目 GUID 和标题／正文判断有没有新内容，并记住处理结果。

第一次运行只建立历史基线，不补发旧消息。新增条目或标题／正文改动才形成通知；重复轮询、仅日期或链接变化都不重复打扰。Bark 发送失败就保留待发内容，下次重试不会再次翻译。

## 常见问题

**手机需要挂 Telegram，或者一直连接我的服务器吗？**

不需要。服务器把消息交给 Bark，手机通过苹果推送收取。手机仍需正常联网，并开启 Bark 通知权限。

**一周大概发多少条？**

取决于 SaveMeTibo 发布、修改了多少提醒，没有固定周频率。每五分钟检查不等于每五分钟发消息。

**Codex 要一直开着吗？**

不需要。平时由 systemd 调度脚本；开启翻译后，只有新增或标题／正文发生变化的消息才临时调用一次 Codex CLI，单次最多等待 30 秒。

**要另开一个 ChatGPT 账号或申请 API Key 吗？**

复用自己已有、兼容的 CLI 登录即可，不要求额外账号。翻译是可选项，没有可用登录也能转发英文。

**能直接部署在 Windows 或 macOS 吗？**

现成服务脚本面向支持 systemd 的 Linux。其他电脑上的 Codex 可以通过已授权的 SSH 连接操作 Linux 服务器。

## 继续阅读

- [部署提示词](DEPLOY_WITH_CODEX.md)：让 agent 接手安装，按需获取 Bark 地址并验收。
- [工程与运维说明](docs/ENGINEERING.md)：代码地图、配置、常用命令、更新和排障。
- [Agent 指南](AGENTS.md)：供 Codex 等编码助手快速了解项目。
- [参与贡献](CONTRIBUTING.md)、[安全说明](SECURITY.md)、[版本记录](CHANGELOG.md)与 [MIT 许可证](LICENSE)。

SaveMeTibo 是独立社区数据源，提醒不等于你的个人账号额度已生效。TiboWatch 与 OpenAI、Tibo、X、Bark、SaveMeTibo 均无隶属关系。
