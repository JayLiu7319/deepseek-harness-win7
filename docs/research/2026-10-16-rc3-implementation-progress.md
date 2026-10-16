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

## R02-C：历史v0/v1逻辑恢复

补齐冻结的事件payload库存、精确字段和嵌套语义、独立词汇/坐标准入及跨事件关联。v0→v1流式stage恢复pre-identity消息、工具结果替换身份、steering、旧turn reason、retry链与compact归属；无法安全解释的历史词汇明确拒绝。保留当前v1的已安装词汇恢复政策，纯库不替代生产Session。压缩chunk run穿过identity edge时继续保持惰性。

新增726个Source派生payload/删除/嵌套损坏场景，并在自有Source ignored cache复制四份上游测试，仅修改import路径和恢复调用观察包装；79个原断言通过，捕获并去重137次真实restore调用。两组完整输出（消息、身份、顺序、错误名/消息/cause）均与干净rc.3 Source匹配。PTC参数结构相等保留JSON boolean/number区分，历史goal/title文本使用既有ECMAScript JSON序列化。

定向范围选择格式planner、物理codec及其新增逻辑恢复消费者，Python3.8.10 **1,177 passed**（1.21秒）；Source/native配对使用固定Node22.22.2。首轮pytest的12个差异来自测试把native冻结容器类型当作JSON类型，另一个夹具误用`text`代替`texts`；修正测试后全选通过，没有放宽业务校验，原日志保留。最初捕获目录缺少`.cache`父目录的启动失败也保留。凭据见 [released-logical-checks.json](../../migration/candidates/rc3/released-logical-checks.json)。

本阶段不切换活动pin或writer，不提升任务状态；下一阶段继续v1→v2的attempt折叠/引用映射、v2→v3系统消息及生产恢复/持久化闭包。尚未运行rc.3全量发行资格。

## R02-D：v1→v2与内嵌attempt

新增相邻v1→v2 streaming stage：紧凑/普通chunk折叠为完整message或独立attempt，保持时间与delta边界，合并可兼容run，保留buffer时序；继承cut穿过attempt明确拒绝，补齐inherited end-seed、旧中断turn结束和goal/change拆分。只重映射审计过的本文件引用；消耗掉的chunk不能再充当来源，交付watermark与跨代际捕获值保持原义。

新增v2 physical/current词汇恢复及独立冻结writer-image校验，延用跨事件关系并验证内嵌stream与消息content/usage/replay一致。LLM新增纯typed assembler和AssistantStreamAccumulator/紧凑流读者；生产Agent旧宽容适配器暂未切换，后续Agent迁移时闭合调用端。Source的Unicode空白与Python `strip()`不同，提取共享ECMAScript文本规则，并增加BOM/U+0085/U+001C等控制，修正历史schedule id trim与中断文本判断。

通过复制并包装两份Source原断言（108测试）捕获169个完整迁移、writer/恢复、独立stage操作前缀；LLM原断言37测试产生144个JSON场景，另加13个assembly/空白控制。函数/Proxy等不能无损表达为JSON的调用保留Source执行和skip观察，另用Python读者提前结束、冻结与输入脱离测试覆盖，不伪称这些调用已经配对。所有新旧六组合同共 **1,493场景完整匹配**（107 planner、193 codec、730 payload、137 v0/v1恢复、169 v2逻辑、157 stream）。Python提供端及直接消费者 **1,511 passed**（1.69秒），固定Node22.22.2；未运行全量发行门禁。

首次v2对照发现invalid stream的TypeError cause文本不同并修复；随后定向回归发现探针局部`catalog`遮蔽旧helper，修正后所有六组重新对照通过。原失败诊断保留。当前字节与原始观察见 [v2-logical-checks.json](../../migration/candidates/rc3/v2-logical-checks.json)。继续v2→v3系统消息、规范envelope和生产恢复/持久化；尚未切换活动pin/writer或提升任务状态。

## R02-E：v2→v3系统历史与规范事件

完成流式系统提示提升、确定性消息身份及碰撞拒绝、受保护首个system head、继承cut和本文件引用重映射；旧PTC事件与精确插件归属槽迁至新词汇，工具JSON和捕获代际保持原义。v3恢复用私有视图复用冻结关系校验，返回原始身份与事件；物理codec在recoverable截尾之前拒绝退役header.system、损坏system结构和必需旧PTC标签，规范envelope校验仍支持可恢复尾部。

复制8份Source测试到独立ignored cache，仅包装公开API记录观测，原519项断言全部通过。捕获1,607个不同API操作/流式前缀，完整Source/native输出一致；与前序6组共3,100场景匹配。Python3.8.10定向范围为格式planner、所有已移植历史codec/逻辑和Assistant stream的提供端与消费者，共 **3,118 passed**。凭据见 [v3-logical-checks.json](../../migration/candidates/rc3/v3-logical-checks.json)，原始输出保存在 `.goose/out/rc3-r02-v3-final-20261017/`。

初版capture包装错误返回decoder观测对象，修正为原始数值cut后重跑Source全选；6个native边界差异修复后全部匹配。批处理曾列错restore corpus文件名，该runner-error和先前失败均保留，不覆盖诊断。继续接通当前Session、generation持久化与query/projection，尚未切换writer/pin或运行发行资格。

## R02-F：完整静态catalog与当前格式边界

新增构建静态catalog，直接组合四个codec及三条相邻edge，历史读取不依赖mount哪些插件。current路径先做已安装词汇/关系恢复，再执行当前Session的header、message、request与settlement字段和surface准入；transformed保持Source的独立验证政策。新增canonical v3 surface库，包含startSeq/endSeq、assistant内嵌来源禁止、未知ignorable元数据不参与surface，以及原子计划中的受保护system首节点。所有新入口仍为显式库，生产Session集成待后续闭合。

Source三份catalog测试共26项原断言通过，记录170个完整静态catalog操作/前缀。另从真实v3恢复输入及当前message/header损坏构造426个当前边界场景，完整Source/native结果匹配；与前序合计九组 **3,696场景匹配**。定向选择全部已移植格式库、当前准入与默认header校验直接消费者（既有Session和surface规格），Python3.8.10 **3,756 passed**（4.70秒）。原始命令/日志/XML和各组结果在 `.goose/out/rc3-r02-catalog-final-20261017/`，字节凭据见 [catalog-checks.json](../../migration/candidates/rc3/catalog-checks.json)。当前writer仍为v0，未提升台账或宣称发行资格。

## R02-G：跨进程内核写锁

新增SessionWriteLease和handle稳定错误身份。Windows用Win7已有的CreateSemaphoreW/WaitForSingleObject/ReleaseSemaphore/CloseHandle，并按与原版相同的绝对路径小写SHA命名；不持有文件或目录句柄，不做超时抢占。POSIX分支用非阻塞flock并验证inode，最多3次重开，不删除锁文件。

固定Node22.22.2的真实rc.3 Source actor与Python3.8.10 actor实际竞争同一内核对象，native/native、Source/Source及两个交叉方向分别验证正常关闭和进程终止，共 **8组通过**，包含独立Session、幂等release、大小写路径、持锁期间读文件与删除/重建目录。Python原有存储合同与双进程测试 **27 passed**。凭据见 [lease-checks.json](../../migration/candidates/rc3/lease-checks.json)，原始观察在 `.goose/out/rc3-r02-storage-lease-20261017/`。初版Node actor关闭后stdin未销毁而超时，修正后全组合通过，失败现场保留。未在此Windows主机执行POSIX分支，也未把当前Windows测试称作Win7虚拟机验收。

本轮retention已实际执行，未发现新增可回收历史产物；首次误把`--output`当结果文件参数的错误保留，随后无参数运行成功。当前空间约180GiB。内核锁继续接入新handle与代际发布，尚未切换生产writer/pin。

## R02-H：当前JSONL代际framing与扫描器

新增canonical generation文件名/路径、当前header/event编码、当前header严格形状与future/历史格式分类、增量原始UTF-8行扫描和checkpoint。scanner只读取当前v3，历史升级走catalog；未换行尾部被忽略，已提交区损坏后若出现turn/end仍拒绝，结构准入在recoverable抑制之前执行。缓冲区跨多次write复制未完成片段，复用decoder buffer不污染历史观察。

选定Source format helpers、scanLog unit、nested v3 streams及native v3 admission，65项原断言通过，128项其他provider测试未选择。捕获153个helper/扫描前缀完整观测，修正包装器对可变Buffer的持有和浮点序号错误信息后全部匹配。原始失败与修复结果均保留。Python新scanner、v3逻辑和catalog直接消费者 **2,357 passed**，凭据见 [jsonl-current-checks.json](../../migration/candidates/rc3/jsonl-current-checks.json)。部分Source断言实际经过其provider，但此处仅配对显式捕获的helper API，不冒充原生provider已通过。继续generation准备/独立验证/排他发布，活动JsonlStore与writer仍待切换。

## R02-I：不可变generation准备、验证与排他发布

新增有界两次stat/read快照、单遍历史转换、header身份/版本交叉校验、raw与Zstandard损坏尾处理、独立header frame和流式checksummed正文。prepare只产生当前artifact，publish复用同一成功或失败；独占临时文件写入/同步后，由最多两个新Python进程独立验证完整v3、已安装词汇/关系和内嵌Assistant流。重新检查历史源identity后以Win7 MoveFileExW write-through无覆盖发布；同字节竞争目标可保留后续append，不同/非规范目标明确拒绝。旧代际保持原字节，写入/关闭/验证/清理的故障保留错误身份与聚合cause，观察者取消不放弃已开始的提交。

新增125个实际文件系统/当前流验证场景与rc.3完整输出匹配；本轮同时复核共享runner的107 planner和153 scanner场景，共385场景匹配。只有两种语言JSON解析器的底层SyntaxError/JSONDecodeError文字按原生解析错误类别比较，完整原文字分别保存在两端日志；其他业务错误、cause、文件状态、调用次数和artifact严格比较。第一轮12处parser文字差异保留，不伪称逐字相同。

Python提供端、当前scanner、format和Assistant stream直接消费者 **590 passed**（14.69秒）。直接执行未修改的Source generation测试 **72 passed / 1 failed**；唯一失败是当前账户创建symlink返回EPERM，尚未到发布断言，原始XML/日志保留，不能称完整Source范围通过。额外原生故障/取消/新解释器隔离测试已通过。凭据见 [generation-checks.json](../../migration/candidates/rc3/generation-checks.json)，原始输出位于 `.goose/out/rc3-r02-generation-final-20261017/` 及前一失败目录。磁盘余量约180GiB，无Portable重建。继续生产Session、handle和query/projection闭包；当前writer/pin未切换，R02未整体签收。

## R02-J：当前v3 Session运行态

新增显式CurrentSession/CurrentSessionStore，覆盖snapshot与restore所有权、继承边界标记、当前surface增量校验、system消息投影与canonical request header。catalog当前恢复实际调用该入口；共享旧Session仅增加可重写校验/时钟接口和显式stream参数，旧活动profile默认保持。修正JSON整数以浮点表示时的数组索引和负零引用判定。

Source六个原测试文件390断言通过；捕获并回放957个独立前缀场景，与实际rc.3匹配。两项原版运行时故障mock以显式故障输入重放，原观察与首次环境差异保留。最终同时复核catalog170与current426场景；Python新运行态、catalog、v3 logical、旧Session/surface及generation直接消费者3,348项通过。只证明显式detached API/helper，不冒充store publication、生产handle或整体R02通过。证据见[session-runtime-checks.json](../../migration/candidates/rc3/session-runtime-checks.json)，原始输出`.goose/out/rc3-r02-session-runtime-final-20261017/`。下一步连接单写handle与冷读；活动pin/writer仍未切换。

## R02-K：v3存储边界与handle生命周期

实现版本方向拒绝、raw location、先词汇后adopt的存储准入，以及调用时的lossless批次快照；generation独立验证改为调用实际存储准入。新增JSONL handle和tracker：单写claim、mutation queue、primed/冷读单调前缀、首次写才取内核lease、torn修复重试、200ms live batching、失败缓冲保留、关闭排空及聚合故障。Cordis事件路由只发送给已拥有write handle的会话，卸载释放全部handle。

实际Source helper/handle通过可观察storage adapter的147场景匹配；generation125场景复核匹配。Python直接提供端、generation/current消费者及旧存储回归1,494项通过，Source未修改storage-contract18断言通过。另验证观察者取消仍提交、取消close仍排空、关闭期间迟到事件、后台失败后显式重试、两种abort时点和实际fiber卸载。原失败夹具调用与首轮差异均保留；旧SQLite清理测试产生7项既有未await告警，不声称零告警。新handle尚未连接真实backend/Agent，非整体R02签收。凭据见[storage-handles-checks.json](../../migration/candidates/rc3/storage-handles-checks.json)。按既有retention扫描无新增可删项，剩余约180GiB。

## R02-L：真实JSONL backend与冷恢复

新增显式v3 JSONL服务/plugin：create/open返回handle，stat/list只读header和opaque revision；按规范文件名选择最高代际，拒绝未来代际、相反编码、旧flat layout和错位id/cwd；read-only历史准备不落盘，write open先取实际内核lease再独立验证/排他发布v3。实现两项cold LRU、同revision共享迁移与最后waiter离开后的owner abort、shared-frozen事件所有权、raw/Zstandard尾部修复及重试。共享旧JsonlStore只复用持久文件原语，不调用旧logical codec或写入路径。

实际两端文件系统50场景匹配，包括v0/v1/v2两种编码的只读和发布、跨实例竞争、pending可见性、冷读、新代际、未知事件与身份拒绝；物理文件字节数/SHA严格一致。revision按不透明token的相等关系比较，原token写入actor日志；仅自有临时root替换，文件清单按确定性字典序输出。Source未修改JSONL spec的175断言通过；最终Python backend/handle/generation/current/catalog/scanner直接范围2,108项通过。另实测共享准备的部分/全部取消、publication期间取消仍持锁至提交、未领取handle回收、fsync失败回滚、Zstandard未完成frame内完整事件重写和实际Cordis卸载。凭据见[jsonl-backend-checks.json](../../migration/candidates/rc3/jsonl-backend-checks.json)。活动writer/Session及Agent/query消费者仍未切换，R02尚未整体签收。

## 输出与磁盘管理

开始前磁盘余量约184GB。先执行既有 `process_artifact_retention.py`，其所有权/结束状态/字节核验没有发现新增可回收项目，未删除未知输出或未解决失败。完整清理观察位于 `.goose/out/rc3-r01-20261016/history-retention.json`。

本批定向测试继续使用conftest提供的新短工作区和自动合成回执清理。日志/XML/真实Source观察保留；后续大批复制、构建或统一门禁前重新核对空间，已完成的可重建夹具按既有规则回收。禁止按目录年龄或通配符整体清空历史。

2026-10-17完成R02-A后再次执行既有retention，未发现额外符合回收条件的历史产物；空间约182GB。保留Node身份失败现场与实际成功配对，不把清理无匹配报告成已释放空间。
# R02-M：只读 handle 与会话观察

新增显式 `CurrentSessionObservationReader`，以 `stat` 的实例身份/revision 复用未发布的恢复会话；缓存只驱逐未固定项，旧 revision 的既有租约保持原切分。冷读经 handle 关闭后仅在内存补齐中断轮次；live 观察延迟生成固定前缀，并在读取或准备期间出现实时 owner 时优先实时会话。补齐 handle 的 inherited cut getter，并提供候选 Session plugin。

定向范围选择观察、真实 JSONL backend，覆盖无持久化写回、缓存更新/替换、取消、错误分类与资源释放：最终 Python 99 项通过，Source 原 observation 27 项通过。首轮夹具 API 和中间异步清理问题的诊断保留；最终无 pending task 告警。两端分别执行，不声明新增配对合同。凭据见 `migration/candidates/rc3/observation-checks.json`。生产 query/Agent 与活动 rc.1 pin 未切换，R02 和 rc.3 均未签收。

## R02-N: v3 query consumers

Candidate corpus and SQLite query services now consume list snapshots and read-only handles, retain one observation reader per service, classify the v3 system-message surface, and return current-format index headers. Exact surface/window reads include inheritedEventCount. Source compatibility checks compare logical identity without requiring equal historical format versions. Existing active services retain their provider hooks until the coordinated runtime switch.

The frozen 31 actual Source/native journeys match, including real JSONL/SQLite, historical v0/v1/v2 reads, live precedence, revision replacement, retained old observations, system-head replacement, search refresh, errors and continuation fields. Random engine UUIDs and opaque revision identities have explicit comparison rules; other values are compared. Native targeted 141 tests and original Source query/SQLite 141 tests pass separately. Initial invalid system-message fixtures are retained and excluded from evidence; the runner now refuses setup failure as a matching journey. Details and hashes: migration/candidates/rc3/query-consumers-checks.json. Agent ownership, listing/Remote consumers and the production switch remain open; this is not R02 or rc.3 acceptance.

## R02-O: Agent handle ownership

Candidate Agent lifecycle now takes the write handle before registry publication, stores constructor/setup suffixes at the commit boundary, and resumes by appending deterministic crash closers plus the restore marker through that same handle. A single teardown drains/closes before registry detach, aggregates scope/write failures and preserves a failed setup as the primary error. Abandoned create/open values close asynchronously after cancellation; configured restore falls back only on the typed persistence absence.

Selected native scope covers new lifecycle, original factory/configuration consumers, actual v3 JSONL and current query: 194 tests passed. Original Source resume suite: 44 passed and one upstream Windows-guarded POSIX unlink case skipped. These are separate runs, not a paired Agent transcript. First fixture assumed a nonexistent ctx.get('agent') service and intermediate observation waited only one loop tick; corrected to the explicit setup Agent argument and an awaited observation barrier. Diagnostics remain. migration check is structurally valid, not a parity certificate. Evidence: migration/candidates/rc3/agent-ownership-checks.json. The candidate still shares the old request machine and Inbox; R03 must replace these before any production switch. R02 and rc.3 acceptance remain open.

## R03-A: Loop-owned durable projections

Added candidate durable Inbox over the standard projection registry, including fork-inherited pending input, lossless committed insertion notifications, splice normalization and globally unique pending identities. Claim commits both queue removals before sending notifications. Added system-prompt surface decisions for capable continuing history, new series, incapable routes and clearing; exact-Session runtime context; compact attempt framing with terminal notification after durable settlement. Candidate prompt registry supports persona prefix/suffix with harness source and web text after tool instructions. Shared old registry retains its original defaults.

77 frozen actual Source/native journeys match; UUID identity relationships and fixed clock are documented comparison rules. Native targeted 342 tests pass, including original prompt/Inbox/stream consumers and explicit reentrant, rejected append and exact-subject tests. Original Source seven projection/prompt suites pass 102 tests. Initial actor surface-options, finish-fixture and private-export mistakes are preserved and excluded. Evidence: migration/candidates/rc3/loop-projections-checks.json. These components still require the candidate request driver and preset consumers; active rc.1 profile/pin remain unchanged, with no R03 or release acceptance claim.

## R03-B: Current Agent request machine

Candidate factory now publishes the current machine with Agent identity as the scope key and explicit parentAgent ownership. Waking send starts the machine immediately, including from session-start observers. Every model request is reconstructed from the v3 surface; system prompts are durable messages, request epochs contain only config/tools/default attribution, and streams settle through the compact attempt owner. Implemented maintenance reservation, latched wake/cancel convergence, route preparation, retries, immutable marked requests, exact initiator attribution and handle-backed resume. Candidate LLM runtime validates and forwards in-history capability. Shared active providers retain old defaults through narrow hooks.

29 actual Source/native machine journeys match, including raw/zstd resume with pending input, prompt capability/clearing, notification failure, cancellation, defaults, retry and unknown-tool continuation. Native selected machine/lifecycle/factory/configured/LLM scope passes 256 tests; strengthened final identity assertions pass 41 machine tests. Original Source 16 Agent suites pass 325 tests and retain one upstream Windows skip. Initial expanded regression failed the Node identity guard at 22.20.0; rerun with required 22.22.2 passed the same selected scope. Source synchronous agent/created veto was explicitly preserved; returned rejection and ordinary notification failures are contained. Diagnostic runs remain. Evidence: migration/candidates/rc3/agent-machine-checks.json. Preset/subagent consumers and Remote contexts are still open; production rc.1 runtime/pin are not switched and R03 is not signed off.


## R03-C: Persona and one-shot child consumers

Added scoped persona prefix/suffix with complete-prompt and runtime-context suppression, explicit-parent spawn/fork setup, current embedded-stream output selection, and eager one-shot result ownership. Existing preset composition remains reusable (no functional upstream preset service delta). Fixed strict JSON admission of native prompt tool wrappers and integral restored seq slicing at fork. Shared old defaults remain unchanged.

29 actual unchanged Source/native journeys match, including structured capture, refusal/cancel, completed-prefix fork and raw/zstd cold resume. Native selected scope passes 238 tests, including old one-shot/preset/prompt consumers and exact scope/disposal checks. Original Source 22 suites: 307 passed, one dangling-symlink setup failed with Windows EPERM; raw failure remains an environment gap, not a pass. Initial structured JSON and cold fork failures are preserved. Evidence: migration/candidates/rc3/agent-consumers-checks.json. Continuable activation/catalog and Remote consumers remain open; production baseline and R03 acceptance are unchanged.

## R03-D: Parent catalog and continuation units

Added parent-owned catalog facts with own-event cut, strict checkpoint/view validation and persistent 64-entry chunk rollover; adjacent-Agent attribution and runtime-owned settlement notices with UTF-16 summary bound; Activation inbox admission closes before release can reenter and memoizes one release. 53 actual Source/native unit journeys match, including invalid restore/checkpoint decisions, inherited facts, rollover, message output absence versus empty, and release rejection. Selected native 172 tests and original Source 30 tests pass. Initial native live-fork test omitted its mandatory inherited cut; corrected fixture and failure preserved. Evidence: migration/candidates/rc3/subagent-units-checks.json. These units still need the complete continuable runtime and consumers; no R03 or baseline acceptance.

## R03-E: Continuable residency and current provider seam

Added one Activation registry with shared child locks, exact ancestry admission, pre-await parent ownership holds, Agent-owned durable inbox delivery, optional agents-service binding, descriptor-after-inherited-marker reconstruction, stat-based duplicate rejection and current parent catalog commits. Natural settlement waits for idle, best-effort flushes, rechecks the same poke and log seq under the child lock, then reserves maintenance before closing delivery. Child-first release captures epoch output before handle release, reports release failure without output, notifies the parent before ownership release and publishes its terminal edge afterward. One-shot catalog failure preserves the primary error and releases the unpublished run. Host prompt delivery stays internal; adjacent-Agent messages own their attribution.

19 actual Source/native journeys match, including raw/zstd spawn/fork cold epochs, queue versus model send, interrupt/park/wake, wrong parent, duplicate and invalid depth. Selected native 169 tests pass, including deterministic flush races, pre-creation holds, catalog failure, handle release failure and scoped child-first drain. Original Source seven suites pass 270 tests. Source observer create/resume options were corrected to canonical agentOptions; both earlier 29-case machine and consumer corpora independently match again and frozen native results pass. Initial fixture API and unbounded handle-release script timing diagnostics are retained; the final test uses an explicit child stream barrier. Evidence: migration/candidates/rc3/subagent-runtime-checks.json. Listing/cache, tools, Remote and SDK consumers remain open; no production baseline or R03 acceptance switch.

## R03-F: Session-owned delegation definitions and listing cache

Added the durable model-selection projection and explicit unpublished-Session setup. Child policy inheritance reads the Session registry even when its parent has no Agent; a seeded empty history is not a fresh Session. Standing compositions immediately reconcile existing Agents, reserve reentrant installs and release scoped definitions on unload. Direct apply keeps an omitted recursion cap absent. Fixed the listing cache consumer to pass the inherited-event cut and skip inherited checkpoints for seeded children, and preserved cancellation precedence over a missing query service.

21 complete unchanged Source/native tool journeys match. Selected native 117 tests and original Source eight suites / 217 tests pass, including real continuable tool delegation, cold send, listing, actual usable cache checkpoints, standing reconciliation and unload. Early actor injection/activation mistakes and one list-result fixture assertion are preserved as diagnostics. Evidence: migration/candidates/rc3/subagent-tools-checks.json. R03 other consumers, R04 Remote and the coordinated R07 schema/pin activation remain open; production rc.1 is not switched.

## R03-G: Protected system head in compaction

Current compaction selects from the first non-system surface node, replays the derived system head exactly once in auxiliary history, omits the retired header system field and commits v3 startSeq/endSeq replacement coordinates. Tool-result pruning uses the same current coordinate contract. Shared hooks preserve active old defaults.

18 actual original selection/complete successful manual-transaction pairs match under an explicit deterministic priced-meter boundary, including empty/no system heads, retained tails and balanced tool cuts. Native 154 selected regressions pass, including a real mounted auxiliary LLM request followed by actual JSONL flush and current pruning. Original Source six suites / 146 tests pass. Initial fixture intent, duplicate adapter and incomplete durable system-message identity failures remain preserved. Evidence: migration/candidates/rc3/compaction-current-checks.json. Token-meter measurement/projections, broader error/invariant parity and goal/other consumers remain open; no complete R03 or baseline acceptance.

## R03-H: Current token measurement and durable accounting

Added embedded-stream provider-output anchors, in-history system prices, attachment occurrence pricing, v3 positional plan/commit, current usage/pressure projections and retained-surface breakdown state v4. Checkpoint parsers enforce safe integers and preserve original nested stripping rules. Exact completed-turn accounting rejects missing attempt boundaries, unsafe or contradictory totals and incomplete bucket disclosure.

7 complete actual Agent/measurement/projection journeys and 132 pure pricing/checkpoint/turn-accounting journeys match unchanged Source. Complete journeys now include actual metered compaction and cold JSONL resume. Native 240 selected regressions and original Source five suites / 119 tests pass. Initial observer plugin/signal errors and unsafe-checkpoint mismatches are retained. Evidence: migration/candidates/rc3/token-meter-current-checks.json. File pricing is covered at the pure projection boundary; mounted file admission remains R05, and turn-outline/UI integration remains open. Goal/other consumers and the production baseline switch remain open.

## R03-I: Current goal activation and pause ownership

Candidate goals now read the strict projection v6, retain the first replay failure and last valid client value, emit global activation edges only on actual changes, and publish scoped committed mutations. The current driver consumes durable Inbox properties and the pre-step signal. Host pause cancels the running turn while retaining pending input; model pause finishes its own turn, and an immediately resumed revision is fenced from the aborted old attempt. Model tools use the projection's open-turn boundary, exact live initiator and original HarnessError policy, including user-only recovery of a paused goal.

78 frozen actual Source/native contracts match, including complete Agent/tool journeys, JSONL cold resume and all three pause races. Native 280 selected tests pass. Seven unchanged original suites report 125 passed and two failures: a corrupt-append assertion without the invariant companion expects a synchronous throw while actual Source records the sticky projection failure, and the production Loader source fixture times out at its existing 30-second deadline without output. These gaps and the initial config/fixture failures remain preserved; no Source bytes or assertions were changed. Evidence: migration/candidates/rc3/goal-current-checks.json. External providers, SDK/Remote consumers, command attachments, invariant activation and coordinated production baseline remain open; this is not complete R03 or release acceptance.

The same unchanged Loader smoke separately passes in its supported built-lib mode (DSH_EXAMPLE_MODE=lib, 8.38 seconds); this diagnoses the source-mode startup boundary without replacing its failed receipt or the corrupt-append assertion.

## R03-J: ACP published subprocess ownership

Current ACP no longer treats a nonpositive PID as permission to bypass a published handle. Direct-result rejection races initialization; rollback still closes stdin, checks the managed range, escalates and preserves all failed range observations. Startup and prompt diagnostics prefer the direct provider rejection while teardown reports its own cause. Old active provider defaults remain unchanged through narrow hooks.

24 complete Source/native observations match: rejected handles with positive/nonpositive PIDs, failed bounded/unbounded range waits and aggregate identities, actual stdio peers and unattended permissions, plus actual current parent Agent/current Subagent service calls. Selected native 113 tests pass, including cancellation of a disposal waiter and real unpublished-child rollback. Unchanged original ACP suite passes 72 tests with one existing skip. The initial observer's arithmetic listener counter was replaced by identity-based tracking; raw failed observations remain. Evidence: migration/candidates/rc3/external-acp-current-checks.json. Broader subprocess managed ranges remain R09; Claude Code/Codex providers are absent from the Python host and remain a separate gap. SDK/Remote and the coordinated production baseline remain open.

R03-K follow-up corrects the earlier interpretation of two parent fixtures: they omitted cwd, so both sides rejected configuration rather than completing delegation. The independent six real-stdio observations remain valid. Explicit parent cwd and mandatory successful child-output assertions now pass in the freshly frozen 24-case corpus; updated ACP evidence binds the corrected report and the 95-test SDK/current-ACP regression. The original 113-test run and earlier observations remain historical, without retroactive parent-success attribution.

## R03-K: SDK on the current Agent runtime

The upstream SDK business source has no functional rc.1-to-rc.3 delta. Its existing Python server now has explicit qualification over actual current factories, v3 durable events and embedded streams, history-capable/incapable system updates, concurrent prompts, closed local-child Agent carriers and exclusion of external child completions. Handshake maxTokens now accepts whole-valued JSON numbers such as 1.0, matching JavaScript safe-integer admission while rejecting booleans, fractional, zero and unsafe values.

16 complete current SDK pairs and the corrected 24 ACP pairs match. Selected native 95 tests pass. Eight unchanged original SDK suites pass 131 tests, including built-scope carrier, plugin apply, transport, client timeout and disposal consumers. Initial explicit-null capability and missing-cwd fixtures are preserved and corrected transparently. Evidence: migration/candidates/rc3/sdk-current-checks.json. Remote registry/Fetch, file admission, absent Claude Code/Codex providers and the coordinated production switch remain open; no complete R03 or release acceptance is claimed.

### R04-A — 显式 Agent Remote（2026-10-17）

候选 Typert registry 去除 Context 反向身份查询，Agent host adapter 只提供 wire/resolve。审批/用户问题携带实际 scoped Agent，Gateway 投影时移除 Agent/signal，并透传 goal/activation-changed。补齐不存在 Agent 的 lookup 错误身份和消息；取消保留原始原因。实际 Source/native 12 组匹配，Python 定向162通过，原版10套件313通过。验证覆盖原 registry/dispatcher/event 直接消费者及当前 SDK/goal，未重复完整门禁。当前可用空间约179GiB；本次测试短工作区由现有收尾机制维护，原始失败/观察/XML保留。生产 pin/profile 未切换，后续继续 Connection/RPCFetch、其他 Remote 消费者。见 migration/candidates/rc3/remote-current-checks.json。

### R04-B — Connection 注册表与请求体（2026-10-17）

候选 Connection 仅依赖 credentials，WebServer 后挂载时添加 /api 与 recovery 全局注入，卸载完全回收。精确 Fetch route 在读体之前选择 buffered/streaming，流式读每次最多64KiB且不设聚合上限；实际 TCP 测过 chunked、提前响应和未完成上传。RPC 必需 payload，错误码采用 gateway/bad-request。Source/native30组一致，Python74通过、原版7套件52通过；相关原认证/服务器连接生命周期回归也通过。Python3.8 EOF内部标志用于检测未消费流的断线，防止并发读取；平台适配在代码和回执中披露。成功测试短工作区按既有规则收尾；诊断和原始观察保留。后续继续 Remote 消费者、信任/反馈以及上传文件合同，未切生产基线。

### R04-C — Session 日志反馈与 Remote（2026-10-17）

候选 sessionFeedback.record 支持空反馈和7类分类，/feedback 命令确认不再附带分享策略句。消息评价改为 feedback/message-put/delete 事实；live 修改验证 flush 参与、持久化身份和最后事件，cold 操作持有 read/write handle 并提交 feedback/committed，永不发布 Session/Agent。实际 Source/native33组匹配，最终 Python63通过，原版4套件51通过；包含真实命令/Gateway消费者、并发CAS、版本冲突/幂等、损坏payload与冷写入取消/排空。初次测试路径选择与两处新夹具缺少 source.kind 的错误记录保留，修正后的两个竞态已单独及最终集合通过。原认证/Host trust源码无功能差分，R04-B已执行其原版套件；后续仍须统一Web集成认证。旧sidecar生产provider等待切换，不将候选通过标作正式基线验收。

### R04-D — 子代理 Remote 与时区规范名（2026-10-17）

CurrentSubagent 接入 list/prompt/interruptByParent Remote，浏览器 prompt 显式 delivery=queue/steer，保留 requestId/canonicalClientTimeZone 与稳定错误/原因。12个实际旅程和610时区输入匹配；最终Python622通过、原版5套件271通过。首次扩大回归742通过/2处新断言失败：快照只有events而非messages；修正后又确认原版空闲/不存在目标的interrupt是不校验身份的接受空操作，运行中才拒绝错误父身份。相应原始失败保留，新加入运行中授权配对并完成最终复验。Python ZoneInfo不回规范别名，因此使用固定Node22.22.2/ICU78.2派生的597名称映射，原严格输入规则先于查表；这是明确Win7运行时适配，无Node依赖。磁盘约179GiB空闲，成功短测试工作区继续自动收尾，原始凭据保留。接下来优先R05附件/文件提供端，再回接session-controller，生产基线未切。

### R05-A / 2026-10-17: verbatim file storage and admission

Added the explicit candidate AttachmentStore file/prompt capability and local content-addressed files. Publication stages and fsyncs bytes, hard-links without replacement, verifies existing digests, removes staging before setting the NTFS shared read-only bit, and publishes filename-preserving aliases. Streaming writes pull incrementally; reads cap chunks at 64 KiB and verify final byte count/digest. Python executor operations finish before cancellation closes their descriptor. Windows directory durability follows the original NTFS boundary; no newer OS API or Python runtime is required.

15 frozen actual Source/native contracts match; 660 selected native tests and 37 unchanged original Source tests pass. Additional native faults exercise a cancelled in-flight disk write and failed alias publication. This is targeted provider completion only: current image publication/projection, LLM file handles, SessionController carriers and production activation remain open. Raw receipts are preserved; owned temporary read-only names are released only inside the actor root, successful short pytest workspaces auto-prune, and free disk remains about 179 GiB. Evidence: migration/candidates/rc3/attachment-files-current-checks.json.

### R05-B / 2026-10-17: LLM file handles and live metering

Current LLM direct calls and prepared Agent dispatches now project files recursively into the original deterministic read-only handle text at the final adapter boundary, after middleware and before text-only image conversion. Attachment path errors degrade that occurrence to a no-path handle; filesystem mapping errors remain terminal provider failures. Unchanged messages retain identity, changed frozen requests stay frozen, and both dispatch and fileRequestText resolve the current execution-world mapping on each call.

20 original/native current pairs match; 329 selected native tests and 113 unchanged original Source tests pass. An actual current Agent consumes a real local upload, retains its durable file block, dispatches only text, and the mounted meter reprices the same unchanged log after a path mapping change. The first broad targeted run used default Node22.20.0 and the old-pin identity checker rejected it (188 passed/141 fixture errors); preserved diagnostics and a fresh full selected run under fixed22.22.2 document the correction. Free space stays about179GiB; successful short fixtures auto-prune. SessionController file receipts/carriers, image concurrency and coordinated activation are still open. Evidence: migration/candidates/rc3/llm-files-current-checks.json.

### R05-C / 2026-10-17: staged upload receipts and mixed command inputs

Added the candidate fileUploads Remote/storage service and POST /api/session/uploadFileBinary streaming Fetch contribution. Receipts belong to the exact Session and Agent scope; binding guards restore prior prompt ownership on failure, successful user-history observations retire bindings, disposed Sessions release receipts, and a cold Agent resolver is uniquely registered/disposed. Commands now have a separate current runtime using input.attachments and resolve all staged file receipts before image writes, preserving mixed/repeated occurrence order. Shared command hooks preserve the active old descriptor/admission behavior.

13 actual current Source/native pairs match;132 selected native tests and80 unchanged original Source tests pass. The first TCP test exposed missing Fetch URL on the Python carrier (98passed/1failed); the bridge now constructs URL from raw request against the same internal base as Source. Fresh expanded tests cover a2MiB chunked upload with8-byte buffered limit, exact immutable readback, route/resolver unload, and Agent disposal during storage. Original failure remains preserved. Successful short fixtures auto-prune; free disk remains about179GiB. SessionController prompt/queue binding ownership, image request concurrency and coordinated activation remain open. Evidence: migration/candidates/rc3/file-upload-current-checks.json.

### R05-D / 2026-10-17: asynchronous image lifecycle and consumers

The candidate local image capability now shares instance-owned compression slots across admission and request projection, publishes prepared batches only after all preparation succeeds, and uses verified immutable read-only objects. Request derivation deduplicates active generations, preserves remaining waiters when one aborts, and replaces an abandoned generation without old completion deleting the replacement. Non-Error native failures retain their cause. Python3.8 semaphore creation is delayed until the first asynchronous call; cancelled executor work retains its slot until the worker finishes. Pi and actual DeepSeek requests prefer this async capability.

11 frozen actual Source/native pairs match,88 selected native tests and35 unchanged Source tests pass; a separately added actual DeepSeek upload consumer passes one test. Initial Source teardown fixture failure and native84passed/4construction errors remain preserved. Win7 Pillow keeps its distinct encoder cache identity; exact pass-through bytes are paired, transformed Sharp/Pillow bytes are not claimed identical. Native decode/dimensions/alpha/sRGB/cache-repair checks cover the supported codec boundary. About179GiB remains free and successful short fixtures auto-prune. SessionController ownership and coordinated production activation remain open. Evidence: migration/candidates/rc3/attachment-images-current-checks.json.

### R05-E / 2026-10-17: execution-world file media

Added the candidate authenticated GET/HEAD /api/file contribution with the original attachment byte cap, opaque composed-FS resolution, stable MIME lookup by displayPath, private/no-store/nosniff/CSP response protections, and original FsError status mapping. All1239 MIME extension mappings are frozen from the pinned mime-types dependency instead of the host registry. The shared carrier now supports bodyless HEAD without replacing its representation length, and emits only one Content-Length.

34 frozen actual pairs and95 selected native tests pass. Real TCP covers HEAD/GET/range/oversize/auth-before-FS/unload; actual FS covers post-stat growth and abort. Unchanged original media suite reports20passed/1failed/1skipped: Windows file-symlink creation returns EPERM; the original FIFO test skips on Windows. Diagnostics remain and no full original-suite pass is claimed. Initial signal identity observation was corrected to compare the Fetch request clone rather than its controller. Successful short test outputs auto-prune and free space remains about179GiB. SessionController prompt/queue receipt ownership and production activation remain open. Evidence: migration/candidates/rc3/session-media-current-checks.json.
