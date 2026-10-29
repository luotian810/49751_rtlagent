# 原样公开自测材料的来源

上游公开仓库：[Vickyiii/rtlagent2026](https://gitee.com/Vickyiii/rtlagent2026)。

本地来源为 `D:/fgpa/rtlagent2026`，本次读取并复制公开任务的日期为 **2026-10-04**。
判定器文件于 2026-10-02 复制，内部上游来源记录继续保留在原样的
`judge/PROVENANCE.md` 中；此文件不替换或修改那份记录。

2026-10-19 对照上游 `f7a8bd465c2a820e006c7a00ecc7df468974635b` 复核：
同步更新 `tasks/README.md`，其余公开题内容与判定器内容均未变化。

## 内置文件

| 上游路径 | 此目录下的路径 | 处理 |
| --- | --- | --- |
| `selftest/judge.py` | `judge.py` | 原样复制 |
| `selftest/judge/veval-judge` | `judge/veval-judge` | 原样复制 |
| `selftest/judge/l3_synth.tcl` | `judge/l3_synth.tcl` | 原样复制 |
| `selftest/judge/PROVENANCE.md` | `judge/PROVENANCE.md` | 原样复制 |
| `tasks/README.md` | `tasks/README.md` | 原样复制 |
| `tasks/ex01_popcount8/` | `tasks/ex01_popcount8/` | 全部实际文件原样复制 |
| `tasks/ex02_detect_1101/` | `tasks/ex02_detect_1101/` | 全部实际文件原样复制 |
| `tasks/ex03_lfsr8/` | `tasks/ex03_lfsr8/` | 全部实际文件原样复制 |

每道题目录包含 `prompt.txt`、`task.json`、`top.txt`、`ref.sv`、`tb.sv` 和
`reference/solution.sv`。文件名与字节内容均保持上游版本，不按模型生成结果改写参考答案或测试台。

## 使用边界

这些是**上游公开样例**，不是隐藏评测题集。复制目的是使工程 ZIP 可以独立运行
`scripts/official_selftest.py --reference`、`--generated` 或 `--solution-manifest`。
`--tasks` 默认指向此处，仍可显式覆盖。

`ref.sv`、`tb.sv` 和 `reference/solution.sv` **仅用于离线自测判定**。
它们没有接入生成智能体的输入，也不能用于生成答案检索。生成智能体仍只根据题面和自有技能产生设计及自测测试台。

本地适配器保留原判定逻辑，仅处理本机工具启动、归档及环境错误说明；本机版本与赛事环境差异继续在结果中明确标注。
来源完整性测试在相邻上游仓库存在时逐文件比较字节内容；独立 ZIP 没有相邻仓库时明确跳过来源对比，仍检查内置材料是否完整。
