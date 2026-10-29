# 可读 RTL 智能体

队伍编号 **49751**；RTL赛道私有提交仓库 **49751_rtlagent**。方案文件位于仓库根目录，入口为 `serve/start.sh`、`run.sh` 和原样 `run_baseline.sh`。固定权重及下载版本见 [模型声明](model/MODEL.md)，建仓状态与部署入口见 [提交说明](submission.md)。

当前开发版 **V11.1**（2026-10-29），**待固定千问实测**。仅修复V11新增的前导零位宽误判，并将设计与验证提示恢复为V10原文；保留V11默认无额外规划及接口机制。315项本地回归全部通过，归档重放不计作新模型成绩。本轮没有模型调用或云端费用。见 [V11.1修复与验证](docs/v11p1_regression_fix_20261029.md)。

历史版本 **V11**（2026-10-28），固定 **Qwen3-14B-Q4_K_M**，2026-10-29完成21题开发测试：**7个L3、12个L1、2个L0，功能7/21**。历史V10为8/21，本轮丢失轮转仲裁题；生成854.097秒，减少25.15%。编译覆盖提高，但功能未提升。实际使用1积分，实例已销毁并保留持久盘；本批7积分授权已关闭。见 [V11完整实测与分析](docs/v11_qwen_retry_20261029.md)。

历史记录：2026-10-28 V11再次云端重试：最终仍因节点CPU/内存/GPU容量不足失败，21题未开始。余额135→135、无活动实例、7积分未使用；V11仍待千问实测。见 [重试记录](docs/v11_qwen_retry_20261028.md)。

历史记录：2026-10-28 V11 云端测试尝试：本地参考21/21通过；One-click节点容量不足，21题均未开始。余额135→135、费用0积分，当前无活动实例；本轮7积分授权未消费。V11仍待千问实测。见 [测试尝试与证据](docs/v11_qwen_test_20261028.md)。

V11迭代阶段记录 **V11**（2026-10-28），固定 **Qwen3-14B-Q4_K_M**，**当时待千问实测**。对照原样官方基线后，默认取消独立行为规划调用，精简通用时序/算术规则，补齐明确文字接口和复位 X/Z 的盲复核入口。310 项本地回归全部通过；本轮没有模型新样本或云端费用。历史基线为 7/21，V10 为 8/21（赢3、丢2），生成耗时为基线 8.73 倍；不是 V11 成绩。见 [V11 改动、基线对照及验证边界](docs/v11_iteration_20261028.md)。

历史版本 **V10**（2026-10-27），固定 **Qwen3-14B-Q4_K_M**，已覆盖 **21/21 题**：8 个 L3、9 个 L1、4 个 L0。由互不重复且配置一致的 7+14 两批构成；V9 历史同题为 7/21，V10 为 8/21，但生成总耗时增加 26.25%。每题一次的开发结果，不是正式比赛分数。补齐实例消费 13 积分，发生未按截止时间销毁的清理失误；当前已销毁并保留持久盘。见 [V10 完整测试与分析](docs/v10_qwen_complete_20261027.md)。本地 294 项回归记录保留。

历史版本 **V9**（2026-10-27），固定 **Qwen3-14B-Q4_K_M**，**已完成 21 题开发实测**。功能 7/21（L0=3、L1=11、L3=7），与 V8 历史通过题集合相同；生成阶段 903.863 秒，较该历史批次减少 11.94%，单轮差异不代表稳定因果增益。计划初稿合法 8/18，但 13 套自检 TB 仍有 8 套误拒正确参考。实际消耗 1 积分，实例已销毁、持久盘保留。详见 [V9 实测与分析](docs/v9_qwen_hackathon_20261027.md) 和 [迭代记录](docs/v9_iteration_20261027.md)。

2026-10-26 V8 千问完整测试已结束：功能 7/21（L0=3、L1=11、L3=7），与 V6 历史复测持平；生成阶段累计 1026.359 秒，本轮减少 11.35%。21 个正确参考全部 L3。实际消耗 1 积分，实例已销毁、持久盘保留。详见 [完整测试与分析](docs/v8_qwen_hackathon_20261026.md)。

历史版本 **V8**（2026-10-26），固定 **Qwen3-14B-Q4_K_M**，**已完成 21 题开发实测**。新增测试台生成前的 DUT 展开预检、按实际阶段保留候选，以及带源码位置和重复错误识别的编译修复。234 项本地回归通过；本轮生成阶段耗时下降，功能通过数持平，自检语义错误和低效修复仍是主要瓶颈。详见 [V8 迭代记录](docs/v8_iteration_20261026.md) 和上述实测分析。

2026-10-25 历史 V7 状态：V7 固定千问测试已有局部观察，完整原始包尚未取回；最后可见 8 题为 5 L0、3 L1，其余最终结果未知。实例已销毁，本轮扣费 4 积分（授权 2）。不得把局部结果写成完整 21 题成绩，详见 [本轮记录](docs/v7_qwen_retry_20261025.md)。

历史版本 **V7**，固定 **Qwen3-14B-Q4_K_M**，**完整千问结果待核验**。新增程序生成的通用激励、保留原计划的格式恢复，以及仅用规格和输入历史的盲期望复核。200 项工程回归通过，本机 Vivado 的 6 个控制符合预期；历史三次归因请求字符数减少 84.0%，尚无整体提速或正确率提升结论。详见 [V7 改动与验证](docs/v7_iteration_20261024.md)。

历史版本 **V6**，固定 **Qwen3-14B-Q4_K_M**。2026-10-24 本轮复测 21 个新样本，独立功能 **7/21**（均 L3），前一轮同版本为 8/21；生成、自检与修复累计耗时由 1041.527 秒增至 1157.822 秒。两轮被测运行时相同，属于重复性观察，没有新版本提升证据。详见 [本轮复测报告](docs/v6_qwen_retest_20261024.md) 与[前一轮报告](docs/v6_qwen_test_20261024.md)。本轮实际使用 1 积分，实例已销毁，持久盘保留。

V6 按接口、位宽与符号、验证初态、采样顺序和无效修复等共性问题精简 skill，补齐固定接口传递、结构化复位前置步骤和字段诊断，不含题目名或固定答案。185 项本地机制回归通过；实现与测试边界见 [V6 迭代记录](docs/v6_skill_20261024.md)。项目后续测试使用 [rtl-qwen-test](../.agents/skills/rtl-qwen-test/SKILL.md)，默认只运行最新版本。

历史 V5 同批测试为官方基线 7/21、V4.2 8/21、V5 8/21，详见 [V5 报告](docs/v5_qwen_test_20261023.md)。本轮旧版与基线只作历史同题对照；每题一次的开发测试不等于正式成绩。

Codex 后续依据结果迭代时使用 [rtl-skill-improve](../.agents/skills/rtl-skill-improve/SKILL.md)，其中整理了公开 RTL 智能体与部署 skill 的适用机制，并提供分阶段日志分析。该操作技能不进入千问提示词；上述 V6 成绩仅属于当时归档版本。来源与落地记录见 [技能参考研究](../output/rtl-skill-research-20261024/REPORT.md)。

## 快速运行

Windows 本地演示使用自带设计与测试台，不调用模型：

```powershell
cd D:\fgpa\readable-rtl-agent
.\run.ps1 -Demo -Backend iverilog
```

已有本地千问服务时，生成新设计：

```powershell
$env:MODEL_NAME = 'Qwen3-14B-Q4_K_M'
$env:LLM_MODEL = $env:MODEL_NAME
$env:LLM_BASE_URL = 'http://127.0.0.1:8000/v1'
.\run.ps1 -TaskDir .\vendor\rtlagent2026_selftest\tasks\ex03_lfsr8 -OutDir .\out\lfsr8 -Backend iverilog
```

题目目录需要 UTF-8 `prompt.txt`。`run.ps1` 查找 Python 3.10+，也可用 `-PythonPath` 指定。`-Backend` 选择 EDA 工具；Vivado 综合增加 `-Synth`。配置方法见 [Vivado](docs/vivado_setup.md)、[Icarus](docs/iverilog_setup.md)。

直接调用 Python：

```powershell
python -m agent.main --input path/to/task --output out/example --backend iverilog --max-rounds 3 --deadline 900
python scripts/simulate.py --source path/solution.v --testbench path/tb.sv --output out/manual --backend iverilog --top TopModule
```

默认在同次设计中核对状态与事件，不额外调用行为规划；`--planning-mode auto` 可显式启用历史规划流程作对照。默认采用结构化验证计划；`--verification-mode legacy` 仅供旧完整测试台流程回归。自建测试台只能提供自检证据。

## Linux / Radeon Cloud

按 [模型声明](model/MODEL.md) 准备固定 revision 与 SHA 的权重，部署说明见 [serve/README.md](serve/README.md)。启动入口不会在线下载模型。

```bash
source /workspace/env.sh
export INFERENCE_BACKEND=llamacpp
export MODEL=/workspace/models/Qwen3-14B-Q4_K_M.gguf
export MODEL_NAME=Qwen3-14B-Q4_K_M
export LLM_MODEL="$MODEL_NAME"
export LLM_BASE_URL=http://127.0.0.1:8000/v1
export MAX_LEN=32768
export EDA_TMP=/var/tmp/eda
export AGENT_TMP=/var/tmp
bash serve/start.sh
bash run.sh vendor/rtlagent2026_selftest/tasks/ex03_lfsr8 out/agent
bash run_baseline.sh vendor/rtlagent2026_selftest/tasks/ex03_lfsr8 out/baseline
```

`serve/start.sh` 统一拉起常驻服务；单题 `run.sh` 不启动模型。agent 与原样官方 baseline 共用模型、量化、上下文和 thinking 配置。官方基线已对照 `fc8e26a`，与 `51fbf8d` 原字节一致，仍采用原文件，其原文件与前版 `f7a8bd4` 相同：单次 16384 token、840 秒内部超时，外层单题预算 900 秒。

服务配置 `FPGACHINA_TOKEN` 后运行 `bash serve/run_api.sh start`，完成本地健康检查再暴露隧道；Linux 自动重启行为待实测。接口包括鉴权的 `/v1/health`、异步 `POST /v1/solve`、`GET /v1/jobs/<job_id>`，默认仅监听本机。正式投题由赛事隧道转发。

## 产物与代码阅读

| 文件 | 内容 |
| --- | --- |
| `solution.v` | 当前选中候选；失败时可能为空 |
| `trace.jsonl` / `summary.json` | 调用、阶段、耗时、停止原因与选中轮次 |
| `round_XX/*_reply.txt` / `solution.v` | 每次模型回复和候选，包括未选中稿 |
| `behavior_plan.json` | 仅供设计使用的未验证行为规划（有效时保存） |
| `verification_plan.json` / `generated_tb.sv` | 独立规格计划及固定测试台 |
| `round_XX/*/result.json` / `tool.log` | EDA 原始证据与实际执行阶段 |

从 [主流程](agent/main.py) 开始，再读 [计划编译器](agent/verification_plan.py)、[工具封装](agent/verification.py)、[诊断](agent/diagnosis.py)、[模型客户端](agent/llm.py) 和 [skill](skill/SKILL.md)。完整职责与候选保留策略见 [设计说明](docs/design.md)。

格式与 TB 编译修复共享一次机会；功能失配不重写测试期望。重复候选不重复运行工具。功能诊断必须来自实际运行的规范 FAIL，并绑定采样编号、全部输入、实际输出和测试台期望；语义推导仍可能错误。一次诊断只支持一次修复。

## 测试与评分边界

```powershell
$env:RTL_AGENT_TEST_BACKEND = 'iverilog'
python -m unittest discover -s tests -v
```

机制回归使用受控回复和真实 Icarus 验证接口、调度、失配检测、异常清理与协议；不构成千问通过率。实际能力测量继续使用固定千问与原样 baseline，同批同配置，保留全部失败。

采用的赛规：RTL L0/L1/L2/L3 逐级判定，正式功能与综合使用 Vivado 2026.1、器件 `xczu3eg-sbva484-1-e`、5 ns。每题五次独立运行取 pass@1 均值；自检 PASS、一次开发采样、仅综合均不等于正式成绩。最新规则以赛事公告为准，工程采用版本见 `manifest.json`。

历史证据保留在 [V1 云端记录](docs/radeon_cloud_validation_20261020.md)、[V2](docs/v2_iteration_20261021.md)、[V3 千问](docs/v3_qwen_test_20261022.md)、[V4 早期开发](docs/v4_iteration_20261022.md) 和 [开发报告](REPORT.md)。历史异模型结果不作为当前千问提升依据。
