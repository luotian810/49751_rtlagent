// 同步复位、允许重叠的 1101 检测器。
// history 保存此前 3 个输入，当前 in 与它们共同组成待检测窗口。
module TopModule (
    input  wire clk,
    input  wire reset,
    input  wire in,
    output reg  detected
);
    reg [2:0] history;
    reg [1:0] filled;  // 已保存的有效历史位数，饱和到 3。

    always @(posedge clk) begin
        if (reset) begin
            history  <= 3'b000;
            filled   <= 2'd0;
            detected <= 1'b0;
        end else begin
            // 非阻塞赋值读取旧 history，所以当前沿即可登记检测结果。
            detected <= (filled == 2'd3) && ({history, in} == 4'b1101);
            history  <= {history[1:0], in};
            if (filled != 2'd3)
                filled <= filled + 1'b1;
        end
    end
endmodule
