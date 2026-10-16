# rc.3 候选评估区

日期：2026-10-16。目标 `dsh-v0.1.5-rc.3` / `a4c74a91e06b00fe0b0937bde982170c526cc842`；差分起点为当前活动rc.1 / `a66e4702047846cdaa10c66c9d3df3951f5ea70d`。

R02-E：新增 [v3-logical-checks.json](v3-logical-checks.json)，v2→v3系统消息、canonical envelope、PTC迁移及恢复已完成纯库验证。Source 519项原断言通过，新增1,607个观测场景匹配，含既有回归共3,118项Python定向测试通过；生产恢复/持久化仍待接通。

R02-F：新增 [catalog-checks.json](catalog-checks.json)，完整静态catalog、当前v3准入与surface保护的显式库入口已完成验证。九组3,696场景配对，Python定向3,756项通过；未挂载当前v3 writer或generation持久化。

R02-G：新增 [lease-checks.json](lease-checks.json)，Win7 API写锁、原版/原生混合双进程互斥与崩溃释放8组场景通过，存储定向27项通过；锁尚未接入生产handle。

R02-H：新增 [jsonl-current-checks.json](jsonl-current-checks.json)，当前JSONL扫描器153场景配对与2,357项直接消费者定向测试通过，尚未替换活动JsonlStore。

R02-I：新增 [generation-checks.json](generation-checks.json)，generation准备/独立进程验证/排他发布125场景配对，直接消费者590项通过；Source generation 72通过/1项创建symlink因EPERM未到断言。生产Session及handle仍待接入，不提升整体验收。

R02-J：新增 [session-runtime-checks.json](session-runtime-checks.json)，显式v3 Session运行态957场景、catalog170及current426场景匹配，Source原390断言和Python3,348定向通过；活动Session/provider未切换。

R02-K：新增 [storage-handles-checks.json](storage-handles-checks.json)，当前存储准入与单写handle/tracker147场景、generation125场景匹配；Python1,494项和Source18项通过。真实backend resolver/冷读尚待接通。

R02-L：新增 [jsonl-backend-checks.json](jsonl-backend-checks.json)，实际文件/跨实例lease/历史只读和写打开发布50场景匹配，Source JSONL原175断言与Python2,108项通过。显式candidate backend/plugin已可用，Agent/query等生产消费者仍待连接。

本区只登记候选发现与建议实施路径。活动reference、baseline、contracts、tasks和既有rc.1资格不变。R01–R11不是正式migration任务；本区不触发自动状态转换。

用户已授权逐项实施与分阶段提交。当前R01候选工具及回归已分阶段提交；Source安装、官方完整构建、实际web profile与三种Agent preset激活已观察成功，业务合同审查和迁移继续推进。持续状态见 [分阶段实施记录](../../../docs/research/2026-10-16-rc3-implementation-progress.md)，静态输入见 [discovery-summary.json](discovery-summary.json)，官方构建与实际激活凭据见 [source-inputs.json](source-inputs.json)。

- [实施路径评估](../../../docs/research/2026-10-16-rc3-baseline-implementation-assessment.md)：关键路径、合同闭包、预设差异、验证和Desktop交接。
- [指定Desktop分发方案](../../../docs/research/2026-10-16-dsh-v0.1.5-rc3-desktop-distribution-evaluation.md)：Electron22、Standard/AIO及外置prereq方向。
- [assessment.json](assessment.json)：297个manifest、两端差分统计、目标字节SHA、声明依赖、当前Loader映射与24份重点审查源码身份。
- [checks.json](checks.json)：本次实际检查及证明边界。
- [session-format-checks.json](session-format-checks.json)：R02-A纯迁移库104场景配对、Source31测试、Python187测试及尚未关闭的持久化范围。
- [released-codec-checks.json](released-codec-checks.json)：R02-B历史物理codec193场景与planner107场景配对、Source69测试、Python310测试；不表示逻辑迁移或v3 writer验收。
- [released-logical-checks.json](released-logical-checks.json)：R02-C历史v0/v1逻辑准入、关联校验与真实v0→v1迁移；726个payload及137个恢复场景匹配，Python1,177测试通过，生产恢复与后续格式仍待闭合。
- [v2-logical-checks.json](v2-logical-checks.json)：R02-D v1→v2的attempt折叠、引用重映射、v2恢复与冻结writer校验，以及LLM压缩流读者；169个逻辑和157个流场景匹配，含既有合同共1,493场景匹配、Python1,511测试通过。

矩阵每行的 `parity` 均为 `not-evaluated-for-rc3`。`current_loader_provider` 仅表示当前注册表字符串匹配，既不证明行为也不执行插件。`review_action` 是建议审查入口，提供端与消费者可跨行动合并；声明依赖不是条件激活或动态服务图。

新增27、删除4是manifest路径差分：native landlock→system家族重组和平台子包不能按数量当作新业务能力；benchmark、fixture、前端编译库同样需要分别解释。

本次只读原始观察位于仓库自有 `.goose/out/rc3-assessment-20261016-f4f9d2ab/`。正式差分脚本按默认renameLimit得到6,774条；完整重命名检测得到6,531条，本区JSON同时披露两种口径。后续正式推进应重建候选Source/test/dynamic inventory及实际profile激活图，不能用旧owner图证明rc.3覆盖。
