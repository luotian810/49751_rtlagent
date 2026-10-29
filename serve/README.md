# 服务启动与异步投题

2026-10-25：V7 与固定千问已完成一次官方 rc-tunnel 的本机公网鉴权、异步投题、结果回传和独立 Vivado 2026.1 L3 验证；测试实例随后销毁，当前没有常驻服务。见 [完整链路报告](../docs/fullchain_validation_20261025.md)。这不代表赛事方已投题或长期连续请求已验证。

当前对照 RTL 上游 `fc8e26a5828b7222e9db439cee29128bcf4f8865`（2026-10-27 核对）；异步协议与官方基线未变。Dockerfile 采用该版明确给出的平台基础镜像摘要；私有镜像由赛事方用于兜底重建，本地未构建该镜像。
2026-10-20 已在 Radeon Cloud FPGA-CHINA 镜像实测 Qwen3-14B-Q4_K_M 的 llama.cpp ROCm 推理。三个公开参考实现和三个 agent 候选均通过 Vivado 2026.1 L3，原样 baseline 为 L1/L1/L3；agent 两次内部自检在 120 秒冒烟预算内超时，保留候选后独立判定通过。验证实例已销毁，当前没有运行中的推理或投题服务；以下命令用于重新部署，详见 [云端验证记录](../docs/radeon_cloud_validation_20261020.md)。

## Linux / Radeon Cloud

本次已校验的模型为 `Qwen/Qwen3-14B-GGUF`、revision `c75e7b2d0234068f674a1bacf548ea32e27ccd29` 的 `Qwen3-14B-Q4_K_M.gguf`，推理后端为镜像自带 llama.cpp `0.4.0-dev`（`f114f91`）。权重大小与 SHA256 见 [模型声明](../model/MODEL.md)。基础镜像须包含 Python 3、Bash、setsid、Vivado 与兼容的推理依赖。

持久环境保存在 `/workspace/env.sh`。如果文件已有内容，在保留原配置的前提下加入：

```bash
export XILINXD_LICENSE_FILE=${XILINXD_LICENSE_FILE:-2100@vivado-lic.fpgachina.svc.cluster.local}
export FLEXLM_TIMEOUT=${FLEXLM_TIMEOUT:-300000000}
export EDA_TMP=/var/tmp/eda
export AGENT_TMP=/var/tmp
export SELFTEST_TMP=/var/tmp
export INFERENCE_BACKEND=llamacpp
export MODEL=/workspace/models/Qwen3-14B-Q4_K_M.gguf
export MODEL_NAME=Qwen3-14B-Q4_K_M
export LLM_MODEL="$MODEL_NAME"
export LLM_BASE_URL=http://127.0.0.1:8000/v1
export LLM_API_KEY=dummy
export MAX_LEN=32768
export RTL_SIMULATOR=vivado
export NO_PROXY=127.0.0.1,localhost
```

每次新开终端或重启实例后重新加载。模型和 EDA 工具先做真实运行检查：

```bash
source /workspace/env.sh
unset DEEPSEEK_API_KEY
bash serve/start.sh
bash run.sh vendor/rtlagent2026_selftest/tasks/ex03_lfsr8 out/agent
bash run_baseline.sh vendor/rtlagent2026_selftest/tasks/ex03_lfsr8 out/baseline
```

`start.sh` 用 `setsid` 启动推理进程，等待 `/v1/models` 中出现指定模型后返回。
重复执行时已就绪的模型不会再次启动。`START_TIMEOUT_S` 默认 900 秒，启动日志默认在
`$AGENT_TMP/serve-logs/<后端名>.log`（本次为 `llamacpp.log`），可用 `SERVE_LOG_DIR` 修改。模型加载失败返回非零。
`run.sh` 不后台启动推理服务，单题默认 900 秒，可由 `AGENT_DEADLINE_S` 覆盖。

投题 HTTP 服务单独启动，与官方“容器重建时不需要投题服务”的流程一致：

```bash
source /workspace/env.sh  # FPGACHINA_TOKEN 已按赛事通知写入此文件
: "${FPGACHINA_TOKEN:?请先在 /workspace/env.sh 配置比赛投题令牌}"
export FPGACHINA_TOKEN
bash serve/run_api.sh start
bash serve/run_api.sh status
curl --noproxy '*' -s -o /dev/null -w '%{http_code}\n' \
    http://127.0.0.1:7860/v1/health  # 无令牌必须返回 401
```

`run_api.sh` 根据官方同名脚本适配本工程的标准库 HTTP 服务，脱离终端运行，进程退出后等待两秒重启。状态与日志在 `${AGENT_TMP:-/var/tmp}/run_api/`；`status` 只检查守护进程，仍须完成 HTTP 健康检查。停止使用 `bash serve/run_api.sh stop`。Linux 的脱离终端、异常重启和停止行为尚待实际部署验证，本地仅完成 Bash 语法检查。

确认带令牌的本地健康检查为 `ready=true`、`track=rtl` 后，再按平台步骤暴露 7860：

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u all_proxy -u ALL_PROXY /var/run/secrets/frp-self-service/install
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u all_proxy -u ALL_PROXY "$HOME/.local/bin/rc-tunnel" expose --port 7860
"$HOME/.local/bin/rc-tunnel" status
```

隧道应显示 `active`。重新 expose 可能改变网址，需要重新报送。只暴露 7860；模型服务
8000 留在环回地址。服务启动前必须准备授权环境，终端中后来改变量不会改变已运行的服务。

本次镜像的安装器经过实例代理返回了 HTTP 403；去代理安装成功。上面的安装命令已按该实测修正。显存须在模型加载后重新测量再启动 HTTP 服务，不能把加载前的采样当成模型占用。

2026-10-25 用户转发的通知补充：服务中断约一分钟后，平台会收回隧道；服务恢复后须重新
`expose`。实例重启后进程及隧道工具会清空，须重新安装工具并启动服务、暴露端口。
因此投题服务必须脱离终端运行；持久化的环境文件与日志不能代替存活进程。
本次通知明确网址报送方式下周另行通知，**当前不要报送网址**；重新 expose 后先保存新网址，
后续按赛事通知报送。上述命令是部署说明，不表示公网链路已经完成实测。

本轮模型加载上下文 32768、单 slot，使用本地权重。最终整卡周期采样覆盖加载及六请求共 609.17 s、509 个样本、0 采样错误，观测峰值 14.852784128 GB（13.8327 GiB）。这不是驱动硬件 high-water 计数器，不保证捕捉瞬时峰值；长题和满上下文边界仍待测试。方案仍须总峰值 ≤32 GB。

`serve/start.sh` 的默认后端仍为 vLLM；选择它时须另有兼容的 vLLM 与该后端支持的模型目录。vLLM 模板按 30 GB 预算推算初始分配比例，该比例不是实测。`GPU_UTIL` 不适用于本次 llama.cpp。方案与基线读取相同的 manifest `generation` 思考设置。

## 本次使用的 llama.cpp 后端

镜像已包含兼容 AMD GPU 的 `llama-server` 时，可以使用本地 GGUF 文件。先确认该程序
支持 `--jinja`、`--chat-template-kwargs`、`--alias`、`--parallel` 和 `--no-context-shift`。
此入口不安装推理依赖、不下载权重；`MODEL` 必须是已有文件，不能填写 Hugging Face 仓库名。

```bash
export INFERENCE_BACKEND=llamacpp
export LLAMA_SERVER=/opt/llamacpp/llama-server
export MODEL=/workspace/models/Qwen3-14B-Q4_K_M.gguf
export MODEL_NAME=Qwen3-14B-Q4_K_M
export LLM_MODEL="$MODEL_NAME"
export MAX_LEN=32768
bash serve/start.sh
```

`serve/llamacpp.sh` 默认监听 `127.0.0.1:8000`，通过 `PORT` 修改端口，`--alias` 与
`MODEL_NAME` 一致。默认只使用 `HIP_VISIBLE_DEVICES=0`；如需换卡，填写单个 GPU 索引。
上下文默认 32768、并发槽位固定为 1，给官方基线的 16384 输出 token 留出输入空间。
题面、系统提示和模板也计入上下文，完整输入加输出必须小于所设长度。

脚本用 Python 读取同目录工程 `manifest.json` 的 `generation.chat_template_kwargs`，
按方案与基线相同的布尔、数字、字符串白名单传给 Jinja 模板，缺少 `enable_thinking`
时默认 `false`。调整思考设置要修改 manifest；方案与基线共用同一服务。按官方 FAQ，
`ROCBLAS_TENSILE_LIBPATH` 默认设为 `/opt/llamacpp/rocblas/library`，已有环境值可覆盖。

上述固定模型已完成权重校验、服务就绪、六次生成及本轮显存采样；长题、满上下文与离线重建尚未验证。GGUF 文件大小不等于运行显存；本后端不采用 vLLM 的 `GPU_UTIL` / `VRAM_BUDGET_GB` 分配比例。

## 请求与结果

所有端点均要求 `Authorization: Bearer <FPGACHINA_TOKEN>`，该令牌与模型 API Key 不同。

```bash
curl -H "Authorization: Bearer $FPGACHINA_TOKEN" http://127.0.0.1:7860/v1/health

curl -X POST http://127.0.0.1:7860/v1/solve \
  -H "Authorization: Bearer $FPGACHINA_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"local-001","nonce":"local-001-agent-1","mode":"agent","prompt":"Implement a module named TopModule with input a and output q. Assign q = a.","interface":"","deadline_s":900}'
```

投题立即返回 HTTP 202：

```json
{"job_id":"服务生成的编号","task_id":"local-001","status":"queued"}
```

使用返回的真实编号，每 2 秒查询一次：

```bash
JOB_ID='替换为接单响应中的真实编号'
curl -H "Authorization: Bearer $FPGACHINA_TOKEN" "http://127.0.0.1:7860/v1/jobs/$JOB_ID"
```

状态为 `queued`、`running` 或 `done`。只有 `done` 包含 `solution`、JSONL 字符串 `trace`
和 `elapsed_s`。同一非空 `nonce` 始终返回同一个任务，新采样必须使用新 nonce。
后台只有一个解题线程，排队时间包含在预算中；排队已超时的任务返回空解且不会启动子进程。
任务异常也会完成并记录失败事件，后续任务仍可运行。任务记录只存在本次服务进程中，不能靠重启保留。

`mode=baseline` 调用原样官方基线：只生成一次，没有自测和修复。正式方案与基线共用模型、
上下文、量化与思考配置。做不出答案的正常结果是空 `solution`，不能将 HTTP 202 或 200 当作功能通过。

健康检查确认模型列表包含指定名称、智能体文件存在、仿真工具可发现；它不检查许可证是否能签出。
`vram_gb` 来自部署者用 `VRAM_GB` 填入的实测 GB，未填时为 null。上线前需实测填写，
不能把 null 或健康检查成功当作显存达标、完整推理或官方环境验证。

2026-10-20 首次 HTTP health 为 `ready=true`、模型名正确、`vram_gb=null`；当时该服务未设置 `VRAM_GB`。完成采样后，在父环境设置 `VRAM_GB=14.852784128` 并重启独立 HTTP 服务，最终 health 返回相同实测值与 ready。该字段来自部署环境声明，不是 health 请求即时测量。验证结束已销毁实例；重新部署后须重新实测，不能把历史值当作新进程的即时测量。2026-10-25 已补齐一次官方隧道的外部单题验证，赛事方正式投题及长期连续请求仍待验证。

## 临时目录与超时

Linux 默认使用 `/var/tmp`，避免云实例的 4 GB `/tmp` 内存盘。每次 EDA 检查建立独立临时目录，
保存源码、日志、波形、综合报告和 DCP 后清理大型中间数据库。单题进程组包含脚本、模型请求与 EDA；
超时先终止这一组，随后强制清理，正常退出也清扫残留。Linux 服务采用 subreaper 回收本题孤儿进程。
云端最新 Linux 回归为 51 通过、7 跳过、0 失败，覆盖相关进程清理与临时证据保留测试；Windows 更新后 58 项全通过。测试替身不代替模型长任务和平台故障恢复验证。本轮真实模型短任务已留证，正式平台连续投题仍待验证。

## Windows 开发

先按主 README 设置 Python 和模型环境，运行 `scripts/use_vivado.ps1`，再启动：

```powershell
& $env:PYTHON_EXE -m serve.serve_api --port 7860
```

Windows 服务直接调用 Python 单题入口，避免依赖 Bash。已有中文主机名 Vivado 修复保留，
未设置 `EDA_TMP` 时仍保留本机完整工具工作目录。`serve/start.sh` 是 Linux 部署入口，
本机 Vivado 2025.2 与开发 API 结果不能替代 Vivado 2026.1、本地开源模型和 Radeon Cloud 验证。

来源：[官方 API 契约](https://gitee.com/Vickyiii/rtlagent2026/blob/master/docs/API_CONTRACT.md)。
