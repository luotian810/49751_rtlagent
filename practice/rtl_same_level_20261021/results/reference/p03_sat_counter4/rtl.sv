module TopModule (
    input wire clk, reset, load, enable, up,
    input wire [3:0] data,
    output reg [3:0] q
);
    always @(posedge clk) begin
        if (reset)
            q <= 4'd0;
        else if (load)
            q <= data;
        else if (enable) begin
            if (up && q != 4'd15)
                q <= q + 4'd1;
            else if (!up && q != 4'd0)
                q <= q - 4'd1;
        end
        // 未赋值的时序分支表示寄存器保持，不是组合锁存器。
    end
endmodule
