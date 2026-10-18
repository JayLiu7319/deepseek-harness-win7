# Desktop 安装后启动修复、样式核对与剩余工作

目标固定为 `dsh-v0.1.5-rc.3` / `a4c74a91e06b00fe0b0937bde982170c526cc842`。最终冻结候选 **`6cbcbf1c`** 已完成除用户延期 Win7 真机与实际内网服务器部署外的剩余约定任务。完整门禁、双架构分发、六组管理员生命周期、真实服务及本地签名更新均有独立绑定，见[完成记录](2026-10-18-desktop-completion-validation.md)和[正式回执](../../migration/evidence/RUN-RC3-DESKTOP-COMPLETION-20261018-6CBCBF1C.json)。下节保留用户安装版故障及最初 `0cfbd91b` 修复的历史过程；旧 `228cfacc` 与失败候选不重标为本次通过。

## 1. 启动错误与本机恢复

错误来自 `workspace` 启动时列举会话：默认 JSONL 后端使用 `zstd`，已有目录含明文 `session.jsonl`，因此按原版存储合同拒绝。不是 Windows 11 不支持，也不是安装包缺少 Python。上次截图中的 EPIPE 与本次编码冲突是两个问题。

本机只读检查发现 4 份可读取的 v0 明文会话和 8 份 v4 明文会话。rc.3 的当前格式为 v3；v4 保留原状，当前版本不会降级读取或回退到较旧代。显式选择 `none` 后，后端成功列出 4 份支持的会话。

已先备份桌面 patch，然后为当前安装版添加完整的匹配配置：

```yaml
- id: session-persistence-jsonl
  config:
    root: !!js dshHomePath('sessions')
    compression: none
```

本机备份位于 `%USERPROFILE%\.dsh\profiles\desktop\cordis.patch.pre-plaintext-recovery-20261018.yml.bak`。没有删除或转换历史会话。恢复后的实际已安装 x64 程序完成主界面、设置 RPC、工作区流、单实例和退出等 6 项检查。原安装程序的管理员交互由用户完成，本次没有据此补记自动安装验收。旧安装版退出时的一条 `Desktop Host is stopping` 日志独立保留。

最初源码修复对 Desktop 执行以下默认策略；最终公共启动层已将同一规则用于 canonical CLI/Web 和 Desktop：默认目录只有明文历史且没有显式压缩配置时，在内存中沿用 `none`；空目录和压缩历史继续使用 `zstd`。显式配置、自定义根目录和混合编码仍按原合同处理。启动不改写用户 patch，不迁移历史文件。另将启动失败标题改用原版 locale，阻止启动未完成时第二个实例提前创建空白窗口，并结束退出后到达的晚请求。

## 2. 最初 0cfbd91b 定向验证（历史）

选择了实际 Desktop/workspace 启动、当前 JSONL 提供端、旧后端编码拒绝、桌面标准管道和插件事务消费者，覆盖原错误及直接依赖链：

- 104 项 pytest 通过，58.51 秒。包含明文和 zstd 旧目录的启动/冷打开、前代字节和 mtime 不变、新目录默认值、显式配置冲突、混合编码拒绝及失败后释放 profile。
- 新源码的真实 Electron 22 开发外壳完成 9 项观察：启动中第二实例、原版页面、RPC/流、单实例、中文原生菜单、插件窗口浅色/深色、退出、历史字节及 mtime 不变和无 renderer 错误。
- 234 份原版前端输入全部匹配固定清单；7 份桌面 Source 输入与生成物的 SHA 全部匹配；插件管理器 3 份源文件与固定 Source 逐字节一致。
- 新 x64 Standard 构建退出0（909.258秒），包内旧数据启动与同目录冷启动分别9项通过；9项二进制管道前检亦通过。安装器126,346,594字节，SHA-256 `1ab360e62e23ef0119dada3906ff8cdd97255e373e2a10133bb86d307e7b5f8a`，位于 `dist/dsh-v0.1.5-rc.3-desktop-upgrade-0cfbd91b-targeted/`。详情及35成员诊断载体身份见[本次检查记录](../../migration/candidates/rc3/desktop-upgrade-current-checks.json)。构建和定向观察不等于新的完整发行资格。

最初两次新增测试分别因测试使用了错误服务名、遗漏请求 AbortSignal 而失败；修正测试后得到以上 104 项通过。开发观察器首次在主进程 inspector 中使用不存在的全局 `require` 而被拒绝，改为主模块的 require 后通过。原失败目录、XML 和观察不覆盖，也不与后续通过合并为新的完整门禁。

## 3. 样式与交互核对

主应用234份固定资源及插件管理器原版HTML/CSS/JS身份保留。Electron22/44在同一Python Host上完成英文/中文、浅色/深色、1/1.25/1.5模拟缩放下主页面、设置、模型、编辑器和插件窗口共120视图；60对可见控件顺序、焦点、弹窗、披露区状态一致，无横向溢出。主应用控件矩形最大差0.01043701171875 CSS px，插件原生表单最大差2 CSS px。Electron22不支持的AccentColor由独立兼容样式补齐，原版设计文件不改写。

| 部分 | 结论与边界 |
|---|---|
| 主应用与插件窗口 | 固定原版设计，120视图及60对控件比较通过；原生表单仍有约1–2 CSS px引擎差异 |
| 语言、主题、缩放 | 覆盖英/中、浅/深和三种模拟缩放；没有据此认证原生OS DPI或所有系统弹窗 |
| 菜单与错误框 | 初始化默认菜单竞态和早开白窗已修复；原生错误框依赖系统度量 |
| 托盘、关闭后隐藏 | 既定Win7桌面设计，与原版最后窗口关闭即退出存在明确差异 |
| 插件安装 | 原版管理器配合Python文件夹/ZIP事务，不宣称npm插件ABI等价 |
| 安装与更新 | NSIS Standard/AIO、离线指南及独立签名完整安装器通道，遵循Win7分发方案 |

比较使用原版renderer和相同Python Host，没有运行上游npm Host全功能认证。初始调研的“100%同构/无任何现代API摩擦”不是实测结论。详见[原始方案与补充](2026-10-16-dsh-v0.1.5-rc3-desktop-distribution-evaluation.md)。

## 4. 剩余任务收口

| 工作 | 最终状态 |
|---|---|
| 共享旧历史策略 | canonical Standard/Creative/Web/Desktop的none/zstd读取、首写v3、独占与冷恢复通过；Minimal保留显式配置 |
| 稳定候选统一资格 | `6cbcbf1c`单次干净完整门禁通过，精确ZIP与输入清单绑定；此前SDK清单失败单独保留 |
| 双架构完整分发 | x86/x64 Portable、四份Standard/AIO及独立离线组件ZIP已核验并交付 |
| 管理员安装生命周期 | 六组全新安装/旧版覆盖升级通过，故障回滚、普通用户fresh/cold、卸载用户文件保留及原机器状态恢复已核对 |
| 视觉矩阵 | 120视图/60对控件比较通过，保留上述有限范围与原生度量差异 |
| 真实provider | 两种架构包内CLI和x64原版Desktop输入框消息、读工具、冷上下文恢复通过 |
| 更新链路 | 双架构本地HTTPS/私有CA/Ed25519/下载/SHA及篡改拒绝通过，同份Standard下载已实际管理员安装 |
| Win7真机与补丁/重启 | 按用户要求延期 |
| 实际内网服务器发布 | 用户后续搭建；已提供部署和验收指南，长期签名密钥及地址由运营配置 |
| 持续披露 | 八项精确Source例外、C58调度及任意插件ABI不扩张；`accepted_upstream`仍为null |

`MIG-DESKTOP-UPGRADE-001`按最终独立证据集成。真实历史、保护备份与失败日志保留；合成副本按归属核验清理，不批量删除`.goose/out`。

## 5. 后续实施：跨入口旧历史

公共 `dsh.boot.session_compatibility` 现在供 canonical profile 启动/热重载和 Desktop 共用。只保留未显式设置压缩、使用默认根目录且只有明文历史的配置；后端编码冲突合同不变。Standard、Creative、Web、Desktop 的 none/zstd 实际服务读取、v0→v3 恢复追加、独占写句柄和冷打开已覆盖，旧文件字节和 mtime 保持不变。Minimal 本身显式使用 none，继续遵循其配置。

定向集合 96 项通过（119.58 秒），输出 `.goose/out/desktop-completion-20261018-b`。前一次 8 项新增夹具失败保留在 `...-a`：读取头使用了错误接口，zstd 历史夹具没有将首行独立分帧；修正夹具后通过。此结果不替代新候选统一门禁。
