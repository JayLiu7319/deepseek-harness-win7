# rc.3 分阶段实施记录

本记录推进 [rc.3实施路径](2026-10-16-rc3-baseline-implementation-assessment.md)。2026-10-17 R07-F 已协调切换活动 pin 至 rc.3；此前各节保留当时状态。候选发现或单项定向通过不构成 rc.3 发行资格。Desktop 继续按指定 Electron22 与 Standard/AIO 方案。

## R07-F：正式组合与目标代际切换（2026-10-17）

正式注册表切换 52 个当前绑定，reference/活动目标推进到 a4c74a91；导入 307 份 manifests、bundle/preset 与严格 Typert host 描述符，三份明确产品 overlay 保留双工具 Minimal。234 份原版 browser 资源按官方构建 SHA 导入并保存独立输入载体，未修改 React/TSX/CSS。四预设 Minimal/Standard/PTC/Cordis 的真实 run_profile 对话及跨会话引用定向通过；输入哈希前后核验，156 entries/129 active、53 client rows 仅是此组合观察。版本为 0.1.5-rc.3，未宣称发行合格。

旧 rc.1 的合同/映射显式标记历史，87 个任务与 1,216 份证据字节不变；原记录 ZIP 和完整成员 SHA 保留，旧资格只关联原候选。当前矩阵重新生成 297 manifests 和原版测试索引，新任务仍 ready、accepted_upstream 为 null，原九项例外进入待重新实测状态。原生产启动范围 133 通过/3 失败，修复 Minimal 产品 roster、persona section 与旧 reference 前端来源后 51 项定向通过；旧用户 persona/text 在 profile 加载与 live reload 边界转换，新键优先且文件不改写，10 项直接消费者通过。初轮 scoped persona 测试误挂 root 触发重复 section，保留诊断并在真实 agent scope 验证。migration check 通过不代表 parity 验收。

运行时与前端替换前的逐字节备份保留，成功短 pytest 工作区由既有机制清理。真实现代/108 浏览器、默认全部消费者、Optional providers、平台、Portable/Desktop 与单次统一资格继续推进；浏览器首轮 Host 回滚超时独立保留，不回填为通过。

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

### R05-F / 2026-10-17: Session prompt and queue ownership

Candidate Session prompt/queue/attachment commands now deduplicate requestIds before route/receipt checks, canonicalize zones, resolve files before image admission, recheck exact Agent identity and commit binding only after delivery. Remove retires receipts, steer retains ownership, edits remain frozen text, continuable child queue access requires its own descriptor. Image authorization reads compact v3 Assistant streams.

23 actual paired journeys,13upload regression pairs,103 selected native tests and29 original Source tests pass. An actual Agent proves file user-history consumption retires the receipt and retry does not call the model again; disposal during admission cannot deliver or bind. Pair actors use real Session/Inbox/files/uploads with controlled dispatch. Initial malformed-image fixture and102passed/1disposed-projection observation failure are preserved. Existing retention audit found no eligible completed copies; successful short fixtures auto-prune and about179GiB remains free. Full activation/model selection/create/fork/list/history/control and production switch remain open. Evidence: migration/candidates/rc3/session-commands-current-checks.json.

### R04-E / 2026-10-17: Session activation and durable selection

Candidate API Agent activation uses explicit Agent setup, shares in-flight create/resume operations, checks cwd/preset/child ownership after race recovery, and restores model intent from the projected v3 log. Borrowed observations remain caller-owned; owned reads dispose on all outcomes. Image admission serializes without poisoning later work.

26 actual Source/native pairs,97 selected native tests and16 unchanged Source tests pass. Actual Agent factory/persistence/query tests cover one creation across six callers, explicit preset setup, cold pending-selection restoration and model dispatch, unpublished inspection, and a cancelled waiter leaving shared creation alive. Initial actor path/cwd fixture errors and nonexistent test-file selection are retained. Successful short workspaces auto-prune; no Portable copies were created. Full SessionController and production activation remain open. Evidence: migration/candidates/rc3/session-agents-current-checks.json.

### R04-F / 2026-10-17: Session identity and fork commands

Current create/adopt maps exact directory/preset/child conflicts and reports workspace attachment failures without losing the created identity. Model changes share image-admission serialization, preserve Remote failures and remain accepted when saving defaults fails. Titles use a typed invalid-title error. Fork observes without activating the source, selects a completed-turn boundary, retains following metadata before the next turn, and resolves subagent workspace lineage. Cold attachment errors now follow the same original inspection mapping.

32 current command pairs plus26 activation and23 prompt regression pairs match;102 selected native tests and21 unchanged Source tests pass. Actual Agent dispatch and persisted v3 child read verify inherited prefix/title/model and independent ordinary-child ownership. Two initial test failures used retired persistence inspection and object-style raw-header access; corrected current-handle observations pass, originals retained. Successful short fixtures auto-prune and about179GiB remains free. List/search/history/control and full production activation stay open. Evidence: migration/candidates/rc3/session-identity-commands-current-checks.json.

### R04-G / 2026-10-17: list/search and format-bound cache

Current listing never probes cold logs: it uses cached whole values or matching predecessor-title hints at watermark -1. Cache domain v7 admits structurally compatible v3-v6 records, but hydration requires exact format generation/lifecycle. Search validates the original UTF-16 query bound, authorizes current message hits, shrinks unsupported page limits, restarts stale cursors and enforces duplicate-cursor, output and100-call bounds.

35 current pairs,141 selected native tests and60 unchanged Source tests pass. Actual v6 cache/list/query, v7 durable reopen and SQLite consumers verify zero handle opens during listing, no activation, strict replay from real v3 events, and persistent format identity. Initial132passed/1new fixture surfaceOp failure remains preserved; corrected append passes. The work-budget fixture was changed from an early invalid-limit rejection to exactly100 cursor/restart calls with asserted budget error. Successful short outputs auto-prune; disk remains about179GiB free. Current history/control and full production activation remain open. Evidence: migration/candidates/rc3/session-list-current-checks.json.

### R04-H / 2026-10-17: raw v3 history, Assistant reconnect and control

Current history sends only logical event records and the complete v3 header, with exact address/page validation. Opted-in Assistant frames retain FIFO order and reconnect baselines with revision/index continuity and new-lifecycle resets. Prepared observations promote only after snapshot delivery, replay constructor suffixes without gaps and release retained reads on failure. Control now observes durable Inbox projection changes, publishes projection before full queue replacement and drains accepted frames on unload.

38 actual current pairs,171 selected native tests and37 unchanged Source tests pass. Real Agent/query integration verifies mid-stream reconnect, compact final message, dense committed journal, cold promotion/end-seed suffix and follower unload while Agent remains attached. Initial null-cwd fixture mismatch and161passed/10wire-observation comparison failures are retained: frozen Python runtime containers are now explicitly serialized as JSON before strict comparison, matching the Source actor boundary; actual Agent integrations already passed. Successful short outputs auto-prune and about179GiB remains free. Full Remote assembly and production activation remain open. Evidence: migration/candidates/rc3/session-history-current-checks.json.

### R09-A / 2026-10-17: shell-free desktop path intents

67 actual current Source/native path-intent pairs,111 selected native tests and44 unchanged Source tests pass. Windows/WSL quoting, browser/editor intent, Explorer URI with commas and Unicode UNC authority, and exact numeric exit-1 delegation follow Source. Real Python children verify UTF-8/literal argv, failed status, abort and process reaping; OS runtime error objects remain explicit Python adaptations. Initial eight URI differences are retained and corrected. No Portable built; successful short fixtures auto-prune and about179GiB remains free. Full desktop packaging/managed-range acceptance and production activation remain open. Evidence: migration/candidates/rc3/native-path-current-checks.json.

### R04-I / 2026-10-17: complete current Session Remote

Complete candidate Session Controller now composes explicit activation, commands, list/search, raw history/control and optional media/file/skill services. It owns one reversible upload Agent resolver and forwards lifecycle/status/error/activity. Background observation ownership releases on success/domain failure/throw/dispose failure; followers close before admitted activation drains. Cold skill listing uses the projected preset without Agent activation; live skill scope is the exact Agent. Model catalog isolates provider failures.

31 actual pairs,129 selected native tests and39 unchanged Source tests pass. Real full Agent/persistence/upload consumers verify selection consumption, file receipt retirement, history/control and caller-fiber disposal while independent Agents survive. Actor startup/Inbox and new test config/request/envelope/ownership assertion errors remain preserved with corrected final qualification. Successful short fixtures auto-prune; no Portable built and about179GiB remains free. Generated descriptors, canonical activation, workspace/sidebar, missing providers and release acceptance remain open. Evidence: migration/candidates/rc3/session-facade-current-checks.json.

### R06-A / 2026-10-17: bounded raw FS byte windows

Added readByteRange inherited by sandbox FS: regular-file gate even for zero length, seek over prefix, at most64KiB chunks and requested bytes, binary pass-through, EOF and cancellation descriptor cleanup.27 actual current pairs and29 new-provider tests pass, including an8-byte read beyond a256MiB prefix.

Expanded native consumers twice report136passed/1existing ReplaceFileW1175 failure/4skips on different atomic overwrites; one isolated case passes, but cause remains open and no successful whole consumer run is claimed. Original Source reports82passed/5Windows EPERM symlink failures, including passing new range cases. No retry/ignore/publication fallback added. Two completed reproducible large fixture files (536870928bytes total) were removed only after XML/ownership/hash verification; failed replacement data remains. New test finalizer bounds future output. Evidence: migration/candidates/rc3/fs-range-current-checks.json. WorkspaceFiles/tools/current profile and overall acceptance remain open.

### R06-B / 2026-10-17: workspaceFiles preview and observation Remote

Candidate workspaceFiles implements stat/list/read/readBytes/readAll/readRelated/changes and reversible header-only workspaceFileScope lookup. File reads follow composed-FS access outside the Session cwd; directories and observation generations remain workspace-contained. Text streaming stops after a page and releases its iterator; byte/full-file caps reject instead of truncating. Related resources use original POSIX/Windows resolution and Unicode scheme matching. Changes register before root resolve, yield ready before queued FIFO observations, isolate reconnect generations and remove abort listeners on return.

95 actual pairs and190 selected native tests pass, including actual parent/child/cold v3 Session and sandbox FS, outside file/related CSS access, directory containment, byte reads, growth caps and slow-root abort/unload. Original Source seven suites report93passed/6EPERM symlink setup failures; no whole Source success claimed. Initial service config-field collision was fixed with dedicated caps; actor lookup and test newline/reserved filename/policy/durability fixture errors remain retained. Successful short fixture cleanup continues, no Portable built and about179GiB free. Browser resources/sidebar, present/tool deltas, current descriptors/composition and overall acceptance remain open. Evidence: migration/candidates/rc3/workspace-files-current-checks.json.

### R06-C — 显式文件交付

新增候选 `CurrentToolPresent`，通过 Session cwd 与组合 FS 验证既有常规文件；不读文件内容、不复制附件。使用实际 execution 弱身份，只在最终成功工具结果后写入所属 Session 的 `deliverables/presented`；后置拦截、作用域覆盖、重复挂载与取消不产生误报。33 组实际原版配对、186 项定向原生测试通过，包含真实二进制文件、独立父子 Agent 和冷持久化读取。原版10项测试中8通过、2因Windows符号链接EPERM失败，原始诊断保留。初轮作用域/schema及真实FS测试夹具错误均已修正；见候选回执 `migration/candidates/rc3/present-current-checks.json`。原版文件打开接口、客户端组装、生产pin及完整门禁仍待完成。

### R06-D — 文件工具增量

新增候选 `CurrentToolFs` / `CurrentToolFsSearch`，复用既有实现并选择rc.3增量。read/write/edit/glob/grep提示随scope工具可见性变化；write和grep不推荐不可见的edit/read；未读修改错误统一携带实际displayPath并保留cause/code；read_image仅提供path展示元数据；搜索区分launch与provider完成失败，spill标记kind=tool/label=result。实际46组配对涵盖32个可见工具子集、执行失败/成功spill与图片内容替换；129项原生、273项原版通过，各有1项既有跳过。真实Agent/FS观察守卫、读取/创建及限制释放已验证。详情见 `migration/candidates/rc3/file-tools-current-checks.json`；单独保留的Win32 1175问题不由本轮通过关闭。后续接入交付文件原生打开、Sidebar、生产组装与浏览器验收。

### R06-E — 交付文件原生打开

新增候选客户端宿主，提供Connection鉴权内 `/api/present.host` 和 `/api/present.open`。动作只能由Session交付事件坐标授权，按被查看Session的cwd校验当前常规文件，反向映射并重新resolve核验Host路径后才调用open/reveal；不接受请求中的文件路径，不激活Agent、不复制/下载文件。调用绑定请求和插件寿命取消；卸载先移除路由、取消并等待已接纳的原生操作，结束即释放订阅。52组实际原版配对、269项原生测试通过，包含真实TCP鉴权、持久化继承声明在冷子会话目录中打开当前源文件、取消/等待/重试；同时修复配对发现的current Connection默认404文本类型头。原版两套测试29通过、1符号链接EPERM失败。回执 `migration/candidates/rc3/present-open-current-checks.json` 保留诊断；Sidebar、生成描述符、生产组装及浏览器/打包验收仍待完成。

### R06-F — 工作区快照与路径

候选工作区注册器从persistence snapshot提取header，接通bootstrap、懒刷新、archive及冷domain重开；不打开事件正文。完整路径准入在realpath前拒绝相对路径、Windows当前驱动相对路径，根目录默认标题保留根拼写。110组原版配对（105跨平台路径事实、5个真实domain/registry旅程）和222项原生测试通过；原版51通过、2符号链接EPERM失败。实际当前Agent/持久化冷会话的启动索引、后到会话归属/归档刷新、存储重开和根目录标题已验证。原版资源、Dockkit、右Sidebar、文件树、文档预览的host入口均为空函数，其浏览器部分保留R08原样导入；不新增Python替代浏览器实现。详情见 `migration/candidates/rc3/workspace-current-checks.json`。当前生产基线和全量验收尚未推进。

### R09-B — 外部应用解析与独立启动

原样导出rc.3应用目录，按平台核验bundle、PATH、文件、版本目录、注册表及XDG入口；一次解析共享懒注册表，SSH不探测，版本名复用固定ICU数字排序。启动器传递字面argv、过滤继承凭据并叠加显式adapter环境；只观察早期失败，真实子进程在宿主退出后继续运行。100组实际配对、192项原生和38项原版测试通过，包含真实目录、独立父子进程、超时信号、fallback/ENOENT。初轮记录器路径归一化和测试命令错误保留。详见 `migration/candidates/rc3/open-in-app-resolver-current-checks.json`；鉴权路由、图标、生产组装和Desktop资格仍待完成。成功短测试夹具自动清理，磁盘约179GiB可用。

### R09-C — 外部应用鉴权路由与图标

三个WebServer路由先经过Connection Host/Origin与浏览器鉴权，再读取正文或解析应用；严格校验方法、JSON类型/64KiB上限、可用应用及实际目录。共享懒解析、缓存正/空图标，ENOENT只刷新当前项一次并清除图标缓存。SSH只取继承process层；图标按原版macOS、Windows PowerShell -File、Linux XDG策略提取，临时文件及时释放。80组配对、321项原生和25项原版测试通过；真实TCP覆盖未读大正文鉴权、chunked成功、超限可读拒绝和卸载，Windows实际System.Drawing生成PNG后清理通过。初轮刷新场景提前拒绝和WebServer测试夹具错误保留，最终正旅程有显式断言。回执 `migration/candidates/rc3/open-in-app-host-current-checks.json`；生产组装、原版浏览器和Desktop资格未签收。

### R09-D — MCP分页循环与代际保留

候选MCP provider对tools/list重复cursor立即拒绝；当前页重复工具优先报错，fetch失败不处置上一代注册。15组配对、115项原生和107项原版测试通过。实际当前插件通知循环后旧工具仍能调用，后续合法通知正常换代；真实stdio服务重复cursor只被请求两次，错误不挂起并回收进程。现有HTTP、图片、ACP创建/撤销消费者同时通过。初轮actor依赖/输出/service及配置夹具错误保留；回执 `migration/candidates/rc3/mcp-current-checks.json`。生产映射和统一验收仍待完成。

### R07-A — 显式初始化自定义profile

启动器新增 --from-default-profile，仅从发布模板复制bundle列表与reload策略；独占创建目录，拒绝已有manifest或残留目录，不复制本地依赖和用户patch。失败只清理本次独占目录，清理失败保留两项错误。desktop保留为应用管理profile，独立loadProfileDirectory供应用加载。47组实际配对、67项原生和22项原版测试通过，覆盖两个真实进程竞争、启动/配置导出及参数边界。配对将模板表限定为原版五项以比较准确诊断，产品八项模板另行实测，不冒充原版增加了三预设。初轮启动测试遗漏waitForExit=False导致中断，原日志保留且不推断计数；修正后设置明确期限通过。回执 migration/candidates/rc3/profile-init-current-checks.json。生产组装、其余启动增量、pin推进和统一验收仍待完成。

### R07-B — home代理准入与patch路径

仅解析后的Harness-home .env允许四类代理变量，项目层拒绝并指出home文件；CA/TLS及其他bootstrap名称仍拒绝，两层均先验证再写环境。启动快照复用Windows大小写折叠并复制原始层，保留既有dict接口。patch仅将insert及嵌套group中的绝对/相对文件路径转为file URL，断言名称不变。37组配对、199项原生和76项原版通过，包含真实带空格/#/%/中文路径的插件装载、凭据Web重启、LLM配置及普通启动。初轮actor将Node原生环境替成普通对象造成大小写差异；改为操作并恢复真实环境后匹配，原诊断保留。回执 migration/candidates/rc3/boot-layers-current-checks.json。代理传输、生产组合和完整资格仍待完成。

### R07-C1 — 出站代理策略

候选纯策略按原版处理大小写/空白优先级、ALL_PROXY和HTTPS单向回退；显式被拒绝的协议槽保持直连，不借用另一协议。保留诊断及NO_PROXY条目顺序，覆盖端口/后缀、loopback全范围、IPv4映射和URL数字地址形式。129组实际配对、169项原生和65项原版通过，原版matcher使用真实undici观察。回执 migration/candidates/rc3/http-proxy-policy-current-checks.json；当前仅纯策略，不计进程安装、原生传输/TLS/取消、子进程或生产组装资格。

### R07-C2 — 代理安装、真实传输与子进程

从启动快照在首个插件前安装策略，嵌套/临时直连/失败启动/正常shutdown恢复原策略、opener与环境。urllib普通调用、独立acquisition opener、LLM/MCP流、OTel requests消费者复用matcher；HTTP绝对URI转发、HTTPS CONNECT及HTTPS代理内TLS保留逐跳证书验证与凭据分隔。子进程恢复用户原配置，对未声明协议补解析结果并保持loopback绕过；不支持的SOCKS留给其他工具并不添加会导致Node启动失败的flag。Windows IPv6拒绝可能迟到，流式连接250ms后并行尝试下一地址、关闭败选socket。64组实际配对、231项原生通过，包含12种真实路由、证书拒绝、隧道TLS取消、LLM文本、实际子进程及启动/失败恢复。原版安装24通过，子进程套件7通过/1Windows大小写独立性断言失败，未改原版或声称全套通过。初轮120s中断及地址/短期限夹具/文本delta断言失败分别保留。回执 migration/candidates/rc3/http-proxy-install-current-checks.json。成功短夹具自动清理，约179.08GiB可用；生产当前组合、原版浏览器/Desktop和统一资格仍待完成。

### R03-L — 嵌入流 Session 统计

候选统计消费者改用assistant/attempt和最终assistant/message的嵌入流，保留重试首token，取消步骤按step/end计数；精确处理outputTokens、小数、空/prototype工具ID及持久化状态/视图边界。67组实际配对、224项原生和44项未改原版测试通过。真实Agent写入JSONL后冷重放、步骤中间checkpoint续算及卸载重挂已验证，并修复磁盘合法整数以float解码时投影range/slice失败；先验证整数域再转换索引。初轮测试DTO错误和实际数值故障记录保留，成功短夹具自动清理。回执`migration/candidates/rc3/session-stats-current-checks.json`；尚未切换生产pin或完成统一发布验收。

### R03-M — 反馈授权遥测

候选OTel默认FEEDBACK_ONLY、拒绝FULL，直接服务emit不上传；仅新提交的本会话canonical反馈授权对应前缀，支持消息反馈及冷会话committed检查，fork继承和伪造bus事件不构成授权。独立协调器对齐live/on-demand、完整历史、游标接续、逐事件脱敏/后端失败、flush与关闭记录；卸载同步执行首个await前的脱敏前缀。72组原版配对、116项原生和74项原版测试通过，真实SDK接收端确认冷历史发送、不激活冷会话、no-op不重发及rc.3资源版本。Python既有protobuf/Source JSON OTLP为SDK适配差异。诊断与回执`migration/candidates/rc3/telemetry-current-checks.json`保留，成功短夹具已自动清理；生产组合和统一发布签收未完成。

### R03-N — 按格式代际增量上传

DeepSeek日志上传候选按Session格式过滤接受水位，缺失版本视为v0，旧格式错误水位不污染v3进度；wire保留格式版本、seedLength、surface/provenance及未知ignorable元数据。41组原版配对、100项原生和44项原版测试通过。真实当前Agent两次HTTP请求验证2xx接受回调、精确suffix和JSONL冷恢复游标；seeded header/system替换修正夹具后有明确成功断言，未将配对拒绝冒充成功。回执`migration/candidates/rc3/session-log-current-checks.json`保留诊断，上传仍为opt-in、默认关闭；生产组装和统一资格尚待完成。成功短夹具自动清理，约179GiB磁盘可用。

### R07-D — Headless实时帧消费者

候选headless从agent/assistant-stream读取本Agent的reasoning，start/end和非reasoning块关闭行，重试重新开启标题；最终非空回答/退出状态只取运行区间持久日志，缺失序号拒绝。28组实际原版runner配对、43项原生和19项原版测试通过，包含真实当前Agent完成/取消、v3 JSONL在退出前flush及监听释放。公共hook重构后的既有HTTP编辑器/重试/startup回归通过，不能据此声称rc.3生产启动已验收。Python appReady为现有启动适配；回执`migration/candidates/rc3/headless-current-checks.json`保留初轮夹具/取消枚举诊断，成功短夹具自动清理。

### R04-J — 当前逻辑日志导出

组合验证发现旧导出仍依赖raw artifact，已新增通过只读handle重建canonical v3 JSONL的候选实现；仅不存在返回404，读取失败关闭handle且不泄漏宿主路径。后代按深度顺序flush/读取，图片及通用文件跨日志去重，嵌入式assistant流中的附件也进入ZIP。27组原版配对、112项原生和45项未改原版测试通过，包含真实Agent的live/cold日志及附件ZIP内容、GET/HEAD、卸载和取消/关闭消费者后的资源释放。ZIP压缩器保留Python标准库适配，不能比较压缩字节身份。回执`migration/candidates/rc3/log-export-current-checks.json`；生产pin尚未切换，继续组合验证。成功短夹具自动清理，失败诊断保留。

### R03-O — 工作区指令与提交边界

候选指令插件迁移到当前 Inbox、fs provider 和步骤投影；基线身份使用原版数字序列化，空候选数组保留，逐文件 UTF-8 上限在流中执行。同目录不可用候选回滚整组观察，不用暂时读取失败撤销已授权指令。40 组原版配对、47 项原生通过，包含真实当前 Agent 读取嵌套文件后在 step/end 之后发布指令、再次修改、卸载及冷 v3 日志。原版套件 151 通过、3 项符号链接创建 EPERM、1 跳过，诊断完整保留；初轮 schema 测试误把结果对象当异常已修正。Win7 Minimal 编辑器作为明确保留工具参与文件触达。回执 `migration/candidates/rc3/instructions-current-checks.json`；生产映射、前端 pin 和统一资格仍未签收。成功短夹具自动清理。

### R03-P — 会话引用预算与完整快照

候选引用按已组装模型路由和上下文容量自动分配预算，保留64KiB下限；显式预算跳过模型查询，只有缺adapter可降级，其他元数据错误继续拒绝。截断预览附带准确遗漏量及完整不可信投影的spill位置或明确不可用原因；捕获格式代际写入持久上下文，转录每行至多64个Unicode码点。36组实际原版配对、101项原生和48项原版测试通过；真实当前Agent引用冷v3会话、读取完整spill及迟到metadata/read/spill取消均验证。组合旅程暴露的LLM resolveModelInfo公共接口缺口已补齐，初轮配置覆盖及测试路径诊断保留。回执 `migration/candidates/rc3/session-reference-current-checks.json`；生产pin和完整发行签收仍待完成。

### R08-A — 原版浏览器发现的默认模型目录缺口

原版 Models 设置页暴露生产 DeepSeek provider 缺失 `deepseek-flash`，其图片输入和 `systemPromptUpdate: in-history` 能力也未进入 prepared call。现补齐原版默认目录、配置 schema 与 adapter 元数据；非法显式能力值继续拒绝。未修改 rc.3 Source 的默认/自定义 provider 与 Python 实际服务比较，两个目录、7 次解析和 7 次 prepared call 完全一致；模型配置、图片/文件消费者及浏览器能力相关定向共144项通过。初轮误选历史 rc.1 capture observer 的60通过/118 setup错误单独保留，不计为通过。见 [有限回执](../../migration/candidates/rc3/deepseek-default-catalog-checks.json)。浏览器模型设置保存/冷恢复、Desktop 和统一发行资格继续实施；成功短测试夹具自动清理，未构建 Portable。

### R08-B — 无投影基线的历史分页

长历史原版浏览器调用 `/api/session/page` 时，`projectionMode=none` 有意省略投影，却被 Python observation 的属性读取转成 KeyError；现将可选 projections 属性映射为 None，不额外计算投影。真实 Agent 的 live/cold 分页保持相同连续日志，冷分页不激活会话；历史、观察租约和激活直接消费者100项通过。见 [有限回执](../../migration/candidates/rc3/history-page-baseline-checks.json)。原浏览器失败载荷保留，完整浏览器组合与发行验收继续实施。

### R08-C — 原版页面与 Chromium108 能力适配

现代浏览器和 Chromium108 的 Source/Python 四条 Minimal fresh/cold 组合旅程均通过。原版前端字节不变；108 Source 明确加载相同 Host 能力适配，区别于未适配原版。按能力缺口注入 URL 非特殊协议完整解析器和现代方法，并将同一能力前缀仅复制到具名 PDF/upload Blob worker，保留原脚本字节、立即撤销时序和可逆所有权；core-js3.49.0/esbuild0.25.12 的157输入可确定重建，86项适配/门禁定向通过。

真实页面覆盖140轮冷历史翻页跳转、Unicode引号路径引用、Markdown/Code/Plaintext切换、12000行有界文本、HTML隔离及相邻JS/CSS、图片、PDF红蓝像素、全屏/折叠/双Dockkit面板、反馈增删、不可变附件和实际下一模型请求，以及 Models Apply 后热目录更新和冷启动保留。worker结束后计数归零且无错误。原版PDF现代API异常、夹具嵌入流/重复调用ID及观察器错误均保留诊断。原始36个报告/Host观察/截图封装为12.5MB并逐成员核验；成功浏览器profile在进程退出后自动清理。见 [有限回执](../../migration/candidates/rc3/browser-capabilities-current-checks.json)。Standard/Creative当前垫片回归、余下交付/重连/浮窗、Desktop与统一资格继续实施，未构建Portable。

### R10-A — Desktop v3 字节协议

按指定桌面方案开始 Electron22 适配；先实现13字节大端帧头、64KiB数据块和1MiB控制消息。83组未修改rc.3 Shell/Host实际编解码观察匹配，原生98项测试通过，包含碎片/交错/截断/取消/大小与字段拒绝；13个完整响应编码与原版逐字节一致。JSON语法错误的Python/V8解析器诊断显式不同，其他协议错误严格比较。见 [有限回执](../../migration/candidates/rc3/desktop-wire-current-checks.json)。实际进程、Electron窗口、Standard/AIO和统一资格仍在实施；未构建Portable，成功短夹具自动清理。

### R09-E — Python 插件 ABI 版本下限

生产版本带 `-rc.3` 后，既有插件安装器将整个版本按点分割转整数，导致本地插件验证被阻断。现在只用三段数字核心比较既有 ABI 下限，发行身份仍保留预发布和构建元数据。安装、升级/回滚及依赖消费者107项通过；新增4项最初错误索引 descriptor 元组，修正后单独4项通过，初轮失败留存。见 [有限回执](../../migration/candidates/rc3/python-abi-version-current-checks.json)。不据此声明完整回归或发布验收。

### R08-D — Standard / Creative 的 Chromium 108 旅程

四条实际原版界面旅程（Python/Source × Standard/Cordis）均通过 fresh/cold 阶段，覆盖工具、提问、审批、计划、取消及运行时 Cordis 管理。未改 Source 108 显式使用同一宿主能力适配，不声称裸原版可直接运行。12份有限报告与原始宿主观察归档35,945,813字节，逐成员核验CRC和SHA；不复制浏览器配置、运行目录或调试树。见 [有限回执](../../migration/candidates/rc3/browser-standard-cordis-108-checks.json)。交付文件、浮窗及完整发行验收仍在实施。

### R10-B — Electron 22 / Python 3.8 实际桌面宿主

实现无HTTP监听的canonical Desktop组合、二进制stdio载体及独立Electron窗口，复用原版transport、codec、locale和管理页，提供可复现输入构建与SHA清单。管理页沿用本项目本地Python插件ABI，服务时改路径提示，不将npm ABI冒充可用。健康事务在影子配置生成旧/新清单后发布，实际Host就绪才提交；失败和中断恢复旧文件，外部修改保留现场。升级保留canonical历史，设置和会话不参与快照。

实际Electron22.3.27/Chromium108.0.5359.215验证原版主页面、管理IPC、设置RPC、持续流取消、安装、损坏升级的自动回退、移除及重连baseline。两个窗口均保持sandbox/contextIsolation/webSecurity并关闭Node。切换Host期间3条预期control stream网络错误原样保留，稳定阶段零错误。首次慢失败定位为逐UI卸载反复生成大型source map，已复用相同activation revision的不可变产物；后续收到真实import拒绝而非就绪超时。41项组合/消费者、48项事务/重建/HMR定向检查通过。实际内置Node16另验证9项管道行为，包括2MiB上传、12路交错HEAD、取消、无悬挂请求、强制清理venv子进程树后重新取得配置锁和EOF正常退出。见 [有限回执](../../migration/candidates/rc3/desktop-carrier-current-checks.json)。安装包、更新集成、x86及物理Win7资格继续实施；成功短夹具自动清理，失败观察留存，未运行统一发行门禁。

### R10-B.1 — 桌面宿主生命周期补查

ClientModules始终以inject子上下文绑定WebServer，覆盖提供端先装载、卸载及重新挂载，避免初始直接注册遗留在旧服务。Desktop的DSH_HOME按空白和波浪号展开；插件事务超时/诊断溢出也清理Windows重定向器的实际Python子进程树。17项真实运行时、提供端生命周期及事务测试通过，另验证5种home解析输入。原始XML保存在`.goose/out/rc3-desktop-provider-lifetime-20261017/results.xml`。安装包仍待资格验证。

### R10-C — 官方离线前置组件

按用户授权从微软下载9个固定输入：x86/x64的SSU、SHA-2、D3DCompiler47、WMF5.1，以及共用.NET4.7.2安装器。二进制保存在仓库外，版本化清单固定官方URL、尺寸、SHA256与WMF内层成员；支持按架构下载、复验和仅提取已核验MSU，不执行安装。8项下载/暂存负例与正例通过；初轮测试夹具误放源码边界内，6项失败独立保留，修正夹具后通过。8个MSU共2949个服务目录的微软签名有效，.NET安装器签名有效；该检查不能代替实际补丁适用性和重启验收。见 [有限回执](../../migration/candidates/rc3/windows-prerequisites-current-checks.json)。AIO按实际依赖先处理SSU/SHA-2及所需重启，再处理D3D/.NET/WMF；不照抄原评估中的示意顺序。安装包、x86运行时和完整发行资格继续实施。

### R08-E — 实际断线重连、交付文件与浮窗

四条 Standard 旅程（现代浏览器/Chromium108 × Source/Python）均完成 fresh/cold。直接中断实际宿主升级后的 WebSocket，原版客户端重新取得101握手；会话header及历史保持一致，后续真实工具调用产生新序列并回到原界面。真实present工具发布文件后修改磁盘内容，原版卡片打开当前字节；可信鼠标拖动验证浮窗移动、缩放和归位保留tab身份。原版前端字节未改，108 Source显式使用相同宿主适配。

现代Python首轮冷观察在会话加载前取得空基线，旧回答可能提前满足完成条件，后续严格历史断言拒绝。已增加发送前attached/idle屏障，新鲜b旅程通过；原失败保留，其余三条实际观察均有一致历史和新完成序列。有限报告、宿主观察与截图逐成员核验归档，成功浏览器profile自动清理。见 [有限回执](../../migration/candidates/rc3/browser-reconnect-delivery-floating-checks.json)。这不替代Desktop安装执行或统一发行资格。

### R11-A — 当前 DeepSeek 完整边界捕获

将既有有限捕获器的Source准入切到当前rc.3后重新执行，76组实际配置、模型、序列化、SSE、HTTP、Files、设置及重试观察严格匹配，未放宽字段比较。120项原始消费者及身份/漂移拒绝用例通过，保留新鲜两侧捕获和日志；没有重标旧rc.1证据。见 [有限回执](../../migration/candidates/rc3/deepseek-capture-current-checks.json)。其余历史观察器、Source配置和统一资格继续迁移。

### R07-E — 协调候选组合

新增集中候选映射和五个原版空apply的browser包host half，不改变正式注册表。冻结独立原版rc.3 manifests、bundles、presets与official前端，通过canonical run_profile加载全部候选provider；当前观察156 entries/129 active，其余显式禁用，client图由实际加载解析为53行，不设固定包数断言。严格生成的Typert描述符驱动Minimal/Standard/PTC创建、选模型、真实对话完成和v3 flush；第二个Standard轮次引用Minimal并提交持久上下文。输入前后SHA及原版干净pin均核验。初轮环境、旧export/instructions与模型接口缺口逐项修复，失败原始观察保留。回执 `migration/candidates/rc3/composition-current-checks.json`。正式两工具Minimal/Creative、前端导入、台账/pin、浏览器与发行资格仍待完成；成功短测试夹具自动清理，约177GiB可用。
