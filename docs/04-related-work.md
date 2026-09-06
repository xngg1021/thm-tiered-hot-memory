# 相关工作：分层记忆、上下文管理与验证边界

读取日期：2026-09-06。本文比较选定公开系统，不是完整文献普查或性能排行榜。

**THM 的公开贡献目前是四层设计、规则勘误和验证契约。** 已有系统分别提供文件化知识、时间图、语义召回、上下文压缩或执行恢复；“使用分层”不足以构成差异。更值得验证的问题是：在同一任务、有效性过滤和完整上下文预算下，THM 的驻留策略是否改善证据选择，且保持来源、删除和恢复语义。此处是比较问题，不是已验证优势。

本文没有安装这些系统、调用其模型或复现其 benchmark。厂商和论文的结果各有数据、模型、预算和评估器，本文不合并分数。THM 当前可复算的范围见[验证契约](03-validation-contract.md)与[架构](02-架构设计.md)。

## 证据和版本口径

- **D：公开文档。** 官方产品页或固定提交的 README；功能描述不等于运行验证。
- **S：源码抽查。** 本次直接读取的配置或 feature 定义；只证明所读代码，不证明所有调用链。
- **L：许可证正文。** 按根目录、组件或例外记录，不推断法律兼容性。
- **M：发布元数据。** 只对应明确命名的 release 或服务公告。
- **P：论文摘要和版本页。** 下表均未全文复核、未复现。
- **I：本文的比较推论或待测问题。** 不归为上游已实现功能。

[来源清单](related-work-sources.json)按对象保存 URL、具体节/代码路径、读取日期、取得的完整 commit、证据层级与未验证项。在线文档没有取得对应 commit 时填空，不借用同项目仓库 HEAD 冒充文档版本。固定提交也不等于最新发布包。

## 四种不同的“层”

| 轴 | 回答的问题 | 例子与不可机械对齐处 |
| --- | --- | --- |
| 驻留与访问 | 什么常驻请求，什么需要检索或外部访问？ | THM 的 T0–T3 主要沿此轴；T3 是外部定位，不保证来源永久不变。 |
| 阅读深度 | 同一内容先看摘要还是全文？ | [OpenViking](https://raw.githubusercontent.com/volcengine/OpenViking/0c5147cae26aec8d6d93445ec6ad86d5faff4035/README.md) 的 L0 摘要、L1 概览、L2 详情可以同时存在，不代表热度驱逐顺序。 |
| 内容类型与表示 | 保存的是经历、事实、策略还是派生知识？ | [Hindsight](https://raw.githubusercontent.com/vectorize-io/hindsight/424601520456a6d06a81b2fdc709a0d023d800af/README.md) 的事实/经历/观察/mental model，以及 [MemOS](https://raw.githubusercontent.com/MemTensor/MemOS/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/README.md) 插件的 trace/policy/world model/skill，不应逐项映射成 T0–T3。 |
| 生命周期与处理阶段 | 何时提取、整理、修订、失效、归档或删除？ | [ReMe](https://raw.githubusercontent.com/agentscope-ai/ReMe/0eba6ea831c915ca92e4c501785951dc00538a41/README.md) 的 source/daily/digest/metadata 包含加工和派生关系；[OpenClaw dreaming](https://docs.openclaw.ai/concepts/dreaming) 的 light/REM/deep 是整理阶段。 |

上述分类是 I。一个系统可同时使用几条轴；“长期存储”“常驻上下文”“可回源”“可恢复”也必须分别判断。

## 直接同类：能力矩阵

“待核”表示本次证据不足，不表示系统一定没有该功能。预算中的 top-k、字符数、检索努力和实际 tokenizer token 数不互换。

| 对象与形态 | 来源、时间与当前知识 | 按任务召回与上下文预算 | 证据 |
| --- | --- | --- | --- |
| Hermes：harness 加可选 provider | 原生 MEMORY.md / USER.md 与会话历史；外部 provider 增量协作，不能把外部知识当成原生文件 | provider 可预取相关记忆、注入上下文及接收会话；不同 provider 的预算与过滤不同 | [H](https://raw.githubusercontent.com/NousResearch/hermes-agent/9a84bee265daad14340a80d7585928cd8ea1f9eb/README.md) D |
| ReMe：本地优先记忆组件/工作区 | source 保留资源与会话来源，daily 和 digest 提炼；frontmatter、Sources wikilink 定位；metadata 是派生面 | BM25、可选 embedding、wikilink 展开，返回行级片段；不需全库塞入上下文 | [R](https://raw.githubusercontent.com/agentscope-ai/ReMe/0eba6ea831c915ca92e4c501785951dc00538a41/README.md) D |
| Signet：跨 harness 的本地 daemon | 原始 evidence、派生索引、当前 ontology 分开；当前知识可含版本属性和审计操作，支持回指证据 | FTS、embedding 与有界图遍历；当前 dreaming 选择 agent scope 证据，不再逐条启动旧 extraction/decision worker | [S](https://docs.signetai.sh/what-is-signet/)、[流程](https://docs.signetai.sh/pipeline/extraction-decisions/) D |
| OpenViking：上下文数据库 | 资源/记忆/skills 使用 URI；会话提交后提炼；具体事实有效区间规则待核 | 目录递归检索、可观察检索轨迹、L0/L1/L2 按需阅读；阅读深度不保证请求总预算 | [V](https://raw.githubusercontent.com/volcengine/OpenViking/0c5147cae26aec8d6d93445ec6ad86d5faff4035/README.md) D |
| MemOS：系统、本地插件、云产品须分开 | 本地插件记录 trace、policy、world model、skill；SQLite 与技能文件；完整系统使用 memory cube 等接口 | 插件按技能、trace/episode、world model 检索；特定宿主有前台超时边界，不外推到所有适配器 | [M](https://raw.githubusercontent.com/MemTensor/MemOS/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/README.md)、[本地插件](https://github.com/MemTensor/MemOS/blob/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/apps/memos-local-plugin/README.md) D |
| Letta / MemFS：当前 agent 产品的 Git 记忆 | 文件 frontmatter 和 Git 历史；system/ 每轮进入上下文，其他文件按需读；文件树仍进入提示 | 默认不建语义/向量索引；memfs-search 为可选 mod，语义/混合搜索另需 QMD；对话搜索是另一路径 | [L](https://docs.letta.com/concepts/memfs) D |
| Hindsight：记忆引擎，可自托管或 Cloud | retain 提取事实、时间、实体与关系；bank 分域；观察与 mental model 是派生知识 | recall 合并语义、BM25、图和时间过滤，再融合、重排、裁剪；reflect 另作综合推理 | [Hn](https://raw.githubusercontent.com/vectorize-io/hindsight/424601520456a6d06a81b2fdc709a0d023d800af/README.md) D |
| Mem0：公开库、自托管服务、托管平台 | 当前 README 描述 ADD-only 提取和时间检索；该算法说明未逐函数复核，不能据此说显式删除 API 不存在 | README 描述多信号召回；所列性能明确来自有专有优化的托管平台，不能当开源库成绩 | [M0](https://raw.githubusercontent.com/mem0ai/mem0/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/README.md) D；默认配置另见下文 S |
| Graphiti / Zep：图引擎与托管平台 | Graphiti 保存 episode 与时间事实，使用时间有效性及失效旧边；失效不等于删除历史 | 语义、关键词与图检索；图时间线不是 T0–T3 换层规则 | [G](https://raw.githubusercontent.com/getzep/graphiti/547422865cca9fb5a82915c074d899428c145ff4/README.md) D |
| ClawMem：本地 vault 与宿主插件 | README 描述保留导入内容的原始时间、来源及生命周期；归档可恢复 | BM25、向量、RRF、查询扩展、重排和图遍历；按 prompt 自动提供上下文 | [C](https://raw.githubusercontent.com/yoloshii/ClawMem/ba09cb83050867c54f4e05a7050c874171c47cd8/README.md) D |
| OpenClaw dreaming：harness 内整理子系统 | 只纳入合格交互会话，过滤 recalled context 防止循环学习；晋升前回读活跃来源、排除已删片段和不可信来源 | recall 次数、不同 query 数及评分共同设门槛；日记不作为晋升证据；深阶段可整理 MEMORY.md | [O](https://docs.openclaw.ai/concepts/dreaming) D |

### 恢复、删除、接入和数据路径

| 对象 | 换层 / 恢复 / 删除边界 | 宿主接入与主要依赖 / 外发边界 |
| --- | --- | --- |
| Hermes | 本次未验证 provider 与原生文件之间的删除传播、恢复或跨会话可见性 | 原生记忆继续启用，外部 provider 同时只选一个；其存储可在本地或云端。provider 会同步对话，必须按实际选项判断外发。[官方说明](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/) |
| ReMe | 文件工具允许移动、删除并提示剩余入链。reindex 重建现有 chunk 的检索索引，不等于重新解析并重建全部 wikilink 图；本次未做崩溃恢复验证 | CLI/HTTP/MCP/Python 和原生集成；embedding 默认关闭，基础文件/BM25 操作无需 LLM，自动整理需模型配置。[文件语义](https://raw.githubusercontent.com/agentscope-ai/ReMe/0eba6ea831c915ca92e4c501785951dc00538a41/docs/en/memory_as_file.md)、[配置](https://raw.githubusercontent.com/agentscope-ai/ReMe/0eba6ea831c915ca92e4c501785951dc00538a41/README.md) |
| Signet | evidence 不被语义摘要改写；daemon 验证并审计 ontology 操作。Windows 的导入写入和 imported-source deletion 有平台限制；完整级联删除待核 | hooks、MCP、插件或 provider 接 daemon；SQLite 为规范状态；推理路由可为 local_only 或 remote_ok，本地 daemon 不等于模型请求不出机。[README](https://raw.githubusercontent.com/Signet-AI/signetai/77ae26b1a3f3b67ff2cee21f27c863d7e69fce37/README.md)、[路由](https://docs.signetai.sh/configuration/inference-routing/) |
| OpenViking | URI 与不同深度内容共存，非自动热度换层。Hermes viking_forget 可按精确 URI 删除；断电恢复及派生层删除范围未测 | 有 Hermes provider；server init 配置模型，可用远端提供商或本地 Ollama。自托管数据库不自动消除推理/embedding 外发。[README](https://raw.githubusercontent.com/volcengine/OpenViking/0c5147cae26aec8d6d93445ec6ad86d5faff4035/README.md)、[provider](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/) |
| MemOS | 插件卸载保留数据、skills、日志和配置；升级可能迁移 SQLite schema；不能称卸载已擦除记忆。完整系统恢复语义待核 | 本地插件适配 OpenClaw/Hermes/DSH，缺配置时本地 embedding、无 LLM，依赖 LLM 的反思会跳过或降级；配置 provider 后须另查外发。云插件在运行前召回、之后保存消息到云端。[总览](https://raw.githubusercontent.com/MemTensor/MemOS/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/README.md)、[插件](https://github.com/MemTensor/MemOS/blob/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/apps/memos-local-plugin/README.md) |
| Letta / MemFS | Git 版本和 worktree 支持检查与同步；Git 可回退不证明物理擦除。local 的持久性与备份由本地负责 | 当前 runtime / App Server 在 letta-ai/letta-code；旧 V1 server 在原仓库 archive 分支且已停止支持。Cloud 的 agent 状态另行托管，不能用 runtime 许可推断云端完整后端。[MemFS](https://docs.letta.com/concepts/memfs)、[仓库迁移](https://github.com/letta-ai/letta/blob/4511fa0bc91f68fbab32b91f694617271ea9012b/README.md)、[当前代码说明](https://github.com/letta-ai/letta-code/blob/701f2a5367828847313876c735ade27b9df97689/README.md) |
| Hindsight | 文档支持保留、检索、综合；本次未核实所有 fact/observation/source 的删除级联和断电语义 | Docker、外置 PostgreSQL或 embedded pg0 等方式；可配置本地或远端模型。wrap_openai 默认指向 Cloud，需显式 URL 才连接自托管，不能按客户端安装位置判断数据位置。[README](https://raw.githubusercontent.com/vectorize-io/hindsight/424601520456a6d06a81b2fdc709a0d023d800af/README.md) |
| Mem0 | 历史 SQLite 与向量存储是不同持久化面；本次未证明删除覆盖两者、日志与备份 | Python Memory 的默认配置类选择 OpenAI LLM + embedder、Qdrant；默认路径详见下段。MemoryClient / 托管版和自托管 HTTP 服务分开。[README](https://raw.githubusercontent.com/mem0ai/mem0/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/README.md) |
| Graphiti / Zep | 旧边失效保留时间历史；MCP 提供 episode 删除，但完整级联与重建行为未核实 | Graphiti 可自托管、使用图数据库；README 默认示例使用 OpenAI，也提供其他 LLM client。Zep 是另一个托管平台，不用旧社区版替当前平台背书。[README](https://raw.githubusercontent.com/getzep/graphiti/547422865cca9fb5a82915c074d899428c145ff4/README.md) |
| ClawMem | README 声称索引事务可回滚、清理孤立 embedding、归档可恢复；这里只作为文档证据，未做故障注入 | Bun/SQLite、本地模型或推理 sidecar；hooks、MCP、OpenClaw/Hermes 插件。README 也给云 embedding 选项，不能泛称每种配置都零外发。[README](https://raw.githubusercontent.com/yoloshii/ClawMem/ba09cb83050867c54f4e05a7050c874171c47cd8/README.md) |
| OpenClaw dreaming | 记录重写前像；模型失败或验证失败可回退；这不证明全系统断电原子性。已删源回读检查不等于所有副本物理删除 | memory-core 内运行；当前官方文档默认启用，可配置关闭；整理使用模型，模型路由与外发未实测。[Dreaming](https://docs.openclaw.ai/concepts/dreaming) |

**Mem0 默认数据路径（S，固定提交抽查）。** `MemoryConfig.history_db_path` 默认是 `MEM0_DIR/history.db`，未设 `MEM0_DIR` 时为 `~/.mem0/history.db`；`VectorStoreConfig` 选择 qdrant，默认配置路径为 `/tmp/qdrant`。LLM 和 embedder 的 provider 默认均是 openai。以上是公开库的配置默认值，不代表平台服务的路径，也不证明运行环境未覆盖默认值或没有遥测。实际部署须核对持久卷及请求目标。[MemoryConfig](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/mem0/configs/base.py)、[向量配置](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/mem0/vector_stores/configs.py)、[Qdrant](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/mem0/configs/vector_stores/qdrant.py)、[LLM](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/mem0/llms/configs.py)、[embedding](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/mem0/embeddings/configs.py)。

## 补充系统：比较具体组件

| 对象 / 类别 | 可确认的比较点 | 条件与未验证项 |
| --- | --- | --- |
| [Pi](https://github.com/earendil-works/pi/blob/9767ba275f3e9a5ee0f5c5342249b629ab1b2282/packages/coding-agent/README.md) / harness | JSONL 会话树、分支、compaction 与扩展点；旧 badlogic/pi-mono 地址转向 earendil-works/pi | 扩展存在不表示默认启用自动分层记忆；会话压缩与跨会话事实记忆分开。D |
| [OpenHands SDK condenser](https://docs.openhands.dev/sdk/arch/condenser) / 上下文组件 | 将事件历史转为压缩视图，Condensation 记录被视图过滤的事件 ID；可用 LLM 或不压缩实现 | 文档中的遗忘视图不等于删除原事件；此行不评价 OpenHands 其他持久记忆功能。D |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence) / 编排与持久化 | checkpointer 保存线程图状态，store 保存跨线程应用数据 | 原 durable-execution 入口已转向 persistence；delta channel 复制/裁剪必须保留所需祖先写入链，恢复责任含保存器实现。不能推断任意外部副作用恰好执行一次。D |
| [Deep Agents](https://docs.langchain.com/oss/python/deepagents/memory) / harness | memory 文件路径配合 StateBackend / StoreBackend / CompositeBackend；namespace 可按 agent 或 user 分域 | 隔离来自身份、路由和权限配置；共享文件不是天然安全边界。D |
| [Codex 本地记忆](https://learn.chatgpt.com/docs/customization/memories?surface=app) / harness 功能 | 从合格历史异步提炼文件；可分别控制生成与使用；本地记忆与 ChatGPT Work 的账号/工作区记忆不同 | 当前固定源码 `Feature::MemoryTool`：key 为 memories、Stage::Stable、default_enabled=false；不能沿用 Beta 标签，也不推断所有客户端已发布或所有用户开启。[源码](https://github.com/openai/codex/blob/ac192cd7937b0d73edc6dffe009940ae53782dd4/codex-rs/features/src/lib.rs) D+S |
| [OpenAI Agents SDK sessions](https://github.com/openai/openai-agents-python/blob/1d471a4775bf2f40179f411824da383deb4c3fca/docs/sessions/index.md) / SDK 组件 | 在 run 前合入历史、后存新条目；可通过 callback 控制传给模型的历史 | 客户端 session 与 conversation_id / previous_response_id 等服务端 continuation 不应混用；不是默认事实库或有效期引擎。D |
| [Gemini CLI memory](https://geminicli.com/docs/tools/memory/) / harness 功能 | 编辑 Markdown；共享项目指令、私有项目笔记和全局偏好分域，接入层级上下文 | 当前页面描述直接文件编辑；不从旧 save_memory 文档推断当前工具或自动提取默认开关。D |
| [Claude Code memory](https://code.claude.com/docs/en/memory) / 产品功能 | CLAUDE.md 与自动记忆分开；自动记忆默认开，可用 /memory 审核/切换；MEMORY.md 索引与按需主题文件配合 | 当前页面启动加载上限为 200 行或 25KB 中先到者；这是行/字节限制，不是 token 数。记忆文件不随旧会话清理自动删除；不把产品文档当服务后端开源证明。D |
| [DeepSeek Harness](https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/d347e703908d0406b7a7ef80e3a0e594d86b2215/README.md) / harness | Cordis 插件化模型、工具、session 等能力；官方站标 Developer Preview | 插件扩展点不是内建 THM 同类引擎；未安装。根 MIT，第三方 notice 另计。[官方状态](https://www.deepseek.com/harness/en/) D+L |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework/blob/2c49f50cf08ebb6c1687146336f039051f159333/README.md) / SDK 与编排 | 中间件、图工作流、checkpoint 和可观测性 | [Python 1.17.0 release](https://github.com/microsoft/agent-framework/releases/tag/python-1.17.0) 发布于 2026-09-03，元数据 prerelease=false；不外推到各语言、Labs 或所有子包稳定性。D+M |
| [memU](https://github.com/NevaMind-AI/memU/blob/385bdb30cda7f5265368934b8008ce2b73283283/README.md) / sidecar 记忆组件 | 当前版本为 agent 整理 Wiki/skill 文件并 commit，服务负责存储、embedding、检索；支持本地或 Cloud backend | 当前形态不能用旧 item/category 三层概括；宿主负责生成，服务不调用 chat 不代表全链路无模型外发。README 兼容表仍有未验证项。D |
| [Mastra OM](https://mastra.ai/docs/memory/observational-memory) / 上下文记忆组件 | Observer 形成观察、Reflector 重写观察日志，近期消息与摘要配合；模型、阈值和 scope 可配置 | 默认 thread scope，resource scope 标 experimental；反思不是持续新增的独立无界层；附件也可能发送给 Observer。D |
| [lossless-claw](https://github.com/martian-engineering/lossless-claw/blob/c6d06e528867004c85ae84897019d94f0cdbea50/README.md) / OpenClaw context 插件 | SQLite 留存原消息，摘要 DAG 可用工具逐步展开；每轮组合摘要与近期原文 | “lossless”指原文保留，不证明模型理解或摘要语义无损；新宿主控制接口有能力门槛，README 当时提示尚无对应稳定 OpenClaw release。D |

## 工业托管服务

| 服务 | 来源可支持的事实 | 不能由这些事实推出 |
| --- | --- | --- |
| AWS AgentCore Memory | [2025-10-13 GA 公告](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available/)；[短期事件](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/using-memory-short-term.html)供长期提取，[DeleteMemoryRecord](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-delete-memory-records.html)删除指定长期记录 | 自管理 extraction strategy 不等于 AWS 服务后端开源；短期事件删除与长期记录删除应分别核对，本次未验证级联、备份删除、全部地域与当前配额。D+M |
| Google Memory Bank | [Vertex AI 发布记录](https://docs.cloud.google.com/vertex-ai/docs/release-notes)于 2025-12-16 宣布 Sessions/Memory Bank GA；当前页面转向 Gemini Enterprise Agent Platform。[Memory revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions)区分创建、更新、删除及派生修订 | GA 不表示每个地区/账号都可用；公开 SDK/示例许可不等于服务端开源。生成使用模型；[产品页](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale)明确 ML 处理跟随模型 endpoint 的 region/multi-region，不能只看静态存储位置。D+M |

两者均是托管服务，本文未创建资源、发送记忆、计费测试或验证删除执行结果。Google 原 overview 入口重定向至汇总页，新的 overview 子页未成功读取；采用已读的官方 revisions、产品页和发布记录限定结论。

## 学术原型与评测入口

以下仅核对 arXiv 标题、摘要和版本/提交历史（P，2026-09-06）。不声称全文审查、源码可运行、最终同行评审状态或代码许可；论文许可与实现代码许可也不互推。

| 条目：完整标题和读取版本 | 摘要允许讨论的方向 | 下一步最小对照问题（I） |
| --- | --- | --- |
| [Memory OS of AI Agent — 2506.06326v1](https://arxiv.org/abs/2506.06326v1)；2025-05-30 | 短期、中期、长期个人记忆和更新机制 | 驻留策略带来的增益是否超出相同预算的简单队列？ |
| [LightMem: Lightweight and Efficient Memory-Augmented Generation — 2510.18866v4](https://arxiv.org/abs/2510.18866v4)；2026-02-28 | 过滤、主题短期整理与离线长期更新 | 总成本是否包含离线构建和整理？此处专指该 ID，不混同名论文。 |
| [MemRL: Self-Evolving Agents via Runtime Reinforcement Learning on Episodic Memory — 2601.03192v2](https://arxiv.org/abs/2601.03192v2)；2026-02-12 | 固定模型、反馈驱动的记忆效用与两阶段检索 | 效用学习是否比单纯使用频次更适合任务召回？ |
| [Agentic Memory: Learning Unified Long-Term and Short-Term Memory Management for Large Language Model Agents — 2601.01885v3](https://arxiv.org/abs/2601.01885v3)；2026-07-23 | AgeMem 将长期/短期管理纳入学习策略 | 学习策略的训练成本、调用成本和规则基线如何分开？ |
| [MemoryCPT: An End-to-End Agent Memory Framework for Cost-Performance Trade-off — 2608.04843v1](https://arxiv.org/abs/2608.04843v1)；2026-08-05 | 离线构建蒸馏、查询相关检索与成本感知摘要 | 统一预算下，压缩是否保存必要证据与限定条件？ |
| [Agent Memory Distillation: Empowering Small LLM Agents with Hierarchical Teacher Memory — 2608.07169v1](https://arxiv.org/abs/2608.07169v1)；2026-08-07 | 教师轨迹形成 workflow/subtask/function 记忆，注入时机不同 | 区分内容粒度与驻留层，并单列教师轨迹取得成本。 |
| [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory — 2410.10813v2](https://arxiv.org/abs/2410.10813v2)；2025-03-04 | 信息提取、跨会话、时间、更新和拒答 | 是否同时测过期答案、错误主体、无答案时拒答？ |
| [LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues — 2605.12493v1](https://arxiv.org/abs/2605.12493v1)；2026-05-12 | 面向环境经验的证据收集；并非 V1 同题升级分数 | 召回运行经验与回答个人历史问题是否分别评估？ |
| [MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks — 2602.16313v1](https://arxiv.org/abs/2602.16313v1)；2026-02-18 | 记忆—行动—环境的多会话相依任务 | 召回正确之后是否实际改善后续动作？ |

表中日期为所读版本的提交日期，不是会议发表日期。MemoryOS 与 MemOS 是不同条目。

## 许可与组件边界

以下按本次取得的固定提交读取正文，仅记录公开声明。项目依赖、模型权重、数据集、托管服务条款及第三方目录可能另有许可；本文不改变 THM 原有许可声明，也不包含竞品代码。

| 对象 | 本次确认的许可范围 |
| --- | --- |
| Hermes | MIT（所列仓库根声明）。[许可证](https://github.com/NousResearch/hermes-agent/blob/9a84bee265daad14340a80d7585928cd8ea1f9eb/LICENSE) |
| ReMe | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/agentscope-ai/ReMe/blob/0eba6ea831c915ca92e4c501785951dc00538a41/LICENSE) |
| Signet | Apache-2.0（所列仓库根声明）。[许可证](https://raw.githubusercontent.com/Signet-AI/signetai/77ae26b1a3f3b67ff2cee21f27c863d7e69fce37/LICENSE) |
| OpenViking | 主项目 AGPLv3；crates/ov_cli 与 examples 为 Apache-2.0；third_party 遵从各自原许可。[根 LICENSE](https://raw.githubusercontent.com/volcengine/OpenViking/0c5147cae26aec8d6d93445ec6ad86d5faff4035/LICENSE)；[crates/LICENSE](https://github.com/volcengine/OpenViking/blob/0c5147cae26aec8d6d93445ec6ad86d5faff4035/crates/LICENSE)；[examples/LICENSE](https://github.com/volcengine/OpenViking/blob/0c5147cae26aec8d6d93445ec6ad86d5faff4035/examples/LICENSE) |
| MemOS | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/MemTensor/MemOS/blob/78a372a4fc853a24d2a78efa3b4bbbd27ab9f7ad/LICENSE) |
| Letta / MemFS | 旧项目根声明 Apache-2.0；当前 Letta Code / App Server 的 LICENSE 也是 Apache-2.0，但明确排除名称、logo、图像等品牌资产；不据此推定 Cloud 完整后端许可。[旧根 LICENSE](https://github.com/letta-ai/letta/blob/4511fa0bc91f68fbab32b91f694617271ea9012b/LICENSE)、[当前 LICENSE](https://github.com/letta-ai/letta-code/blob/701f2a5367828847313876c735ade27b9df97689/LICENSE) |
| Hindsight | MIT（所列仓库根声明）。[许可证](https://github.com/vectorize-io/hindsight/blob/424601520456a6d06a81b2fdc709a0d023d800af/LICENSE) |
| Mem0 | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/mem0ai/mem0/blob/dae67f74f5cc7bf138c7d7d6f9cec5ce4b4373b3/LICENSE) |
| Graphiti / Zep | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/getzep/graphiti/blob/547422865cca9fb5a82915c074d899428c145ff4/LICENSE) |
| ClawMem | MIT（所列仓库根声明）。[许可证](https://github.com/yoloshii/ClawMem/blob/ba09cb83050867c54f4e05a7050c874171c47cd8/LICENSE) |
| OpenClaw dreaming | MIT（所列仓库根声明）。[许可证](https://raw.githubusercontent.com/openclaw/openclaw/8f18f14aa09123d85127a28c6f52f2fcac473096/LICENSE) |
| Pi | MIT（所列仓库根声明）。[许可证](https://github.com/earendil-works/pi/blob/9767ba275f3e9a5ee0f5c5342249b629ab1b2282/LICENSE) |
| OpenHands SDK | MIT（所列仓库根声明）。[许可证](https://github.com/OpenHands/software-agent-sdk/blob/fe91d7dfc94d299e3751acb2b0c80ccbc582623c/LICENSE) |
| LangGraph | MIT（所列仓库根声明）。[许可证](https://github.com/langchain-ai/langgraph/blob/81bf17b23123e4ef8b9d5f49fa09a0122fc2edd1/LICENSE) |
| Deep Agents | MIT（所列仓库根声明）。[许可证](https://github.com/langchain-ai/deepagents/blob/6c89fe2197a2dfe4f3851cda38565bcadba6066b/LICENSE) |
| Codex | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/openai/codex/blob/ac192cd7937b0d73edc6dffe009940ae53782dd4/LICENSE) |
| OpenAI Agents SDK | MIT（所列仓库根声明）。[许可证](https://github.com/openai/openai-agents-python/blob/1d471a4775bf2f40179f411824da383deb4c3fca/LICENSE) |
| Gemini CLI | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/google-gemini/gemini-cli/blob/85aca163f6c73ac6ce380b5447359146b8adcae4/LICENSE) |
| DeepSeek Harness | MIT（所列仓库根声明）。[许可证](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/LICENSE) |
| Microsoft Agent Framework | MIT（所列仓库根声明）。[许可证](https://github.com/microsoft/agent-framework/blob/2c49f50cf08ebb6c1687146336f039051f159333/LICENSE) |
| memU | Apache-2.0（所列仓库根声明）。[许可证](https://github.com/NevaMind-AI/memU/blob/385bdb30cda7f5265368934b8008ce2b73283283/LICENSE.txt) |
| Mastra | ee/ 及第三方内容除外，其余 Apache-2.0；EE 使用独立许可，不能整仓统称 Apache-2.0。[LICENSE.md](https://github.com/mastra-ai/mastra/blob/2e476c33bd8311597a2de14fa31a263a1ce7669a/LICENSE.md) |
| lossless-claw | MIT（所列仓库根声明）。[许可证](https://github.com/martian-engineering/lossless-claw/blob/c6d06e528867004c85ae84897019d94f0cdbea50/LICENSE) |
| Claude Code、AWS AgentCore、Google Memory Bank、Mem0 Cloud、Zep 等托管/产品服务 | 未取得可据以认定其完整服务后端开源的许可证，不作开源后端判断。 |

GitHub 自动识别的 NOASSERTION 不能直接写成“无许可证”：Signet、memU、Mastra、OpenClaw 本次均回到实际文件检查。OpenViking 也不能只引用 CLI 的 Apache-2.0 覆盖主项目 AGPLv3。

## THM 公开设计涵盖与缺口

| 维度 | 目前公开证据 | 缺口 / 状态 |
| --- | --- | --- |
| 四层与活跃度 | [架构](02-架构设计.md)记录 T0–T3、历史公式与反例；[原公式检查](../scripts/thm_numeric_audit.py)可复算 | 不能据公式检验声称真实记忆更准确或阈值最优。 |
| 来源、版本、时间有效性 | [验证契约](03-validation-contract.md)要求稳定身份、修订/有效区间及不同事件语义 | 是验收要求，不是读者可安装的公共引擎能力。 |
| 任务召回与预算 | 契约区分存储、召回、构造上下文和宿主请求，并要求完整包预算 | tokenizer、模型实际请求、语义泛化与原系统兼容性仍需独立实验。 |
| 换层、删除与恢复 | 契约要求先写目标、验证、提交索引，再有条件清理；锁、版本检查、删除 tombstone 等须测 | 公开仓库不含原始运行引擎；原引擎仍不可用（ORIGINAL_ENGINE_UNAVAILABLE），不能标记原引擎修复完成。 |
| Hermes 接入 | 验证契约固定在其已读的 upstream commit，定义原生写入及冻结快照边界 | 新增 related-work 采用另一次固定快照，不修改旧契约 pin；未声称 THM provider 已部署或已观察真实模型请求。 |
| 比较效果 | 本仓库提供规范和机械检查，能据此设计实验 | 没有公共可复现的 THM 对成熟竞品端到端成绩。未公开的 reference implementation 也不构成公开可安装功能。 |

## 下一次对照实验：最小问题清单

以下只定义问题，不在本次新增适配器或运行 benchmark。

1. 在相同输入、固定时间、主体/项目/环境过滤和完整上下文预算下，简单近因/频次、按需检索与 THM 候选策略分别选择哪些证据？
2. 来源版本改变、有效期结束或用户纠正后，是否仍召回旧值？是否保留旧值的历史有效区间和回源关系？
3. 无答案、错误主体、相似实体、否定条件和同义改写是否正确处理？保留开发集与留出查询，不看结果改题。
4. 自动展示、检索返回、实际使用和来源确认是否分开？重复注入会不会自行强化热度？
5. 模型入口的完整请求是否真的包含选中内容？字符估算、检索 top-k 和目标 tokenizer token 分别报告。
6. 晋升、驱逐或移动在每个持久化边界中断后能否恢复？重复执行、冲突写入及删除 tombstone 是否保持一致？
7. 删除是否覆盖正文、摘要、索引、缓存和另行管理的会话？备份中的保留与物理清理是否被明确区分？
8. 固定模型与查询时，分别报告召回质量、正确空结果、实际请求预算、在线延迟、离线整理成本和数据外发目标；再决定是否开展有限模型实验。

## 仍未验证的事项

直接同类的功能主要是 D；源码抽查只覆盖 Mem0 的默认配置和 Codex 的 feature 元数据。各系统真实安装、故障恢复、删除级联、隔离、遥测与完整网络路径均未测试。Letta Cloud 等商业托管后端及 Mastra EE 的完整许可边界没有扩展判断。论文全部限于摘要与版本元数据。各项更细的范围和固定版本见[来源清单](related-work-sources.json)。

本次未复制外部实现代码、未变更原公式或历史报告、未发布真实记忆。比较结论停留在可核实的公开证据和明确待测问题。
