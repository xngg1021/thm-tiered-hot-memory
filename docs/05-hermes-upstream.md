# Hermes 上游接入研究与勘误

读取日期：2026-09-06。本页替换原 80 行研究稿中的过强映射和未充分支持的结论；原稿保存在[历史文件](05-hermes-upstream-original-20260906.md)。历史文件不是当前接入规范。竞品概览继续见[相关工作](04-related-work.md)及其来源清单。

## 已核对的接口

以下源码链接固定在 `9a84bee265daad14340a80d7585928cd8ea1f9eb`，不把该快照冒充所有用户的安装版本。

| 接口 | 源码支持的语义 | THM 的正确处理 |
| --- | --- | --- |
| initialize(..., hermes_home=...) | 调用方提供 profile-scoped 路径 | 未来 provider 应使用所传路径；当前 CLI 可显式传 --mem-dir，不能猜当前 sticky profile |
| system_prompt_block | 静态 system 内容 | 不用它承载不断变化的动态召回 |
| prefetch / queue_prefetch | 准备即将到来的 turn 所需召回文本，后台预取可供后续使用 | 仍须检查实际 manager 调用及最终请求；不是每个 API 请求都一定执行的证明 |
| sync_turn | 非阻塞地保存完成的 turn | 不等于只有 session_search 才有归档，也不自动定义 T2 |
| on_session_switch | 对 resume/branch/reset/rewind 等切换重新绑定状态 | 防止后续写入落入旧会话 |
| on_memory_write | 镜像 add/replace/remove 写入及来源元数据 | **只记写入类型。写入不是检索命中，也不是实际采用，不能顺手增加 hit** |
| on_pre_compress | 在压缩前提供处理入口；版本化 checkpoint 有额外契约 | 必须按具体实现检查持久化结果，不自动声明无损 |

原始依据：[MemoryProvider ABC](https://github.com/NousResearch/hermes-agent/blob/9a84bee265daad14340a80d7585928cd8ea1f9eb/agent/memory_provider.py)。本轮读取的是接口定义，没有部署 THM provider。

## 层级关系的修正

Skills 保存按需的程序性操作说明；T1 可以保存主题资料。二者可以互补，不能因为都是 Markdown 就断言功能等价。MemoryProvider 是宿主扩展机制，可以参与多个生命周期环节；它不等于 THM 的 T3 外部定位层。

检查某个文件没有 hit 计数，不足以证明整个上游没有任何使用统计。自动整理的范围和默认开关也要针对具体版本、模块与配置检查。本页不沿用原稿的“官方明确没有全部排程巩固”等全局结论。

此前 issue 分组、评论数、标签和功能日期保留为历史检索线索。没有随本页提供逐项可复查的 issue 快照，故不据此推断维护者偏好、优先级、竞争者缺乏实机证据或方案的原创性。公开先行工作只用于工程比较，不是权利判断。

## 投稿路径

固定提交的 [CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/9a84bee265daad14340a80d7585928cd8ea1f9eb/CONTRIBUTING.md) 明确将新的 memory provider 放在独立插件中；原有 provider 的 bugfix 仍可贡献。该要求来自维护和耦合边界，不代表所有记忆相关修复或新 skill 都被拒绝。

因此 THM 完整 provider 的候选方向是独立插件；上游贡献应选择可复现、范围小、通用的具体问题。当前不自动创建新仓库、评论 issue、提交 PR 或承诺维护者会合并。公开主脚本仍是[索引维护与建议工具](06-engine-guide.md)，不是已安装的 provider。
