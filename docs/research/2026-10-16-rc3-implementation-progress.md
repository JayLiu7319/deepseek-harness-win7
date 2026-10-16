# rc.3 分阶段实施记录

本记录推进 [rc.3实施路径](2026-10-16-rc3-baseline-implementation-assessment.md)。活动pin在共享合同与消费者稳定前仍为rc.1，候选发现或单项定向通过不构成rc.3发行资格。Desktop继续按指定Electron22与Standard/AIO方案。

## R01：候选发现工具与输入审查

`scripts/candidate_inventory.py`以显式base/target读取Git对象，不移动checkout或修改活动台账。它建立目标manifest归属、去除devDependencies的反向运行依赖、目标源码中的literal profile roots、bundle/preset声明及条件位置。条件声明保持待运行验证，Loader注册和依赖可达性不提升为激活证据。

从实际 `verify_release.py` AST取得21组Source配置和82个配对驱动，记录配置/驱动原始SHA、literal旧pin和目标路径匹配；继承配置和导入helper仍需逐合同审查。结果见 [discovery-summary.json](../../migration/candidates/rc3/discovery-summary.json)，全量观察保存在本次自有输出目录。

定向验证覆盖新CLI/输出保护、Git对象与任意base/target、subpath和dev-only依赖、未知ref拒绝、非literal profile拒绝、旧发现消费者与原差分观察器：**39 passed**，Python3.8.10，17.74秒。命令、完整日志及XML位于 `.goose/out/rc3-r01-20261016/inventory-pytest.*`。未重复运行全量pytest或构建Portable。

独立rc.3 Source位于 `.goose/out/rc3-source-20261016`；frozen-lockfile安装完成，`CI=true`只使用上游支持的hook跳过，不修改上游源码。官方完整构建及profile实际激活结果在后续条目追加，不能把静态发现当作R01全部完成。

## 输出与磁盘管理

开始前磁盘余量约184GB。先执行既有 `process_artifact_retention.py`，其所有权/结束状态/字节核验没有发现新增可回收项目，未删除未知输出或未解决失败。完整清理观察位于 `.goose/out/rc3-r01-20261016/history-retention.json`。

本批定向测试继续使用conftest提供的新短工作区和自动合成回执清理。日志/XML/真实Source观察保留；后续大批复制、构建或统一门禁前重新核对空间，已完成的可重建夹具按既有规则回收。禁止按目录年龄或通配符整体清空历史。
