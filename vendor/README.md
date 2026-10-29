# 官方 RTL 自测判定器副本

`rtlagent2026_selftest/` 内以下文件从本机 `D:/fgpa/rtlagent2026/selftest/` 原样复制，未编辑判分逻辑：

- `judge.py`
- `judge/veval-judge`
- `judge/l3_synth.tcl`
- `judge/PROVENANCE.md`

另外，`rtlagent2026_selftest/tasks/` 包含上游三道公开题及其说明，完整原样复制；
文件清单与使用边界见 [PROVENANCE.md](rtlagent2026_selftest/PROVENANCE.md)。
自测默认使用该内置目录，因此解压工程后不需要另行取得相邻的上游仓库。
也可以用 `--tasks <目录>` 显式改用其他符合上游布局的离线题集。

复制日期：2026-10-02。公开来源：[RTL track 参考仓库](https://gitee.com/Vickyiii/rtlagent2026)。上游内部来源和提交号见原样保留的 `judge/PROVENANCE.md`。

2026-10-19 已对照 RTL `f7a8bd4`：同步题目说明 README；判定器及三道公开题代码、参考答案与测试台内容未变化。

判定器相关 Git 可执行位变化不改变判分逻辑，保留既有来源记录。新版协议、评分与提交要求以 [更新说明](../docs/upstream_update_20261019.md) 链接的官方文档为准。项目根目录的官方 `baseline.py` 与 `run_baseline.sh` 已按 `f7a8bd4` 单独同步原样版本，不属于本目录中的判定器。

`scripts/official_selftest.py` 动态导入副本，仅替换 `veval-judge.run()` 和版本探测函数，让 Windows 可以启动 `.bat` 工具、处理超时进程树并保留日志。任务布局读取和报告输出位于适配层；分级仍调用上游 `judge()` 与 `judge.py._translate()`。

规则保持为：DUT 严格分析、参考装置放松分析、`xelab -timescale 1ps/1ps`、固定仿真种子 0、`Mismatches: 0` 且采样数大于 0、无仿真超时，最后调用原始综合 Tcl。资源、WNS 与推算 Fmax 仅作记录，不新增时序达标条件。

**这是公开样例的本地复现，不是比赛官方成绩。** 当前本机安装 Vivado 2025.2；公告指定版本为 2026.1，最终须在指定环境复验。本工具不使用模型或 Key，也不向智能体提供参考测试台。内置参考实现和测试台仅由 `scripts/official_selftest.py` 离线评测读取，不接入 `agent.main` 的生成输入。
