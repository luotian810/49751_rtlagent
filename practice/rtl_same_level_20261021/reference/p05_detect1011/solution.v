module TopModule (
    input wire clk, reset, in,
    output reg detected
);
    reg [2:0] history;
    reg [1:0] filled;
    always @(posedge clk) begin
        if (reset) begin
            history <= 3'b000;
            filled <= 2'd0;
            detected <= 1'b0;
        end else begin
            // 右侧读取旧 history，与本沿输入一起形成待检测窗口。
            detected <= (filled == 2'd3) && ({history, in} == 4'b1011);
            history <= {history[1:0], in};
            if (filled != 2'd3)
                filled <= filled + 2'd1;
        end
    end
endmodule
