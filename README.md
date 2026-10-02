# AI 中文日报

每天用可信来源保底，再按主题跨作者、跨项目、跨期刊发现候选，统一精选内容，通过用户指定的 API 服务调用 GPT-6.1 Sol 生成中文摘要，并发送到 Telegram。

日常目标10条：GitHub项目3条、AI技巧2条、成长2条，健康、科研、心理学各1条；重大AI事件有才报，最多额外3条。不足时少报，不补广告、小更新或重复内容。读取公开标题、元数据和有限摘录，不保存完整文章。所有链接由程序从来源补入，模型不能添加陌生链接。

## 当前版本

- Python 3.12，仅使用标准库，无需购买服务器或安装第三方 Python 包。
- API 地址为 `https://api.790053500.com/v1`，模型为该端点实际列出的 `gpt-6.1-sol`，推理强度为 `medium`（中等）；每次任务最多请求一次模型，失败不自动重试。
- 候选最多80条，提示内容最多48,000 UTF-8字节，推理与可见输出合计最多8,192 tokens；各栏目名额、来源ID、证据说明和内容长度由程序校验。
- 根据用户最新决定，不设预算上限，不记录费用或模型用量；费用在用户 API 平台后台查看。
- 去重缓存只记录公开内容的链接/标题哈希和发送尝试时间，保留90天，与费用无关。
- 默认只生成采集预览。自动推送和消息接收由 `DIGEST_ENABLED` 控制。

## GitHub 配置

仓库 **Settings → Secrets and variables → Actions → Secrets** 中配置：

| Secret | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 用户指定 API 服务的调用密钥（保留现有 Secret 名称） |
| `TELEGRAM_BOT_TOKEN` | BotFather 生成的 Token |
| `TELEGRAM_CHAT_ID` | 接收日报的私人聊天 ID |

密钥只放 Secrets，不写入源码、README 或日志。接收者需要先给机器人发送 `/start`。开启 GitHub 轮询后会回复 `/start`、`/help` 和普通消息；发送 `/digest` 或「生成日报」可请求最新日报。只接受配置的私人聊天，其他用户不能触发模型调用。普通消息只回复使用提示，不发送私人聊天内容给模型。

GitHub查询使用工作流已有的临时 `github.token`，权限仍为 `contents: read`；无需新增个人令牌，令牌只发送给GitHub API且不跟随重定向。

## 先预览，再手动试跑

1. 打开仓库 **Actions → AI 中文日报 → Run workflow**。
2. 选择 `preview`：只采集，无模型调用、无 Telegram 推送；下载运行中的 `digest-…` artifact 查看 `preview.md` 和 `sources.json`。
3. 预览正常后，选择 `send`：生成中文日报并推送到上述聊天。结果保存为 `digest.txt` 和 `delivery.json`，不包含费用统计。
4. 选择 `bot` 可手动检查待处理消息；试跑成功后，在 **Settings → Secrets and variables → Actions → Variables** 创建 `DIGEST_ENABLED`，值填 `true`。

开启后每天北京时间 **07:00** 触发自动日报，并约每 **5 分钟**检查一次消息；发送「生成日报」或 `/digest` 可额外请求最新日报。每天07:00之后首次实际执行会补偿定时延迟，当天自动任务最多尝试一次。GitHub 调度和模型生成可能延迟，不保证07:00准点送达或五分钟内回复；变量未设为 `true` 时，定时任务不接收消息或推送。将变量改为 `false` 可关闭自动任务。

为防止重复调用，处理消息前先确认 Telegram 的消息游标，同一批「生成日报」请求只调用一次模型。超过24小时的积压命令不执行，定时生成失败当天不自动重试；用户可重新发送 `/digest`。消息游标和新闻去重只是运行状态，不记录费用。电脑可以关机。

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

来源与每类时间窗口均配置在 `config.json`：

| 栏目 | 内容来源 | 时间范围 |
| --- | --- | --- |
| GitHub 3条 | 今日Trending；Skills/MCP/Agent/知识管理和自动化/工作流/研究/生产力主题搜索；新兴项目搜索 | 当日采样；近180天有推送，新兴项目近90天创建 |
| AI技巧 2条 | HN跨作者主题检索后读取原文；Mollick/Simon可信博客；AINews跨作者X转述 | 原创文章近30天；X汇总近72小时 |
| 成长 2条 | HN习惯、学习、判断、沟通、专注、生产力主题检索；James Clear、Stanford GSB、Greater Good保底 | 原文近90天，社区收录日不能替代发布日期 |
| 健康 1条 | PubMed跨期刊搜索睡眠、运动、久坐、饮食方式的综述；Cleveland Clinic科普保底 | 研究近60天；科普近90天 |
| 科研 1条 | Nature研究论文；PubMed微生物组、人类学习、睡眠记忆、决策研究 | Nature近7天；PubMed近30天 |
| 心理学 1条 | PubMed情绪调节、社会联结、认知偏差、注意力控制、正念研究；APS保底 | PubMed近60天；APS近30天 |
| AI重大动态 | OpenAI、Google AI、Anthropic、Hugging Face | 近72小时，重大事件才入选 |

- GitHub高星搜索要求至少1,000星；新兴项目要求近90天创建且至少300星，不能把新建或最近提交当成增长证明。Trending允许总星数至少300且当日新增至少100的项目。真实星数与增长是线索，采样日不是发布日期，源码可见也不等于宽松开源授权。
- 主题查询按北京时间日期轮换，每个主题源每日查询两个方向，不限定作者或项目名单；手动生成当日沿用同一轮主题。保留近180天维护要求。已发送候选先去除，再填来源名额，避免旧结果占满搜索名额。
- HN只是跨网站发现线索：逐篇读取原网站的公开元数据和有限摘录，过滤缺少发布日期、旧文章和无法读取的页面。HN分数不是X点赞，也不证明事实可靠。HN检索覆盖的是社区索引，不是全网。
- X从免费 [AINews](https://news.smol.ai/) 汇总中跨作者筛选原帖链接，不再限定三个作者；仍不直接登录X、不调用付费X API、不保证账号覆盖。标明社区转述和汇总日期，无完整点赞数据，不能冒充X高赞榜。
- PubMed先按主题和出版时间搜索，再读取原论文摘要，保留期刊、研究类型、方法与结论摘录。日期不完整、无摘要、撤稿或相关撤稿标记的记录会排除。摘要不等于全文，被索引不等于高质量；健康优先日常知识，不推送手术或补充剂促销建议。
- 在提示容量内让不同原作者/机构有机会被比较。编辑准则为实用性40%、可信度30%、个人关联20%、新意10%；这是取舍标准，不输出虚构的客观评分。最终摘要说明价值并给出可行小行动。
- 原Ollama/vLLM/Transformers常规版本、HN泛讨论和YouTube发布信息不恢复。AI重大动态不选普通修复、微小跑分提升、企业合作或宣传文章。
- 成长区分作者观点和研究；健康、科研、心理学必须标明证据性质或信息不足。单项、动物或初步研究不推断成人体因果结论，不提供个性化用药建议。
- 日期缺失、超出所属栏目时间范围或明显在未来的条目会过滤；文章读取部分失败也记录，不把失败显示为全部成功。NIH两个源在验证时返回403，当前由实际可读取的Cleveland Clinic补充。
- 去重缓存可能被GitHub回收；丢失后可能重复推送。Telegram发送超时不盲目重发，也可能导致漏送，需查看Actions结果。
- 栏目选题、重大程度和摘要仍依赖模型判断；名额是上限，不保证每天凑满10条。
- 当前未接付费网页搜索或X检索接口。免费通用网页搜索测试出现无关结果或验证码，因此范围搜索使用已验证的GitHub、HN和PubMed；不声称找到全网最佳。
- 新发现页面及其重定向只读取公开HTTPS地址，阻止本机、内网及异常端口。若本机代理返回合成DNS地址，会通过Google Public DNS验证公共目标（仅域名，无文章、聊天或凭据）；GitHub正常DNS无需此步骤。
- GitHub 公开仓库连续 60 天无活动时可能自动停用定时任务，需要在 Actions 页面重新启用。

## 参考

- [GPT-6.1 Sol 官方模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [GPT 推理参数及兼容说明](https://developers.openai.com/api/docs/guides/latest-model)
- [Chat Completions 接口](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [GitHub Trending](https://github.com/trending)
- [HN Algolia公开检索](https://hn.algolia.com/api)
- [PubMed E-utilities查询参数](https://www.ncbi.nlm.nih.gov/books/NBK25499/)
- [GitHub 定时触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

交付和验证状态见 [STATUS.md](STATUS.md)。
