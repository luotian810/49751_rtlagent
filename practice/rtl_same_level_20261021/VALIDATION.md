# 实际验证记录

日期：2026-10-21，北京时间。

- 范围：本题包的人工参考实现与自编测试台；没有调用生成模型，没有计算模型能力分或赛事成绩。
- 系统：Windows 本机；Icarus Verilog 编译器和 vvp 运行时均为 13.0 stable。
- Python：3.12.14。
- Linux：提供运行命令，但本次没有执行 Linux 版验证；本机 WSL 列表为空。
- Vivado：本次未执行；没有综合、器件资源或时序结论。

## 参考实现仿真

| 题号 | 结果 | 上升沿或组合输入采样检查次数 |
| --- | --- | ---: |
| p01_priority8 | passed | 256 |
| p02_rotate8 | passed | 4096 |
| p03_sat_counter4 | passed | 8253 |
| p04_shift8 | passed | 2337 |
| p05_detect1011 | passed | 2830 |
| p06_serial_parity8 | passed | 6357 |

共 24,129 次采样检查。时序测试还在下降沿改输入后检查寄存输出未提前变化，以检查同步更新约束。

## 错误设计对照检查

每题分别注入一个常见功能错误，六个错误设计均被对应测试台输出 RTL_AGENT_FAIL 拒绝。这里只说明六个选定错误被发现，不是完整故障覆盖率。

- p01_priority8：错误地优先选择最低位。
- p02_rotate8：左右循环方向颠倒。
- p03_sat_counter4：加法越过上界发生回绕。
- p04_shift8：串行移位方向颠倒。
- p05_detect1011：检测了错误的四位序列。
- p06_serial_parity8：valid 在分组完成后未按拍清零。

## 证据与复现

每题的日志、结果 JSON 和波形位于 results/reference/<题号>/；总汇总为 results/reference/summary.json。错误设计对照的汇总、说明和日志位于 results/negative/。

在已加载 Vivado 环境的 Linux 机器上，执行：

```bash
python3 run_practice.py --reference --backend vivado
```

本次最初在受限运行环境中启动 Icarus 时遇到访问冲突，之后以正常权限运行通过。上述记录取自最终真实仿真，没有把工具异常记作功能失败或通过。

