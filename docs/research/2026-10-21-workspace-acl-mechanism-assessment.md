# 工作区 ACL 异常：机理、原版对照与修复评估

日期：2026-10-21。输入为[内网问题记录](2026-10-21-acl_issue_analysis.md)、当前 Python 实现与固定上游 `dsh-v0.1.5-rc.3 / a4c74a91e06b00fe0b0937bde982170c526cc842`。原记录保留，不用本次推断覆盖现场陈述。

## 结论与证据边界

**优先判断为工作区原有 DACL/继承范围与 DSH Windows 沙箱授权物化相互作用，而非 Win7 特有权限故障。** 原记录把 `S-1-4-…` 不可解析 SID、写删权限、OI/CI 继承判作 DLP 污染，证据不足：这正是本项目和固定上游主动生成的工作区能力 ACE。本次已在现代 Windows 上通过实际 Python 提供端及原版提供端分别复现核心症状，无需借助管控软件。

现场尚缺原始 SDDL、实际 SID、运行令牌及前后快照，不能据此认定内网每一个失败对象均出自同一机制。尤其“文件 DACL 受保护且为空”与“只继承一条能力 ACE”是不同状态；本次没有复现前者由普通新增工作区 grant 自动产生。

初次机理评估阶段只增加评估记录和本地诊断载体，未修改生产实现、原版源码或现有工作区权限；ACL 实验仅修改当次新建的独立系统临时目录，结束后恢复并删除。该阶段验证不是全量回归、发行验收或 Win7 真机复验。后续候选方案与用户理想效果不一致，尚未接受，按用户要求与问题分析分开提交；当前 master 没有合入修复。见[issue #4](https://github.com/czh869452912/deepseek-harness-win7/issues/4)及第 9 节。

## 1. 这条 SID 很可能来自 DSH 自己

Python [windows_acl.py](../../dsh/sandbox/windows_acl.py) 的 `capability_sid()` 与原版 [workspace-sid.ts](../../reference/packages/sandbox/sandbox-windows-acl/src/workspace-sid.ts) 都对规范化工作区路径做 SHA-256，读取前两个小端 UInt32，分别执行 `% (2**30 - 1) + 1`，生成 `S-1-4-x-y`。私有临时目录另用 `temp\0` 前缀及末尾 `-1` 隔离身份。

双方 [ACL 提供端](../../reference/packages/sandbox/sandbox-windows-acl/src/acl.ts) 都合并如下 ACE：

```text
Allow, OI|CI, mask=0x00110156, trustee=S-1-4-x-y
mask = (FILE_GENERIC_WRITE | DELETE | FILE_DELETE_CHILD) & ~READ_CONTROL
```

它不是账户目录里的登录用户，所以无法翻译成账户名本身是预期现象。它只服务于受限令牌写访问的第二次检查；正常用户/组的可读写授权仍需存在。**新增 Allow ACE 本身不会否决其他有效 Allow；不能把“这条 ACE 不含读权限”直接等同于“它拒绝所有人读”。**

工作区 ACE 按设计常驻；临时目录 ACE 才在卸载时撤销。删除工作区 ACE 后，再次进入需要物化授权的会话仍可能重新出现。目录改名后旧 SID 留下、新路径派生新 SID也属于原版已披露的行为。现场应在真实规范路径上计算完整 SID 并与实际 ACE 比较，不能只比 `S-1-4` 前缀。

## 2. 已复现的主要因果链

### 2.1 用户授权只作用于“此文件夹”

实验父目录的初始 DACL 为 `D:P(A;;FA;;;当前用户SID)`：当前用户可操作目录，但其 FullControl 不继承。未加入沙箱授权时，新文件可使用创建令牌的默认 DACL，本次实测含当前用户/SYSTEM 等授权，读写正常。

加入 DSH 的 OI/CI 能力 ACE 后：

```text
父目录：当前用户 FullControl（不继承）
       + S-1-4-x-y 写删（OI/CI）
新文件：只有继承的 S-1-4-x-y 写删
```

在这个实际构造中，可继承 ACE 参与子对象安全描述符生成，原先依赖的令牌默认 DACL 不再为新文件补齐用户读权限。创建时取得的句柄可以写完内容，但关闭后重新打开要再接受访问检查，故“生成成功”和“随后读不了”能同时成立。受限令牌包含的能力 SID也不是普通启用用户 SID，不能代替普通授权检查。

本次普通宿主 Python 与受限 Python 都写出了文件，随后读失败；旧文件保留其原有显式用户授权，仍可读。DSH 的宿主原子写则能创建 `.tmpdir`，但该目录也只继承能力 ACE，于 `create-temp` 阶段失败，留下需恢复权限后清理的暂存目录。这也连接了[10月16日的暂存目录问题](2026-10-16-win7-atomic-write-permissions-investigation.md)。

这能解释为何大部分工作区正常，少数改过权限设置的工作区反复出现：真正差异是用户/组规则的继承范围、子目录保护与已有对象 ACL，不只是用户能否在根目录列目录。只在目录本层具有权限，不足以支持后续创建、读取、替换、删除的一整套操作。

### 2.2 NULL DACL 被合并成真实 DACL

NULL DACL 允许所有访问；EMPTY DACL 是存在的 ACL 但没有 ACE，通常拒绝数据访问。二者不能通过 `.Access.Count == 0` 区分，必须检查原始安全描述符的 DACL 是否存在、指针是否 NULL、ACE 数和 control flags。

双方 `grant` 对 NULL 的旧 ACL 都执行 `SetEntriesInAclW`，可能构造只有能力 SID 的新 DACL。对受保护的 NULL DACL 目录，本次两版都从 `D:PNO_ACCESS_CONTROL` 变成仅含能力 ACE 的真实 DACL，宿主随后无法再创建文件。这是另一条可造成明显权限退化的路径。

NULL DACL 不受保护时，重新设定 DACL 还可能带回祖先可继承规则，本次首轮该对照没有失败；不能把所有 NULL DACL 都宣称会得到同一最终 ACL。上游 README 另明确披露 NULL DACL 在 grant/revoke 往返后可能成为 EMPTY DACL，未把它实现为可靠支持的工作区类型。

微软说明，继承传播也可能把子对象的 NULL DACL 变成只有继承 ACE 的 DACL；移除最后一条继承 ACE 后留下 EMPTY DACL，并不还原 NULL。因此“清理未知 SID”不是语义安全的通用修复。

### 2.3 “空且受保护 DACL”仍有待查部分

普通 grant 合并保留既有 ACE，没有显式把新文件设为 protected 或清空所有 ACE。另一方面，两版 FS 在覆盖已有文件时，都把目标 DACL 复制到暂存文件并设置 `PROTECTED_DACL_SECURITY_INFORMATION`，再原子发布，因此**看到 protected 并不能据此认定 DLP**；但这条覆盖路径本身也没有证明会从正常 ACL 生成空 ACL。

需分别追踪该对象是直接创建、覆盖、移动还是修复脚本处理后的结果，以及是否实际为 NULL、EMPTY、查询失败或后续撤销传播。目录授权修改、外部程序或管控驱动均可继续调查，但目前不能指定某个厂商为根因。

## 3. 与固定上游的对照

| 行为 | 固定上游 | 当前 Python | 对本问题的含义 |
|---|---|---|---|
| 工作区能力 SID | 路径哈希生成 `S-1-4-x-y` | 相同算法 | SID 不是 Win7 适配新增的身份 |
| 工作区授权 | 合并 OI/CI、`0x110156`；精确 ACE 存在则跳过 | 同类读合并写和精确跳过 | 两边都有继承及 NULL DACL 风险 |
| 授权生命周期 | 工作区常驻；私有临时目录撤销 | 相同基本策略 | 删除 SID 后复发不等于外部软件重写 |
| shell 令牌 | `DISABLE_MAX_PRIVILEGE | LUA_TOKEN | WRITE_RESTRICTED` | 相同 `0xd` | 管理员组 deny-only、双重写检查并非 Win7 独有 |
| 默认对象 DACL | 补模式选择的限制 SID 全权 ACE | 还显式补当前用户全权 ACE | Python 已修过管理员默认对象 ACL 启动问题；不自动修复磁盘父目录继承 |
| write/edit 工具 | 文件策略检查后在宿主 FS 执行 | 同类路径 | 宿主和 shell 不同令牌可有不同有效权限；宿主仍受 NTFS ACL 约束 |
| Windows 原子覆盖 | 复制目标 DACL、保护暂存 DACL、ReplaceFileW | 相同核心策略，另有失败诊断加固 | protected 不等于异常，不能放弃 DACL 保留来绕过失败 |

原版声明该 Windows 后端仅为 partial enforcement，并披露常驻 ACE、NULL DACL 往返等限制。没有发现它在这些入口自动修复用户继承范围、接管所有权或为所有文件追加用户全权。上述运行实验以仓库固定版本为范围；后续公开版本仅做源码和发行记录核对，见下一节。

### 3.1 后续官方版本是否已修复

截至 2026-10-21 本次公开仓库查询，最新公开发行标签为 `dsh-v0.2.1-rc.2`，发布于 2026-10-17；查询时该标签与主分支 HEAD 均指向 `687f282e8625c6b8d11ff58211a90524be2e4317`。这是本次查询快照，不代表之后的版本状态。

后续官方版本增加了 Windows ACL 诊断/修复技能：`dsh-v0.2.0-rc.1` 引入，`rc.2` 继续改进授权范围、备份和恢复。其修复面包括特定祖先目录的当前用户授权及特定外来 AppContainer Allow ACE，并保留 Deny、owner、继承设置等。它明确不把 DSH 的 `S-1-4-*` 当成污染；其目录授权也不是通用的用户 OI/CI 继承修复，不能据此认为本案所有异常文件和新对象继承均已解决。

对上述最新提交的 [ACL 源码](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sandbox/sandbox-windows-acl/src/acl.ts)核对，工作区能力写授权仍采用同类合并方式；新增 Everyone 的 `FILE_DELETE_CHILD` Deny 和 Low integrity label 属于其他沙箱边界处理，没有发现本案所需的 NULL DACL 拒绝或普通用户可继承授权完整性检查。工作区授权缓存也不能视作后代 ACL 的持续自检。

因此，**后续官方版增强了诊断和部分修复能力，但没有证据确认本次已复现的继承/NULL DACL 机制得到完整修复**。这里没有运行最新官方 Desktop 复现，不能把源码核对写成最新版本真机验收。参见[官方 rc.1 发行记录](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.0-rc.1)、[rc.2 发行记录](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.0-rc.2)及[该提交的诊断技能说明](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sandbox/sandbox-windows-acl/assets/diagnose-windows-sandbox-acl/SKILL.md)。

## 4. 原记录需要修正的判断

1. **“不可解析 SID = DLP 污染”不成立。** 对本案应先核对 DSH 派生 SID；不能按前缀批删或把合法 Deny 一并当作脏数据。
2. **“空保护 DACL 形成 owner 无法修改 ACL 的死锁”不成立。** owner 通常具有隐含 WRITE_DAC；本次对空保护 DACL 文件以原 owner 直接 `icacls /grant` 成功，无需 takeown。OWNER RIGHTS、受限令牌的额外检查等需另外分析。
3. **“workspace-write 原本就不允许 shell 在工作区写入”不符合产品契约。** 两版均意图允许真实用户本就有权操作的工作区写入；遇到拒绝应查令牌和完整 ACL。尤其只给 Administrators 的授权在 LUA 下可能无法满足普通检查，即使能力 ACE 已存在。
4. **“沙箱把 Get-Acl 返回内容清空”缺乏实现证据。** 当前提供端运行受限进程，没有拦截该 cmdlet 并伪造返回值的逻辑；读取 ACL 需要相应权限，失败必须保留错误。也不能把 NULL DACL 的空列表当成拒绝全部。
5. **“修复后旧会话缓存 ACL 判定”不能笼统成立。** 新打开操作会检查当前描述符；已打开句柄、未变的令牌与提供端授权物化缓存是不同状态。若修复删除了能力 ACE，Python 同进程的 `workspaces` 集合会阻止重新物化，需要明确失效/重建提供端；这是代码中可确认的缓存点。
6. **“无 EFS、无 ADS 就排除所有管控”不成立。** 内核过滤器不必使用 EFS 或 ADS；EPERM/EACCES 文本也不能单独识别具体原因。
7. **“干净目录生成后再复制回去可避开坏继承”不可靠。** 新建目的对象通常再次受目的目录继承影响；移动又可能保留源 ACL。必须核对最终对象权限。
8. **“只能 takeown + FullControl”过强。** 正常 owner 可直接修复 DACL，非保护文件也可通过恢复正确的父目录继承修复。protected 文件需要单独处理，接管所有权只在确有必要时使用。

## 5. 可行修复方案与建议顺序

### 5.1 现场恢复：修复用户授权及继承范围

先记录真实用户令牌、父目录和异常/正常文件的原始 SDDL，备份待调整对象 ACL，区分共享目录、显式 Deny 与组织策略。若已确认该工作区应由此用户编辑，恢复该用户或有效工作组对“此文件夹、子文件夹和文件”的适当权限；通常 Modify 即满足读写删除需求，不必一律 FullControl。

例如，由有权限的维护者针对已确认的工作区合并 `当前用户:(OI)(CI)M`，而不是替换整个 DACL。**本次夹具保留能力 ACE，仅合并这条用户继承授权后，既有非保护异常文件已恢复可读，受限 PowerShell 5.1 的 .NET 写入/读取也成功。** 实际显式 Deny、受保护子对象、共享权限和企业策略可能要求更具体处理；此结果不是通用一键脚本。

现有 protected 文件逐一核对并修复预期权限，必要时才取得所有权。不建议原记录的递归 `/inheritance:r`、全树 reset、只保留用户/SYSTEM 全权：它们会改变协作者、管理员及管控权限。也不建议单纯删除能力 ACE，因它既可能触发继承退化，也会破坏受限 shell 的工作区写入。

若修复移除了能力 ACE，需重建 provider/重启 Host 让授权重新物化；单纯新开 shell 不保证清除服务端缓存。验证应在重新打开文件后进行，并包含受限 shell、宿主 write/edit、新建子目录、原子替换及删除，而非只验证写入返回成功。

### 5.2 程序 P0：在 grant 前拒绝已知危险 ACL，提供准确诊断

建议首先实现 Windows ACL 提供端的防护，保持现有权限边界：

- 读取并区分 NULL、EMPTY、protected、ACE 继承标志和原始 Win32 错误；不能把查询失败降级成空列表继续写 ACL。
- 在合并前识别 NULL DACL，保守拒绝物化并给出配置说明，避免从“全部允许”静默变为“仅能力 SID”。
- 检查加入能力 ACE 后新对象是否会缺少普通用户/组的必要授权，识别“用户只授权此目录、能力 ACE 将成为唯一可继承 Allow”等明确危险布局。复杂组、CREATOR_OWNER、显式 Deny 和受保护后代不能靠一条字符串规则判断。
- 报告阶段是授权物化、创建、读回还是原子发布，列出受影响路径及合法能力 SID 的来源，避免误导为 DLP 或建议反复重试。
- 将授权缓存与 ACL 变化协调：根目录 ACE 被外部移除时允许重新核验/物化；根目录精确 ACE 存在也不证明整棵树健康。先保护根入口，后代仍按实际访问严格拒绝，不承诺一次预检查覆盖整个工作区或消除竞争。

这里的拒绝是对不安全的授权变更提前失败，不是把沙箱改为无限权限，也不是由程序擅自给用户提升磁盘权限。任何 preflight 都不能替代每个操作的失败处理；改动后的重验应覆盖普通继承、只作用本层、NULL/EMPTY、protected 后代、显式 Deny、LUA/管理员组和多会话缓存。

### 5.3 程序 P1：独立诊断接口与显式修复流程

可提供宿主侧只读安全描述符诊断，通过 `ctx` 服务注册并受可读取路径策略约束，返回真实错误和身份信息，而不是任意 PowerShell 命令字符串白名单。读 ACL 仍是 READ_CONTROL 授权，不能假定所有调用者都有权限。

自动修复继承或为父目录追加用户规则会改变整个工作区的权限语义，应作为有明确预览、范围、备份和恢复能力的独立操作。若后续研究“仅为新对象显式指定合法安全描述符”，必须覆盖 shell 任意脚本及原子暂存等所有创建路径；只修 write/edit 工具无法解决 shell 批量转换。

不建议取消 LUA、改成真实用户无限制 shell、为能力 SID 加读或全权、失败后自动提权，或按扩展名限制 shell 写入作为替代。能力 SID 不取代普通用户授权；WRITE_RESTRICTED 也不是任意程序可用的扩展名安全边界。

## 6. 本次实际验证

机理实验环境为现代 Windows build 26200、x64 Python 3.8.10；Python `platform` 返回的 `Windows-10` 字符串不用于将该系统认作 Win7。原版 grant 直接运行固定 reference 源码，使用 Node 22.22.2、现有 tsx/koffi 及 Win32 依赖。PowerShell 对照为系统 Windows PowerShell 5.1.26100.9711，不是 Win7 补丁版。

| 对照 | Python 实测 | 原版 grant 实测 |
|---|---|---|
| 当前用户 FullControl OI/CI 的正常目录 | 宿主、受限子进程、原子写正常 | 本次未单独执行此原版正常目录行 |
| 当前用户仅此目录 FullControl，再加能力继承 ACE | 新文件写成功、读失败；旧文件可读 | 相同 |
| 受保护 NULL DACL，再加能力 ACE | 变为能力 ACE 唯一规则，宿主新建失败 | 相同 |
| 保留能力 ACE，补用户 OI/CI Modify | 原异常非保护文件可读，受限 PS5.1 可写可读 | 原版 grant 产生的目录修复后，Python runner 的受限 PS5.1 同样成功；不冒充原版 token 的执行结果 |
| owner 对 EMPTY protected 文件直接 grant | 成功恢复可读，未 takeown | 本次未单独执行此原版行 |

本地原始载体位于仓库 `.goose/out/acl-mechanism-20261021-a/` 与 `...-c/`，含 `probe.py` 和 `observations.json`；c 另有 `upstream-grant.mjs`。两次退出均为 0，分别约 1.375 秒、2.453 秒，JSON 确认本次夹具清理完成。`...-b/` 保留首次原版调用的 ESM loader 路径错误：该轮原版没有执行 grant，不能作为两边行为匹配证据；c 改为 file URL 后才取得实际原版结果。

初次机理评估未运行 pytest 或构建 Portable，当时没有修改生产行为。迁移只读 `scripts/migration.py check` / `ready` 均退出 0，前者报告台账与固定清单有效，后者没有列出可领取任务；不将台账有效性视为本问题已修复。初次文档相对 Markdown 链接、空白及代码围栏检查通过。尚需在内网对实际工作区完成 SID 精确匹配、原始 SDDL/令牌对照，并在 Win7 对选定修复做定向验收。

## 7. 后续现场补充：账户、手动建目录与跨工作区复制

### 7.1 用户补充的事实与尚未确认的部分

用户后续说明：

- Windows 登录账户是具有管理员组成员资格的日常用户，通过 LDAP 认证登录，不是本地内置 Administrator。是否属于标准 AD 域登录、具体 Windows 用户 SID 和令牌组属性，尚未通过现场输出确认。
- 工作区是在该账户下，通过资源管理器手动创建在 E 盘的某个上级目录内；该上级目录下创建的多个工作区均反复遇到问题。
- 将存在 ACL 问题的文件放到另一个工作区后，观察到 DSH 文件操作也开始出现类似问题。用户已明确复制方式是**资源管理器 Ctrl+C / Ctrl+V，并使用新文件名**，不是剪切、同盘拖拽移动或覆盖已有同名文件。
- **尚未单独测试目标工作区中全新、无关文件是否也失败**；复制前后及 DSH 首次操作前后的 ACL 快照也尚未取得。当前不能认定整个目标工作区被复制件改变了权限。

这些是用户提供的现场描述，不是本次在内网采集或复现的结果；不要与第 6 节的独立夹具实验混为一谈。

### 7.2 LDAP、管理员成员资格和创建者的关系

如果 LDAP 登录实际对应常见 AD 域账户，NTFS 访问检查使用的是 Windows 令牌中的用户 SID、组 SID 及其属性；LDAP 认证方式本身不是“可写不可读”的直接原因。域账户是正常的权限主体，同名域账户与本地账户仍可能是不同 SID，应以实际身份核对。

具有管理员组成员资格不等于每个进程都使用完整管理员权限。UAC 配置影响宿主是否提升；本项目还会主动创建 LUA 受限子令牌，管理员组可能作为 deny-only SID，不能再依赖该组的 Allow ACE 满足正常访问检查。因此“目录只授予 Administrators 全权”可能解释宿主与 shell 的差异，但**尚未证明现场目录就是这种布局**。直接给实际用户或正常启用的业务组授权，也仍需通过受限令牌的额外写检查，不能替代工作区能力 ACE。

**自己通过资源管理器创建目录，不保证后代权限继承完整。** 创建者、owner、创建时拿到的句柄权限和后续重新打开对象的权限是不同概念。目录可能继承上级的异常布局，也可能只在本层给用户授权，或者依赖 CREATOR_OWNER、管理员组及创建令牌默认 DACL。在未取得具体 ACE 前，不能断言是哪一种。

因此，调查重点是 E 盘实际上级目录及工作区中的用户/有效组授权是否覆盖“此文件夹、子文件夹和文件”，以及子对象是否禁止继承，而不是单凭“域用户”“管理员成员”或“由我创建”判断健康。相关机制见 [Microsoft SID 属性说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/sid-attributes-in-an-access-token)和 [UAC 说明](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/how-it-works)。

### 7.3 普通复制是否会把异常 ACL 带到另一个工作区

资源管理器按默认方式将文件复制到新名字时，目的文件通常是新对象，继承**目的目录**的权限；不能把同一 NTFS 卷内移动可能保留源 ACL 的规则套用到这次已确认的复制。特定策略或保留安全描述符的复制实现可能改变结果，必须以实际前后 ACL 为准。参见 [Microsoft 复制与移动权限说明](https://learn.microsoft.com/en-us/troubleshoot/windows-client/windows-security/permissions-on-copying-moving-files)。

因此，“复制后另一个工作区也出现问题”目前优先保留以下待验证解释：

1. **目标目录也存在继承缺口。** 两个工作区可能共用同一个有问题的上级目录；新复制件按目标 ACL 创建后同样异常，并非源文件 ACL 自动传播。
2. **复制与目标工作区首次授权物化时间接近。** 复制后才首次触发 DSH 的受限 shell，目标根目录加入能力继承 ACE，暴露其已有普通用户继承缺口。第 2.1 节机制支持这种可能性，但尚无该现场的前后快照证明。
3. **问题实际上局限于复制件。** 如果复制件确实保留了异常 ACL，可能只影响该文件。当前 [FS 覆盖实现](../../dsh/fs/fs_local.py)会保留被编辑目标文件的 DACL，不保证编辑后自动修好它；这与修改整个工作区 ACL 是不同事情。

当前检查到的提供端没有“读到某文件的异常 ACL，就将其反向写到父目录或其他文件”的流程；根目录能力授权与目标文件原子覆盖是各自的路径。若目标目录在复制前确实正常，却在普通复制后、DSH 尚未操作前发生 ACL 变化，则需要继续查资源管理器策略、其他进程或内网管控，不能仅用当前 DSH 机制解释。只有普通复制保留旧 ACL 的现场证据出现后，才继续追查相应复制行为。

### 7.4 最小现场对照：定位变化时点与影响范围

使用可丢弃且获得授权的测试工作区；第一次观察先不修 ACL，不覆盖业务文件。记录源异常文件、目标工作区及其实际上级目录，在三个时点对照：

| 时点 | 应记录与验证的内容 |
|---|---|
| 复制之前，目标工作区尚未由 DSH 物化授权 | 上级目录和工作区 ACL；在 DSH 外新建独立文件，关闭后重新打开读取 |
| Ctrl+C / Ctrl+V 到新文件名之后，DSH 操作之前 | 源文件和复制件 ACL；目录 ACL 是否变化；独立文件是否仍可读 |
| 首次触发 DSH 授权及文件操作之后 | 工作区 ACL 是否新增能力 ACE；复制件和独立文件是否可读；分别用受限 shell、write/edit 新建无关文件并关闭后重读 |

如果目标工作区此前已由同一 Host 使用，单纯再开会话不构成“首次物化”对照；工作区能力 ACE 常驻，且 Host 有授权缓存。也不要为制造空白对照先删除已有能力 ACE。

在 DSH 外、使用同一实际账户运行以下**只读示例**，将路径替换为现场路径；每个时点保存输出并标明时刻、进程身份和是否提升：

```powershell
whoami.exe /user
whoami.exe /groups
icacls.exe 'E:\实际上级目录'
icacls.exe 'E:\实际上级目录\目标工作区'
icacls.exe 'E:\实际上级目录\目标工作区\复制件.txt'
$acl = Get-Acl -LiteralPath 'E:\实际上级目录\目标工作区' -ErrorAction Stop
$acl | Format-List Owner, AreAccessRulesProtected, Sddl
```

对源异常文件、复制件和对照文件也分别记录 SDDL 与查询错误。`Get-Acl` 失败不能记作空 ACL；NULL/EMPTY 的最终区分仍按第 2.2 节读取原始描述符。这里的命令没有在内网执行，新建对照文件的读写结果仍待用户现场采集。

判定时先分范围：只有复制件失败，查该文件；所有新文件失败，查目的目录继承；仅受限 shell 失败，查令牌正常授权与能力授权；DSH 未操作前父目录已经变化，扩展到外部写权限来源。受限 shell 失败本身不能证明目录无问题，也不能证明沙箱按设计禁止全部工作区写入。

### 7.5 多个工作区共用异常上级目录时的避免方式

先选择应由当前用户编辑的专用上级目录，备份其 ACL，核对真实账户 SID，然后按第 5.1 节合并该用户或有效业务组对“此文件夹、子文件夹和文件”的 Modify 授权。修复范围应是已确认的个人工作区树，不是整个 E 盘；不要通过改用本地管理员、长期提升 Desktop 或退出沙箱来替代继承修复。

非保护后代可能通过正确父级授权传播恢复；受保护目录及文件需要逐一核对。保留已有能力 ACE、合法 Deny 和其他主体授权，不使用全树 reset、递归关闭继承或批删 `S-1-4-*`。如需改在新目录工作，应选不受该异常父级继承影响、且已验证用户继承正常的专用位置；仅在同一个异常父级下新建兄弟工作区，不能保证避免复发。

修复或迁移后，应覆盖新建一级/二级子目录、复制到新名字、关闭后重读、write/edit 原子替换与受限 shell 写删。新文件创建返回成功不算完成验证。当前没有对真实 E 盘目录执行修复，也没有据此确认 LDAP、资源管理器或某款管控软件为根因。

## 8. 修复方向与 MinerU 场景

此前认可的处理方向为：**现场优先核对工程目录或专用上级目录的正常用户权限继承，产品侧加固统一的 Windows ACL 授权物化流程。** 当前候选的具体设计和交互仍需迭代，不能将该方向等同于已接受候选方案。没有调整真实工程权限或生成新发行包。

MinerU 场景补充：用户曾在工作区修改权限模式下，通过 DSH 的 pwsh 调用 Python 脚本，使用 MinerU API 转换文档并将结果写成 Markdown；生成的 Markdown 同样出现 ACL 异常。若脚本没有主动指定安全描述符，Python 写出的文件仍受 Windows 父目录继承和创建令牌影响；API 转换成功或当前句柄写入成功，不代表关闭后重新打开可读。现场脚本是否主动改 ACL、失败对象的实际描述符仍待核对，不能仅凭工具名称定责。

这说明只修 write/edit 无法覆盖 Python、shell 重定向和第三方程序的全部创建路径。也不应让读取工具提权、让 pwsh 放弃受限令牌，或在每次生成后统一追加 FullControl。现场若只有一个工程异常，优先限定该工程；多个工程共用异常上级时，再评估专用上级的继承修复，保留合法能力 ACE、Deny 和其他主体授权。

最终方案需要覆盖两条授权入口、变更前检查、当前 ACL 重验、失败与恢复边界及实际产物关闭重读。候选设计与实现独立保留在 PR，不能作为“官方已修复”或主分支/现有 Win7 发行包已具备该能力的依据。

## 9. 问题跟踪与候选状态

本问题以 `UPSTREAM-WINDOWS-ACL-001` 文档标识登记，跟踪为[issue #4](https://github.com/czh869452912/deepseek-harness-win7/issues/4)，入口见[原版已知问题](../upstream-known-issues.md)与[原版和迁移版状态](../known-differences.md)。master 仅提交问题分析和已知问题，不修改运行时，也不新增该项为已接受的机器行为例外。

独立候选包含授权预检、重验、temp 身份校验及宿主诊断/审批恢复工具，曾完成现代 Windows 定向验证（最新 x64 132 通过/1 个既有平台跳过，x86 恢复范围 25 通过）。这些结果属于候选，不能认证当前 master、真实 Win7 或既有发行包；完整代码、测试与记录随其 PR 保留。没有调用真实 MinerU 服务。

用户明确指出候选设计和理想效果不一致，要求先独立存档和评审。不能因为夹具通过就关闭 issue；最终交互、自动化程度、读写工具覆盖、已有受损文件和异常上级目录的处理仍需重新确定。

## 10. 最终方案必须保留恢复能力

命令启动前的统一拒绝也可能阻断诊断与修复 shell，使 agent 在异常工作区无法自救；不能把这种状态称作完整解决。该可用性缺口属于新增候选本身，不归因于原版。独立宿主诊断/授权恢复是已试验方向之一，尚不代表最终产品决定。最终方案应在保留沙箱边界的同时，让可读对象继续可读、正常创建产物后续可用，并提供实际可用的异常诊断与恢复流程，明确宿主权限不足、审批不可用及 protected 后代的限制。

## 参考

- [Microsoft: CreateRestrictedToken](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)：WRITE_RESTRICTED、LUA 及双重访问检查。
- [Microsoft: File Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights)：创建、继承、句柄与访问权限。
- [Microsoft: NULL DACLs and Empty DACLs](https://learn.microsoft.com/en-us/windows/win32/secauthz/null-dacls-and-empty-dacls)：NULL 与 EMPTY 的相反语义。
- [Microsoft: Automatic Propagation of Inheritable ACEs](https://learn.microsoft.com/en-us/windows/win32/secauthz/automatic-propagation-of-inheritable-aces)：既有后代传播及 NULL/EMPTY 转换。
- [Microsoft: Owner of a New Object](https://learn.microsoft.com/en-us/windows/win32/secauthz/owner-of-a-new-object)：owner 隐含 WRITE_DAC 与取得所有权。
- [原版 Windows ACL 后端说明](../../reference/packages/sandbox/sandbox-windows-acl/README.zh.md)：常驻授权、NULL DACL 和 partial enforcement 的既有限制。
