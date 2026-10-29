// 拼接两份输入，取跨越边界的 8 位窗口，实现循环移位。
module TopModule (
    input wire [7:0] in,
    input wire [2:0] amount,
    input wire right,
    output reg [7:0] out
);
    reg [15:0] doubled;
    reg [15:0] moved;
    always @* begin
        doubled = {in, in};
        if (!right) begin
            moved = doubled >> amount;
            out = moved[7:0];
        end else begin
            moved = doubled << amount;
            out = moved[15:8];
        end
    end
endmodule
