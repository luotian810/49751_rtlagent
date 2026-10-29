# 与现有示例同量级的 6 道 RTL 练习

创建于 2026-10-21。原创练习，参照已有 popcount8、detect_1101、lfsr8 的代码规模和知识点编写；不是官方题目，也不是官方隐藏题预测。难度接近的判断来自设计规模与考点，未经过学生或多模型难度标定。

## 题目概览

| 题号 | 名称 | 类型 | 主要考点 | 与已有例子的关系 |
| --- | --- | --- | --- | --- |
| p01_priority8 | 8 位高位优先编码器 | 组合 | 最高有效位、全零输入、默认赋值 | 与 popcount8 同为小规模组合逻辑 |
| p02_rotate8 | 8 位双向循环移位器 | 组合 | 方向、位宽、零移位、循环回填 | 与 popcount8 同量级，考察位操作 |
| p03_sat_counter4 | 4 位饱和加减计数器 | 时序 | 同步复位、加载优先级、饱和边界、保持 | 与 lfsr8 同量级的受控状态更新 |
| p04_shift8 | 8 位可加载串行移位寄存器 | 时序 | reset > load > enable、输入位位置 | 与 lfsr8 接近，状态转移稍简单 |
| p05_detect1011 | 允许重叠的 1011 检测器 | 时序 | 重叠、复位清历史、脉冲所在周期 | 与 detect_1101 直接同级的迁移练习 |
| p06_serial_parity8 | 每 8 位串行奇偶校验器 | 时序 | 接收使能、分组进度、单周期 valid | 与 lfsr8 接近，控制略多，可最后练习 |

建议顺序：01 → 02 → 04 → 03 → 05 → 06。每题完整接口与所有边界行为见 `tasks/<题号>/prompt.txt`；汇总版在 `QUESTIONS.md`。

## 文件用途

```text
tasks/<题号>/prompt.txt          题面，投给智能体或练习者
reference/<题号>/solution.v     人工参考实现，含中文注释
testbench/<题号>/tb.sv          自检测试台，不作为生成上下文
run_practice.py                统一仿真入口，不使用 API key 或模型
tools/verification.py          从现有工程原样复制的 EDA 适配器
results/                       运行后生成，默认不包含在题面包中
```

`tasks/` 下只有题面。让智能体作答时仅提供这些题面，不要给它 `reference/` 或 `testbench/`。参考实现只用于核对题意、验证判定链路或练习后查阅。

## Linux 下验证参考实现

前提：Python >= 3.10，Vivado 已安装且已加载环境，所需许可证可用。本包不安装 EDA 或模型，不需要任何 Python 第三方库。

```bash
cd rtl_same_level_20261021
python3 run_practice.py --reference --backend vivado

# 也可以只运行一道：
python3 run_practice.py --reference --backend vivado --task p05_detect1011
```

已安装 Icarus 的开发环境可使用：

```bash
python3 run_practice.py --reference --backend iverilog
```

这只是开发仿真，不能作为 Vivado 综合或正式 L0–L3 成绩。本入口不做综合。

## 验证智能体或手写的答案

每道答案放在 `answers/<题号>/solution.v`，然后运行：

```bash
python3 run_practice.py --solutions answers --backend vivado
```

如果沿用现有工程，先在工程根目录调用智能体（模型需要已启动）：

```bash
bash run.sh practice/rtl_same_level_20261021/tasks/p01_priority8 output/practice_answers/p01_priority8
python3 practice/rtl_same_level_20261021/run_practice.py \
  --solutions output/practice_answers --backend vivado --task p01_priority8
```

只有一题答案时一定指定 `--task`；不指定则检查全部六题，缺少文件会明确报错。生成入口读取的是题面，不把人工参考答案作为生成上下文。

## 验证覆盖范围

- 01：穷举 256 种输入，含全零、单个 1、多个 1。
- 02：穷举 256 个输入 × 8 个移位量 × 2 个方向，共 4096 组。
- 03：穷举 16 个旧状态、四个控制位和 16 个加载值的单步转换，并检查连续上下界饱和。
- 04：遍历全部旧状态、串行输入和使能，检查复位/加载优先级和连续移位。
- 05：重叠示例、全部 256 个八位串、跨复位边界、确定性随机输入。
- 06：全部 256 种八位分组、位间暂停、连续分组、部分分组复位、确定性随机控制。

所有时序测试均在下降沿驱动，在上升沿后 `#1` 比较；使用 `!==` 检出未知输出。只有完整测试通过才打印独立 `RTL_AGENT_PASS`。工具还会检查错误标记和主机超时；测试台自身另有限时保护。

这是有限测试，不能替代形式验证。运行汇总明确记录宿主系统与工具路径；不要把 Windows 开发自测写成 Linux 实测。实际验证记录见 `VALIDATION.md`。
