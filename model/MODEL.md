# 固定模型声明

更新日期：2026-10-30。当前智能体 V11.1，105 个开发能力样本及 300 个工程请求已核验；正式投题服务已上线。历史早期版本成绩见各自归档，不作为本版本新增成绩。

| 项目 | 固定配置 |
| --- | --- |
| 仓库 | [Qwen/Qwen3-14B-GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF) |
| revision | `c75e7b2d0234068f674a1bacf548ea32e27ccd29` |
| 文件 | `Qwen3-14B-Q4_K_M.gguf` |
| 量化 | Q4_K_M |
| 字节数 | 9,001,752,960 |
| SHA256 | `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0` |
| 许可 | Apache-2.0；[原文](Qwen3-LICENSE)、[固定 revision 核验](license-verification.json) |
| 默认位置 | `/workspace/models/Qwen3-14B-Q4_K_M.gguf`，提前准备并校验，不纳入 Git |
| 服务名 | Qwen3-14B-Q4_K_M |
| 推理栈 | 官方镜像 llama.cpp 0.4.0-dev build 1，commit f114f91，ROCm/gfx1100 |
| 设备 | AMD Radeon Pro W7900D，单 GPU；比赛总显存预算仍为 32 GB |
| 上下文 | 32768 token，单槽，Jinja，no-context-shift，无额外 RoPE 缩放 |
| 思考 | manifest.generation.chat_template_kwargs.enable_thinking=false；reasoning_effort=null |
| 输出预算 | 方案设计/修复8192、TB3072、归因768等；客户端总上限16384；官方基线固定16384 |
| 监听 | `127.0.0.1:8000`，不公开 |
| 微调及辅助模型 | 均无 |

权重来源：[固定 revision 文件](https://huggingface.co/Qwen/Qwen3-14B-GGUF/tree/c75e7b2d0234068f674a1bacf548ea32e27ccd29)。启动方式见 [serve/README.md](../serve/README.md)；方案与官方基线共用同一服务、同一权重、量化、上下文及思考设置。原样基线不加载 agent、skill 或工具。

显存证据：2026-10-29 周期采样观测峰值 14.883463168 GB；10月30日完整300请求批次3273个周期样本、0错误、观测峰值14.864891904 GB。均低于32 GB，但不代表硬件高水位，不保证捕获采样间瞬时峰值。健康接口的实时当前占用与这些历史峰值分别解释。

上下文真实探针完成32600输入token、16输出token，无截断；这是合成负载，不证明任意满上下文输出。105样本为37L3/54L1/14L0，参考105L3。完整隔离复验及私有基础镜像冷构建未完成，不以权重下载、环回监听或无代理运行冒充已完成。

历史曾使用的商业模型仅留在历史文档中；当前运行、基准与本次维护均固定上述千问。详细证据边界见 [验证摘要](../docs/validation_status_20261030.md)和[设计报告](../REPORT.md)。
