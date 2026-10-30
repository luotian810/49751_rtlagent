# 第三方来源与许可

| 来源 | 本仓库覆盖范围 | 许可原文 |
| --- | --- | --- |
| AMD / Vickyiii/rtlagent2026，commit `fc8e26a5828b7222e9db439cee29128bcf4f8865` | 原样 `baseline.py`、`run_baseline.sh`、`vendor/rtlagent2026_selftest/`，及依据官方示例适配的启动/接口文件 | [MIT，Copyright (c) 2026 AMD](LICENSES/AMD-rtlagent2026-MIT.txt) |
| Qwen/Qwen3-14B-GGUF，revision `c75e7b2d0234068f674a1bacf548ea32e27ccd29` | 外部准备的 Q4_K_M 权重；权重不在 Git 仓库内 | [Apache License 2.0](model/Qwen3-LICENSE)，[来源核验](model/license-verification.json) |

上述许可分别适用于对应上游内容，不将队伍全部自有源码自动改授为 MIT。基础镜像、Vivado 与 llama.cpp 的原有许可由各自分发保留；本仓库不重新分发工具二进制。上游文件来源详见 [vendor 记录](vendor/rtlagent2026_selftest/PROVENANCE.md)。
