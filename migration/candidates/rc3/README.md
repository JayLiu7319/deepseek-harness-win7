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

R02-M：新增 [observation-checks.json](observation-checks.json)，只读handle冷观察、内存中断补齐、revision/实例缓存、LRU与独立租约、延迟live快照已连接。Source原27项与Python99项分别通过；生产query/Agent尚未切换，不表示整体验收。

R02-N：新增 [query-consumers-checks.json](query-consumers-checks.json)，显式v3语料/Query/SQLite通过当前list/open handle读取，观察缓存随服务复用，surface和索引使用v3分类。真实Source/native31组旅程匹配，两端各141项定向测试通过；活动profile和Agent仍待切换。

R02-O：新增 [agent-ownership-checks.json](agent-ownership-checks.json)，候选Agent在发布前拥有写handle、存储setup后缀，resume显式持久化崩溃修复，退出排空后释放身份，取消迟到handle与聚合错误已覆盖。Python194通过；Source44通过/1项原有Windows guard跳过。请求机、Inbox与Agent身份scope仍待R03替换，活动profile未切。

本区保留各阶段当时的候选状态。R07-F 已协调切换正式 reference、baseline、运行时映射与原版前端；旧 rc.1 资格保持原身份，新任务 MIG-RC3-ALIGNMENT-001 等待当前目标的完整证据。R01–R11 是实施行动编号，不触发自动验收。

R03-A：新增 [loop-projections-checks.json](loop-projections-checks.json)，持久化 Inbox、提示词历史投影、运行时上下文和流式 attempt 结算合同的 77 个实际配对场景匹配；Python 342 项、Source 原套件 102 项通过。persona prefix/suffix 顺序作为候选服务提供。请求驱动与 preset 消费者尚待连接，非整体 R03 签收。

R03-B：新增 [agent-machine-checks.json](agent-machine-checks.json)，候选请求机、Agent 身份作用域、显式父 Agent、非阻断通知、提示词历史和实际 handle 恢复的 29 个流程配对匹配。Python 定向 256 项及最终机器 41 项通过；Source 原驱动 325 项通过、1 项既有 Windows guard 跳过。preset/subagent 与 Remote 消费者仍待连接，活动 pin 不变。

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

R03-C: [persona / one-shot consumer evidence](agent-consumers-checks.json): 29 actual Source/native journeys matched; 238 selected native tests passed; Source 307 passed with one Windows dangling-symlink EPERM environment gap. Continuable consumers and baseline switch remain open.

R03-D: [parent catalog and continuation units](subagent-units-checks.json): 53 actual pairs, 172 selected native and 30 original Source tests passed. Lifecycle integration remains open.

R03-E: [continuable residency evidence](subagent-runtime-checks.json): 19 actual current pairs, 29+29 direct consumer rechecks, 169 selected native and 270 original Source tests passed. Remaining consumers and production switch stay open.

R03-F: [Session-owned delegation tools](subagent-tools-checks.json): 21 complete tool journeys, 117 selected native and 217 original Source tests passed. Explicit Session inheritance and actual listing-cache hits are covered; remaining consumers and baseline activation stay open.

R03-G: [current compaction](compaction-current-checks.json): 18 explicit-meter transaction pairs, 154 selected native and 146 original Source tests passed. The system head and v3 replacement contract are covered; current token-meter and remaining consumers are open.

R03-H: [current token measurement](token-meter-current-checks.json): 7 actual Agent journeys, 132 pure contracts, 240 selected native and 119 original Source tests passed. Actual metered compaction/cold resume are covered; mounted file admission and outline/UI consumers remain open.

R03-I: [current goal ownership](goal-current-checks.json): 78 actual contracts and 280 selected native tests pass. Original seven suites report 125 passed / two retained failures (corrupt-append assertion and Loader timeout); no full original-suite pass is claimed. Actual pause/resume races and cold activation are covered; remaining consumers and baseline activation stay open.

R03-J: [current ACP ownership](external-acp-current-checks.json): 24 complete pairs, 113 selected native tests and 72 original Source tests pass (one original skip). Actual current parent delegation and published-result rejection are covered; absent Claude Code/Codex providers and broader managed ranges remain open.

R03-K: [current SDK consumers](sdk-current-checks.json): 16 complete SDK pairs, 95 selected native tests and 131 original Source tests pass. Also corrects R03-J's two missing-cwd parent fixtures: earlier observations only showed configuration rejection; new 24-pair receipt plus successful-output assertions now cover actual parent delegation. Old observations are retained. Remote/file admission and baseline activation remain open.

R04-A: [explicit Agent Remote](remote-current-checks.json): 12 actual pairs, 162 selected native and 313 original Source tests pass. Candidate registry has no reverse Context identity; goal Remote, activation emit, waterfall rejection/cancellation are covered. Connection/RPCFetch and production baseline remain open.

R04-B: [carrier-neutral Connection](connection-current-checks.json): 30 actual pairs (seven TCP upload journeys), 74 selected native and 52 original Source tests pass. Headless registry, optional Web carrier/recovery bootstrap, buffered/streaming body selection and required RPC payload are covered. Auth/trust/feedback deltas and production switch remain open.

R04-C: [canonical feedback](feedback-current-checks.json): 33 actual pairs, 63 final selected native and 51 original Source tests pass. Session feedback Remote/categories and actual command acknowledgement, Session-log message feedback, cold write ownership, immutable CAS/no-op results and cancellation/disposal are covered. Production sidecar replacement awaits the unified switch.

R04-D: [subagent Remote and wire zones](subagent-remote-current-checks.json): 12 actual control journeys plus 610 zone inputs match (13 paired cases); final native622 and original Source271 tests pass. Actual Queue/Steer, running-parent authorization, idle no-op and canonical zone provenance are covered. Mounted attachment admission awaits R05.

R05-A: [verbatim file storage](attachment-files-current-checks.json): 15 actual paired contracts, 660 selected native tests and 37 original Source tests pass. Bounded file streams, immutable read-only hard-link aliases, concurrent digest verification, cancellation cleanup and mixed prompt admission are covered. LLM handles, SessionController file carriers, image codec deltas and production activation remain open.

R05-B: [LLM file handles and metering](llm-files-current-checks.json): 20 current pairs, 329 selected native tests and 113 original Source tests pass. Actual Agent/local file/middleware/adapter and token-meter path changes are covered. The initial old-pin observer rejected an incorrect Node version; its diagnostics remain. SessionController and current image closure remain open.

R05-C: [upload receipt ownership and commands](file-upload-current-checks.json): 13 current pairs,132 selected native and80 unchanged original Source tests pass. Actual streaming Connection route, Session receipt isolation/rollback/history retirement, mixed command admission and2MiB TCP readback are covered. A TCP-discovered missing Fetch URL was fixed and its failure retained. SessionController delivery and production activation remain open.

R05-D: [async image lifecycle](attachment-images-current-checks.json): 11 actual pairs,88 selected native tests plus one new actual DeepSeek consumer, and35 unchanged Source tests pass. Shared cancellation/generation isolation, FIFO compression, immutable image publication and cache repair are covered. Pillow codec identity remains explicitly separate from Sharp; SessionController and production activation remain open.

R05-E: [execution-world media reads](session-media-current-checks.json): 34 actual pairs and95 selected native tests pass; unchanged Source suite has20passed/1EPERM symlink failure/1Windows FIFO skip. Exact GET/HEAD /api/file, pinned1239 MIME mappings, opaque FS targets, byte limits, actual TCP auth/HEAD length/route unload are covered. Original failure is preserved; SessionController delivery and activation remain open.

R05-F: [Session prompt and queue ownership](session-commands-current-checks.json): 23 actual pairs plus13upload regression pairs,103 selected native tests and29 unchanged Source tests pass. Binding rollback/retirement, idempotency, durable queue edits/steer, compact-stream authorization and actual Agent consumption/disposal are covered. Full SessionController assembly/activation remain open.

R04-E: [Session Agent activation](session-agents-current-checks.json):26 current pairs,97 selected native tests and16 original Source tests pass. Real persistence restores pending model selection; factory dedup and ownership races are covered. Full SessionController and production activation remain open.

R04-F: [Session identity commands](session-identity-commands-current-checks.json):32 current pairs plus49 activation/prompt regressions,102 selected native and21 Source tests pass. Actual model routing and persisted fork prefix/title are covered. Full controller and production activation stay open.

R04-G: [Session list/search/cache](session-list-current-checks.json):35 current pairs,141 selected native and60 original Source tests pass. Lists perform no cold handle opens; cache format identity and predecessor title-only hints are covered with actual storage and SQLite consumers. History/control and production activation remain open.

R04-H: [Session history/control](session-history-current-checks.json):38 current pairs,171 selected native and37 original Source tests pass. Actual Agent/query verifies live Assistant reconnect and gap-free cold promotion; control uses durable Inbox replacement snapshots. Full Remote assembly and production activation remain open.

R09-A: [native desktop intents](native-path-current-checks.json):68 current pairs,111 selected native and44 Source tests pass. Actual child argv/UTF-8/abort/reaping and controlled platform open/reveal/WSL/Explorer contracts are covered. Packaged desktop acceptance remains open.

R04-I: [complete Session facade](session-facade-current-checks.json):31 current pairs,129 selected native and39 Source tests pass. Real full Agent/persistence/uploads, background promotion ownership, projected cold skills, lifecycle and unload are covered. Current generated descriptors/production composition and workspace/sidebar alignment remain open.

R06-A: [bounded FS byte windows](fs-range-current-checks.json):27 current pairs and29 provider tests pass. Expanded consumers136passed/1existing Win321175 failure/4skips; Source82passed/5EPERM symlink failures. Overall FS consumer acceptance remains open.536870928bytes of completed reconstructible range fixtures were audited and removed; failed data retained.

R06-B: [workspaceFiles previews/change feed](workspace-files-current-checks.json):95 current pairs and190 selected native tests pass; Source93passed/6EPERM symlink fixture failures. Actual parent/child/cold header scope, composed-FS reads, related resources, contained listing, caps and change generation cleanup are covered. Current descriptors/activation and browser Sidebar remain open.

R06-C: [explicit filesystem deliverables](present-current-checks.json):33 current pairs and186 selected native tests pass; unchanged Source8passed/2EPERM symlink fixture failures. Final successful tool-result commit, scoped replacement/nested ownership, actual binary source and persisted parent/child isolation are covered. Authenticated opens, current composition and browser acceptance remain open.

R06-D: [current file tool increments](file-tools-current-checks.json):46 actual pairs,129 selected native tests (one skip) and273 Source tests (one skip) pass. All32 visibility subsets, path-aware mutation remediation, image path-only presentation metadata and search provider/spill boundaries are covered. Production activation and remaining R06/browser consumers stay open.

R06-E: [authenticated declared-file actions](present-open-current-checks.json):52 actual pairs and269 selected native tests pass; unchanged Source29passed/1EPERM symlink fixture failure. Real TCP auth, cold inherited child source, verified Host mapping, cancellation and unload waiting are covered. Remaining Sidebar/frontend composition and production promotion stay open.

R06-F: [current Workspace identity/snapshots](workspace-current-checks.json):110 actual pairs and222 selected native tests pass; unchanged Source51passed/2EPERM symlink fixture failures. Snapshot-header bootstrap/refresh/cold domains, fully qualified paths/root titles and real current persistence consumers are covered. Pure Sidebar host halves confirmed; browser/profile activation remains open.

R09-B: [verified external application launches](open-in-app-resolver-current-checks.json):100 actual pairs,192 selected native and38 unchanged Source tests pass. Exported catalog, actual filesystem locators, registry/XDG precedence, numeric ICU ordering and detached child survival/credential scrub are covered. Authenticated routes/icons, production activation and desktop acceptance remain open.

R09-C: [authenticated external-app routes/icons](open-in-app-host-current-checks.json):80 actual pairs,321 selected native and25 unchanged Source tests pass. Actual HTTP pre-body auth/bounded chunks, stale launcher refresh/removal, icon cache and real Windows PNG extraction/temp cleanup are covered. Current profile/frontend/desktop qualification remains open.

R09-D: [MCP cursor rejection](mcp-current-checks.json):15 actual pairs,115 selected native and107 unchanged Source tests pass. Repeated-cursor precedence, retained generation, later successful notification swap and real stdio bounded startup/process closure are covered. Current profile activation remains open.

R07-A: [explicit profile initialization](profile-init-current-checks.json):47 actual pairs,67 selected native and22 unchanged Source tests pass. Exclusive two-process creation, failure cleanup, shipped-template metadata and actual boot/dump consumers are covered. Product retains three extra presets; current provider composition and production promotion remain open.

R07-B: [home proxy admission and inserted filesystem paths](boot-layers-current-checks.json):37 actual pairs,199 selected native and76 unchanged Source tests pass. Actual local plugin loading and credentials/LLM/boot consumers are covered. Outbound proxy transport and current composition remain open.

R07-C1: [outbound proxy policy](http-proxy-policy-current-checks.json):129 actual pairs,169 selected native and65 unchanged Source tests pass, including actual Source undici matcher parity. Candidate pure routing is covered; installation, real native transport and child integration remain open.

R07-C2: [process proxy transport and child egress](http-proxy-install-current-checks.json):64 actual pairs and231 selected native tests pass. Source install24pass; subprocess egress7pass/1Windows case-fold expectation failure retained. Actual HTTP/TLS forwarding, nested TLS verification/cancellation, LLM, child and boot restoration are covered. Current composition and release qualification remain open.

R03-L: [embedded-stream Session stats](session-stats-current-checks.json):67 actual pairs,224 selected native and44 unchanged Source tests pass. Actual Agent/JSONL cold replay, checkpoint-tail timing and unload/remount are covered. Validated JSON numeric positions now work with Python range/slice. Current composition and release qualification remain open.

R03-M: [feedback-only telemetry](telemetry-current-checks.json):72 actual coordinator pairs,116 selected native and74 unchanged Source tests pass. Real SDK collector covers canonical own feedback, inherited/fake-event rejection, stored cold history and no-op mutations. Current production composition and release qualification remain open.

R03-N: [generation-scoped DeepSeek log upload](session-log-current-checks.json):41 actual pairs,100 selected native and44 unchanged Source tests pass. Exact raw DTO/provenance, format-gated watermarks, real Agent HTTP 2xx acceptance and JSONL cold cursor rebuild are covered. Production composition and release qualification remain open.

R07-D: [live-frame headless consumer](headless-current-checks.json):28 actual runner pairs,43 selected native and19 unchanged Source tests pass. Actual current Agent completion/cancellation, v3 disk flush and subscription release are covered; production activation remains open.

R04-J: [logical log export](log-export-current-checks.json): 27 Source pairs, 112 native and 45 unchanged Source tests pass. Real v3 live/cold ZIP export includes generic streamed files and releases the producer on cancellation; production composition remains staged.

- R03-O: [workspace instructions](instructions-current-checks.json): 40 Source/native pairs, 47 native passes; Source 151 passes / 3 symlink EPERM failures / 1 skip. Candidate only.

R03-P: [session reference budgets and full snapshots](session-reference-current-checks.json): 36 actual pairs, 101 selected native and 48 unchanged Source passes. Actual cold v3 Agent references and late-provider cancellation covered; production promotion remains open.

R07-E: [coordinated candidate composition](composition-current-checks.json): unchanged rc.3 inputs, active/disabled Loader audit, derived client graph and actual strict Remote conversations plus cross-session reference. Production promotion and browser/release qualification remain open.

R11-O/P: [current Source fixtures and exception requalification](source-fixtures-current-checks.json) and [current ACP consumers](acp-current-checks.json). Seven snapshots rebuilt from actual rc3 Source, eight retained defect predicates requalified and obsolete token-meter exception retired. Current ACP writer/metadata/stat/setup ownership, actual process permissions/MCP/cold restore and paired observations pass; exact required-lane collection passes. Unified qualification remains open.

R11-Q: [original Web source and current consumers](web-source-current-checks.json). The202-file original source mirror,40-scenario versioned corpus and three external Session sources match pinned rc3. Actual canonical boot derives client rows from the active Loader; owned v3 feedback protocol, generation admission and empty-root lookup are covered. Source manifest41 passes,9 generation pairs match; targeted80 and70 passes. Prior failed runs remain failed; unified qualification remains open.

R11-R/R10-I: [fixed b0 candidate finite observations](b0ff-finite-current-checks.json). Actual extracted x64 Portable matches3 engine and7 route compositions; x86 Portable13-step runtime and both desktop installer builds pass. Actual packaged x86 GUI passes5 lifecycle/transport checks. The b0 unified gate remains failed145/1; administrator installation and physical Win7 remain untested. The9ab3 candidate is qualified independently.

R11-S: [current Loader consumers](loader-consumers-current-checks.json). The9ab3 unified gate remains failed540/1. Actual canonical deliverables activation/disposal, effective current client registrations and current feedback acknowledgement are verified. Corrected client46 and feedback49 pass; unchanged Source1 and16 pass. Earlier151/1 and1063/1skip/1failure observations remain independent failures; unified qualification remains open.

R11-T/R10-J: [fixed9ab3 finite observations](9ab3-finite-current-checks.json). The exact x64 ZIP matches3 engine and7 route cases; x86 completes13 runtime steps. Both architectures compile Standard/AIO and pass9 pipe preflight plus5 actual packaged GUI checks each. No administrator installation or Win7 qualification. The [297-manifest responsibility matrix](../../rc3-capabilities.json) separates effective registrations, sealed original inputs and optional scope; counts do not certify parity. Clean dd4b8ba8 qualification runs separately.

R11-U: [current commands Remote identity](command-remote-current-checks.json). Current provider explicitly declares submittedAttachments in both descriptor modes and rejects the old images wire field. Selected48 and153 pass; unchanged Source55 pass. dd4b unified gate remains failed2762/1skip/1failure; remaining regression diagnostics and stable qualification are separate.

R10-K: [fixed dd4b desktop observations and bounded cleanup](dd4b-finite-current-checks.json). Both architectures pass nine pipe preflight and five packaged GUI checks; each records one control-stream network error after stable assertions, retained for follow-up. x86 Portable13 steps pass. Unified gate remains failed;23 verified older prerequisite copies (833,624,527 bytes) pruned, original inputs and installers retained.

R11-V: [shared development interpreter and current compaction consumers](regression-consumers-current-checks.json).182 selected passes include actual Source/native LLM/context observations; foreign interpreters and product ownership remain guarded. The interrupted partial diagnostic retains182 raw failure reports and its stop reason; release receipt consumers and remaining regression are separate pending checks.

R10-L: [renderer-before-host shutdown](desktop-shutdown-current-checks.json). Actual packaged dd4b reproduces a closing-phase error and is rejected by the strengthened observer. Two actual development Electron22 runs pass six lifecycle checks;19 native consumers pass. Final packaged x86/x64 qualification remains pending. CDP timeout is distinguished from actual process exit.

R11-W: [shared observer selection and native-search closure](observer-closure-current-checks.json). Actual Source/native consumers120/58/41/27 pass within the retained263pass/22error run; corrected native-search39 and seven complete extracted-validator consumers pass independently. Exact136-module paths/bytes replace the stale114-module inventory. Interrupted diagnostic failures remain failed; unified acceptance stays pending.

R11-X: [current Headless and JSONL consumers](headless-jsonl-current-checks.json).23 selected passes cover actual default read tool, cold continuation, three pi-ai wire protocols, retries and owned current JSONL handles/checksummed frames. Earlier36/3 and100/2 runs remain failures, including the retained test-authoring mistakes. Unified qualification remains pending.

R11-Y: [current profile/cache lifecycle](profile-cache-lifecycle-current-checks.json). Current profile recovery and four live Web Agents drain before provider teardown;171 Agent/projection/persistence consumers pass. Nine actual current Source/native cache cases plus rejection controls and25 unchanged Source tests pass. Actual original-browser session-plugin23-step journey exits cleanly. Failed initial shutdown and intermediate initialization attempts are retained; packaged/unified qualification remains pending.

R11-Z: [current query observers and example receipt](query-observers-current-checks.json).107 pass/1 browser-environment skip. Actual Source/native FTS lifecycle and2034 Unicode observations use v3 read-only persistence handles and current engines; strict provenance/damage checks remain. Example build receipt targets the current protocol; ICU fixture copy excludes architecture directories. Unified qualification remains pending.

R11-AA: [current Session read observers](session-readers-current-checks.json). Actual current Source/native corpus, trace, filters, lineage, point-read ownership, 17 durable snapshots and 7883 Unicode/extraction/order observations match. Selected56 and236 pass; earlier54pass/13error text fixture failure retained. Python optional observation attributes now raise AttributeError. Full qualification remains pending.

R11-AB: [remaining current consumers](remaining-consumers-current-checks.json). History tools45, subprocess ownership38, ACP/current process27, teardown/physical-tree119 and corrected manifest6 pass. Web cold export/restart43 pass within a retained43/1 run; the inventory failure is fixed separately. Completed75c4566a partial diagnostic remains failed; unmodified subprocess Source119/4/15skip remains a failed selected run, never a skip or full gate. Stable qualification follows separately.

R10-M: [fixed916e packaged desktop lifecycle](desktop-916e-current-checks.json). Actual x86 Portable13 steps pass; both architectures compile Standard/AIO, pass nine packaged pipe checks and six complete GUI lifecycle checks each. Renderer/console errors remain zero through physical exit0. Four exact installer hashes and screenshots are sealed independently of the running unified gate. Fourteen verified old prerequisite copies (526,960,355 bytes) pruned; original downloads, installers and diagnostics retained. Administrator installation and deferred Win7 execution remain untested.

R11-AC: [current release receipt controls](gate-controls-current-checks.json). The916e complete gate remains failed4490pass/1skip/1failure. Initial whole-control scope1411pass/163fail identifies a shared query-engine fixture identity and retired cancellation expectation. Corrected1579 controls/read consumers/real collection pass; positive receipt runs first, current JSONL handle/module identity and completed-read values stay strict. Actual19347 collection requires3933 lanes. Raw failed gates remain sealed; fresh unified qualification follows separately.

R10-N: [fixed1446 packaged desktop lifecycle](desktop-1446-current-checks.json). Both architectures compile Standard/AIO and pass nine pipe checks and six actual packaged lifecycle checks each, with zero renderer/console errors through physical exit0. Actual x86 Portable13-step product run passes; a post-run wrapper lookup error and corrected value.steps validation are both retained. Four exact installer hashes, raw commands and screenshots are sealed. Fourteen old916e prerequisite copies (526,960,355 bytes) pruned after verification. Full qualification remains independently running; administrator installation and deferred Win7 execution remain untested.

R10-O: [actual plugin window with closed parent pipes](plugin-window-pipes-current-checks.json). Both packaged architectures open the actual native menu window, list plugins and pass7 lifecycle checks with zero renderer/console errors and physical exit0 after parent stdout/stderr closure. Initial CDP-keyboard menu timeout retained separately; product and frontend unchanged.

R11-AD: [current PTC publication](ptc-events-current-checks.json). Failed1446 full gate remains18969pass/6skip/1failure, with371 unexecuted. Active Tools now publishes current ptc events and shaping waterfall; durable actual Web shutdown/reopen and direct consumers275 pass, unmodified Source PTC91 pass, previously unexecuted371 pass, and21 configured Source diagnostics exit0. Old required-event rejection stays strict. These independent observations do not form a complete qualification.
