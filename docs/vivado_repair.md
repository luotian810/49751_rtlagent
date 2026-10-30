> 历史记录：以下状态、模型与测试范围属于文中原日期；当前状态见 [验证摘要](validation_status_20261030.md)。开发归档路径不是本仓库附件。

# Vivado 2025.2 综合修复与复验

验证日期：2026-10-05。本机 `D:\vivado\2025.2\Vivado` 的综合崩溃已通过进程级设置修复；最小 AND 电路综合返回 0，并生成有效 DCP。修复保留现有安装、许可证配置和系统电脑名，无需重启。

## 根因与证据

本机 Windows ANSI 代码页为 936，电脑名为 `鸡哥`。Vivado 把主机名加入 `.Xil/Vivado-进程号-主机名/` 临时目录；综合器 `xv_synth` 的 `write_design` 路径将 UTF-8 文件名交给按 CP936 解释窄字符串的 `fopen`。文件打开失败后，后续 `fprintf` 使用空的 `FILE*`，触发 `HUTProcHandlers::invalidParamHandler`；异常处理链最终报出 `0xC0000374`。

调试记录中的关键数据如下：

| 记录 | 观察结果 |
| --- | --- |
| 调用 fopen 前（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/debug_fopen_path/before_open.json`） | `windows_acp=936`；UTF-8 路径为 `.Xil/Vivado-27984-鸡哥/files.rtd`，同一字节按 ANSI 解读为 `.Xil/Vivado-27984-楦″摜/files.rtd` |
| 调用 fopen 后（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/debug_fopen_path/after_open.json`） | 返回寄存器 `RAX=0`，即空文件指针 |
| 崩溃记录（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/debug_fopen_path/crash.json`） | 包含 `_stdio_common_vfprintf`、`invalidParamHandler` 与 `0xC0000374` 异常 |
| 调用路径分析（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/temp_probe/synth_fprintf_analysis.json`） | `files.rtd` 打开后未检查空指针便调用 `fprintf` |

栈记录部分名称来自最近邻符号。偏移很大的名称只能用于辅助定位，不能当作精确函数名或单独的根因证据；结论依据路径字节、代码页、`fopen` 返回值和修复对照共同确认。

同一台 Windows 11 25H2、同一套 Vivado 2025.2，在 ASCII 主机名覆盖后已通过最小综合。因此，旧记录提到的操作系统支持范围差异不能单独解释本次崩溃，也不需要先升级 Vivado 才能使用本次修复。[修复前记录](vivado_validation.md) 保留当时的失败与排查过程。

## 修复方式与作用范围

设置当前进程环境变量：

```powershell
$env:_CLUSTER_NETWORK_NAME_ = 'RTLLOCAL'
```

本机实测该变量使 Winsock `gethostname` 返回 ASCII，Vivado 因而生成不含中文主机名的临时路径。Microsoft 的 [hostname 文档](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/hostname) 明确说明 `_CLUSTER_NETWORK_NAME_` 会覆盖命令输出，适用列表包含 Windows 11。[gethostname API 文档](https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-gethostname) 也描述了集群环境下的主机名覆盖，但正文写作 `CLUSTER_NETWORK_NAME`；本机实际使用并验证的是带首尾下划线的进程变量。

工程已集成两处配置：

- [scripts/use_vivado.ps1](../scripts/use_vivado.ps1)：检查系统电脑名；含非 ASCII 字符且变量未设置时设为 `RTLLOCAL`，供当前 PowerShell 及其后续子进程继承。
- [agent/verification.py](../agent/verification.py)：仅为 Windows 上的 `vivado`、`xvlog`、`xelab`、`xsim` 子进程配置相同变量；保留已有覆盖值和父进程环境。

原有四个工具入口检查、许可证路径配置和安装附带 Tcl 仓库逻辑均保留。设置不更改系统电脑名、系统或用户环境变量、注册表、Vivado 安装和许可证内容；关闭配置终端后失效。

## 用户复现

在工程目录运行，无需模型 API Key：

```powershell
cd D:\fgpa\readable-rtl-agent
.\run.ps1 -Demo -Backend vivado -Synth -OutDir .\runs\verified_demo
```

检查公开样例的参考实现与已保存的生成产物：

```powershell
.\scripts\use_vivado.ps1
$env:PYTHON_EXE = 'C:\Users\25119\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $env:PYTHON_EXE scripts/official_selftest.py --reference --level 3 --output runs/reference_l3
& $env:PYTHON_EXE scripts/official_selftest.py --generated --level 3 --output runs/generated_l3
```

手工启动 GUI 时，在执行过 `use_vivado.ps1` 的**同一终端**运行 `vivado`。桌面快捷方式不会继承这个终端的变量。其他安装目录与许可证路径的覆盖方法见 [配置说明](vivado_setup.md)。

## 本轮验证结果

| 检查 | 实际结果与证据 |
| --- | --- |
| 最小 AND 电路 | result.json（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/ascii_winsock_control/result.json`） 为 `passed`、返回码 0；DCP（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/ascii_winsock_control/synthesized.dcp`） 已生成 |
| Python 测试 | 完整日志（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/python_tests.txt`）：43 项通过 |
| 生成设计公开样例 | L3 报告（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/generated_l3/report.md`）：3 道全部通过，合计 712 个采样点零失配 |
| 官方参考实现 | L3 报告（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/reference_l3/report.md`）：3 道全部通过，合计 712 个采样点零失配；父终端清除覆盖变量后，由 Python 工具层自动配置子进程 |
| 教学设计一键入口 | 演示报告（开发归档路径，未随库交付：`../runs/vivado_repair_20261005/demo/report.md`）：3 道仿真与综合全部通过，8,201 次检查，并生成 DCP、资源和时序报告 |

三道生成设计的综合资源与时序估计如下，官方参考实现本轮结果相同：

| 题目 | 本地判定 | 失配 / 采样 | LUT | FF | WNS（ns） |
| --- | --- | --- | ---: | ---: | ---: |
| popcount8 | L3 | 0 / 257 | 10 | 0 | 无寄存器路径 |
| detect_1101 | L3 | 0 / 226 | 3 | 3 | 4.581 |
| lfsr8 | L3 | 0 / 229 | 8 | 8 | 4.566 |

时钟约束为 5 ns；WNS 是综合后的寄存器间路径估计，未执行布局布线。教学检查点在各题 `runs/vivado_repair_20261005/demo/<题目>/synth/synthesized.dcp`，同目录保存 `utilization.rpt` 与 `timing_summary.rpt`。

本机使用 Vivado 2025.2，比赛指定 2026.1。公开样例的本地 L3 自测检验已保存 RTL 与判定链路，不能作为正式比赛成绩、隐藏题通过率或新一轮模型盲测结果。综合后的资源与时序报告未经布局布线，不承诺板级最高频率。离线本地开源模型、ROCm 部署、同模型 baseline 对比和正式平台验证仍待完成。
