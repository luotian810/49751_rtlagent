# 模型声明（云端阶段验证，尚未完成参赛验收）

建仓补充（2026-10-29）：本仓库队伍49751，当前智能体`2026.10.29-v11.1-qwen-only`，待固定千问实测。下述权重仓库、revision、量化、文件SHA和32768上下文继续沿用；权重文件不进入Git。下方云端测量段落保留其原始日期和范围，不能作为V11.1的新成绩。

更新日期：2026-10-20；当前规则复核至 RTL 官方 `51fbf8dc169bb320e6691c2ced34f331c2659ac0`（`1019-commit`），以下云端实测执行时采用 `f7a8bd4`，两版本协议、基线与判题器文件未变。已在 Radeon Cloud FPGA-CHINA 镜像中校验固定权重并运行 llama.cpp ROCm；agent 三个公开题候选均通过 Vivado 2026.1 L3，原样 baseline 为 L1/L1/L3。每模式每题一次，非正式成绩。验证实例已销毁，当前没有运行中的云服务，持久 `/workspace` 保留。

## 当前本地开源主模型

| 项目 | 已记录配置与证据范围 |
| --- | --- |
| 权重仓库 | [Qwen/Qwen3-14B-GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF) |
| 固定 revision | `c75e7b2d0234068f674a1bacf548ea32e27ccd29` |
| 权重文件 | `Qwen3-14B-Q4_K_M.gguf` |
| 量化 | `Q4_K_M` |
| 文件大小 | `9,001,752,960` 字节 |
| SHA256 | `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0` |
| 下载与校验 | `model-download.json` 状态为 `verified`，记录耗时 111.31 s |
| 云端路径 | `/workspace/models/Qwen3-14B-Q4_K_M.gguf` |
| 服务模型名 | `Qwen3-14B-Q4_K_M` |
| 基座与微调 | Qwen3-14B；本工程未进行微调 |
| 许可证 | 待正式封存时核对并保留所用固定 revision 的许可证原文 |
| 推理后端 | 官方镜像自带 llama.cpp，`0.4.0-dev`，build 1，commit `f114f91`，Clang 23.0.0 |
| 验证 GPU | AMD Radeon Pro W7900D，`gfx1100`；当前规则明确初赛与决赛均为 W7900 / gfx1100，不再提供 R9700 |
| 服务地址 | `http://127.0.0.1:8000/v1`，环回监听 |
| 上下文 | 32768 token、单 slot 已实际加载；完整长上下文边界尚未压测 |
| 单次输出上限 | V1 方案默认 16384；V2 按用途限为 DUT 8192、TB 3072、归因 768；官方原样基线固定 16384 |
| 思考配置 | `generation.chat_template_kwargs.enable_thinking=false`；`reasoning_effort=null` 表示不发送；Jinja 模板已启用 |
| RoPE | 启动脚本未设置额外 RoPE 缩放 |
| 启动显存采样 | 44.8 s 整卡周期采样，观测峰值 13.5267 GiB；不是完整任务峰值 |
| 本次最终显存采样 | 模型加载及六请求共 609.17 s、509 个整卡周期样本、0 采样错误；峰值 `14,852,784,128` 字节，即 14.852784128 GB / 13.8327 GiB |
| 生成与逐题判定 | agent 为 L3/L3/L3、零失配；baseline 为 L1（255/257 失配）/L1（4/226）/L3（0/229） |
| 内部自检限制 | agent 1 次自检通过、2 次在 120 s 冒烟预算内自检未完成并保留候选；之后独立公开判定通过，不写作内部无超时 |
| 断网重建 | 未验证；下载成功与环回推理不能代替独立断网复现 |

证据保存在 `D:/fgpa/output/cloud/round2/` 的下载校验、环境、显存采样、生成 trace 与独立判定文件中，115 项云端证据已逐项校验 SHA256。整卡采样包含本轮模型、KV cache 和 GPU 运行时，观测窗口内低于 32 GB；它不是驱动硬件 high-water 计数器，不保证捕捉采样间瞬时峰值，也不证明未测长题及满上下文边界。验证卡 48 GiB 的容量不改变单卡 32 GB 约束。

## 启动和配置一致性

`serve/start.sh` 支持 `INFERENCE_BACKEND=llamacpp` 或 `vllm`，本次已验证启动的是前者。llama.cpp 要求 `MODEL` 是已存在的本地 GGUF 文件，不在线下载；配置 `ROCBLAS_TENSILE_LIBPATH=/opt/llamacpp/rocblas/library`，用 `--jinja`、单 GPU、`--parallel 1` 及 `--no-context-shift` 启动。`MODEL_NAME`、`LLM_MODEL`、服务 `--alias` 必须一致。

方案与官方基线共用同一服务、权重 revision、量化、上下文及思考设置。两者只从 `manifest.json` 的 `generation` 读取 `chat_template_kwargs` 与 `reasoning_effort`，不能借此改变基线采样参数或输出预算。调整思考或上下文配置后，须同步声明并重新验证两条链路。

官方 `baseline.py` 与 `run_baseline.sh` 采用 `f7a8bd465c2a820e006c7a00ecc7df468974635b` 的原样文件；2026-10-20 已核对它们与 `51fbf8dc169bb320e6691c2ced34f331c2659ac0` 的 Git blob 完全相同，单次输出上限仍为 16384、请求超时仍为 840 秒。基线本身不带 API 鉴权头，使用环回地址本地服务；正式单题外层预算为 900 秒。本轮公开题目只作阶段验证，不代替同批五次独立采样，也不据此计算比赛增益。最新版明确初赛及决赛评测均须断网运行，本工程仍需完成离线复现验证。

## 历史开发 API

DeepSeek 商业 API 用于早期 RTL、自测测试台与修复开发，默认声明模型为 `deepseek-flash`，地址 `https://api.deepseek.com`。密钥只从进程环境读取，不进入源码、权重声明或报告。商业 API 运行不满足正式断网本地推理要求；`DEEPSEEK_THINKING` 不替代当前本地模型的 manifest 配置。

## 辅助模型

当前未配置辅助模型。以后若添加判别、打分或嵌入模型，须声明名称、基座、参数量、用途、位置和显存；训练或微调还需声明方法、数据及可复现权重。辅助模型不进入官方裸跑基线，主模型、辅助模型和运行时的总显存仍受单卡 32 GB 限制。

详细环境、失败记录、未完成的提交验证及费用见 [云端验证报告](../docs/radeon_cloud_validation_20261020.md)。
