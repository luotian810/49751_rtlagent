# V9 固定千问完整测试与分析（2026-10-27）

**V9 功能通过 7/21（33.3%），全部 L3；L0=3、L1=11。通过题集合与 V8 相同，本轮没有功能净增益。生成阶段累计 903.863 秒，较 V8 历史批次的 1026.359 秒减少 11.94%。**

21 个候选全部独立判定，21 道正确参考均达到 L3，独立环境错误 0、生成进程超时 0。仅运行 V9，每题一次，模型固定 Qwen3-14B-Q4_K_M。该题集参与过迭代，属于开发回归；不是未见题泛化测试、五次 pass@1 或正式前 70 分成绩。

完整证据已下载和核验。实例已销毁，持久化 `/workspace` 保留；刷新后的余额 **150→149，实际消耗 1 积分**，低于本轮 3 积分上限，授权已关闭。

## 历史同题对照

| 指标 | V8（10 月 26 日） | V9（本轮） |
| --- | ---: | ---: |
| 独立功能通过 | 7/21 | 7/21 |
| L0 / L1 / L3 | 3 / 11 / 7 | 3 / 11 / 7 |
| 生成阶段累计耗时 | 1026.359 s | 903.863 s |
| 模型调用 | 68 | 68 |
| 模型调用累计耗时 | 859.172 s | 724.572 s |
| 计划初稿合法 | 4/18 | 8/18 |
| 计划最终合法 | 12/18 | 14/18 |
| 格式恢复调用 | 14 | 10 |
| 实际执行自检 | 12/21 | 13/21 |
| 正确参考被生成 TB 接受 | 5/12 | 5/13 |
| 两轮共同覆盖的正确参考被接受 | 5/9 | 5/9 |
| 最终候选自检 PASS | 5 | 4 |
| 自检 PASS 但独立功能失败 | 1 | 0 |

分析器已核对题面、独立判题材料和固定模型配置，允许历史同题比较。本轮不是同期 A/B，每题只有一个新样本；生成输出存在抽样波动，11.94% 是本次观察差异，不能单独证明稳定或因果性的提速。生成耗时包含 agent 内部工具；运行器阶段总耗时 2094.340 秒还包含正确参考控制和独立判题，二者不能混用。

等级上有 2 题 L0→L1、2 题 L1→L0，功能通过题没有新增或丢失：旋转 12 位、带使能序列检测达到 L1；有符号加减、深度 3 FIFO 退到 L0。不能只展示编译改善而省略回归。

## 结果说明

1. **计划格式开销下降，模型调用总数没有下降。** 格式恢复由 14 次、222.907 秒降为 10 次、140.095 秒；计划生成与恢复合计 361.932 秒，占模型时间 49.95%（V8 为 54.25%）。同时归因调用 6→9、代码修复 9→10，合计调用仍为 68。临时量命名规范化及通用清单对应了格式障碍，但单轮结果不足以把全部差异归因于某一个改动。

2. **可执行 oracle 的语义仍不可靠。** 13 套已执行 TB 均与归档的实际仿真 `tb.sv` 字节匹配。本地 Icarus 对正确参考回放时，13 套均实际执行仿真，其中 8 套发生断言失败，没有编译错误或超时。错误跨越位宽/移位范围、组合与寄存输出时刻、复位/保持、接受事务计数和仲裁指针等类别；不是单一题目故障。共同覆盖的 9 套控制中，两轮都只接受 5 套正确参考。

3. **盲复核会给出与自身推导矛盾的期望。** 优先编码器的实际输入为 `in=ff`、实际 `index=7`，oracle 期望 0；正确参考也被同一 TB 拒绝。盲复核理由一方面推导最高位为 7，一方面把 `sample=2` 混作输出值，最终却提交期望 0，程序按值关系将其归为 `dut_error`。修复调用返回重复候选，候选保留，独立判定仍为 L3。输入历史和观测绑定能限制上下文，不能证明推导语义正确。

4. **代码修复仍缺少实际效果。** 10 次修复调用累计 120.814 秒，只有 2/21 个最终代码不同于初稿，这两题只从 L0 升到 L1，均未功能通过。变量范围切片仍重复出现；过程赋值到 net 的修复又引入 ANSI 端口重声明；FIFO 的语法/未声明符号错误在多轮持续出现。2 次重复候选停止不等于根因已经解决。V9 新增多驱动分类在本轮新样本中没有遇到对应根日志，不能把某题的编译改善直接归功于它。

5. **合法计划不保证 HDL 能编译，也不保证参考算法正确。** 序列练习题的计划通过结构检查，但生成的下一状态表达式括号不平衡，Vivado 报 TB 第 51 行语法错误，未执行功能自检。其余未执行计划仍涉及读取 DUT 输出、临时变量自引用及未声明符号；这些检查继续拒绝，没有为了提高执行数量而放宽。

本轮没有出现自检假通过，但 V8 曾假通过的弹性缓冲题这次因参考算法读取 DUT 输出而未执行自检，不能据此宣称已修复自检假通过问题。

下一轮可依据这些跨题证据优先研究：参考表达式的低成本语法控制、完整状态事件与输出发布模型、盲复核中“推导理由—期望值”的一致性，以及编译根错误对应的结构性修复。当前只完成测试与分析，没有继续改动被测 V9 或运行时规则；后续变化须升级版本并重新用固定千问验证。

## 调用耗时

| 用途 | V8 次数 / 秒 | V9 次数 / 秒 |
| --- | ---: | ---: |
| 初稿设计 | 21 / 220.338 | 21 / 201.076 |
| 验证计划 | 18 / 243.172 | 18 / 221.837 |
| 格式恢复 | 14 / 222.907 | 10 / 140.095 |
| 失败归因 | 6 / 29.362 | 9 / 40.750 |
| 代码修复 | 9 / 143.393 | 10 / 120.814 |

68 次调用均记录返回成功，输出长度截断 0；这不代表生成的代码或期望值正确。

## 逐题独立判定

| 题目 | V8→V9 等级 | V9 生成秒 | 调用 | V9 最终候选自检 |
| --- | ---: | ---: | ---: | --- |
| [gen_v4/v4_01_rotate12](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_01_rotate12/solution.v) | L0→L1 | 47.829 | 4 | FAIL |
| [gen_v4/v4_02_signed_addsub6](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_02_signed_addsub6/solution.v) | L1→L0 | 34.190 | 3 | 未执行 |
| [gen_v4/v4_03_negedge_mod7](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_03_negedge_mod7/solution.v) | L1→L1 | 52.564 | 4 | FAIL |
| [gen_v4/v4_04_group_sum3](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_04_group_sum3/solution.v) | L1→L1 | 48.780 | 3 | FAIL |
| [gen_v4/v4_05_enabled_1101](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_05_enabled_1101/solution.v) | L0→L1 | 84.137 | 5 | FAIL |
| [gen_v4/v4_06_readyvalid_fifo2](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v4/v4_06_readyvalid_fifo2/solution.v) | L1→L1 | 58.604 | 3 | FAIL |
| [practice/p01_priority8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p01_priority8/solution.v) | L3→L3 | 36.444 | 4 | FAIL |
| [practice/p02_rotate8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p02_rotate8/solution.v) | L0→L0 | 22.550 | 3 | 未执行 |
| [practice/p03_sat_counter4](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p03_sat_counter4/solution.v) | L3→L3 | 57.242 | 4 | FAIL |
| [practice/p04_shift8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p04_shift8/solution.v) | L3→L3 | 21.794 | 2 | PASS |
| [practice/p05_detect1011](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p05_detect1011/solution.v) | L1→L1 | 36.668 | 3 | TB 编译失败 |
| [practice/p06_serial_parity8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/practice/p06_serial_parity8/solution.v) | L1→L1 | 75.147 | 4 | FAIL |
| [gen_v2/v2_01_signed_sat8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_01_signed_sat8/solution.v) | L3→L3 | 21.541 | 2 | PASS |
| [gen_v2/v2_02_counter_priority](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_02_counter_priority/solution.v) | L3→L3 | 28.111 | 2 | PASS |
| [gen_v2/v2_03_elastic_buffer](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_03_elastic_buffer/solution.v) | L1→L1 | 45.534 | 3 | 未执行 |
| [gen_v2/v2_04_fifo3](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_04_fifo3/solution.v) | L1→L0 | 51.997 | 3 | 未执行 |
| [gen_v2/v2_05_enabled_101](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_05_enabled_101/solution.v) | L1→L1 | 38.210 | 3 | 未执行 |
| [gen_v2/v2_06_round_robin4](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/gen_v2/v2_06_round_robin4/solution.v) | L1→L1 | 56.443 | 4 | FAIL |
| [public/ex01_popcount8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/public/ex01_popcount8/solution.v) | L3→L3 | 24.543 | 3 | PASS |
| [public/ex02_detect_1101](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/public/ex02_detect_1101/solution.v) | L1→L1 | 24.831 | 3 | 未执行 |
| [public/ex03_lfsr8](../../output/rtl-v9-qwen-hackathon-20261027/results/generated/latest/public/ex03_lfsr8/solution.v) | L3→L3 | 36.704 | 3 | 未执行 |

## 复现与清理证据

- 被测版本 `2026.10.27-v9-qwen-only`；冻结输入 219 文件，50 个 latest 源文件校验，原样官方基线仅用于身份核对，没有基线生成任务。参考控制本地 21/21，云端 Vivado 2026.1 为 21/21 L3。
- 固定 Qwen3-14B-Q4_K_M，revision `c75e7b2d0234068f674a1bacf548ea32e27ccd29`；实际 GGUF 9001752960 字节，SHA256 `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0`。32768 上下文、单槽、thinking=false，temperature=0.2，与 V8 配置一致。
- W7900D / gfx1100、llama.cpp `f114f91`、Vivado 2026.1、器件 `xczu3eg-sbva484-1-e`、5 ns。401 次整卡周期采样，采样错误 0，峰值观测 14.8540416 GB；不等同于硬件最高水位或完整长上下文压力边界。
- 输入 ZIP 325384 字节，SHA256 `c71f8ac76c4a876f9d3b95a78dcf2d315e32b43115a0affdfb1b1fc7fdbf6681`。证据 ZIP 1136324 字节，SHA256 `c30425efe4b693b43aff5f5f6e2f49d1e87b56ed0de04c9453565f5ec09d5302`；1184 个索引文件，排除 0，完整性核验通过。
- One-click 先因节点容量/匹配不足失败，费用 0；用户随后明确同意 Hackathon 人工兜底。实际未使用自动销毁；操作者在导出核验后提前完成销毁，未触发用户接管。原始租约为北京时间 13:18:29，停止计算 14:58:29、最晚销毁 15:08:29，租约字节本地/云端一致。
- 余额曾被首页缓存显示为 150，刷新用量页面和最终首页均为 149；按刷新后的证明确认实际费用 1 积分。持久化选择和销毁确认均保留，未请求删除持久盘。本批授权关闭，未用的 2 积分不自动转到下一批。

[完整证据](../../output/rtl-v9-qwen-hackathon-20261027/cloud-evidence.zip) · [完整批次核验](../../output/rtl-v9-qwen-hackathon-20261027/verification.json) · [逐题 CSV](../../output/rtl-v9-qwen-hackathon-20261027/analysis/latest.csv) · [机制统计](../../output/rtl-v9-qwen-mechanisms-20261027/mechanisms.json) · [原始诊断与 TB 字节来源](../../output/rtl-v9-qwen-hackathon-20261027/analysis/runtime-diagnostics.json) · [本地参考控制](../../output/rtl-v9-qwen-hackathon-20261027/oracle-controls/summary.json) · [清理与费用](../../output/rtl-v9-qwen-hackathon-20261027/cleanup.json) · [无实例及余额截图](../../output/rtl-v9-qwen-hackathon-20261027/cloud-final-balance-header.png)
