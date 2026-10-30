# V11.1 完整105样本能力结果

共21道开发题，每题5次，105/105全部独立判定；L3=37，L1=54，L0=14。功能均值35.2%。
五组L3：[7, 6, 8, 9, 7]；正确参考105/105达到L3，独立环境错误0。
内部自检PASS共28，其中9个独立功能失败。生成阶段总4442.659秒，模型调用328次。

这是原93样本加12个从未开始的样本，未重投旧失败；两天间重启过同一模型配置。开发题不是未见题，不是比赛正式成绩；无同批能力基线，不计算正式增益。

| 题目 | 五次等级 | L3/5 |
| --- | --- | ---: |
| latest/gen_v4/v4_01_rotate12 | L1, L1, L1, L1, L0 | 0 |
| latest/gen_v4/v4_02_signed_addsub6 | L1, L1, L0, L1, L0 | 0 |
| latest/gen_v4/v4_03_negedge_mod7 | L1, L1, L1, L1, L1 | 0 |
| latest/gen_v4/v4_04_group_sum3 | L1, L0, L1, L3, L1 | 1 |
| latest/gen_v4/v4_05_enabled_1101 | L0, L1, L0, L1, L0 | 0 |
| latest/gen_v4/v4_06_readyvalid_fifo2 | L1, L1, L1, L1, L1 | 0 |
| latest/practice/p01_priority8 | L3, L3, L3, L3, L3 | 5 |
| latest/practice/p02_rotate8 | L0, L0, L0, L0, L0 | 0 |
| latest/practice/p03_sat_counter4 | L3, L3, L3, L3, L3 | 5 |
| latest/practice/p04_shift8 | L3, L3, L3, L3, L3 | 5 |
| latest/practice/p05_detect1011 | L1, L1, L1, L1, L1 | 0 |
| latest/practice/p06_serial_parity8 | L1, L1, L1, L1, L1 | 0 |
| latest/gen_v2/v2_01_signed_sat8 | L3, L3, L3, L3, L3 | 5 |
| latest/gen_v2/v2_02_counter_priority | L3, L3, L3, L3, L3 | 5 |
| latest/gen_v2/v2_03_elastic_buffer | L1, L1, L1, L1, L1 | 0 |
| latest/gen_v2/v2_04_fifo3 | L0, L0, L1, L1, L1 | 0 |
| latest/gen_v2/v2_05_enabled_101 | L1, L1, L1, L1, L1 | 0 |
| latest/gen_v2/v2_06_round_robin4 | L1, L1, L3, L3, L1 | 2 |
| latest/public/ex01_popcount8 | L3, L1, L3, L3, L3 | 4 |
| latest/public/ex02_detect_1101 | L1, L1, L1, L1, L1 | 0 |
| latest/public/ex03_lfsr8 | L3, L3, L3, L3, L3 | 5 |

压力、公网和断网验收分别记录，不把能力批次补齐当作全部工程验收完成。
