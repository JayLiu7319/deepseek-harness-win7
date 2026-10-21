# 原版已知问题

本文登记 Windows ACL 已复现问题。已接受的精确行为例外仍以 [upstream-bug-exceptions.json](../migration/upstream-bug-exceptions.json) 为准；文档发现不自动等于已接受的迁移差异。

## UPSTREAM-WINDOWS-ACL-001：能力授权与原有 DACL/继承相互作用

跟踪：[issue #4](https://github.com/czh869452912/deepseek-harness-win7/issues/4)。状态：**固定原版与未修复迁移提供端均已复现，master 尚无修复；候选实现和设计另提 PR，用户反馈其效果与预期不一致，尚未接受或发布。**

两种已验证触发条件：

1. 目录对当前用户只有本层 FullControl，没有普通主体的可继承读写授权。加入 OI/CI 工作区能力 ACE 后，新文件可能只继承能力写删 ACE，导致写入完成后重新打开失败；原有显式授权文件仍可读。
2. 目录为受保护 NULL DACL。合并能力 ACE 会将允许全部访问的 NULL DACL 改成真实能力独占 DACL，宿主随后不能新建文件。

固定原版目标为 `dsh-v0.1.5-rc.3 / a4c74a91e06b00fe0b0937bde982170c526cc842`。现代 Windows build 26200 已在独立夹具中复现，Win7、LDAP/域登录或管理员成员身份不是必要前提。`S-1-4-*` 不可解析身份是提供端的正常能力 SID，不能单凭其存在认定 DLP。内网实际失败对象的 SDDL、令牌、复制影响范围及变化时点仍待采集，不能将夹具结论直接覆盖所有现场现象。

涉及固定源码：[acl.ts](../reference/packages/sandbox/sandbox-windows-acl/src/acl.ts)、[grant.ts](../reference/packages/sandbox/sandbox-windows-acl/src/grant.ts)和[workspace-sid.ts](../reference/packages/sandbox/sandbox-windows-acl/src/workspace-sid.ts)。后续官方版本的源码查询范围及限制见[机理评估第 3.1 节](research/2026-10-21-workspace-acl-mechanism-assessment.md#31-后续官方版本是否已修复)，不能将新增诊断技能等同于底层问题已完整修复。

维护方向：备份并核对工程或专用上级目录的正常用户/有效业务组可继承 Modify 授权，单独核对 protected 后代。不要以全树 reset、批删能力 SID、长期管理员运行或取消 LUA 作为通用修复。具体权限变更必须结合现场 ACL 和授权范围，不能直接执行初始记录中已被复核否定的建议。

候选的命令启动预检会阻断诊断和修复命令，这是迁移候选自身需要解决的问题，不作为原版缺陷登记。最终方案须兼顾可用性、已有文件恢复、正常产物读写和权限边界；Win7 SP1 + PS 5.1 及实际 LDAP/域账户验收仍待完成。

参见[原版与迁移版状态](known-differences.md)、[机理与现场分析](research/2026-10-21-workspace-acl-mechanism-assessment.md)及[初始记录](research/2026-10-21-acl_issue_analysis.md)。
