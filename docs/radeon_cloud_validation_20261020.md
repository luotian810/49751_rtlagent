# Radeon Cloud RTL 验证记录（2026-10-20）

本次已在 AMD 中国站 Radeon Cloud 的 FPGA-CHINA 镜像中，用本地 Qwen3-14B-Q4_K_M 生成 RTL，并以 Vivado 2026.1 的官方公开判定链路独立复核：agent 三道候选均为 L3、零失配；原样 baseline 分别为 L1、L1、L3。每道公开题每模式只运行一次，这是开发冒烟结果，不能作为盲测通过率、比赛增益或正式成绩。

本轮另以三个公开参考实现确认 EDA 授权与判定链路，均为 L3。云端回归为 51 通过、7 跳过、0 失败；更新后的 Windows 回归 58 项全通过。须保留的限制是：agent 两次在 120 秒冒烟预算内未完成内部自检，服务保留的候选随后独立判定通过；不能写成全流程无超时。本轮扣 1 积分，在新授权 3 积分内；实例已销毁、停止计费，当前没有运行中的云服务。适用赛道为 RTL。

## 验证范围与依据

采用的 RTL 官方参考版本为 `f7a8bd465c2a820e006c7a00ecc7df468974635b`（`1017-2-commit`）。报告口径依据该版本的 `SCORING.md`、`docs/FAQ.md` 及工作区赛事技能中于 2026-10-19 核对的条款。本文编写时未另行联网复核后续公告。

本次执行公开参考模式 `--reference --level 3`，输入是仓库内公开样例原有的参考实现，判定器保持原样。公开测试台和参考答案仅用于开发者核验判定链路，不进入模型生成上下文。每个样例执行一次；没有据此计算 pass@1、pass@5、方案增益或比赛总分。

证据文件位于本地 `D:/fgpa/output/cloud/round2/`：

- `environment.json`：实例内工具路径、版本、GPU 与磁盘探测。
- `reference-summary.json`：三个公开参考实现的逐项判定汇总。
- `model-download.json`：模型固定版本、文件大小、SHA256 与校验成功状态。
- `runtime-evidence.json`：模型服务启动日志、模型列表与启动阶段整卡显存采样。
- `linux-tests-v2.log`：最新云端 Python 回归日志；早期失败记录保留在 `linux-tests.log`。
- `generation-checkpoint.json`：生成阶段采样与 HTTP health 检查点，不是最终判定汇总。
- `partial-evidence-bundle.json`：按路径收集的生成文件、trace 与阶段日志；其中 `generation-smoke.json` 记录六次调用。
- `final-evidence-bundle.json`：最终云端证据包；115 项云文件取回后已逐项校验 SHA256。
- `agent-results/summary.json`、`baseline-results/summary.json`：模型产物的独立公开判定与逐项失配数。
- `vram-samples.json`、`http-health-final.json`：覆盖模型加载及六次请求的最终采样、填写实测值后的健康检查。
- `windows-tests.log`：更新后本机 58 项全部通过的回归日志。
- `instance-destroyed.png`：本轮结束后控制台显示 `No active instance` 的截图。
- `cleanup.json`：清理观测时间、额度变化、持久盘保留与证据校验记录。

云端源码目录为 `/workspace/rtl-validation-20261020/readable-rtl-agent`。本轮通过 Jupyter 终端直接导入源码；持久代码与小型证据保存在 `/workspace`，EDA 工作目录放在 `/var/tmp`。

## 实际云环境

| 项目 | 观测值或配置来源 |
| --- | --- |
| 平台 | AMD 中国站 Radeon Cloud |
| 镜像 | `fpgachina-rtlhls@sha256:a7cf627e11708e8a6dcd9de689ff934f7b450b79369ebc7bb0217e8b54d81e56`；来源为控制台镜像记录 |
| 配额 | 本账号模板配置为 1 GPU、16 核、55 GiB、持久 `/workspace` 25 GiB；不是以宿主机 `nproc` 或 `free` 推断 |
| GPU | `AMD Radeon Pro W7900D`，架构 `gfx1100` |
| GPU 总显存 | `51,522,830,336` 字节，约 48 GiB |
| Vivado | `2026.1`，SW Build `6511674` |
| EDA 路径 | `/tools/Xilinx/2026.1/Vivado/bin/` 下的 `vivado`、`xvlog`、`xelab`、`xsim` |
| 目标器件与时钟 | `xczu3eg-sbva484-1-e`，5 ns |
| 授权 | 环境探测显示授权变量已配置；三项仿真及综合实际通过，支持该次执行可签出所需授权的结论 |
| Python | `3.14.7` |
| llama.cpp | `0.4.0-dev`，build 1，commit `f114f91`，Clang 23.0.0 |
| Python 模块 | 探测到 `torch`、`vllm`、`huggingface_hub`；模块存在不代表相应推理后端已经实测 |

探测时 `/workspace` 总量为 25 GiB，`/tmp` 为 4 GiB；`/var/tmp` 可用约 1.95 TB，为节点本地盘。记录的 GPU 使用量为 `28,028,928` 字节，但这是环境探测瞬间的空闲状态，**不能作为模型推理峰值显存**。正式方案仍须按单卡 32 GB 约束测量权重、KV cache 及运行开销，不能因为验证卡有 48 GiB 就扩大预算。

## 三个公开参考实现的复核结果

| 公开样例 | 编译 | 逐拍仿真 | 综合 | 比较样本数 | 失配数 | 等级 | 该次耗时 |
| --- | --- | --- | --- | ---: | ---: | --- | ---: |
| `ex01_popcount8` | 通过 | 通过 | 通过 | 257 | 0 | L3 | 27.15 s |
| `ex02_detect_1101` | 通过 | 通过 | 通过 | 226 | 0 | L3 | 40.31 s |
| `ex03_lfsr8` | 通过 | 通过 | 通过 | 229 | 0 | L3 | 40.99 s |

这里的“比较样本数”是公开测试台中的逐拍检查数量，不是多次独立模型采样次数。三个结果均无工具错误与本地环境错误，等级按编译、仿真、综合逐级成立。

综合资源记录分别为：`popcount8` 使用 10 LUT、0 FF；`detect_1101` 使用 3 LUT、3 FF；`lfsr8` 使用 8 LUT、8 FF。三者 DSP、BRAM、SRL、CARRY、MUXF 计数均为 0。后两个设计记录的综合 WNS 分别为 4.581 ns 与 4.566 ns；本次没有布局布线，不能将判定器推导的 Fmax 字段作为实现后的最高工作频率。

原始工作目录记录为：

```text
/var/tmp/rtl-official-20261020/ex01_popcount8/work_fr3vmt5j
/var/tmp/rtl-official-20261020/ex02_detect_1101/work_cwp3qvhc
/var/tmp/rtl-official-20261020/ex03_lfsr8/work_swi6tesz
```

这些是临时目录，不保证实例销毁后仍存在；判断依据是已取回并校验的证据。三个原始 summary 中的 `scope_note` 沿用旧版脚本固定文字，仍含“必须在赛事指定 Vivado 2026.1 环境复验”的提示；本次 `environment.json`、汇总与每项结果均明确记录 2026.1，版本一致项为 `true`。旧文字不改变本次已发生的 2026.1 复核，原始实测 JSON 保持原样。后续 `scripts/official_selftest.py` 已改为根据实际版本条件生成该提示。这次复核仍不是赛事方正式评测。

## 本地模型部署与当前边界

已经下载并校验的本地主模型为：

| 项目 | 值 |
| --- | --- |
| 权重仓库 | `Qwen/Qwen3-14B-GGUF` |
| 固定 revision | `c75e7b2d0234068f674a1bacf548ea32e27ccd29` |
| 文件 | `Qwen3-14B-Q4_K_M.gguf` |
| 量化 | `Q4_K_M` |
| 文件大小 | `9,001,752,960` 字节 |
| SHA256 | `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0` |
| 已取回状态 | `verified`；下载与校验记录耗时 111.31 s |
| 云端权重路径 | `/workspace/models/Qwen3-14B-Q4_K_M.gguf` |
| 后端 | 镜像自带 llama.cpp `0.4.0-dev`，commit `f114f91`，ROCm |
| 服务模型名 | `Qwen3-14B-Q4_K_M` |
| 监听地址 | `127.0.0.1:8000`，未公开模型端口 |
| 服务已加载上下文 | `32768` token，单 slot；长上下文边界尚待压测 |
| 思考配置 | `enable_thinking=false`，使用 Jinja 模板；方案和官方原样基线共用 manifest 配置 |

`runtime-evidence.json` 记录 `model loaded`、单 slot 的 `n_ctx_slot = 32768`、环回监听地址，以及模型列表中的正确模型名；`start.sh` 报就绪。这些证据证明本次权重加载与服务就绪，不再把 ROCm 部署写成完全未验证。

启动阶段的整卡周期采样持续 44.8 s，观测峰值为 `14,524,186,624` 字节（13.5267 GiB），采样错误为 0。采样包含该时段模型和 GPU 运行时，并非驱动硬件高水位计数，也未覆盖后续全部生成任务；它不能替代完整题集总峰值显存结论。

最终 `vram-samples.json` 覆盖模型加载及六次生成请求，共 609.17 s、509 个整卡周期样本，采样错误 0，观测峰值为 `14,852,784,128` 字节，即 **14.852784128 GB（13.8327 GiB）**，在本次观测窗口内低于 32 GB。该结果包含模型和 GPU 运行开销，但不是驱动硬件 high-water 计数器，不能保证捕获采样间的瞬时峰值，也不证明未测长题或满上下文的显存上限。

首次 HTTP health 为 `ready=true`、模型名正确、`vram_gb=null`，因为该进程未设置 `VRAM_GB`。最终在父环境填入上述十进制 GB 实测值并重启独立 HTTP 服务，`http-health-final.json` 返回 `ready=true`、`model=Qwen3-14B-Q4_K_M`、`vram_gb=14.852784128`。该字段是部署者环境声明，不是 health 请求即时测量；health 的 `simulator_license=not_checked` 也不替代实际 EDA 授权运行证据。

本轮按每题每模式一次执行开发冒烟，总共六次模型生成。为控制本轮验证费用，单题传入 `deadline_s=120`，不是正式默认的 900 秒配置；因此这些耗时和超时现象不能直接外推为正式题集表现。

| 公开题目 | agent 生成及内部检查耗时 | agent 内部状态 | agent 独立判定 / 失配 | baseline 生成耗时 | baseline 独立判定 / 失配 |
| --- | ---: | --- | --- | ---: | --- |
| `ex01_popcount8` | 34.581 s | 自检通过 | L3 / 0/257 | 3.271 s | L1 / 255/257 |
| `ex02_detect_1101` | 115.002 s | `service_timeout`，保留候选；自检未完成 | L3 / 0/226 | 4.590 s | L1 / 4/226 |
| `ex03_lfsr8` | 115.002 s | `service_timeout`，保留候选；自检未完成 | L3 / 0/229 | 4.568 s | L3 / 0/229 |

后两题的独立自测测试台生成耗尽本轮受限预算，不能因为候选最终通过就声称智能体全流程无超时。`detect_1101` 前两轮还出现 output wire/reg 声明错误，第三轮 lint 通过，失败与修复过程保留在 trace 中。baseline 是单次生成，不运行自测和修复；前两题虽可编译，但功能失配，因此止于 L1，未跳过失败继续综合。

baseline 失败可从保留代码中定位：`popcount8` 将 `(in >> i) & 1` 各项直接串接 `+`，没有用括号包住每个完整位提取表达式，实际运算符优先级导致 255/257 失配；`detect_1101` 在同一时钟沿用非阻塞赋值更新 `shift_reg`，又用旧 `shift_reg` 更新 `detected_reg`，使输出多延迟一周期，出现 4/226 失配。报告只归因，未替 baseline 修复或重投。agent 相应候选使用 `$countones` 与移位状态比较，最终公开判定通过。

独立判定在生成之后执行，不含在上表生成耗时中。agent 三题判定各耗时 28.14、40.64、40.65 s；baseline 各为 8.69、8.60、40.52 s。agent 资源分别为 10 LUT/0 FF、1 LUT/4 FF、8 LUT/8 FF；后两题综合 WNS 为 4.684、4.566 ns。未执行布局布线，不作实现后 Fmax 承诺。

方案与基线共用同一主模型、权重 revision、量化、上下文和思考配置。尚未完成每题五次独立采样、长题稳定性、离线重建或赛事平台连续投题；本轮不计算增益或正式成绩。

## Linux 与 Windows 回归

最新 `linux-tests-v2.log` 显示：58 项执行，51 通过、7 跳过、0 失败，耗时 46.113 s。跳过项为四项 Windows 主机名兼容设置、两项需要外部原始上游 checkout 的逐字对照，以及需要 Icarus 的本地链路测试。云镜像实际使用 Vivado，不因 Icarus 项跳过推断 Vivado 缺失。

此前首轮 `linux-tests.log` 有 1 项失败、3 项错误、7 项跳过；原日志保留，最新结果不覆盖失败历史。回归中的模拟模型、伪工具和 300 次协议任务验证工程行为，不产生真实模型能力成绩。真实模型的公开题目结果须另列。

更新后的 Windows 正常权限回归在 `windows-tests.log` 中记录 58 项全部通过，耗时 12.700 s。此前沙箱下临时目录与 Icarus 访问受限导致的执行失败归为环境限制；正常权限复核成功，不作为 RTL 或模型能力故障。两平台回归范围不同，云端跳过项不伪写为通过。

## 失败记录与费用边界

上一轮已完成中国站登录与比赛镜像启动，但浏览器文件选择器上传调用阻塞约 4 小时 16 分，恢复后 JupyterLab 出现 `Server Connection Error`，未确认源码导入成功。没有足够证据判断文件选择器内部原因，不能归因为 RTL、Vivado 或许可证问题。该轮未运行云端仿真、综合或本地模型。

上一轮授权上限为 3 积分，控制台实际扣除 5 积分，超出授权 2 积分；恢复控制后已销毁实例并确认 `No active instance`。以账户控制台的 150 → 145 积分为依据，当时 Jupyter 的过期费用提示不作为结算证据。详细过程见 `D:/fgpa/output/cloud/cloud-attempt-20261020.md`。

本轮得到新的**最多 3 积分**授权，改为终端直接导入源码，完成上述真实云环境、模型生成与独立判定。控制台结算如下：

| 项目 | 本轮观测 |
| --- | --- |
| 启动 | 2026-10-20 12:59:59，北京时间 |
| 销毁后确认记录 | 2026-10-20 13:33:39，北京时间；平台未提供精确停止时间 |
| 销毁前控制台运行时长 | 31 minutes |
| 销毁前实例消耗 | 1 积分 |
| 账户余额 | 145 → 144，本轮扣 1 积分，低于 3 积分授权上限 |
| 清理确认 | `No active instance`，已停止本轮实例计费 |
| 持久内容 | `/workspace` 保留，未删除持久工作区 |
| 本地归档 | 115 项云证据已取回并逐项校验 SHA256；另有 Windows 回归日志与清理截图 |

当前不保留运行中的投题或模型服务，也未验证正式 `rc-tunnel` 接入。后续重新启动会产生新的实例费用；本报告不将本轮开发验证写为长期上线。

## 当前可以支持的结论

已取得的实测链路是：固定版本本地 GGUF 权重加载 → llama.cpp ROCm 推理 → agent/原样 baseline 返回候选 → Vivado 2026.1 公开判定。agent 三道候选均 L3，baseline 为 L1/L1/L3；本次加载和六请求窗口的整卡周期采样峰值为 14.852784128 GB，最终 HTTP health 已填入该测量值。Linux 和 Windows 最新回归均无失败。

尚未完成的提交验证包括：长题及满上下文稳定性与显存边界、离线重建、方案与基线同批多样本对比、正式隧道及赛事平台连续投题，以及正式提交材料。三个公开题、每模式一次的开发冒烟不能替代盲测 pass@1 或正式增益分；agent 两次内部自检超时仍是需要改进的已知问题。本轮已结束并销毁实例。

## 后续官方规则复核（2026-10-20）

本节是在上述云端验证结束后追加的规则记录，不改变执行时采用的 `f7a8bd4`、模型配置、样本数或测试证据，也不表示运行过新一轮验证。

已读取本地从官方远端取得的 `origin/master`，提交为 `51fbf8dc169bb320e6691c2ced34f331c2659ac0`（`1019-commit`），并对照 `f7a8bd465c2a820e006c7a00ecc7df468974635b`。变化限于 8 个说明或示例文件：初赛与决赛统一为 W7900 / gfx1100，不再提供 R9700；断网运行要求明确适用于所有评测；10 月 31 日明确为初赛评测，决赛要求和答辩方式在初赛结果公布后另行公告；辅助模型条款编号改为 2.13。

能力 30 分、增益 40 分及其公式，L0–L3 系数、五次独立采样 pass@1、900 秒预算、单卡 32 GB 限制均未改变。已逐一核对 `docs/API_CONTRACT.md`、`example/baseline.py`、`example/run_baseline.sh`、服务启动与 HTTP 服务、`selftest/judge.py`、`selftest/score.py` 以及三个底层判题文件的 Git blob，两版本完全相同；基线常量仍为 `MAX_TOKENS = 16384`、`TIMEOUT_S = 840`。因此此次规则更新不要求改动本报告采用的协议、基线或判题实现。

来源：[固定版本 SCORING.md](https://gitee.com/Vickyiii/rtlagent2026/blob/51fbf8dc169bb320e6691c2ced34f331c2659ac0/SCORING.md)、[固定版本 FAQ.md](https://gitee.com/Vickyiii/rtlagent2026/blob/51fbf8dc169bb320e6691c2ced34f331c2659ac0/docs/FAQ.md)、[固定版本 baseline.py](https://gitee.com/Vickyiii/rtlagent2026/blob/51fbf8dc169bb320e6691c2ced34f331c2659ac0/example/baseline.py)。
