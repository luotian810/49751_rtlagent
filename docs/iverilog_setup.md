# 本机 Icarus 环境与 DLL 修复

2026-09-28，在本工程 `.tools/iverilog/` 安装了 Icarus Verilog **13.0 stable** 的 MSYS2 mingw64 二进制包。仅写入工程目录，没有安装系统服务、修改注册表或永久 PATH。

工具来自 [MSYS2 Icarus 软件包](https://packages.msys2.org/packages/mingw-w64-x86_64-iverilog)。逐包下载地址与校验值保存在 `.tools/iverilog/packages.json`，许可文本保存在 `.tools/iverilog/share/licenses/`。解包使用 Windows 自带 `tar`。这是本地开发仿真工具，不加入正式 Vivado 评分路径。

## 为什么出现找不到 libstdc++ 的弹窗

`iverilog.exe` 会启动 `lib/ivl/ivl.exe`。MSYS2 软件包把 `libstdc++-6.dll`、`libgcc_s_seh-1.dll` 等运行库放在 `bin/`。没有 MSYS2 环境时，内部进程未必能找到相邻目录的 DLL。

本工程已完成两项修复：工具封装仅给子进程补上 `bin/` 的 PATH；把同一套已校验软件包中的 DLL 复制到 `lib/ivl/`。因此直接运行 `.tools/iverilog/bin/iverilog.exe -V` 也能输出完整版本信息，并正常退出。没有从不明 DLL 下载网站获取文件。

普通仿真使用 README 命令，无需再配置。希望在当前终端直接使用 `iverilog` / `vvp` 时执行：

```powershell
.\scripts\use_iverilog.ps1
iverilog -V
```

若在另一台 Windows x64 机器重建，可用 Python 执行 `scripts/setup_iverilog.py`。此操作需要网络，从固定的官方 MSYS2 URL 下载并验证 SHA-256；无需管理员权限。工程已有工具时无需重复下载。Linux 开发环境请使用发行版 Icarus 包，或直接按赛事要求配置 Vivado。

## 本机工具状态

| 工具 | 实测状态 |
| --- | --- |
| Icarus Verilog 13.0 | 编译、仿真、VCD 导出通过 |
| ModelSim 10.1c | 编译可用；启动仿真报告许可证不可用 |
| Vivado / xsim | 未发现可用安装，未执行官方判定或综合 |

Icarus 与 Vivado 支持的 SystemVerilog 特性不完全相同。例如本次模型生成的 enum 三元赋值在 Icarus 下需要显式类型转换，后续修复为兼容的状态常量实现。工具兼容性失败应在报告中保留，不等同于已证明硬件算法错误。
