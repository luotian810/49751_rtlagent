> 历史记录：以下状态、模型与测试范围属于文中原日期；当前状态见 [验证摘要](validation_status_20261030.md)。开发归档路径不是本仓库附件。

# V8 固定千问完整测试与分析（2026-10-26）

**V8 功能通过 7/21（33.3%），均达到 L3；L0=3、L1=11。与 V6 历史复测的 7/21 持平，本轮未出现新的功能通过题。生成阶段累计 1026.359 秒，比该历史批次的 1157.822 秒减少 11.35%。**

21 道正确参考均达到 L3，21 个候选全部独立判定，独立环境错误 0、生成进程超时 0。本次只测试 V8，每题生成一次，未重跑旧版或基线。题集参与过开发迭代，属于回归测试；不作为未见题泛化、五次 pass@1 或正式 70 分成绩。

云实例已销毁，持久化 `/workspace` 保留。刷新后的余额 117→116，实际消耗 **1 积分**，低于本轮 3 积分上限；本批授权随完成关闭。

## 历史对照与成本

| 指标 | V6 历史复测 | 本轮 V8 |
| --- | ---: | ---: |
| 功能通过 | 7/21 | 7/21 |
| L0 / L1 / L3 | 3 / 11 / 7 | 3 / 11 / 7 |
| 生成阶段累计耗时 | 1157.822 s | 1026.359 s |
| 模型调用 | 65 | 68 |
| 验证计划初稿合法 | 2/18 | 4/18 |
| 验证计划最终合法 | 7/18 | 12/18 |
| 实际执行自检 | 7/21 | 12/21 |
| 本地正确参考被生成 TB 接受 | 4/7 | 5/12 |
| 自检 PASS 但独立功能失败 | 0 | 1 |

历史对照采用经过完整核验的 V6 复测包，题面、独立判题器、权重与推理配置匹配；本轮不是同期 A/B。V6 另一历史批次为 8/21，本报告不取最好结果或混算批次。耗时为单题 agent 生成进程的墙钟累计，包含内部工具；不含外部正确参考与独立评分。测试运行器总耗时 2193.194 秒含这些外部控制，不能与生成耗时混用。单轮历史差异尚不能证明稳定或因果性的提速。

功能通过题集合与 V6 复测相同。等级发生两处变化：`v4_02_signed_addsub6` L0→L1，`v4_05_enabled_1101` L1→L0；没有功能胜题或失题。

## 问题与依据

1. **自检 oracle 的语义错误是首要瓶颈。** 12 个已执行 TB 均与云端留存的实际 `tb.sv` 字节匹配；用正确参考在本地 Icarus 回放，12 个均实际完成仿真，7 个触发错误断言，未出现编译失败或超时。位计数 TB 用 `$clog2(stim_in)` 代替置位数，输入 1 时错误期望 0；串行校验在正确参考的 `valid=1` 时期望 0；FIFO、仲裁和序列题也出现状态/输出时机失配。增加自检执行数量尚未带来可信的判断。

2. **自检会同时误收错误设计、误拒正确参考。** 弹性缓冲候选自检 PASS，独立判定却有 409/1042 次失配；同一生成 TB 对正确参考在 sample 12 期望 `out_valid=1`、实际为 0，回放失败。不能把内部 PASS 当作独立功能通过。

3. **代码修复效果仍弱。** 9 次修复模型调用累计 143.393 秒，21 个最终代码中只有 1 个不同于初稿。该样本修正了非法负数字面量及赋值问题，最终可编译，但有符号比较/饱和语义仍错误。两道旋转题继续使用变量范围切片；另一个样本的多过程驱动冲突在展开阶段重复出现，被归到 `unknown`。通用诊断已能定位，千问仍未可靠完成结构性修复。

4. **时序契约与状态更新易被误读。** 下降沿题的候选使用上升沿；握手、使能保持、输出发布时机和序列重叠仍是功能失败集中区域。串行校验的诊断还把 11 次输入与第 8 位混用，说明修复依据本身需要核验。以上是对已观测样本的归因，不是对全部未见题的结论。

5. **验证计划仍消耗主要模型时间。** 18 次计划生成加 14 次格式恢复，共 466.079 秒，占 859.172 秒模型调用累计时间的 54.25%；初稿 14/18 不合法。失败涉及临时量命名/依赖顺序、非法 `$random`、缺少端口、错误字段以及参考算法读取 DUT 输出。格式恢复提高了可执行率，尚未解决期望值正确性。

下一轮优先处理跨题通用机制：明确采样边沿、边沿前后状态与接受事务数；约束独立参考模型的表达与时序；缩小计划输出格式和恢复负担；检查重复修复是否真正移除了错误结构，并补齐多过程驱动类诊断。先在当前固定千问下验证这些机制，不依据参考答案编写题目专用修补。本轮仅测试与分析，未改动被测运行代码或运行时 skill。

## 调用时间

| 用途 | 次数 | 模型累计秒 |
| --- | ---: | ---: |
| design | 21 | 220.338 |
| failure_diagnosis | 6 | 29.362 |
| independent_testbench | 18 | 243.172 |
| repair | 9 | 143.393 |
| testbench_format_repair | 14 | 222.907 |

68 次模型调用均记录成功，未出现输出长度截断；这不表示生成代码或期望值正确。

## 逐题结果

自检列只统计实际运行过的 TB；未执行与失败分开。独立等级为云端 Vivado 2026.1 结果。

| 题目 | 独立等级 | 生成秒 | 模型调用 | 最终候选自检 |
| --- | ---: | ---: | ---: | --- |
| gen_v4/v4_01_rotate12（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_01_rotate12/solution.v`） | L0 | 17.512 | 2 | 未执行 |
| gen_v4/v4_02_signed_addsub6（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_02_signed_addsub6/solution.v`） | L1 | 53.904 | 5 | 未执行 |
| gen_v4/v4_03_negedge_mod7（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_03_negedge_mod7/solution.v`） | L1 | 58.557 | 4 | FAIL |
| gen_v4/v4_04_group_sum3（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_04_group_sum3/solution.v`） | L1 | 58.964 | 3 | 未执行 |
| gen_v4/v4_05_enabled_1101（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_05_enabled_1101/solution.v`） | L0 | 119.153 | 3 | 未执行 |
| gen_v4/v4_06_readyvalid_fifo2（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v4/v4_06_readyvalid_fifo2/solution.v`） | L1 | 73.364 | 3 | FAIL |
| practice/p01_priority8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p01_priority8/solution.v`） | L3 | 31.853 | 3 | 未执行 |
| practice/p02_rotate8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p02_rotate8/solution.v`） | L0 | 24.793 | 3 | 未执行 |
| practice/p03_sat_counter4（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p03_sat_counter4/solution.v`） | L3 | 35.053 | 2 | PASS |
| practice/p04_shift8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p04_shift8/solution.v`） | L3 | 21.760 | 2 | PASS |
| practice/p05_detect1011（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p05_detect1011/solution.v`） | L1 | 53.807 | 5 | FAIL |
| practice/p06_serial_parity8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/practice/p06_serial_parity8/solution.v`） | L1 | 99.967 | 5 | FAIL |
| gen_v2/v2_01_signed_sat8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_01_signed_sat8/solution.v`） | L3 | 30.553 | 2 | PASS |
| gen_v2/v2_02_counter_priority（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_02_counter_priority/solution.v`） | L3 | 20.796 | 2 | PASS |
| gen_v2/v2_03_elastic_buffer（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_03_elastic_buffer/solution.v`） | L1 | 58.300 | 3 | PASS |
| gen_v2/v2_04_fifo3（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_04_fifo3/solution.v`） | L1 | 54.538 | 3 | 未执行 |
| gen_v2/v2_05_enabled_101（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_05_enabled_101/solution.v`） | L1 | 33.311 | 3 | 未执行 |
| gen_v2/v2_06_round_robin4（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/gen_v2/v2_06_round_robin4/solution.v`） | L1 | 79.701 | 4 | FAIL |
| public/ex01_popcount8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/public/ex01_popcount8/solution.v`） | L3 | 26.028 | 4 | FAIL |
| public/ex02_detect_1101（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/public/ex02_detect_1101/solution.v`） | L1 | 51.891 | 4 | FAIL |
| public/ex03_lfsr8（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/results/generated/latest/public/ex03_lfsr8/solution.v`） | L3 | 22.554 | 3 | 未执行 |

## 环境、模型和证据

- 版本 `2026.10.26-v8-qwen-only`；只运行 latest 组，共 21 个新样本。冻结包 219 文件，当前 49 个运行文件逐字节一致；官方基线原文件保留，没有基线生成任务。
- 固定 `Qwen3-14B-Q4_K_M`，revision `c75e7b2d0234068f674a1bacf548ea32e27ccd29`；实际 GGUF 9001752960 字节，SHA256 `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0`。32768 上下文、单槽、thinking=false，temperature=0.2，运行配置与历史固定配置一致。
- W7900D / gfx1100，llama.cpp 0.4.0-dev、f114f91，Vivado 2026.1，器件 `xczu3eg-sbva484-1-e`、5 ns；Python 3.14.7。421 次整卡周期采样，错误 0，观测峰值 14.8558848 GB；没有验证硬件最高水位或完整长上下文压力边界。
- 先前四次 One-click 启动在平台调度层失败，费用均为 0。本次用户明确批准改用无原生自动回收的 Hackathon，并在线兜底销毁；原租约 14:46:18，计算停止线 16:26:18、销毁线 16:36:18（北京时间），本次提前完成销毁。没有将人工兜底写成自动回收。
- 证据 ZIP 1109776 字节，SHA256 `ca604d24c94c8ff86754b8db9049fcd68474219e0845278bdd7a05f40669209c`；1148 个索引文件，遗漏 0，摘要、CRC、成员清单、完整批次和观察样本检查全部通过。

完整证据包（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/cloud-evidence.zip`） · 核验结果（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/verification.json`） · 分析数据（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/analysis/analysis.json`） · 逐题 CSV（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/analysis/latest.csv`） · 修复与 TB 字节依据（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/analysis/runtime-diagnostics.json`）

机制分析（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-mechanisms-20261026/mechanisms.json`） · 本地正确参考控制（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/oracle-controls/summary.json`） · 清理和费用（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/cleanup.json`） · 最终余额及无实例截图（开发归档路径，未随库交付：`../../output/rtl-v8-qwen-retry5-20261026-144618/cloud-final-balance-header.png`）

平台账户菜单曾显示缓存余额 117；刷新后的积分页面及最终首页均为 116，费用按刷新证据确认。下载的原始证据不因本地控制或报告而改写。
