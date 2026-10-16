# rc.3 候选评估区

日期：2026-10-16。目标 `dsh-v0.1.5-rc.3` / `a4c74a91e06b00fe0b0937bde982170c526cc842`；差分起点为当前活动rc.1 / `a66e4702047846cdaa10c66c9d3df3951f5ea70d`。

本区只登记候选发现与建议实施路径。活动reference、baseline、contracts、tasks和既有rc.1资格不变。R01–R11不是正式migration任务；本区不触发自动状态转换。

用户已授权逐项实施与分阶段提交。当前R01候选工具定向39项通过；Source安装完成、官方构建推进中，实际激活及业务迁移尚待完成。持续状态见 [分阶段实施记录](../../../docs/research/2026-10-16-rc3-implementation-progress.md)，可重建的静态输入见 [discovery-summary.json](discovery-summary.json)。

- [实施路径评估](../../../docs/research/2026-10-16-rc3-baseline-implementation-assessment.md)：关键路径、合同闭包、预设差异、验证和Desktop交接。
- [指定Desktop分发方案](../../../docs/research/2026-10-16-dsh-v0.1.5-rc3-desktop-distribution-evaluation.md)：Electron22、Standard/AIO及外置prereq方向。
- [assessment.json](assessment.json)：297个manifest、两端差分统计、目标字节SHA、声明依赖、当前Loader映射与24份重点审查源码身份。
- [checks.json](checks.json)：本次实际检查及证明边界。

矩阵每行的 `parity` 均为 `not-evaluated-for-rc3`。`current_loader_provider` 仅表示当前注册表字符串匹配，既不证明行为也不执行插件。`review_action` 是建议审查入口，提供端与消费者可跨行动合并；声明依赖不是条件激活或动态服务图。

新增27、删除4是manifest路径差分：native landlock→system家族重组和平台子包不能按数量当作新业务能力；benchmark、fixture、前端编译库同样需要分别解释。

本次只读原始观察位于仓库自有 `.goose/out/rc3-assessment-20261016-f4f9d2ab/`。正式差分脚本按默认renameLimit得到6,774条；完整重命名检测得到6,531条，本区JSON同时披露两种口径。后续正式推进应重建候选Source/test/dynamic inventory及实际profile激活图，不能用旧owner图证明rc.3覆盖。
