// 8 位 Fibonacci LFSR。优先级：同步复位 > 装载 > 移位。
module TopModule (
    input  wire       clk,
    input  wire       reset,
    input  wire       load,
    input  wire [7:0] data,
    output reg  [7:0] q
);
    wire feedback = q[7] ^ q[5] ^ q[4] ^ q[3];
    always @(posedge clk) begin
        if (reset)
            q <= 8'h01;
        else if (load)
            q <= data;
        else
            q <= {q[6:0], feedback};
    end
    // 题目允许装载 0，故不擅自把全零状态替换为非零种子。
endmodule
