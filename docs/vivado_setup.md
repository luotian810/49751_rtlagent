# Windows Vivado 2025.2 配置与运行入口

本工程提供进程内配置脚本，适用于当前安装：

| 项目 | 默认路径或值 |
| --- | --- |
| Vivado 安装目录 | `D:\vivado\2025.2\Vivado` |
| 许可证文件路径 | `D:\vivado\License.lic`、`D:\vivado\vivado_lic2037.lic` |
| 安装附带 Tcl 仓库 | `D:\vivado\2025.2\data\XilinxTclStore` |
| `XILINX_LOCAL_USER_DATA` | `NO` |
| `_CLUSTER_NETWORK_NAME_` | 中文等非 ASCII 电脑名且未设置此变量时使用 `RTLLOCAL` |

脚本仅检查许可证文件是否存在，再把路径写入当前进程的 `XILINXD_LICENSE_FILE`。它不会读取或复制许可证内容，也不会更改注册表、系统环境变量或用户环境变量。当前终端的后续子进程继承这些设置，关闭终端后失效。

## 配置当前终端

```powershell
cd D:\fgpa\readable-rtl-agent
.\scripts\use_vivado.ps1
Get-Command xvlog, xelab, xsim, vivado
```

脚本设置 `XILINX_VIVADO`、`XILINX_ROOT`、`XILINXD_LICENSE_FILE`、`XILINX_TCLAPP_REPO`、`XILINX_LOCAL_USER_DATA` 和 `RTL_SIMULATOR`，并把 Vivado 的 `bin` 加入当前进程的 `PATH`。Tcl 仓库直接使用安装附带目录，以避开缺失的用户缓存。

本机中文电脑名曾导致 Vivado 2025.2 综合临时路径编码错误。脚本在电脑名含非 ASCII 字符且 `_CLUSTER_NETWORK_NAME_` 未设置时，将此进程变量设为 `RTLLOCAL`；已有设置会保留。Python 工具层同样为 `vivado`、`xvlog`、`xelab`、`xsim` 子进程配置此变量，且不改变 Python 父进程环境。修复无需重命名电脑、修改注册表、重装软件或重启。根因和实测证据见 [修复报告](vivado_repair.md)。

手工使用 GUI 时，要在已执行配置脚本的**同一个 PowerShell 终端**中启动：

```powershell
vivado
```

桌面快捷方式不会继承该终端的进程变量。关闭终端后配置失效，下次使用时重新执行配置脚本即可。

找到命令只表示工具文件存在，不证明许可证可用，也不证明仿真、综合或时序检查已经通过。真实结果必须查看每次运行的状态和日志。

## 通过统一入口选择工具

```powershell
# 运行工程附带演示，不调用模型。
.\run.ps1 -Demo -Backend vivado

# auto 检查默认安装或 XILINX_VIVADO 指定的安装，找到后自动加载进程配置。
.\run.ps1 -Demo -Backend auto

# 显式指定 Icarus，不加载 Vivado 配置。
.\run.ps1 -Demo -Backend iverilog
```

`auto` 仍由 Python 工具层按 Vivado → Icarus → ModelSim 的顺序选择。发现工具后运行失败会报告真实失败，不会静默换用其他工具并把结果标为 Vivado 通过。

生成流程可以请求综合；模型连接需先在同一终端配置：

```powershell
.\scripts\connect_deepseek.ps1
.\run.ps1 -TaskDir .\vendor\rtlagent2026_selftest\tasks\ex03_lfsr8 `
    -OutDir .\out\lfsr8_vivado -Backend vivado -Synth -Deadline 600
```

演示入口也支持综合，并可指定结果目录：

```powershell
.\run.ps1 -Demo -Backend vivado -Synth -OutDir .\runs\verified_demo
```

每题先仿真，成功后调用综合；任一步未通过，命令最终返回非零退出码。综合日志在每题的 `synth/` 子目录。2026-10-05 已修复本机综合崩溃，实际复验结果见 [Vivado 修复报告](vivado_repair.md)；[旧报告](vivado_validation.md) 保留修复前的失败记录。

## 运行赛事公开测试台

以下命令不访问模型 API，使用工程内置的原样公开题目与判定器：

```powershell
.\scripts\use_vivado.ps1
$env:PYTHON_EXE = 'C:\Users\25119\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $env:PYTHON_EXE scripts/official_selftest.py --reference --level 3 --output runs/reference_l3
& $env:PYTHON_EXE scripts/official_selftest.py --generated --level 3 --output runs/generated_l3
```

`--reference` 检查官方参考实现；`--generated` 检查本工程已保存的三道 DeepSeek 产物。自己的方案可用 `--solution-manifest` 传入 `{题目ID: RTL路径}` JSON 文件。`--level 3` 包含编译、参考仿真和综合；只检查功能时可改成 `--level 2`。

本地适配器只调整 Windows 进程启动、路径和报告；原判定器与公开测试台按字节保留。Windows 工具崩溃会在 JSON 结果中标记 `TOOL_CRASH`，Markdown 报告注明工具崩溃，原始上游 verdict 同时保留。公开样例不代表隐藏题通过率。

## 覆盖安装和许可证路径

```powershell
.\scripts\use_vivado.ps1 `
    -VivadoRoot 'E:\AMD\2025.2\Vivado' `
    -LicenseFiles 'E:\licenses\first.lic', 'E:\licenses\second.lic'

.\run.ps1 -Demo -Backend vivado `
    -VivadoRoot 'E:\AMD\2025.2\Vivado' `
    -LicenseFiles 'E:\licenses\first.lic', 'E:\licenses\second.lic'
```

安装目录优先级是显式 `-VivadoRoot`、当前进程的 `XILINX_VIVADO`、默认 `D:\vivado\2025.2\Vivado`。没有传入 `-LicenseFiles` 时，脚本在安装目录的上两级寻找 `License.lic` 与 `vivado_lic2037.lic`。配置会检查四个工具入口、Tcl 仓库和全部许可证路径，缺失时给出明确错误。

以上配置面向本机 Vivado 2025.2。公开样例本地 L3 结果仍须在比赛指定的 Vivado 2026.1 环境复验；综合后的资源和时序报告未经过布局布线，不能作为板级最高频率承诺。离线本地开源模型部署与正式比赛提交验证仍待完成。
