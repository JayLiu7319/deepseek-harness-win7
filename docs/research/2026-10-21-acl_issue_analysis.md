# 批量生成文件 ACL 权限异常（"可写不可读 / 完全拒绝访问"）诊断与修复指引

> **问题跟踪**：[issue #4](https://github.com/czh869452912/deepseek-harness-win7/issues/4)。本文件保留初始现场记录和当时建议，不代表当前修复方案。主分支尚未合入修复；候选实现另提 PR，用户反馈当前设计与理想效果不一致，尚未接受或发布。

> **2026-10-21 后续复核**：本文保留最初现场记录及当时推断；后续源码对照、实际 ACL 实验、账户与跨工作区复制分析见[工作区 ACL 机理与修复评估](2026-10-21-workspace-acl-mechanism-assessment.md)，以该评估中的证据边界和修复建议为准。下文将不可解析 `S-1-4-*` 直接归因于 DLP、将空保护 DACL 认作 owner 无法修复的死锁、以及建议全树重置/关闭继承等结论已被复核修正，不应作为当前操作依据。

> 本文档是一份**自包含**的问题分析与处理指引：不依赖任何具体工作目录、文件名或现场数据，可直接提供给智能体（agent）或人工排障使用。文中出现的文件名均为占位示例（如 `example_output.md`），涉及的 SID 为模式化示例。
>
> 适用场景：脚本/工具在某目录下批量生成文件（如 PDF→Markdown 批量转换）后，**新生成的文件全部无法读取**——创建者、owner、管理员一律被拒；而同一目录下**旧文件、源文件正常**。

---

## 0. 一句话结论

新文件全量无法读取、旧文件正常，根因通常是：**目录 ACL 被混入了一条"不可解析 SID"的继承 ACE（污染 ACE），导致新文件继承到的 DACL 上没有任何允许读取的 ACE**（甚至连 owner 自己的授权都没有）。常见修复手段（`icacls /reset`、`Set-Acl`）会因"空 + 受保护 DACL"或 DLP 驱动拦截而失败；**真正有效的是 `takeown` + 对文件直接 `icacls /grant` 注入显式 FullControl ACE**。

---

## 1. 症状识别（逐条核对）

出现以下**任意多条**组合，即命中本问题：

1. 由生成/转换脚本**新产出**的文件，所有进程（编辑器、命令行、owner 本人）都无法打开。
2. VSCode 报错形如：
   `NoPermissions (FileSystemError): Error: EPERM: operation not permitted, stat 'F:\...\example_output.md'`
   （注意是 **EPERM** 而非 EACCES，常被误解为"驱动/加密拦截"，实为 DACL 无读取授权）。
3. PowerShell `Get-Content` 报 `Access to the path ... is denied` / `UnauthorizedAccessException`；`[System.IO.File]::Open` 同样被拒。
4. **时间分界线清晰**：同目录下某时间点之前创建的文件全部正常，之后创建的文件全部不可读；源文件（如 PDF）正常，生成物（如 MD）异常。
5. `icacls <file>` 报"拒绝访问 / Access is denied"，或提示 `No mapping between account names and security IDs was done.`（存在无法映射的 SID）。
6. `icacls <dir> /reset /t` 直接失败（"拒绝访问"），即使以管理员身份运行。
7. `attrib` 无 `E`（EFS 加密）标志、文件无多余 NTFS 流、资源管理器里文件名不是绿色——**排除"EFS 加密"和"备用数据流"两种情况**，锁定为纯 ACL 问题。
8. 目录本身可列目录、可新建文件，但**新建后立即读不了**（新建即坏，说明问题在"继承源"，不在个别文件）。

---

## 2. 根因与因果链

### 2.1 Windows 文件权限继承机制（背景）

新文件创建时，Windows 会继承父目录中带 `ContainerInherit/ObjectInherit`（即 CI/OI）标志的 ACE，并写入创建者信息。正常情况下新文件的 DACL 至少包含：`SYSTEM: FullControl`、`创建用户: FullControl`、以及一条当前登录会话 SID 的 ACE——**任何主体有至少一条读取授权**。

### 2.2 问题发生的前提：目录上存在"污染 ACE"

某些企业终端管控软件（文档 DLP / 文档加密类，常见如亿赛通、天锐绿盾、IP-Guard 等）会在目录 ACL 上写入一条：

- **IdentityReference 是一个不可解析的 SID**（模式如 `S-1-4-<unique>-<unique>`，`NT NON_UNIQUE` 权威；`Translate` 无法映射为任何账户名）；
- **权限组合只有** `DeleteSubdirectoriesAndFiles, Write, Delete, Synchronize`（可写、可删，**唯独不可读**）；
- **带 `ContainerInherit, ObjectInherit` 继承标志**（会传染给该目录下所有新建对象）。

这条 ACE 的存在本身不破坏目录（目录仍可列出、可创建），但它**改变了新文件继承到的权限集合**：如果正常 ACE（SYSTEM/用户 FullControl）没有被一起继承下来，新建文件得到的 DACL 就只有这条"可写不可读"的 ACE——于是**所有主体（含 owner）都没有读取授权**。

### 2.3 终极形态：空 + 受保护的 DACL

部分管控场景会更彻底：文件创建后被设置成

- `AreAccessRulesProtected = True`（禁用继承），且
- DACL 中 **Access 列表为空**（零条 ACE）。

即"空 DACL + 保护"。这种文件在 Windows 安全模型下**不授予任何主体任何权限**，连 owner 都读不了；而 owner 想改写 ACL 需要走 `WRITE_DAC`，面对空保护 DACL + DLP 实时拦截时也常常失败——形成**死锁**。

### 2.4 为什么"源文件正常、生成物异常"

源文件（PDF/Office）在污染发生前创建，继承了**污染前的正常目录 ACL**，所以正常；批量生成物（MD）在污染发生的时间窗口内创建，继承的是**污染后的目录 ACL**，所以集体中招。这就是"时间分界线"现象的来源。

---

## 3. 排查 SOP（智能体 / 人工均可照做）

按顺序执行，每步都有判定分支。**所有 ACL 查证命令建议使用等价 PowerShell 的 `Get-Acl` + `icacls` 双通道交叉验证**。

### 步骤 1：确认症状范围（区分"哪些坏、哪些好"）

```powershell
# 列出目录内所有目标文件，逐个测试可读性
Get-ChildItem -File "F:\path\to\dir\*.md" | ForEach-Object {
  try { $null = Get-Content -LiteralPath $_.FullName -TotalCount 1 -ErrorAction Stop; "READ-OK   $($_.Name)" }
  catch { "READ-DENY $($_.Name)" }
}
```

- 若"源文件/旧文件 OK、生成物全 DENY"→ 命中本问题，继续步骤 2。
- 若**全部** DENY（包括旧文件）→ 可能是更高层（整目录/父目录/卷）权限问题，另查目录 ACL。

### 步骤 2：读单个异常文件的 ACL（核心证据）

```powershell
$p = 'F:\path\to\dir\example_output.md'
$a = Get-Acl -LiteralPath $p
"owner     = $($a.Owner)"
"protected = $($a.AreAccessRulesProtected)"
$a.Access | ForEach-Object {
  '{0} | {1} | {2} | inherited={3} | flags={4}' -f $_.IdentityReference, $_.AccessControlType, ($_.FileSystemRights -join '+'), $_.IsInherited, $_.InheritanceFlags
}
```

**判定**：
- `protected=True` 且 `Access.Count=0` → 空+受保护 DACL，最极端形态（见 2.3）。
- `Access` 中只有 `S-1-4-...` 一条 Allow `Write,Delete` → 污染 ACE 直接落在文件上。
- 有 `FACRI\xxx FullControl` 但仍读不了 → 怀疑 DLP 驱动实时拦截（见步骤 5）。

### 步骤 3：扫描目录与全树，定位污染源 ACE

```powershell
# 目录级：哪条 ACE 带 CI/OI 继承标志且不可解析？
(Get-Acl -LiteralPath 'F:\path\to\dir').Access | ForEach-Object {
  '{0} | {1} | inherit={2}' -f $_.IdentityReference, ($_.FileSystemRights -join '+'), $_.InheritanceFlags
}

# 尝试解析可疑 SID；解析失败 = 污染/管控 SID 的特征
try { ([System.Security.Principal.SecurityIdentifier]'S-1-4-<unique>-<unique>').Translate([System.Security.Principal.NTAccount]).Value }
catch { 'UNRESOLVABLE SID（典型管控标记）' }

# 全树扫描：哪些对象仍带 S-1-4* 或 Deny ACE 或 ACL 不可读
Get-ChildItem -LiteralPath 'F:\path\to\dir' -Recurse -Force | ForEach-Object {
  try {
    $a = Get-Acl -LiteralPath $_.FullName
    $bad = $a.Access | Where-Object { $_.IdentityReference -like 'S-1-4*' -or $_.AccessControlType -eq 'Deny' }
    if ($bad) { 'DIRTY: ' + $_.FullName }
  } catch { 'ACL-UNREADABLE: ' + $_.FullName }
}
```

### 步骤 4：排除"加密 / 附加数据流"两个干扰项

```powershell
attrib "F:\path\to\dir\example_output.md"          # 无 E 标志 → 非 EFS 加密
Get-Item "F:\path\to\dir\example_output.md" -Stream *   # 仅 $DATA → 无 ADS 标记
```

两项都阴性 → 纯 ACL 问题，进入修复。

### 步骤 5：区分三层拦截（决定修复手段）

| 层级 | 特征 | 处置 |
|---|---|---|
| A. 目录 ACL 污染 | 目录上有不可解析 SID 的 CI/OI ACE | 修复目录（见 §4 方案一） |
| B. 文件 DACL 空/坏 | 文件 protected=True + 0 ACE，或仅 S-1-4 写删 ACE | 修复文件（见 §4 方案二） |
| C. DLP 驱动实时拦截 | ACL 显示 owner 有 FullControl 但仍 EPERM；`attrib`/`icacls` 均被"拒绝访问" | 单靠 ACL 命令无效，需管控软件解密/授权，或联系 IT；可尝试用**普通用户态进程**复制文件后在新位置读取 |

> 判断技巧：若**对正常文件的读测试也偶发失败**、或 ACL 显示正常却仍拒绝，优先怀疑 C 层（驱动）。

---

## 4. 修复方案（需管理员权限的 PowerShell 窗口执行）

### 方案一：清理目录级污染 + 重建干净继承（治本）

```powershell
# 1) 取回所有权（/r 递归、/d y 跳过确认）
takeown /f "F:\path\to\dir" /r /d y

# 2) 重置整个目录树 DACL 为继承自父（若 /reset 因空保护 DACL 失败，跳过本步不 panic）
icacls "F:\path\to\dir" /t /q /c /reset

# 3) 重建：关闭继承并显式授予 用户 + SYSTEM FullControl（OI)(CI 让子对象继承）
icacls "F:\path\to\dir" /t /q /c /inheritance:r /grant "DOMAIN\user:(OI)(CI)F" "NT AUTHORITY\SYSTEM:(OI)(CI)F"
```

### 方案二：直接修复受影响文件（本问题最有效、最直接的解法）

> 方法 A（优先）：`takeown` + `icacls /grant` 给文件注入显式 FullControl ACE。
> 该方法对"空+受保护 DACL"和"仅 S-1-4 写删 ACE"两种形态都有效，因为它是**对文件本身写 ACE**，不依赖继承。

```powershell
Get-ChildItem "F:\path\to\dir\*.md" -File | ForEach-Object {
  takeown /f $_.FullName | Out-Null
  icacls $_.FullName /grant "DOMAIN\user:(F)" /T
}
```

> 方法 B（若 A 失败）：PowerShell Set-Acl 注入——注意必须用**无继承标志**的规则（文件 ACE 不能用 ContainerInherit）；若报 UnauthorizedAccess，回退到方法 A。

```powershell
Get-ChildItem "F:\path\to\dir\*.md" -File | ForEach-Object {
  $acl = Get-Acl -LiteralPath $_.FullName
  $acl.SetAccessRuleProtection($false, $true)   # 解除保护（保留现有 ACE）
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule('DOMAIN\user','FullControl','Allow')
  $acl.AddAccessRule($rule)
  Set-Acl -LiteralPath $_.FullName -AclObject $acl
}
```

### 修复后验证

```powershell
# 全部目标文件应 READ-OK
Get-ChildItem "F:\path\to\dir\*.md" -File | ForEach-Object {
  try { $null = Get-Content -LiteralPath $_.FullName -TotalCount 1 -ErrorAction Stop; "READ-OK   $($_.Name)" }
  catch { "READ-DENY $($_.Name)" }
}
# 抽查 ACL：owner 名下应有一条显式 FullControl
(Get-Acl -LiteralPath 'F:\path\to\dir\example_output.md').Access
```

---

## 5. 常见失败手段及原因（避免走弯路）

| 手段 | 结果 | 原因 |
|---|---|---|
| `icacls <dir> /reset /t` | 失败（拒绝访问） | 对被保护且空/坏的 DACL，icacls 无法改写（"empty protected DACL" 死锁） |
| `icacls /inheritance:r /grant` **只针对目录** | 目录生效，文件仍拒 | 文件 DACL `protected=True`，不随目录重新继承 |
| PowerShell `Set-Acl`（owner 身份） | 可能报 UnauthorizedAccess | DLP 驱动拦截 ACL 写；或运行令牌受限制 |
| 给目录 ACL 追加规则（不动文件） | 新文件好转，旧文件依旧 | 旧文件是 protected，不会重新继承 |
| `takeown` 单独执行 | 只改 owner，不解锁 DACL | owner 不自动等于授权；但它是后续 icacls 的前提 |
| 全量 `attrib` 检查 | 无 E 标志 | 不是 EFS，纯 ACL 问题（排除项） |
| 判断"是加密"而终止 | 误判 | 无加密标志、无 ADS，实为 ACL 无读取授权 |

**一句话**：只要文件的 DACL 上**没有允许你读取的 ACE**，任何"改目录、改继承"的操作都救不了它——必须**直接往文件上写 ACE**（`takeown` + `icacls /grant`）。

---

## 6. 预防与长期方案

1. **批量生成脚本输出到"干净目录"，再拷贝回目标目录**：拷贝（非移动）会给新位置文件重新分配目标目录的 ACL，避开污染继承源。
2. **生成后自检**：脚本写完每个文件后立即尝试读取一次，失败即警告（附修复命令）。
3. **识别并隔离管控软件**：若目录反复出现不可解析 SID 继承 ACE（文件名常带特定管理前缀等特征），是 DLP/文档管控软件在改写 ACL。联系 IT 确认策略；转换类工作流建议在管控外目录进行或申请放行规则。
4. **建立修复脚本**：将 §4 方案一+方案二保存为 `repair_acl.ps1`，复发时一键执行（需管理员）。

---

## 7. 智能体（DSH/harness）环境注意事项

在 DSH 等沙箱化智能体环境里排查本问题，还要注意以下环境因素，避免误判：

1. **沙箱策略拦截 ACL API**：`Get-Acl`/`Set-Acl` 可能在 `workspace-write` 模式下被策略拦截（报 `file access denied under workspace-write mode`）或返回不完整结果（如 Access 列表为空、owner 为空——**这是拦截假象，不是文件真为空**）。此时应**以更宽权限（如 danger-full-access）重试同一命令**，用真实用户令牌重新读取以拿到准确 ACL。
2. **沙箱会话缓存旧访问判定**：修复后沙箱进程可能仍按启动时的旧缓存拒绝访问（表现为"修复了但还读不了"）。**验证是否真修复，应优先用刚启动的进程/新窗口，或直接看 ACL 结构**，不要被旧会话的持续 DENY 误导。
3. **沙箱探测文件会污染现场**：在异常目录里做"新建文件"对照实验时，创建出的探测文件同样会继承坏 ACE 而无法删除。**修复完成后应清理探测文件**；若删不掉，交给管理员窗口 `takeown` + 删除。
4. **区分"沙箱看不到"和"真的坏"**：诊断命令输出需交叉验证（`icacls` 与 `Get-Acl` 对照），单通道结果可能因沙箱而失真。
5. **不要自行用 `Set-Acl` 大规模改 ACL**：改 ACL 属高影响操作，应输出明确的**人工管理员命令**让用户执行，而不是在沙箱内直接写。
6. **"write 工具通道"与"shell 通道"权限模型不同（重要）**：同样的文件创建操作，走 DSH 的 **write/edit 工具**（harness 后端持有工作区写授权，代理写入）与走 **pwsh/任意命令通道**（受限沙箱令牌，`BUILTIN\Administrators` 常为 `Group used for deny only`）表现可能**截然相反**：
   - 实测对照：目录 ACL 已修复（czh7885 FullControl 且继承完好）后，**DSH write 工具**创建的文件成功、可读、ACL 正常；而同一目录下 **pwsh 内 `.NET WriteAllText` / `Set-Content` / `New-Item` 三种方式全部 Access denied，文件未创建成功**。
   - 结论：**"shell 里建文件失败"不代表目录 ACL 有问题**，它可能只是沙箱对任意命令通道的文件策略降权。排查时要用 write 工具或真实用户进程做创建性验证，不要用 shell 通道的结果反推"目录还是坏的"。
   - 这也解释了为何"修好 ACL 后，DSH write 工具写出的分析文档一切正常，而 pwsh 新建文件仍被拒"——两者权限来源不同。

---

## 8. 面向 DSH/harness 本身的改进建议（供维护者参考）

基于本次排障经历，harness 可从以下方向优化，降低同类问题的排障成本：

1. **提供只读 ACL 诊断入口**：在沙箱内允许受限的 `Get-Acl`-等价查询（读安全描述符是低风险诊断操作），避免"为了诊断被迫提权/被策略拦截"的两难。
2. **启动时工作区 ACL 自检**：环境初始化时扫描工作区根目录 ACL，若发现不可解析 SID 的 CI/OI 继承 ACE（管控污染特征），在会话开始时输出预警，注明"此后新建文件可能不可读"。
3. **沙箱令牌贴近真实用户**：尽量用真实用户（非受限/降权）令牌运行文件操作，使 ACL 判定与用户侧一致，减少"沙箱缓存旧判定"导致的修复假象。
4. **文件操作结果标准化**：对"创建/写入成功但随后读失败"的情况，返回结构化诊断（如提示"文件可能缺少读取 ACE，父目录存在污染继承"），帮助模型快速定位。
5. **提供修复命令模板注入**：检测到空保护 DACL 时，可直接给出 §4 方案二的管理员命令作为建议动作，减少来回试错。

---

## 8.5 DSH 沙箱配置评估（本次实践后的建议）

**目标**：在"安全（不越权、不破坏）"与"可用（能正常读写工作区、能准确诊断 ACL）"之间取得平衡。

### 现状（本次会话观察到的行为）

| 通道 | 读（已修复目录） | 写（已修复目录） | ACL 查询 | 说明 |
|---|---|---|---|---|
| DSH write/edit 工具 | ✅ | ✅ | 间接 | harness 后端持工作区授权，代理写入，结果是"真实用户"效果 |
| pwsh（workspace-write 模式） | ✅ 读 | ❌ 新建被拒 | ⚠️ 被拦截/返回空 | 受限令牌（`BUILTIN\Administrators` = deny only），对任意命令通道更严格 |
| pwsh（escalated danger-full-access） | ✅ | ✅（需人工批） | ✅（需人工批） | 需审批，仅单次 |

### 建议（按优先级）

1. **【高】区分"任意命令通道"与"受管工具通道"的写权限**：推荐保持现状——任意命令（pwsh）默认不授予目录写权限，避免模型借 shell 越权改动工作区；文件产出统一走 write/edit 工具（已良好工作）。若要放宽，建议仅对**明确的工作区路径**、且**追加白名单扩展名**开放，而不是全局放开。
2. **【高】增加"只读诊断"子模式**：在 workspace-write 模式内，对 `Get-Acl`/`icacls` 这类**只读 ACL 查询**默认放行（当前需提权到 danger-full-access 才能拿到准确 ACL，且易被误判为"文件真的空/坏"）。这能显著降低排障成本，且不扩大写权限。
3. **【中】写权限与 ACL 自检联动**：当工作区目录存在"污染 ACE"（不可解析 SID + CI/OI）时，写操作前先给出预警/阻断建议，而非让模型反复试错后才发现。
4. **【中】会话级令牌刷新**：若修复发生在会话中期，让沙箱子进程能感知 ACL 变化（或提示重启会话），避免"旧令牌缓存"导致假阴性。
5. **【低】探测文件生命周期管理**：沙箱做"新建文件"诊断实验时，自动记录创建的探测文件，并在会话结束时清理（或提示用户），避免遗留无法删除的文件污染现场。

**总体判断**：本次问题**根因不在沙箱**（是目录被管控软件污染 + 文件空保护 DACL），沙箱本身未误伤；但**"只读 ACL 诊断需提权"和"shell 通道写拒绝易被误读为目录故障"两点值得优化**。不建议为了本次场景全面放开任意命令通道的写权限（安全收益/成本比不划算）。

---

## 9. 命令速查表

| 目的 | 命令（管理员窗口，`DOMAIN\user` 替换为实际账户） |
|---|---|
| 确认症状范围 | `Get-ChildItem -File "路径\*.md" \| % { try { $null=Get-Content $_.FullName -TotalCount 1 -EA Stop; "OK $($_.Name)" } catch { "DENY $($_.Name)" } }` |
| 读文件 ACL | `(Get-Acl "文件").Owner` / `(Get-Acl "文件").AreAccessRulesProtected` / `(Get-Acl "文件").Access` |
| 看目录可继承 ACE | `(Get-Acl "目录").Access \| % { "$($_.IdentityReference) | $($_.FileSystemRights) | $($_.InheritanceFlags)" }` |
| 排除加密/ADS | `attrib "文件"`、`Get-Item "文件" -Stream *` |
| 修复目录树 | `takeown /f "目录" /r /d y` → `icacls "目录" /t /q /c /inheritance:r /grant "DOMAIN\user:(OI)(CI)F" "NT AUTHORITY\SYSTEM:(OI)(CI)F"` |
| 修复单/批文件 | `takeown /f "文件"` → `icacls "文件" /grant "DOMAIN\user:(F)" /T` |
| 验证 | 重跑"确认症状范围"命令 + `(Get-Acl "文件").Access` |

---

## 附：本次典型案例（脱敏复述）

- 现场：某工作区根目录存放一批 PDF 与配套 Office 文档；用本地自用转换脚本批量将 PDF 转为 Markdown 输出到同目录（脚本本身是普通 `open(..., "w")` 写文件，无任何 ACL 逻辑，**脚本非问题来源**）。
- 现象：当天批量生成的 11 个 .md 全部无法读取（VSCode EPERM / Get-Content Access denied），同日之前的旧 .md 与所有 PDF 正常；目录可列、可新建，但新建即坏。
- 证据链：
  - 目录 ACL 含一条**不可解析 SID（S-1-4 权威）**、权限仅 `Write,Delete`、**带 CI/OI 继承标志**的 ACE；
  - 异常 .md 的 `AreAccessRulesProtected=True`、Access 列表为空（或仅剩该 S-1-4 ACE），**无任何读取授权**；owner 均为当前用户；
  - `attrib` 无 E、无 ADS → 排除加密；`Translate` 解析失败 → 管控标记特征；
  - `icacls /reset /t` 失败、「`Set-Acl` 循环」失败（脚本未用 -ErrorAction Stop 导致误报成功）；
  - **`takeown` + `icacls <文件> /grant "DOMAIN\user:(F)" /T` 后全部恢复可读**，清理目录污染 ACE 后根目录恢复干净。
- 结论：`mineru`/转换工具无辜，根因是**目录被写入管控型污染 ACE（疑似企业 DLP/文档管控软件），把"不可读"的 DACL 传染给了继承它属性新建的文件**。
