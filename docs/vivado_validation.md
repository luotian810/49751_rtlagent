> 历史记录：以下状态、模型与测试范围属于文中原日期；当前状态见 [验证摘要](validation_status_20261030.md)。开发归档路径不是本仓库附件。

# Vivado 接入与实际验证记录

> 历史记录：本文保留 2026-10-02 至 2026-10-04 的验证状态。2026-10-05 已定位中文主机名导致的 UTF-8/CP936 路径问题，并接入进程级 ASCII 主机名修复。最新综合结果与复现方法见 [修复报告](vivado_repair.md)。

验证日期：2026-10-02、2026-10-04。工程可运行仿真；综合尚未完成。

## 已完成的结果

本机使用 `D:\vivado\2025.2\Vivado`。配置脚本已接入现有许可证路径和安装附带的 Tcl 仓库。没有把许可证或 API Key 复制进工程。

三道 DeepSeek 生成设计使用赛事原样公开参考测试台，在 `xvlog → xelab → xsim` 中通过本地 L2：

| 题目 | 生成设计失配 / 采样数 | 官方参考实现失配 / 采样数 |
| --- | ---: | ---: |
| 8 位人口计数 popcount8 | 0 / 257 | 0 / 257 |
| 重叠序列检测 detect_1101 | 0 / 226 | 0 / 226 |
| 8 位 LFSR | 0 / 229 | 0 / 229 |

合计每组 712 个采样点，无失配。这里检验的是已保存的生成产物，不是新一轮模型盲测；不能据此计算 pass@1 或 baseline 增益。

- 生成设计 L2 报告（开发归档路径，未随库交付：`../runs/vivado_2025_2/generated_l2/report.md`）
- 参考实现 L2 报告（开发归档路径，未随库交付：`../runs/vivado_2025_2/reference_l2/report.md`）
- [原样公开材料与来源](../vendor/rtlagent2026_selftest/PROVENANCE.md)

三道带注释的教学设计还通过本工程独立自检：popcount8 检查 256 次、detect_1101 检查 2,824 次、lfsr8 检查 5,121 次，共 8,201 次。它们是手写示例，仅用于教学和工具验证。演示报告（开发归档路径，未随库交付：`../runs/vivado_2025_2/demo/report.md`） 同时记录仿真与综合的不同状态。

各题可查看源码和信号波形：

| 教学源码 | Vivado 导出的 VCD |
| --- | --- |
| [popcount8](../demos/popcount8/solution.v) | wave.vcd（开发归档路径，未随库交付：`../runs/vivado_2025_2/demo/popcount8/wave.vcd`） |
| [detect_1101](../demos/detect_1101/solution.v) | wave.vcd（开发归档路径，未随库交付：`../runs/vivado_2025_2/demo/detect_1101/wave.vcd`） |
| [lfsr8](../demos/lfsr8/solution.v) | wave.vcd（开发归档路径，未随库交付：`../runs/vivado_2025_2/demo/lfsr8/wave.vcd`） |

完整 Python 测试 **37 项通过、无跳过**，真实仿真后端明确为 Vivado；覆盖正确输出、缺少通过标记、先 PASS 后 FAIL、HDL 时间上限与主机超时等。见 完整日志（开发归档路径，未随库交付：`../runs/vivado_2025_2/python_tests.txt`）。后续内置公开题目后，又执行适配器的 **8 项定向回归**，见 适配器日志（开发归档路径，未随库交付：`../runs/vivado_2025_2/selftest_adapter_tests.txt`）。

## 修复和接入

1. `scripts/use_vivado.ps1` 配置当前进程；`run.ps1 -Backend vivado` 和本机的 `auto` 自动使用它。支持显式覆盖安装和许可证路径。
2. 安装自带 Tcl 仓库通过 `XILINX_TCLAPP_REPO` 指定，并设置 `XILINX_LOCAL_USER_DATA=NO`，修复原先从用户缓存加载 `::tclapp::support::appinit` 失败的问题。这两个变量见 [Xilinx 官方 Tcl Store 说明](https://github.com/Xilinx/XilinxTclStore/wiki/Adding-a-New-App-to-the-Repository)。
3. `xelab --debug typical` 保留信号跟踪信息，修复 `xsim` 波形导出时报没有 trace information 的错误；无信号的空设计也能正确运行。
4. 错误识别避开 Vivado 回显的 Tcl 源码，仍要求真正的独立 PASS 输出行；综合还必须有完成标记和 DCP 检查点。
5. Windows 进程崩溃标记为工具环境错误。自测适配器保留上游原始 verdict，JSON 结果标记 `TOOL_CRASH`，Markdown 报告注明工具崩溃并排除计分。
6. `run.ps1 -Demo -Synth` 已接通：仿真通过后综合，任一步失败即返回非零退出码。资源、时序、DCP 仅在工具实际成功时产生。

## 综合未通过：已取得授权，工具进程崩溃

目标器件为 `xczu3eg-sbva484-1-e`。综合日志确认取得 `Synthesis` / `xczu3eg` 许可证，然后在模块综合阶段异常退出：

```text
INFO: [Common 17-349] Got license for feature 'Synthesis' and/or device 'xczu3eg'
...
INFO: [Synth 8-6155] done synthesizing module 'TopModule' ...
exit code: 3221226356 = 0xC0000374 (STATUS_HEAP_CORRUPTION)
```

没有生成有效 DCP、资源或时序报告，不能声称 L3 通过。

| 对照检查 | 结果与作用 |
| --- | --- |
| 官方 popcount 参考实现请求 L3 | 编译、仿真 0/257，通过授权后同样崩溃；不能归因于生成 RTL |
| 最小两输入 AND 门 | 同样崩溃，说明并非只影响复杂 RTL |
| 单线程综合 | 同样崩溃，未形成有效修复 |
| 仅设置进程 COMPUTERNAME/HOSTNAME 为 ASCII | 实际临时路径仍使用系统主机名，同样崩溃；未更改真实主机名 |
| Vivado `-tempDir` 指定工作目录 | 工具仍在其下建立带系统主机名的目录，同样崩溃 |
| 最终三道教学设计综合 | 均报告 `error`，保留原始日志 |

官方参考解控制报告（开发归档路径，未随库交付：`../runs/vivado_2025_2/reference_control_l3/report.md`） 保存上游 `L2 / SYNTH_FAIL` 原字段和本地 `TOOL_CRASH` 说明。这不推翻独立 L2 运行的成功证据，但该次完整 L3 请求不能当作有效综合成绩。

本机系统版本为 Windows 11 25H2，build 26200.9457。AMD 的 [操作系统支持表](https://www.amd.com/en/support/adaptive-socs-and-fpgas/installer-info-general.html) 将 Windows 11 Enterprise 25H2 对 Vivado 2025.2 标为不支持，对 2026.1 标为支持；本机版本不在 2025.2 支持列表内。另外，Vivado 自动创建的 `.Xil/Vivado-进程号-主机名/` 含中文，超出 [AMD 2025.2 命名约定](https://docs.amd.com/r/2025.2-English/ug973-vivado-release-notes-install-license/Vivado-Naming-Conventions) 列出的字符范围。**这些是已发现的兼容性因素，尚未证明哪个导致本次堆损坏。**

## 复现与剩余工作

运行方法见 [Vivado 配置页](vivado_setup.md)。以下命令不消耗 DeepSeek API 额度：

```powershell
cd D:\fgpa\readable-rtl-agent
.\run.ps1 -Demo -Backend vivado -OutDir .\runs\my_vivado_demo

# 同时请求综合；在当前安装下预计返回非零并保存崩溃证据。
.\run.ps1 -Demo -Backend vivado -Synth -OutDir .\runs\my_vivado_synth
```

建议下一步使用比赛指定的 **Vivado 2026.1** 和 AMD 支持的操作系统环境复测官方参考解 L3，再复测生成产物；升级本身不保证解决已观察到的崩溃。若继续调查中文路径，应在短 ASCII 路径和 ASCII 主机名的环境中做受控对照，涉及主机名修改与重启时单独安排。

本次未修改系统主机名、重启电脑或安装另一套大型 EDA 软件。比赛要求的离线本地开源模型、ROCm 容器、同模型 baseline 对比仍未完成；目前交付属于本机开发验证工程，不能标作正式比赛提交已验证。

Windows ZIP 附带代码、便携 Icarus、公开样例、日志与 VCD；不包含 Vivado 安装、许可证、API Key 或模型权重。解压后已有报告中的绝对路径记录来自原机器，重跑会生成当前路径。
