# 启动和异步投题

2026-10-30，正式服务已通过官方 rc-tunnel 上线并完成指定表单报送，实例外健康鉴权 401/401/200 已验证。当前状态见 [验证摘要](../docs/validation_status_20261030.md)。本文件的启动命令供重建使用，已经运行的服务不应重新 expose。

## 固定环境

采用官方 RTL `fc8e26a5828b7222e9db439cee29128bcf4f8865` 指定的基础镜像摘要。完整镜像名见 [Dockerfile](../Dockerfile)。需要 Python 3 标准库、Bash、setsid、llama.cpp ROCm `f114f91`、Vivado 2026.1 和可用许可证。

权重预先置于 `/workspace/models/Qwen3-14B-Q4_K_M.gguf`，revision、大小、SHA256 和 Apache-2.0 许可见 [MODEL.md](../model/MODEL.md)。启动不下载权重或安装依赖。

`defaults.sh` 为 `start.sh`、`run_api.sh` 和 `run.sh` 提供一致默认值：llama.cpp、Qwen3-14B-Q4_K_M、32768 上下文、GPU 0、16 个 CPU 线程、环回 8000；llama.cpp 脚本固定单槽、Jinja、no-context-shift。思考设置来自 manifest，保持 false。临时目录为节点本地 `/var/tmp` 与 `/var/tmp/eda`，不依赖 `/workspace/env.sh` 中的模型配置。显式环境变量仍可指定实际挂载路径，不能因此更换参评权重或推理设置。

## 模型及容器退路

```bash
./serve/start.sh
./run.sh <task_dir> <out_dir>
./run_baseline.sh <task_dir> <baseline_out_dir>
```

`start.sh` 用 setsid 启动模型、等待模型名就绪后返回 0；重复执行会复用现有服务。默认等待上限 900 秒，日志在 `$AGENT_TMP/serve-logs/llamacpp.log`。容器退路只需先调用 start.sh，再调用每题入口；无需 HTTP 服务。Dockerfile 的 ENV 也让原样官方基线获得相同模型配置。

## 后台投题服务

先通过安全渠道向进程注入 `FPGACHINA_TOKEN`。已有实例从原配置获取令牌，不在命令行、日志或截图中输出它。

```bash
./serve/run_api.sh start
./serve/run_api.sh status
curl --noproxy '*' -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7860/v1/health
```

不带令牌必须为 401。run_api.sh 以 setsid 和重定向实现后台监督，子进程退出后 2 秒重启；关闭页面不会退出。日志在 `${AGENT_TMP:-/var/tmp}/run_api/serve_api.log`。`status` 仅说明监督进程活着，须另查 HTTP 健康。停止命令为 `./serve/run_api.sh stop`，不会停止云平台计费。

已有真实 Linux 生命周期、短时限清理及 300 请求证据。投题为 Bearer 鉴权的异步协议：POST `/v1/solve` 返回 202/job_id，GET `/v1/jobs/<job_id>` 轮询；`mode=baseline` 直接调用原样基线，`mode=agent` 调用方案，单槽串行执行。

## 健康数据与公网

`GET /v1/health` 检查模型名和仿真器工具可用性。`vram_gb` 每次从本容器 `/dev/dri` 获配的唯一 AMD render 节点映射到 sysfs，读取当前整卡已用字节，按十进制 GB 返回；不会把宿主机其他 GPU 或旧 `VRAM_GB` 环境快照当作当前值。无法唯一测量时返回 null 和 `vram_measurement=unavailable`。这不是峰值显存，也不运行额外模型请求。

`simulator_license=not_checked` 表示该次健康请求没有签出 Vivado 许可证。健康成功不替代真实 EDA 验收；已完成的仿真/综合证据见验证摘要。不能为每次隧道健康探测启动耗时 EDA。

当前已报送 URL 见验证摘要；仅鉴权 7860 经官方隧道公开，模型 8000 仅环回监听。隧道使用 `rc-tunnel status` 检查，不自行编辑 frpc 配置、不重新 expose 已报送服务。外部健康验证必须在实例外的电脑执行并安全注入令牌；本次维护只复核健康，不重投能力样本。

## 复现验证边界

默认值和健康接口有本地机制测试；原环境已有真实 Qwen/Vivado 运行与相同配置的重复启动证据。私有镜像完整冷构建以及严格网络隔离仍待赛事方具备对应环境时复验：当前实例没有 Docker/Podman，unshare 被拒绝。不得将“无需手动补模型配置”的修复等同于已经在私有干净容器运行通过。
