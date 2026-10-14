# rc.1 Session 继承切分推进记录

日期：2026-10-14。承接 [首批推进](2026-10-14-rc1-bootstrap-progress.md)，首批提交为 `cdd7b20a`，工作分支 `codex/rc1-baseline-upgrade`。目标仍固定 `a66e4702047846cdaa10c66c9d3df3951f5ea70d`。

本批交付 A03 的继承切分、逻辑/物理边界和投影消费合同。生产 reference、默认 header、当前 JSONL decode、alpha 证据台账及原版 Web 资源尚未整体切换，不能据此宣告 rc.1 或发行完成。

## 实现与边界

- `Session.inheritedEventCount`、`ownEvents()`、`isOwnSeq()` 独立于 `firstLiveSeq`。构造 seed 可以包含子 Session 自己的后缀；恢复重放长度不能覆盖持久化继承切分。seeded metadata 要求显式 seed 与切分，重验安全整数、负零、非零 unseeded cut 和越过日志的 cut；end-seed 的构造/恢复语义保持上游行为。
- `validate_rc1_session_header` 严格要求 `isSeeded:boolean`，拒绝 own `seedLength`，包括值为 undefined 的字段。显式带 `isSeeded` 的一般 Session 准入执行新字段规则；缺少该字段的 alpha 准入暂留至协调切换。**因此这不是默认构造/所有公开入口已完成 rc.1 准入的证明。**
- `lineage_storage` 将 logical metadata + exact cut 编码为私有 version-0 JSONL header，decode 分别返回两者。seeded cut 0 与 unseeded 0 不合并。旧文件无需批量改写；外来版本在当前格式形状检查前拒绝。此边界尚未替换当前 canonical store 的 decode 入口。
- `SessionStorageMetadata` / `SessionInspection` 携带精确切分；准备缓存、恢复、实时借用及显式新格式的 `SessionStore.prepare` 传递它。投影 `init(header, inheritedEventCount)`、完整/尾部 restore、hydrate 都收到实际 cut。旧单参数定义通过注册时的明确 arity 适配保留；initializer 内部 TypeError 不会被误判后重试。
- envelope 的 `ignorable` 只接受 literal true。JSONL 明文/zstd 读取保留未知且 marked 的事件与序号，不跳过日志行；未标记的未知类型仍拒绝。此项没有替换完整已知事件词汇表。
- 旧 SQLite schema 没有该 envelope 列，明确拒绝新 ignorable 写入并回滚，不悄悄丢掉标记，也不改写既有数据库 schema。既有 reader/普通读写回归仍保留；canonical 旧包名退休、兼容 reader/export 的产品归属仍待后续批次处理。

## 定向验证

选择原有 Session/fork/缓存、projection/checkpoint/preparation、冷历史/查询、子代理、审批/计划及实际 Web profile 引用消费者，覆盖新提供端的直接使用链路。Python 3.8.10；候选 Source Node 22.20.0；旧 alpha 观察器保持 Node 22.22.2 身份要求。

| 范围 | 结果 | `.goose/out/` 目录 |
|---|---|---|
| 初始继承切分和现有 Session 回归 | 169 passed、1 夹具失败；恢复在 owned probe 后追加 end-seed 属于正确上游行为 | `rc1-lineage-initial-20261014` |
| 修正夹具后，Session/projection/checkpoint/preparation | 234 passed | `rc1-lineage-projection-20261014` |
| 更广直接消费者 | 299 passed、120 setup errors；旧审批 Source observer 拒绝非固定 Node | `rc1-lineage-consumers-20261014` |
| 仅按原 Node 22.22.2 要求复验审批消费者 | 122 passed | `rc1-lineage-permission-pinned-node-20261014` |
| 独立 rc.1 测试及恢复原有冷 lineage 用例 | 90 passed | `rc1-lineage-boundary-final-20261014` |
| JSONL none/zstd、旧 SQLite 回滚/普通存储、准备/冷 lineage | 103 passed | `rc1-lineage-storage-final-20261014` |
| 最终变动后的边界、两种存储、准备、冷 lineage、投影、fork、候选 workflow | 136 passed | `rc1-lineage-stable-20261014` |
| 原样 rc.1 sequence/session/fork/JSONL 的 header/seed/inherit/own/fork/ignorable 场景 | 114 passed，155 未选中；不是完整 Source gate | `rc1-lineage-source-20261014/vitest-pinned-targeted.log` |
| 原样 rc.1 Source/native、最终实现输入 | 14 类 observations matched | `rc1-lineage-stable-paired-20261014` |
| 现有 alpha pin/inventory/迁移记录一致性 | check 退出码 0；不认证 rc.1 | `rc1-lineage-record-check-20261014` |

重叠测试不累加。失败输入/日志保留。原有 `tests/test_session_lineage.py` 已按首批提交字节恢复，新增用例位于独立的 `tests/test_session_rc1_lineage.py`。Source 测试直接使用实际 Node 可执行文件和已安装的 Vitest；先前 pnpm exec 触发的开发 hook 失败与 Windows shim 对正则管道的解析失败也保留。

14 类配对含首批 10 类，加上 lineage、storageLineage、strictHeaders、projectionLineage。严格 header 观察以 Python 的专用 rc.1 validator 对应真实 Source `Session.fromRestore` 准入；没有用这一局部观察证明默认 alpha 入口已退休。观察封存所有 tracked Source、编译库输入、输入摘要、实际导入 Python 模块、两个 observer 文件哈希，且拒绝缺少/额外 observation 类别。

定向封存摘要为 `.goose/out/rc1-lineage-stable-20261014/receipt.json`，校验最终实际 Python 模块及 observer 字节仍与配对观察一致，并分别保存两次成功 pytest XML 和 Source 原始观察/日志摘要；不把重叠或失败运行拼成完整资格。Python 3.8 AST、候选 JSON、文档相对链接及 diff 空白检查通过。

## 继续切换的顺序

1. 将完整 canonical JSONL decode、读/写 coordinator、恢复及 cold/live query source 统一为 logical header + exact cut；完成查询索引/Remote、SDK/ACP、子代理和 default/fork 的必要消费者及原样配对。
2. 同时退休默认 alpha header 准入与 projection 适配，处理完整事件词汇及旧 SQLite reader/export 的归属。不能只改默认 header 而遗漏冷数据和消费者。
3. 协调 reference、baseline、活动契约 revision、mapping、274-manifest inventories 和新任务；旧 86 项 integrated 与冻结证据保持历史身份。
4. 导入已构建的原版 rc.1 Web/client 资源，验证活跃 Loader 行、轮次导航、深分页/跳转、流式、设置与 schedule；文件引用重跑原样 rc.1 浏览器旅程。
5. 稳定候选完成相关定向闭环后安排一次 `verify_release.py`，回执绑定确切提交、冻结输入和 Portable ZIP。当前未执行完整回归/发行门禁，也未认证 Win7 真机。

当前行动状态见 [候选台账](../../migration/candidates/rc1/actions.json)；以上结果没有提升任何历史迁移任务或 `accepted_upstream`。
