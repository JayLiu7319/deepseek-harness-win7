# rc.1 首批推进记录

日期：2026-10-14。用户已认可 [行动评估](2026-10-14-rc1-baseline-and-capability-action-plan.md) 并授权推进。分支 `codex/rc1-baseline-upgrade`，起点产品提交 `38e650cf56d0c8a9d423057cf2c044055aa4a143`。

本记录描述首批实现及定向验证，未签发完整迁移/发行资格。目标固定 `a66e4702047846cdaa10c66c9d3df3951f5ea70d`。生产 reference、baseline 和 Web 产物仍在 alpha.1，`accepted_upstream` 为 null；跨模块 Session 和证据换代闭合后整体切换。

## 已实施

- A01：严格 Git NUL parser 支持 `R066` 等补零状态，保持非法相似度/路径拒绝及无写入检查。正式两端观察成功：3,732 变化、34 重命名、260 直接 owner；声明依赖归属不是完整动态影响图。
- A05：抽象 file-reference 服务与共享 grammar 独立于 local provider；Remote await `(agent, query, signal)`，使用每个 Agent 的会话 cwd。在 executor 执行目录 I/O，提供有界共享索引、独立取消、失效刷新和卸载清理。移除文件全文读取及改写用户消息；仅在 read 工具可见时贡献指引。语法/排序使用 JS UTF-16 语义。
- A03 子合同：`SessionSeq`/`SessionLogOffset` 安全整数准入、拒绝负零，`eventAt`、缓存 `snapshotEvents` 及稳定不可变范围；新增 `turnOutline` stateVersion 2 和 Loader 行。草稿保持 wire 数组身份，registry 在 schema parse 前比较 raw view，避免重复推送。未向 alpha 默认组合增加未来版本行。
- A04 子合同：`systemPrompt.getSectionOrder/getContextOrder` 及必要消费者：计划、审批、沙箱、子代理、结构化输出、persona、Web、deliverables、workflow/ralph 和启动 source 指引。兼容常量仍供既有导入，生产消费者使用服务 API。
- A06 准备：独立干净 rc.1 Source 的 frozen install 和原版 `build:official` 完成；版本 `0.1.2-rc.1`、短 SHA `a66e470`、220 client artifacts、完整 Web dist 保留，尚未导入生产。开发 hook 在子模块 linked worktree 配置下失败，使用上游支持的局部 `CI=true` 跳过；未修改源码或公共 Git 配置。
- A07：[候选能力矩阵](../../migration/candidates/rc1/capabilities.json) 覆盖全部 274 manifest：203 runtime、49 frontend、9 tooling、7 fixture、6 platform；新增 6、删除 4。每行包含角色、依赖、声明可达性、Loader entrypoint、client、alpha 历史合同、有限配对、缺口和 triage。声明可达性不是激活证明；LSP 等未增加默认依赖。

## 验证

各次分别保留，重叠测试不累加。Python 为 3.8.10；候选 Source 构建/配对为 Node 22.20.0，旧 alpha 数值观察器保持原要求 22.22.2。输出使用新的自有 `.goose/out` 目录，失败未覆盖。

| 范围 | 结果 | `.goose/out/` 下目录 |
|---|---|---|
| 差分 parser、真实两端及无写入 | 31 passed、观察成功 | `rc1-a01-20261014` |
| 引用/Remote/生命周期初步 | 27 passed | `rc1-file-reference-20261014` |
| 索引、轮次、registry、checkpoint、引用 | 100 passed | `rc1-index-and-outline-20261014` |
| 提示词服务及必要消费者、真实 Web profile/会话 | 327 passed、1 既有 Windows skip（POSIX symlink cwd） | `rc1-prompt-consumers-20261014` |
| 最新引用/取消、轮次、索引、缓存及三个 Web preset | 95 passed | `rc1-search-final-20261014` |
| Session append、快照、fork、派生缓存、性质及数值消费者 | 108 passed、73 setup errors（共享 Source Node 身份拒绝） | `rc1-session-consumers-20261014` |
| 按原 Node 22.22.2 要求复验数值/冻结 metadata 消费者 | 79 passed；身份检查未放宽 | `rc1-session-numbers-pinned-node-20261014` |
| 候选 graph 别名、dev 排除、台账不变和异目标拒绝 | 2 passed | `rc1-candidate-workflow-fixed-20261014` |
| rc.1 原样 file-reference/local、prompt、turn-outline | 118 passed、1 Windows chmod skip | `rc1-source-preparation-20261014/source-contracts.log` |
| rc.1 原样 sequence、registry/raw gate、outline、prompt | 144 passed | 同目录 `source-registry-and-sequence.log` |
| 配置 whole-float 准入和取消语义 | 15 passed、8 deselected | `rc1-config-admission-20261014` |
| 实际 rc.1 Source/native | 10 类 observations matched | `rc1-capabilities-bootstrap-final-20261014` |
| Chromium108 原样 GUI、实际 remote.mux，standard fresh/cold | 两阶段 qualified | `rc1-reference-browser-fixed-20261014` |
| 现有 alpha migration 台账及 pin/inventory 一致性 | check 退出码 0 | `rc1-migration-check-20261014`；不认证 rc.1 |

10 类配对是 grammar、mention、目录/模糊候选（含 UTF-16 排序）、搜索限制配置准入、数值准入、轮次 snapshot/change/checkpoint、顺序 API 及 indexed reads。记录 Source/编译库输入和实际 Python 模块哈希，不等同完整 Session/持久化合同。

浏览器输入中文/空格路径、显示候选并用真实键盘接受 mention；选择前后 durable events 和模型请求相同。截图、wire 与 host 观察保留。此旅程仍使用 alpha.1 原版前端，证明引用修复可用，不证明 rc.1 轮次 UI 或 Win7 真机。

首次 outline 夹具遗漏 surfaceOp、profile 夹具把系统策略事件误判为引用写入、minimal 完整 persona 遮蔽空指引、cold browser 在 Session 附着前提前采样，以及候选 graph 隔离夹具缺少 base Git 对象，均已修正输入/时序后复验。原始失败保留；没有修改前端适配宿主。

## Session 下一批义务

rc.1 **逻辑** `SessionHeader` 禁止 `seedLength`，要求 `isSeeded:boolean`，Session/Storage 独立携带 `inheritedEventCount`。JSONL 的私有 version-0 **物理** header 仍写 `seedLength`：`toHeaderLine(header, inheritedEventCount)` 编码，`fromHeaderLine` 解码为逻辑 metadata + exact cut。

现有 JSONL 优先在 decode 边界转换，不提前批量改写文件。需要闭合 seeded/unseeded、0/负零/超长 cut、fork/end-seed、准备/恢复、冷历史/查询、projection init/restore、Remote、SDK/ACP 和子代理；旧 SQLite 数据及历史证据保留，独立确定兼容 reader/export，再退休 canonical 旧包名。

下一批见 [候选行动台账](../../migration/candidates/rc1/actions.json) 和 [候选区说明](../../migration/candidates/rc1/README.md)。A02 正式 pin/台账换代、A03/A04 剩余契约、A06 原版资源导入和 rc.1 深历史导航、A08 稳定候选完整门禁仍待完成。旧 86 项 integrated 继续描述历史冻结候选，不作为 rc.1 完成证明。
