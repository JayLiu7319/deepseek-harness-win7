# rc.1 基线迁移与验收记录

本轮按用户授权将活动基线从 `dsh-v0.1.2-alpha.1` 切换到 `dsh-v0.1.2-rc.1`，固定 Source 为 `a66e4702047846cdaa10c66c9d3df3951f5ea70d`。本产品版本和发行标签仍单独管理；本轮不发布 Release。

## 已完成的实现

- 原样同步 `packages`、`apps/web` 和官方构建产物，更新前端输入、工作流 bundle 和 vendor 版本；原版 TSX/CSS 不因 Python host 改写。
- Session 采用 `isSeeded`、独立 inherited cut、`ownEvents`、索引读取以及严格区分的 seq/offset；JSONL 私有 version0 格式继续读取既有数据。准备、查询、投影、缓存、Remote、SDK、ACP 和子代理同步消费新契约。
- 增加 whole-log 轮次摘要；迁移 turnBoundary v2、schedule v2、llmRetry v1 和 permissions v2。权限预设读取 Session 投影，seed 边界保留继承来源。
- 修复文件引用提供端与 Remote 的异步接口，按 Agent 工作目录维护有界索引并处理取消、失效和卸载；原版 composer 选择引用不自动注入文件正文。
- 迁移 Remote 错误词汇及子代理相邻消息投递，清理已删除的 canonical 包名。旧 SQLite 数据由显式产品自有只读 reader 导出为 canonical JSONL，保留原数据库；不冒充已删除的上游 SQLite provider。
- `read_image` 接受无扩展名附件路径，按签名识别格式并由实际附件解码完成校验。
- Windows 投影缓存写入仅对共享/访问冲突做有界原子替换重试；保留原记录并传播永久失败。
- 反馈 sidecar schema 按 Source 数值语义接受有限安全整数的浮点表示，真实 Loader 冷恢复可重开。刷新开发期四个静态客户端库，封存前端 bundle 保持原字节。
- Web 测试镜像补齐 `queue-image.e2e.ts`；同步35个原版 Web 快照场景及新 Remote 错误码，schedule 客户端清单遵从禁用行。

## 本轮定向证据

以下均为实际运行，不能拼接成完整发行回执：

| 验证 | 结果 / 范围 |
|---|---|
| rc1 capabilities Source / Python3.8.10 | 21 类完整观察匹配，含 Session、lineage、chunk、投影、引用和提示词顺序 |
| permissions Source / Python | 55 项匹配；含 v2 状态解析、种子、命令和卸载 |
| Agent 依赖生命周期 Source / Python | 43 项匹配；覆盖六项必需服务，含 sessionProjections 丢失和恢复 |
| JSONL Source / Python | 1,030 项观察匹配，含格式版本拒绝和真实互读 |
| FS Source / Python | 514 项匹配；新增五项无扩展名图片读取场景 |
| 权限命令 / 浏览器证据拒绝控制 | 128 项 Python 通过 |
| 权限、Agent 依赖与 durable tool 配对消费者 | 245 项 Python 通过 |
| 文件工具与附件消费者 | 67 项 Python 通过 |
| 先前剩余 Session / compaction / ACP 消费者 | 51 项 Python 通过 |
| Session / fork / 反馈 / 沙盒 / Web 快照修正 | 142 项通过、1项既有跳过；包括实际 sidecar 冷恢复和非法数值拒绝 |
| 基线、前端及记录消费者 | 141项通过；旧 alpha 差分 pin 单独修正后复验31项通过 |
| Search / schedule / Session profile 消费者 | 35项通过 |
| 最后证据控制批次 | 430项通过；Source snapshots 的损伤控制已改为当前 JSONL 行，旧 SQLite 名称不再冒充 canonical 提供者 |
| 原版 Edge / Python Edge / Python Chromium108 | minimal 140 轮历史、首次启动及真实进程冷恢复、原版可信输入分页跳转、中文/空格路径引用选择通过 |

原始观察保留在 `.goose/out/rc1-*20261015/` 各自目录。Source 与 native 浏览器都观察到最早回合加载并进入视口；完整高亮/所有滚动时序不由这一有限断言推广。Chromium108 的完整解压旅程会独立重跑，并绑定实际 ZIP、解释器、导入字节、浏览器身份及 fresh/cold 两阶段。

## 证据和能力边界

alpha.1 的合同、Source 夹具、SQLite 历史输入和原始回执封存在 `migration/history/2026-10-14-alpha1/`；历史任务不会因 pin 更新而成为 rc.1 验收。活动能力矩阵为 `migration/rc1-capabilities.json`，共274 manifest：203 runtime、49 frontend、6 platform、9 tooling、7 fixture。Loader 注册、实际激活、Source 配对和整体资格分别记录。

LSP stdio 样机、外部搜索/云 provider、GitHub ingress 等按既定评估保持独立可选批次，不加入默认 Portable 的运行依赖。真实 Win7 与真实远端模型 provider 沿用已有延期/未验证边界。

## 统一资格

当前状态：实现及定向检查完成后冻结候选，执行 `scripts/verify_release.py`。在完整 Python、固定 Source 配置、全部选定配对合同和实际解压 Portable/浏览器都通过前，`accepted_upstream` 保持 null，迁移任务保持 running，不宣称已完成正式验收。

首轮干净 `a6191cdb197c9e317fe6c358193ebd255c11b1fa` 的 Portable 构建完成，但完整 Python 在145项通过后因缺失上游测试镜像停止。原 XML、日志、冻结输入和精确失败 ZIP 保存在 `.goose/out/rc1-release-a6191cdb-20261015/`；ZIP SHA256为 `74942c18f58377a9763f65bd868331089aa7bf5a24c9c9a3af9801d1c42067b5`。该运行保持 failed，后续修正不得补签它。

第二轮干净 `be4c1d4b4e94086fce2b3edda290a9033f061514` 构建完成，完整 Python 在1,606项通过、1项跳过后因旧 Session header 夹具缺少 `isSeeded` 停止。原 XML、日志、冻结输入和失败 ZIP 保存在 `.goose/out/rc1-release-be4c1d4b-20261015/`；ZIP SHA256为 `bbc23b8d5a5259c63d6286d269f4004dc5c10393cd01a13d6dd443015dfce269`，保持 failed。

随后按 Session/Agent 共享服务及直接消费者选取246个测试文件，实际得到3,281项通过、106项失败、3项跳过。失败归并到15个文件：补齐观察器的 `sessionProjections`、独立 inherited cut 和当前 Remote 错误码；改用第二个实际 persistence 实例验证外部写入失效；重新构建示例 Web 插件；旧 SQLite 测试改为断言 canonical 名称退役及产品自有 SQL hash/reader。修复批次329项通过，最后39项 ACP/JSONL/Web 定向复验全部通过。各次原始日志和 XML 保留于 `.goose/out/rc1-session-spine-consumers-20261015/` 与 `.goose/out/rc1-session-spine-repair-20261015/`，这些分段结果不能替代下一份完整回执。

第三轮干净 `1ab872569e0eab044fba033880b1f863c8500a8a` 构建完成，完整 Python 得到4,431项通过、1项跳过、1项失败：必跑清单未同步已重命名的 SQLite 退役检查用例。已修正清单，失败回执保持 failed；原 XML、日志、冻结输入及失败 ZIP 保存在 `.goose/out/rc1-release-1ab87256-20261015/`，ZIP SHA256为 `b350a445714bcb427551a35fefe98bedabed8e8a31d5a6261feec9da0c5218aa`。同时更新三份合同的 canonical Remote/SDK/persistence 消费路径及 `init(header, inheritedEventCount)`；后续未覆盖消费者作为独立定向批次检查，不拼接签收第三轮候选。

后续190个文件及未执行验收控制的定向批次得到3,976项通过、5项失败、5项跳过、860项范围外取消选择。5项失败归并为 headless 夹具缺少投影服务、CLI package manifest 未同步、minimal 固定行数/旧行名以及 Source 缓存观察器参数签名和 v5 文档格式；修正后的32项复验通过。minimal 现在比较实际原版配置行，CLI 安装锚点 manifest 原样同步 rc.1。

缓存恢复复核另外确认：Source `hydratePrepared` 对任意解析异常回退，Python 原来只捕获三类异常。新增实际 Source 的 `prepared-runtime-malformed` 场景，修复前保留 Source 成功重放而 Python 抛出同一个 RuntimeError 的完整观察；修复后9个实际 Source/native 场景匹配，72项缓存、投影和 preparation 消费者通过。观察器继续验证 v4 读取兼容、v5 写入、精确 identity、错误身份及 prepared fallback 不改写旧记录。证据保留于 `.goose/out/rc1-unexecuted-consumers-20261015/`；本批仍不能替代下一份完整候选资格。

冻结前53项检查通过，包含真实必跑用例定义、SQLite 退役声明、CLI/minimal 配置、9场景缓存 Source/native 配对及迁移记录消费者；Python3.8 AST 与 diff 检查通过。

第四轮干净 `91414951d8c7bb29c177c49ef0d1d1e0f1383403` 构建完成，完整 Python 得到7,861项通过、5项跳过、1项失败：真实浏览器插件卸载后返回新版结构化 RemoteError，旧观察器只匹配 `JSON.stringify(error)` 中的 message，而 message 不可枚举。原始 XML、日志、冻结输入及失败 ZIP 保留于 `.goose/out/rc1-release-91414951-20261015/`；ZIP SHA256为 `07872c7b89f6472f58c2d266914b40c6436821854742ab24d74a7f253a7b635c`。修正后的观察器断言完整线上错误信封、endpoint、code、message 和浏览器错误结构；导出适配器沿用普通 Error 的公开契约。三个实际 Edge 安装/HMR/卸载/刷新/重启/升级回滚旅程通过，保持失败回执不补签。

随后单独诊断21组 Source 配置及82个配对驱动：98组通过，5组失败；这不是完整资格。修正 session-recovery 明文损伤夹具的压缩设置、storage-cache 的显式 inherited cut，以及 pruner/compaction/ACP-MCP 观察组合缺失的 session-projection 服务，分别复验成功。compaction 进一步暴露实际产品遗漏：rc.1 invariant 新增 summary/prune 当前完整可见区间校验，Python 仍仅校验首尾。已按原版补齐严格 seq、完整区间、重放和预提交状态，只在提交后推进 surface；旧合法摘要夹具补上真实较早 surface 输入，新增17项非法区间/已替换区间/序号/合法裁剪观察。172项 Source/Python 配对通过（含两项原有、未放宽判据的上游差异）；214项 compaction、pruner、事务及 Agent/HTTP 消费者通过。负零由两端相同的 JSON envelope 边界先行拒绝，独立记录而不伪称触发 invariant。另101项 ACP-MCP、JSONL 恢复及迁移记录消费者通过。诊断与修复原始证据保留于 `.goose/out/rc1-source-paired-diagnostics-20261015/`，下一干净候选重新统一资格。
