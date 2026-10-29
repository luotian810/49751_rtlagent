# RTL 同级练习题（仅题面）

日期：2026-10-21。以下是原创练习，非官方题库；参照现有 8 位组合逻辑、LFSR 和序列检测例子的规模设计。所有模块名均为 TopModule。组合题无时钟；时序题均为高有效同步复位。具体行为以各题完整说明为准。

建议先独立完成，再查阅另一份含答案题包。将对应 tasks/<题号> 目录交给智能体时，只提供 prompt.txt。

## p01_priority8：8 位高位优先编码器

实现名为 TopModule 的纯组合逻辑模块，接口必须完全一致：

module TopModule (
    input  wire [7:0] in,
    output reg  [2:0] index,
    output reg        valid
);

功能：8 位高位优先编码器。
1. 若 in 非零，valid=1，index 为最高有效 1 的位编号，编号从 in[0] 的 0 到 in[7] 的 7。
2. 若 in=8'h00，valid=0 且 index=3'd0；不得将 index 作为无关项。
3. 没有时钟、复位或流水线；所有输出都必须有确定赋值，不得推断锁存器。

例：in=8'b00101000 时 index=5、valid=1；in=8'b10000001 时 index=7、valid=1。
仅提交可综合的完整 Verilog/SystemVerilog 模块，不包含测试台。

## p02_rotate8：8 位双向循环移位器

实现名为 TopModule 的纯组合逻辑模块，接口必须完全一致：

module TopModule (
    input  wire [7:0] in,
    input  wire [2:0] amount,
    input  wire       right,
    output reg  [7:0] out
);

功能：对 8 位无符号输入做循环移位。
1. right=0 时向左循环移动 amount 位；right=1 时向右循环移动 amount 位。
2. amount 的范围为 0..7；amount=0 时 out=in。
3. 被移出的一端的位必须从另一端回填，不能补零或做算术符号扩展。
4. 没有时钟、复位或流水线，不得推断锁存器。

例：in=8'b10000001、amount=1，左循环结果为 8'b00000011，右循环结果为 8'b11000000。
仅提交可综合的完整 Verilog/SystemVerilog 模块，不包含测试台。

## p03_sat_counter4：4 位饱和加减计数器

实现名为 TopModule 的 4 位无符号饱和加减计数器：

module TopModule (
    input  wire       clk,
    input  wire       reset,
    input  wire       load,
    input  wire       enable,
    input  wire       up,
    input  wire [3:0] data,
    output reg  [3:0] q
);

所有时序逻辑在 clk 上升沿工作，reset 为高有效同步复位。
每个上升沿按下列优先级更新 q：
1. reset=1：q 置 0，忽略其他输入。
2. reset=0 且 load=1：q 置为 data；加载不受 enable 限制。
3. reset=0、load=0、enable=1：up=1 则加一，但 q=15 时保持 15；up=0 则减一，但 q=0 时保持 0。
4. 其余情况保持 q。

注意这是饱和计数，不允许 15 加一回到 0 或 0 减一回到 15。
不要求复位前的初始值；测试会先复位。仅提交可综合模块，不包含测试台。

## p04_shift8：8 位可加载串行移位寄存器

实现名为 TopModule 的 8 位可加载串行移位寄存器：

module TopModule (
    input  wire       clk,
    input  wire       reset,
    input  wire       load,
    input  wire       enable,
    input  wire       serial_in,
    input  wire [7:0] data,
    output reg  [7:0] q
);

所有时序逻辑在 clk 上升沿工作，reset 为高有效同步复位。
每个上升沿按下列优先级更新 q：
1. reset=1：q 置为 8'h00。
2. 否则若 load=1：q 置为 data；不受 enable 限制。
3. 否则若 enable=1：q 左移一位，旧 q[7] 丢弃，serial_in 写入 q[0]，即 q <= {q[6:0], serial_in}。
4. 否则保持。

例如 q=8'h81、serial_in=1，执行一次有效移位后 q=8'h03。
不要求复位前的初始值；测试会先复位。仅提交可综合模块，不包含测试台。

## p05_detect1011：允许重叠的 1011 检测器

实现名为 TopModule 的串行 1011 序列检测器：

module TopModule (
    input  wire clk,
    input  wire reset,
    input  wire in,
    output reg  detected
);

1. 在 clk 每个上升沿采样一位 in。
2. reset 为高有效同步复位；reset=1 的上升沿清除全部匹配历史并令 detected=0，该沿的 in 不计入序列。
3. reset=0 时，若最近四个有效采样位（含当前位），按时间从早到晚为 1、0、1、1，则 detected 在当前上升沿更新后为 1；否则为 0。
4. 允许重叠。输入串 1011011 包含两次命中，分别在第 4、7 位采样后产生脉冲。
5. detected 是寄存输出，不得额外延迟一拍。复位后不足四个采样位时不得命中。

不要求复位前的初始值；测试会先复位。仅提交可综合模块，不包含测试台。

## p06_serial_parity8：每 8 位串行奇偶校验器

实现名为 TopModule 的每 8 位串行奇偶校验器：

module TopModule (
    input  wire clk,
    input  wire reset,
    input  wire enable,
    input  wire in,
    output reg  parity,
    output reg  valid
);

全部时序逻辑在 clk 上升沿工作，reset 为高有效同步复位。
1. reset=1 时清除分组进度、部分结果，并令 parity=0、valid=0；忽略 enable 和 in。
2. reset=0 且 enable=1 时接收当前 in；enable=0 时不接收，不推进分组进度。
3. 从复位或上一组完成之后开始，每接收 8 位构成一组，不重叠、不滑动。
4. 第 8 位被接收的同一个上升沿更新后，parity 等于这 8 位的异或（1 的个数为奇数时为 1），valid=1。
5. 其余非复位上升沿 valid=0，包含 enable=0 的沿；parity 保持上次完整分组的结果。
6. 第 8 位完成后下一次有效输入直接开始新组；不足 8 位的部分组遇到 reset 必须丢弃。

例如一组 8 位有三个 1，则完成沿 parity=1、valid=1；下一沿即使 enable=0，valid 也必须清零。
不要求复位前的初始值；测试会先复位。仅提交可综合模块，不包含测试台。

