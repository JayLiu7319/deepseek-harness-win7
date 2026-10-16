# rc.3 分阶段实施记录

本记录推进 [rc.3实施路径](2026-10-16-rc3-baseline-implementation-assessment.md)。活动pin在共享合同与消费者稳定前仍为rc.1，候选发现或单项定向通过不构成rc.3发行资格。Desktop继续按指定Electron22与Standard/AIO方案。

## R01：候选发现工具与输入审查

`scripts/candidate_inventory.py`以显式base/target读取Git对象，不移动checkout或修改活动台账。它建立目标manifest归属、去除devDependencies的反向运行依赖、目标源码中的literal profile roots、bundle/preset声明及条件位置。条件声明保持待运行验证，Loader注册和依赖可达性不提升为激活证据。

从实际 `verify_release.py` AST取得21组Source配置和82个配对驱动，记录配置/驱动原始SHA、literal旧pin和目标路径匹配；继承配置和导入helper仍需逐合同审查。结果见 [discovery-summary.json](../../migration/candidates/rc3/discovery-summary.json)，全量观察保存在本次自有输出目录。

定向验证覆盖新CLI/输出保护、Git对象与任意base/target、subpath和dev-only依赖、未知ref拒绝、非literal profile拒绝、旧发现消费者与原差分观察器：**39 passed**，Python3.8.10，17.74秒。命令、完整日志及XML位于 `.goose/out/rc3-r01-20261016/inventory-pytest.*`。未重复运行全量pytest或构建Portable。

独立rc.3 Source位于 `.goose/out/rc3-source-20261016`；frozen-lockfile安装完成，`CI=true`只使用上游支持的hook跳过，不修改上游源码。

2026-10-17：官方 `build:official` 完成（322.58秒），随后通过 `import_frontend.recorded_inputs` 校验干净目标checkout、四个official环境值、完整234项产物及聚合SHA；尚未导入产品前端。新增 `rc3_profile_activation.mts` 在独立home/workspace实际运行canonical web profile，分别创建minimal/standard/cordis Agent，观察v3 Session、127个ACTIVE entry及28个无fiber配置节点，实际client graph为53行。minimal仅`pwsh`，standard与cordis包含`present`及新工具；产品minimal保留editor的差异仍按评估披露。完整可审查输入见 [source-inputs.json](../../migration/candidates/rc3/source-inputs.json)。

首次tsx直导入未使用Source路径映射，因const enum `FiberState`导出失败；指定Source自己的tsconfig后实际启动、创建和shutdown成功，原失败日志保留在新输出目录。运行时探针不包含模型请求或浏览器执行，不据此声明Win7或Web旅程通过。

同时修正候选lane审计的`**`匹配零级目录和注释片段误识别，并重新生成静态审查摘要；新增回归用例与既有候选工具用例定向通过。21组Source配置、82配对驱动仍需随业务合同逐项审查，R01尚不能宣称全部关闭。

## R02-A：独立格式迁移库

新增 `dsh/session/format`：lossless JSON快照与安全整数、canonical代际文件名、完整且唯一的相邻迁移链、流式event/run及finish顺序、预声明继承边界一致性、codec/catalog分派和header-only状态、current/transformed验证及拒绝cause语义。库本身不挂载服务、不读写日志，活动Session仍写v0。

新增显式rc.3 Source配对入口 `scripts/session_format_oracle.py` 和104个共用输入场景。两端完整输出（含错误名、消息、cause）全部一致，包含双相邻stage、compact run、finish尾事件、来源decoded/transformed、未来版本拒绝、损坏当前header、codec/迁移缺口与重复、decoder和restorer失败分层。合成stage/codec仅验证库合同，不能代替真实历史格式迁移。

验证范围：上游自身4文件31测试；Python新库、失效runner控制及既有Session数字/冻结header消费者，共 **187 passed**（6.99秒）。复用已有JSON/冻结实现，因此覆盖其公开Session消费者。首次消费者执行因PATH选到Node22.20.0而触发73个Source身份setup错误，保留原日志；将该次子进程PATH指向已安装且合同要求的Node22.22.2后全选范围通过，没有修改旧身份门禁。凭据见 [session-format-checks.json](../../migration/candidates/rc3/session-format-checks.json)，完整原始输出在 `.goose/out/rc3-r02-format-*20261017/`。

R02后续仍需真实v0/v1/v2/v3 codec、历史迁移与v3 Session恢复、不可变代际/锁/发布、query/projection和持久化直接消费者一起关闭；本子阶段不切换默认writer，也不提升migration任务状态。

## R02-B：历史v0/v1/v2物理codec

新增独立 `format_v0_to_v1` 与 `format_v1_to_v2` 库，保持rc.3已发布格式的物理语义：完整物理header字段与精确成员拒绝、`seedLength`存在即seeded（含零）、v0/v1压缩text/reasoning/tool-call run的惰性展开、稠密seq、provenance范围及v2压缩编码、row-atomic recoverable前缀和closed-turn拒绝、v2从已接纳end-seed发现继承边界。物理codec继续保留opaque payload，不把它冒充逻辑恢复校验。

新增193个历史codec场景，逐项完整Source/native结果匹配；扩展配对CLI允许显式corpus，重复输入与错误Source仍fail closed，JSON比较显式区分boolean和number。收尾复核新增3个stage/decoder继承边界与restorer版本boolean控制，修复Python布尔与数字相等造成的错误放行或错误拒绝时机；修改前3处差分原样保留。最终 **107个planner场景匹配**，Python格式库和codec共 **310 passed**；上游两份codec规格共 **69 passed**。当前Windows执行，Python3.8.10与固定Node22.22.2。选择范围覆盖新增物理提供端、header/provenance/recovery直接消费者及配对入口；未重跑全量门禁。

凭据见 [released-codec-checks.json](../../migration/candidates/rc3/released-codec-checks.json)，最终原始行与错误位于 `.goose/out/rc3-r02-codec-strict-final-20261017/{codec,planner}/`。同步修正静态发现摘要指向修复glob后的原始观察和SHA；旧观察继续保留。活动台账`check`/`ready`均exit0（141.70/72.50秒），不推进任何未验收的业务状态。首个60秒预算超时已保留；其读取范围为17,161个历史输入/证据路径约12.41GiB，另有86个LFS历史ZIP约6.44GiB，不能据静默输出诊断为挂起。R02-A的104场景与字节凭据保留为早期阶段记录，本条记录后续修正与107场景结果。

下一闭包为历史逻辑校验/相邻迁移、v3结构准入与Session恢复，再接代际持久化与query/projection消费者。当前v0 writer、活动pin及既有发行资格未切换，R02尚未整体关闭。

## 输出与磁盘管理

开始前磁盘余量约184GB。先执行既有 `process_artifact_retention.py`，其所有权/结束状态/字节核验没有发现新增可回收项目，未删除未知输出或未解决失败。完整清理观察位于 `.goose/out/rc3-r01-20261016/history-retention.json`。

本批定向测试继续使用conftest提供的新短工作区和自动合成回执清理。日志/XML/真实Source观察保留；后续大批复制、构建或统一门禁前重新核对空间，已完成的可重建夹具按既有规则回收。禁止按目录年龄或通配符整体清空历史。

2026-10-17完成R02-A后再次执行既有retention，未发现额外符合回收条件的历史产物；空间约182GB。保留Node身份失败现场与实际成功配对，不把清理无匹配报告成已释放空间。
