# AI 中文日报

每天从公开 RSS、GitHub Releases、HN、YouTube 发布信息和免费社区汇总中采集近 24 小时资讯，用 DeepSeek Flash 合并事件、生成中文摘要，并发送到 Telegram。

目标 5～15 条，重要资讯不足时少报。只读标题与来源摘录，不抓整篇正文、不处理视频字幕。所有原文链接由程序从来源补入，模型不能添加陌生链接。

## 当前版本

- Python 3.12，仅使用标准库，无需购买服务器或安装第三方 Python 包。
- 模型固定为 `deepseek-flash`，关闭思考模式；每次任务最多请求一次模型，失败不自动重试。
- 候选最多 40 条，提示内容最多 12,000 UTF-8 字节，输出最多 3,200 tokens。
- 根据用户最新决定，不设预算上限，不记录费用或模型用量；费用在 DeepSeek 后台查看。
- 新闻去重缓存只记录公开新闻的链接/标题哈希和发送尝试时间，与费用无关。
- 默认只生成采集预览。自动推送和消息接收由 `DIGEST_ENABLED` 控制。

## GitHub 配置

仓库 **Settings → Secrets and variables → Actions → Secrets** 中配置：

| Secret | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek 调用密钥 |
| `TELEGRAM_BOT_TOKEN` | BotFather 生成的 Token |
| `TELEGRAM_CHAT_ID` | 接收日报的私人聊天 ID |

密钥只放 Secrets，不写入源码、README 或日志。接收者需要先给机器人发送 `/start`。开启 GitHub 轮询后会回复 `/start`、`/help` 和普通消息；发送 `/digest` 或「生成日报」可请求最新日报。只接受配置的私人聊天，其他用户不能触发模型调用。普通消息只回复使用提示，不发送私人聊天内容给模型。

## 先预览，再手动试跑

1. 打开仓库 **Actions → AI 中文日报 → Run workflow**。
2. 选择 `preview`：只采集，无模型调用、无 Telegram 推送；下载运行中的 `digest-…` artifact 查看 `preview.md` 和 `sources.json`。
3. 预览正常后，选择 `send`：生成中文日报并推送到上述聊天。结果保存为 `digest.txt` 和 `delivery.json`，不包含费用统计。
4. 选择 `bot` 可手动检查待处理消息；试跑成功后，在 **Settings → Secrets and variables → Actions → Variables** 创建 `DIGEST_ENABLED`，值填 `true`。

开启后约每 **5 分钟**检查一次消息，并在每天北京时间 **08:17** 起的首次轮询尝试发送当天日报。GitHub 调度可能延迟，不保证准点或五分钟内回复；变量未设为 `true` 时，定时任务不接收消息或推送。将变量改为 `false` 可关闭自动任务。

为防止重复调用，处理消息前先确认 Telegram 的消息游标，同一批「生成日报」请求只调用一次模型。超过一小时的积压命令不执行，定时生成失败当天不自动重试；用户可重新发送 `/digest`。消息游标和新闻去重只是运行状态，不记录费用。电脑可以关机。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
python3 -m digest.run
```

采集预览写入 `output/`。已配置三个环境变量并明确需要真实推送时，再执行：

```bash
python3 -m digest.run --live
```

程序不自动读取 `.env`，示例文件仅说明环境变量名称，防止误把密钥文件上传。

## 来源和边界

来源配置在 `config.json`：OpenAI、Hugging Face、Google 博客，Ollama/vLLM/Transformers Releases，HN AI 讨论，OpenAI YouTube，AINews 社区汇总。

- X 来源为 [AINews](https://news.smol.ai/) 的公开汇总，同时可能包含 Reddit/Discord；不直接登录 X，不保证覆盖任意账号。汇总日期太旧时不会补进日报。
- HN 按 AI 查询采集，属于讨论来源，不能作为官方公告的替代品。
- YouTube 只报告视频发布时间和标题，不生成整段视频摘要。
- 没有发布日期、超过 24 小时、明显在未来的条目会过滤；失败来源会显示在报告和日报中。
- 仅用来源摘录概括，重要细节请看原文；未经核验的社区说法要求模型标注。
- 去重缓存可能被 GitHub 回收；丢失后同一条近 24 小时新闻可能再次出现。遇到发送超时，不盲目重发，避免重复；这也可能导致某条日报漏送，需查看 Actions 结果。
- 同一事件的合并依赖模型判断，尚需真实试跑观察摘要质量。
- GitHub 公开仓库连续 60 天无活动时可能自动停用定时任务，需要在 Actions 页面重新启用。

## 参考

- [DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [HN 搜索 API](https://hn.algolia.com/api)
- [GitHub 定时触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

交付和验证状态见 [STATUS.md](STATUS.md)。
