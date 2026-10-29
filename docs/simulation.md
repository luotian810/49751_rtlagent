# 本地仿真与证据

`agent/verification.py` 调用真实工具。`passed`、`failed`、`unavailable`、`timeout`、`error` 是不同结果；缺少工具或许可证不能算通过。

自动选择顺序是 Vivado、ModelSim、Icarus。设置 `XILINX_VIVADO` 为 Vivado 安装目录，或者将工具放入 PATH；设置 `MODELSIM_BIN` 为 ModelSim 的可执行文件目录。Windows 下也会识别已有的 `D:\modelsim_10.1c\win64`。

```powershell
python scripts/simulate.py --source examples/counter/rtl.sv --testbench examples/counter/tb.sv --top TopModule --backend modelsim --output output/manual-simulation
```

请替换为实际文件路径。testbench 顶层模块必须叫 `tb`。执行所有输入激励和断言后，单独输出 `RTL_AGENT_PASS` 并调用 `$finish`。检查失败时输出 `RTL_AGENT_FAIL` 并结束仿真，或调用 `$fatal`。工具还会检查编译退出码和错误日志；只输出标记而没有充分断言不能证明功能正确。

每次运行保存原始 `rtl.sv`、`tb.sv`、看门狗、工具脚本和编译产物。独立 CLI 还保存 `result.json`、`simulation.log`。ModelSim 与 Vivado 会尽量写出 `wave.vcd`；可用 GTKWave 或支持 VCD 的波形查看器打开。Icarus 如需波形，请在 testbench 中加入 `$dumpfile("wave.vcd"); $dumpvars(0, tb);`。

仿真有两层超时：默认主机总运行时间 60 秒（`--timeout` 可改），以及固定 1 ms 模拟时间。独立 HDL 看门狗在模拟时间耗尽时发出失败标记；ModelSim/Vivado 的 Tcl 脚本也限定运行时长。主机超时会结束工具的进程树。

`lint` 是语法/编译检查，`simulate` 是当前 testbench 的功能检查。模型生成的 testbench 与 RTL 可能犯同一种错误，必须结合题目参考模型或官方测试判断。ModelSim / Icarus 的开发验证结果不代表官方 Vivado 通过率。

`synth` 仅在显式或自动选中的 Vivado 后端执行真实 `synth_design`，默认器件 `xc7a35tcpg236-1` 用于开发冒烟检查。正式提交前通过环境变量 `RTL_AGENT_PART` 设置赛题要求器件。综合保存 `utilization.rpt` 和 `synthesized.dcp`，没有进行布局布线、时序收敛或官方评测。
