# 实测记录（2026-09-28）

环境：Windows x64、Python 3.12.14、Icarus Verilog 13.0（MSYS2 mingw64）；模型：DeepSeek deepseek-flash。

## 已完成的真实检查

- 30 项 Python 测试全部通过，包含真实 HDL 仿真、失败标记、无 PASS、看门狗、超时清理、接口与 HTTP 协议。日志：[python_tests.txt](../runs/python_tests.txt)。
- PowerShell 启动入口实际运行通过，Bash 启动文件通过 bash -n 语法检查；Bash/Linux 下完整执行未验证。
- 官方 baseline.py、run_baseline.sh 与本地原参考仓库逐字节一致。
- 三道手写教学设计通过，共 8,201 次检查，并导出 VCD 波形。见 [教学报告](../runs/demo/report.md)。

## DeepSeek 生成产物与独立复核

下面是开发修改后的指定运行记录，期间存在多次调试与重跑，**不是盲测 pass@1、不是泛化通过率或官方成绩**。智能体只读取 prompt.txt；独立人工测试台在生成结束后由外部脚本检查，未进入模型输入。

| 任务 | 模型自检 | 选中 RTL 轮次 | 本次生成秒数 | 输入/输出 token | 独立检查 |
| --- | --- | ---: | ---: | ---: | --- |
| [popcount8](../runs/deepseek_final/popcount8/solution.v) | 通过 | 1 | 5.328 | 886/865 | passed，256 次 |
| [detect_1101](../runs/deepseek_final/detect_1101/solution.v) | 通过 | 2 | 12.797 | 2427/2665 | passed，2824 次 |
| [lfsr8](../runs/deepseek_lfsr8_revised/solution.v) | 通过 | 1 | 7.610 | 1162/1726 | passed，5121 次 |

每次模型调用的 token 和工具调用摘要见对应目录 trace.jsonl；完整测试台、每轮 RTL、日志和 wave.vcd 均保留。

## 失败分析与实际修改

1. **ModelSim 许可证不可用。** 编译成功，仿真报告 Unable to checkout a license。没有把该状态记为通过，改用免许可证的开发仿真器。
2. **便携 Icarus 缺少 DLL 搜索路径。** 内部 ivl.exe 找不到 bin 下的 libstdc++-6.dll。已补子进程 PATH 并复制同版本 DLL 到内部程序目录；直接版本检查与真实仿真均恢复。旧证据在 runs/deepseek_popcount8，后续没有用其结果计为模型功能失败。
3. **生成测试台写错期望值。** runs/deepseek_verified/popcount8/generated_tb.sv 把 01111110 的人口计数写为 7，实际为 6。此轮保存为失败；后续提示要求所有期望统一由参考算法计算，没有为了通过而修改 DUT 算法。
4. **DeepSeek 长推理耗尽输出预算。** 初版序列检测和 LFSR 的测试台调用达到 8192 token，未返回完整 tb。开发配置现在默认 thinking=disabled；开启长推理仍可由环境变量配置。参考 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。
5. **枚举类型兼容错误。** 序列检测 RTL 首轮在 Icarus 下出现 This assignment requires an explicit cast；工具反馈后第二轮改用明确的状态常量，随后自检和独立复核均通过。
6. **测试台随机种子非法。** runs/deepseek_final/lfsr8/generated_tb.sv 使用 $random(常量 + i)，运行器正确拒绝通过。提示补充 seed 必须是 integer 变量；新版还允许最多一次只针对测试台语法/系统任务错误的独立修复。功能断言 RTL_AGENT_FAIL 不走此分支，不能通过修改期望值让错误 DUT 通过。该改进有单独单元测试。

原始失败目录保留用于学习和复核。最终 LFSR 采用 runs/deepseek_lfsr8_revised，已单独通过人工测试台。

## 未验证范围

未安装可用 Vivado，因此没有官方 L1/L2/L3、目标器件综合/时序结果；没有本地开源模型、ROCm 显存、Docker 镜像构建、agent/baseline 增益或大题集成绩。HTTP 经过本机协议测试，未在赛事平台进行端到端压力测试。

本工程已经完成开发机器上的生成与仿真闭环；正式参赛仍需补齐这些实测。
