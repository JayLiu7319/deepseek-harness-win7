# rc.1 候选推进区

2026-10-15：约定范围已完成，合格代码为 `d5f74c2d`，单次完整门禁通过。A01–A06、A08 的退出条件和精确证据已更新到 `actions.json`；A07 的274-manifest 审计保留逐项边界，LSP/云搜索/ingress 等仍是独立可选工作。当前活动清单为 [rc1-capabilities.json](../../rc1-capabilities.json)，本目录较早的 `capabilities.json` 是候选发现快照。详见 [完整签收记录](../../../docs/research/2026-10-15-rc1-baseline-migration-progress.md)。以下保留2026-10-14 的推进历史与原计划，不代表当前仍待切换。

固定目标：`a66e4702047846cdaa10c66c9d3df3951f5ea70d`（`dsh-v0.1.2-rc.1`）。

这里记录已获用户授权的 rc.1 增量工作。`capabilities.json` 是目标的全部 274 个 manifest、声明依赖、候选 profile 可达性、Python Loader 提供端、编译 client、alpha 历史合同和缺口分类；`actions.json` 是行动项的推进记录。二者**不是** `tasks/*.json` 的 migration 状态，也不能使 alpha 的既有证据满足 rc.1。

本批已经实现差分观察器修复、路径引用服务、公共提示词顺序 API 及消费者、新轮次摘要和 raw-view 通知门控、seq/offset 数值准入及索引读取。完整 Session 逻辑 header/继承切分、持久化和其他调用消费者仍需闭包；生产 `reference`、`baseline.json` 和官方 Web 产物尚未切换。轮次摘要已经可以通过 Loader 显式安装，未向 alpha 默认组合增加未来版本行。

方案见 [行动评估](../../../docs/research/2026-10-14-rc1-baseline-and-capability-action-plan.md)，结果和证据边界见 [首批推进记录](../../../docs/research/2026-10-14-rc1-bootstrap-progress.md) 和 [继承切分推进记录](../../../docs/research/2026-10-14-rc1-session-lineage-progress.md)。后者交付显式新 metadata 的精确 cut、ownEvents/isOwnSeq、JSONL 边界、preparation/projection 消费和 ignorable 保留；默认入口、canonical decode 和全部 query/Remote 等消费者尚待统一切换。

候选清单可以在另一个干净的 rc.1 checkout 重建；输出必须选择新路径，以免覆盖已有观察：

```powershell
.venv/Scripts/python.exe scripts/rc1_inventory.py --source-root <clean-rc1-checkout> --output <fresh-capabilities.json>
.venv/Scripts/python.exe scripts/rc1_capabilities_oracle.py --source-root <built-clean-rc1-checkout> --output <fresh-output-directory>
```

Source 准备使用目标自身的 frozen lockfile 和 `build:official`。本机 linked worktree 的开发 hook 安装不兼容子模块 Git 配置；使用上游 `scripts/install-lefthook.mjs` 明确支持的局部 `CI=true` 跳过 hook，退出后恢复环境。未修改上游文件或 Git 公共配置。

## 下一批的固定顺序

1. 先闭合新版 Session：逻辑 header 的 `isSeeded`、独立 `inheritedEventCount`、`ownEvents`/`isOwnSeq`、ignorable envelope、projection init/restore 参数；同时修改 fork、prepare/restore、冷读取、Remote、SDK/ACP、子代理和查询消费者。
2. 物理 JSONL 仍按上游 version-0 `seedLength` 记录继承切分，在编码/解码边界转换成新版逻辑 metadata；不把旧 JSONL 文件整体改写成新逻辑 header。具体准入和切分超长等非法值使用 rc.1 原样测试验证。
3. SQLite 默认生产组合已经使用 JSONL；上游删除 SQLite backend 后，保留旧 SQLite 数据及历史验证。单独确定本产品兼容 reader/export 名称和只读迁出流程，再退休 canonical 旧包名；不能删除数据库或把旧 SQLite Source 验收替换为 rc.1。
4. 原子切换 reference、baseline、modules、test/dynamic inventory、当前合同修订、mapping 和任务；保留 alpha 历史文件、原始 artifacts 和冻结回执。新目标的活动任务只引用新的合同修订，重新实测 Source 缺陷例外，不全仓库替换 SHA。
5. 导入独立 rc.1 官方构建的原样 Web/client 资源，更新默认组合的 turn-outline/ui-schedule 及有效 Loader 模块，再验证轮次轨道、深历史跳转、设置/计划任务、文件引用和冷恢复。
6. 上述关联批次稳定后冻结候选并运行一次 `verify_release.py`。首批的定向和浏览器结果不代替这一步。

LSP、外部搜索、云沙箱和 ingress 保持 A07 独立可选批次；默认 profile 的直接依赖出现缺口时，按候选矩阵升级为 P0。
