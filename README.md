# 49751 RTL 本地智能体

当前智能体为 **V11.1**，固定本地 **Qwen3-14B-Q4_K_M**。2026-10-30 已完成 105 个开发能力样本和同一会话 300 个工程请求的证据核验，正式投题服务与公网网址表单已上线、报送。本次维护补齐启动默认值、许可、交付清理及健康显存采样；不改变智能体、运行时 skill、原样官方基线或模型推理配置。

开发能力结果：**37 L3 / 54 L1 / 14 L0，共 105**；105 个正确参考均 L3。内部 28 次 PASS 含 9 次误报。不能用这些已参与迭代的题目推断正式比赛分数。300 工程请求用于接口和稳定性检查，其中一条客户端暂停的截止观察异常保留。

## 阅读入口

- [模型来源、固定权重与许可](model/MODEL.md)
- [启动、后台投题与健康检查](serve/README.md)
- [设计报告与失败分析](REPORT.md)
- [当前验证及部署状态](docs/validation_status_20261030.md)
- [105 能力样本分析](docs/v11p1_capability_20261030.md)、[300 工程请求分析](docs/v11p1_engineering_20261030.md)
- [运行时技能包](skill/README.md)、[第三方许可](THIRD_PARTY_NOTICES.md)

## 复现

使用 [Dockerfile](Dockerfile) 声明的官方 FPGA-CHINA 基础镜像。提前将已校验的固定 GGUF 权重挂载到 `/workspace/models/Qwen3-14B-Q4_K_M.gguf`；权重不放入 Git，也不在启动或解题时下载。镜像内需要既定 llama.cpp ROCm、Vivado 2026.1 及可用许可证。

```bash
./serve/start.sh
./run.sh <task_dir> <out_dir>
./run_baseline.sh <task_dir> <baseline_out_dir>
```

`serve/defaults.sh` 和 Dockerfile 提供既定模型及推理默认值，无须依赖开发者的私有 env.sh。输入是 `prompt.txt`，输出为 `solution.v`、`trace.jsonl`。方案与基线调用同一环回推理服务；官方基线的两份文件保持逐字节原样。原始 `run_baseline.sh` 在非容器环境会自动查询当前服务模型，容器环境另由 Dockerfile 提供模型变量。

远程投题额外将赛事令牌安全注入 `FPGACHINA_TOKEN`，然后 `./serve/run_api.sh start`。后台监督与模型均脱离 Notebook/终端；只公开鉴权的 7860，8000 保持本机。已上线实例请只检查 `status` 和健康，不重新 expose 或启动新实例。

## 仓库范围

`agent/`、`skill/`、`serve/` 是运行路径；`evals/`、`practice/`、`vendor/` 是开发题及外部判定材料，不供生成进程读取参考答案。练习运行结果、EDA 数据库、模型权重、令牌和本机输出不提交。

历史文档保留其原日期和模型/预算范围。原本指向开发工作区、未随 Git 交付的证据链接已改成明确的归档路径，不能当作本仓库可下载文件。Codex 开发技能不属于运行时 skill 依赖。

完整私有镜像重建和严格网络隔离目前仍无可执行环境证据；不得把无代理成功、健康返回 200 或配置修复写成这两项已经通过。正式成绩由赛事方评测产生。
