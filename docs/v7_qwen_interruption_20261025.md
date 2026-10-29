# V7 千问测试中断与费用记录

本轮 **没有开始生成样本**。计划的 21 个 V7 样本全部未开始，正确率与生成耗时没有测量值，不能写成 0/21 通过。2026-10-25 11:15（北京时间）已确认云平台显示 **No active instance**，余额 **122**。

原授权为最多 2 积分，启动前余额 135，清理时余额 122；本轮实际扣除 **13 积分，超过授权 11 积分**。原始授权和 lease 保留，没有将费用归入其他批次或扩大授权。

## 发生经过与原因

1. 10 月 24 日 22:34（北京时间）记录计费起点并启动临时实例，随后确认 Ready。
2. 打开 Notebook 的操作因自动审批服务达到 Codex 使用额度而未执行。这是审批无法完成，并非判断操作不安全。上传、bootstrap、模型身份核验与测试均未执行。
3. 原记录要求 10 月 25 日 00:14 停止计算、00:29 前销毁，但本地 lease 仅是时间约束。`launch.sh` 和运行器最多停止进程，不能触发平台销毁；本轮连 bootstrap 也未启动。未建立独立于 Codex/UI 会话的销毁机制，导致中断期间持续计费。
4. 用户恢复会话后，控制台显示实例运行约 12.65 小时、消费 13 积分。立即提交 Destroy 并确认 No active instance。只销毁本轮临时实例，没有请求删除持久卷。

这是测试操作及预算控制失败，不能归因于 Qwen 或 RTL 方案功能。此前预算防护没有覆盖会话中断，是本次超额的直接流程缺口。

平台文档说明实例闲置、关闭浏览器或退出登录均不会停止计费；销毁实例才停止计费，持久化 `/workspace` 按平台政策保留。本轮没有重新挂载核验持久盘内容。[官方销毁说明](https://amd-aim.github.io/radeon-cloud-docs/guides/destroy/)

## 仍有效的验证

| 项目 | 结果 | 能说明什么 |
| --- | --- | --- |
| 本轮本地 Icarus 参考控制 | 21/21 通过 | 冻结题库与本地判定路径正常 |
| V7 工程回归，前序已完成 | 200 通过 | 工程机制控制符合预期 |
| V7 本机 Vivado 2025.2 控制，前序已完成 | 4 个正确实现接受、2 个错误实现拒绝 | 本地控制成立，不能替代云端 2026.1 |
| V7 固定千问新样本 | 0 个开始，21 个未开始 | 正确率、速度和增益仍待测 |

V6 历史两轮的 8/21、7/21 不属于 V7，不作为本轮结果。冻结包 SHA 为 `a86e3e34926711ff7b6ee2fc9208d56bf2158155715b82a9cc25f81e7b2a48fe`，保持不变。`preparation.json` 内零实例/零调用是准备时快照，最终费用以本结案和清理证据为准。

## 重试条件

本批已关闭，不能复用原授权或重置旧 lease。重试只测同一固定 Qwen 的最新版 V7，原样基线和旧版不重跑，可复用冻结输入及已通过的本地控制。

再次产生费用前，须同时具备新的明确预算，以及独立于当前聊天存活的计费截止保障。平台有资源池决定的 Auto-reclaim，文档未将它描述为用户可设置的两小时费用封顶；本账号是否有满足预算的回收时限尚未确认，不能宣称保护已建立。[官方启动说明](https://amd-aim.github.io/radeon-cloud-docs/guides/launch/)

官方 CLI 提供销毁和状态命令，可作为后续独立清理方案的接口；仅发现该接口不等于已经登录、配置或验证了定时销毁。本次未安装或登录 CLI、未创建自动化任务、未启动新实例。[官方 CLI 实例管理](https://amd-aim.github.io/radeon-cloud-docs/cli/instances/)

## 证据

- [本次最终状态](../../output/rtl-v7-qwen-test-20261024/ACTIVE_RUN.md)、[样本状态](../../output/rtl-v7-qwen-test-20261024/outcome.json)、[费用和清理](../../output/rtl-v7-qwen-test-20261024/cleanup.json)
- [清理前控制台脱敏记录](../../output/rtl-v7-qwen-test-20261024/cloud-interruption-before-cleanup.txt)、[清理后记录](../../output/rtl-v7-qwen-test-20261024/cloud-after-cleanup.txt)
- [原始租约](../../output/rtl-v7-qwen-test-20261024/lease.json)、[原始授权](../../output/rtl-v7-qwen-test-20261024/authorization.json)
- [本地参考控制](../../output/rtl-v7-qwen-test-20261024/local-preflight/summary.json)、[V7 前序工程验证](v7_iteration_20261024.md)

![清理后余额 122，No active instance](../../output/rtl-v7-qwen-test-20261024/cloud-after-cleanup.jpg)
