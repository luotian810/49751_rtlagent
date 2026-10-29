# V6 固定千问复测结果（2026-10-24）

本轮 **7/21 个样本通过独立功能判定，全部达到 L3**；前一轮相同 V6 为 8/21。本轮没有新增通过题，`practice/p05_detect1011` 从 L3 变为 L1；`public/ex02_detect_1101` 从 L0 变为 L1，仍未通过功能。

被测智能体仍为 `2026.10.24-v6-qwen-only`。11 个 agent Python/阶段规则文件与前一轮、当前工程均一致，模型配置、题面与独立判题材料核对可比；最近新增的是 Codex 操作技能，没有进入被测千问提示词。因此这是同版本新样本的重复性观察，不能写成新版本提升或把两轮最好结果合并。

## 主要结果

| 观测项 | 前一轮 V6 | 本轮 V6 复测 |
| --- | ---: | ---: |
| 每题一次的新样本 | 21 | 21 |
| 独立功能通过 / L3 | 8 | 7 |
| L0 / L1 / L2 / L3 | 4 / 9 / 0 / 8 | 3 / 11 / 0 / 7 |
| 生成、自检与修复累计耗时 | 1041.527 s | 1157.822 s |
| 模型调用 | 61 | 65 |
| 计划初稿合法 | 1/18 | 2/18 |
| 计划最终合法 | 5/18 | 7/18 |
| 实际执行自检 | 5/21 | 7/21 |
| 最终候选自检通过 | 4/21 | 4/21 |
| 正确参考被生成 TB 接受 | 4/5 | 4/7 |

本轮累计生成过程增加 116.295 秒，约 **11.2%**。该计时不含实例准备和外部判题；两轮分别运行且每题一次，不能据此确定算法或推理吞吐变化。没有运行时代码变化，也没有功能提升证据。

| 题集 | 本轮功能通过 |
| --- | ---: |
| gen_v4 | 0/6 |
| practice | 3/6 |
| gen_v2 | 2/6 |
| public | 2/3 |

18 个计划中，7 个最终合法；另外 11 个未形成可执行计划，其中一题格式恢复在 47.7 秒预算处超时。计划生成及格式恢复共 34 次调用、720.097 秒，占模型调用累计时间 **68.3%**。占比较上轮 72.3% 低，但绝对耗时反而增加 20.008 秒，不能写成该环节提速。

本地 Icarus 用正确参考复核了全部 7 套实际执行的生成 TB：4 套接受，3 套误拒绝。两轮共同的 5 套控制均为 4/5；新增的两套控制都误拒绝，因此 4/5 与 4/7 的覆盖集合不同。该控制不改变云端判级，也不证明随机覆盖充分。详细机制与根因见 [失败归因](../../output/rtl-v6-qwen-retest-20261024/FINDINGS.md)。

## 模型、环境与费用

- 固定 `Qwen3-14B-Q4_K_M`，权重 revision `c75e7b2d0234068f674a1bacf548ea32e27ccd29`，SHA256 `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0`，大小 9001752960 字节。实际文件、服务进程和本地端点绑定检查通过。
- llama.cpp `0.4.0-dev build 1 (f114f91)`、单槽、32768 上下文、thinking=false，agent temperature=0.2。Vivado 2026.1、器件 `xczu3eg-sbva484-1-e`、5 ns，单题开发预算 240 秒，进程上限 250 秒，最多 3 轮。
- 21/21 云端正确参考达到 L3，独立判题环境错误 0。模型调用有 1 次格式恢复超时，已保留；其余调用不代表都产生了有效计划。
- 整卡每 5 秒采样共 448 次，0 采样错误，观测峰值 **14,858,543,104 字节（14.8585 GB）**，未超过 32 GB。周期采样不是硬件高水位或完整长上下文压力测试。
- 本轮授权最多 2 积分，实际 **1 积分**，余额 136→135。已导出并核验证据，云平台确认 **No active instance**，持久化 `/workspace` 保留。

这些题参与过开发，本轮仅是开发回归和重复性测量；没有重跑旧版或官方基线，也不是未见题、正式多次 pass@1 或正式比赛成绩。

## 逐题结果

| 任务 | 等级 | 独立功能 |
| --- | --- | --- |
| gen_v4/v4_01_rotate12 | L0 | 失败 |
| gen_v4/v4_02_signed_addsub6 | L0 | 失败 |
| gen_v4/v4_03_negedge_mod7 | L1 | 失败 |
| gen_v4/v4_04_group_sum3 | L1 | 失败 |
| gen_v4/v4_05_enabled_1101 | L1 | 失败 |
| gen_v4/v4_06_readyvalid_fifo2 | L1 | 失败 |
| practice/p01_priority8 | L3 | 通过 |
| practice/p02_rotate8 | L0 | 失败 |
| practice/p03_sat_counter4 | L3 | 通过 |
| practice/p04_shift8 | L3 | 通过 |
| practice/p05_detect1011 | L1 | 失败 |
| practice/p06_serial_parity8 | L1 | 失败 |
| gen_v2/v2_01_signed_sat8 | L3 | 通过 |
| gen_v2/v2_02_counter_priority | L3 | 通过 |
| gen_v2/v2_03_elastic_buffer | L1 | 失败 |
| gen_v2/v2_04_fifo3 | L1 | 失败 |
| gen_v2/v2_05_enabled_101 | L1 | 失败 |
| gen_v2/v2_06_round_robin4 | L1 | 失败 |
| public/ex01_popcount8 | L3 | 通过 |
| public/ex02_detect_1101 | L1 | 失败 |
| public/ex03_lfsr8 | L3 | 通过 |

## 证据

[逐题 CSV](../../output/rtl-v6-qwen-retest-20261024/analysis/latest.csv) · [完整性核验](../../output/rtl-v6-qwen-retest-20261024/verification.json) · [原始证据包](../../output/rtl-v6-qwen-retest-20261024/cloud-evidence.zip) · [冻结输入](../../output/rtl-v6-qwen-retest-20261024/cloud-input.zip) · [机制统计](../../output/rtl-v6-retest-analysis-20261024/mechanisms.json) · [归因检查](../../output/rtl-v6-qwen-retest-20261024/inspection.json) · [清理记录](../../output/rtl-v6-qwen-retest-20261024/cleanup.json) · [前一轮 V6](v6_qwen_test_20261024.md)

原始证据包 978707 字节，1053 个索引成员，0 排除；SHA256 `a4d5099cfeae78b38a0012048b11af7e27701990e0b45d3211d4aff56434895d`。冻结输入 307918 字节，SHA256 `c83af46acd10a0b6ac737d410558e68b681b0c37004d12eea266d388a2e5ec49`。

![实例已销毁，余额 135](../../output/rtl-v6-qwen-retest-20261024/cloud-no-active-instance.jpg)
