# V2 独立能力回归题集

这是新编的 **6 道开发回归题**，用于发现公开三题之外的常见语义错误。它不是官方隐藏题集，也不是对真实比赛难度的抽样；通过本题集不能推出“达到 70 分”。题目、参考实现和测试台由本次开发协作创建，采用确定性激励以便复现。

| 题目 | 主要边界 | 错误候选必须被检出 |
| --- | --- | --- |
| `v2_01_signed_sat8` | 65,536 对有符号输入穷举，正负饱和与精确边界 | 截断回绕 |
| `v2_02_counter_priority` | 同步复位、reset/load/en 优先级、装载与模 32 回绕 | load 覆盖 reset |
| `v2_03_elastic_buffer` | 停顿保持、满槽同拍消费/替换、无旁路、空输出为零 | 满槽永远拒收 |
| `v2_04_fifo3` | 深度 3、空满同时 push/pop、指针回绕 | 满时同时出入丢失写入 |
| `v2_05_enabled_101` | 10101 重叠、使能间隙保留历史并清脉冲 | 匹配后清空状态 |
| `v2_06_round_robin4` | 轮询、未接受/无请求时保持、复位优先级 | 固定优先级 |

`prompts/<task_id>/prompt.txt` 是唯一生成输入。将该**单题目录**传给 `run.sh`，不把本目录整体传入；`evaluator/` 只供独立判定进程读取。参考答案和测试台不能进入模型上下文、提示词、技能包或运行期答案检索。

每题保留三层检查：一份可综合的 `TopModule` 参考候选；采用另一种表达方式的 `RefModule`；测试台中的独立整数/队列/输入历史检查。错误候选位于 `mutants/bug.sv`，仅用于确认测试台确实能检出指定错误，不能用来训练后再将同题成绩宣称为盲测。

## 本地复验

在工程根目录运行（Windows 可将 `python` 替换为本机 Python 完整路径）：

```text
python scripts/evaluate_suite.py --validate-fixtures --output output/v2/fixtures
```

此模式使用已有 Icarus，不安装依赖。成功条件为 6 份参考全部通过，且 6 份错误候选全部**编译成功但功能失配**。若工具无法启动、参考自检不一致、仿真超时或没有有效采样标记，不能算通过。

测试台仅在全部激励执行完成后输出有效统计。DUT 提前结束仿真、参考模型检查失败或看门狗触发时，输出 `TIMEOUT` 并拒绝把部分零失配结果判为通过。

生成结果清单格式：

```json
{
  "v2_01_signed_sat8": "signed_sat8/solution.v",
  "v2_02_counter_priority": "counter_priority/solution.v",
  "v2_03_elastic_buffer": "elastic_buffer/solution.v",
  "v2_04_fifo3": "fifo3/solution.v",
  "v2_05_enabled_101": "enabled_101/solution.v",
  "v2_06_round_robin4": "round_robin4/solution.v"
}
```

路径相对于清单。每题也可提供路径数组，代表同配置下独立生成的多个样本；不允许重复路径充当独立样本。缺题保留在分母并算失败，未知题号报错。

```text
python scripts/evaluate_suite.py --run v1=results/v1.json --run v2=results/v2.json --run baseline=results/baseline.json --output output/v2/comparison
```

默认只报告逐题功能回归及按题平均的独立样本通过率。Icarus 不给出赛事 L1–L3 等级、综合结果或分数。

## 前 70 分开发估计

要使用当前赛规中能力 30 分和增益 40 分的算式，需要使用 Vivado 完成分级，并在相同模型 revision、量化、上下文、思考配置、单题墙钟预算下分别生成方案与**原样官方基线**的可比样本：

```text
python scripts/evaluate_suite.py --backend vivado --level 3 --run v1=results/v1.json --run v2=results/v2.json --run baseline=results/baseline.json --baseline baseline --estimate-first70 --confirm-comparable-settings --output output/v2/vivado-comparison
```

每题各样本系数先求均值，再按题求平均；不得使用最好一次。样本数不匹配或有工具环境错误时不计算估计。`B=1` 按采用的官方文字特殊规则将增益项记满；该边界容易让简单开发题产生虚高结果，不能据此宣称泛化能力。正式规则要求每题 5 次独立采样，本工具如实显示实际样本数。

Vivado 后端复用 `scripts/official_selftest.py` 与原样 `vendor/` 判定器；未修改官方基线和判分逻辑。目标器件 `xczu3eg-sbva484-1-e`、时钟 5 ns。使用本机 Vivado 2025.2 时仍属开发验证；赛方指定的 2026.1 环境和最终隐藏题结果另行验证。

本工具只评测已存在文件，不联网、不调用模型，也不会新增生成重试。所有结果都带 `is_official_contest_score: false`，不计算后 30 分。
