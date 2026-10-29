// 8 位人口计数：统计输入中 1 的个数。
// 0..8 需要 4 位，不能用 3 位输出（否则 8 会溢出）。
module TopModule (
    input  wire [7:0] in,
    output reg  [3:0] out
);
    integer bit_index;
    always @* begin
        // 每次组合计算先赋默认值，避免推断锁存器。
        out = 4'd0;
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
            out = out + {3'b000, in[bit_index]};
    end
endmodule
