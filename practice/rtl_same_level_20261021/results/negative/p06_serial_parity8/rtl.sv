module TopModule (
    input wire clk, reset, enable, in,
    output reg parity, valid
);
    reg [2:0] bit_count;
    reg partial_xor;
    always @(posedge clk) begin
        if (reset) begin
            bit_count <= 3'd0;
            partial_xor <= 1'b0;
            parity <= 1'b0;
            valid <= 1'b0;
        end else begin
            // valid 是单周期完成脉冲，暂停接收时也必须清零。
            if (enable) begin
                if (bit_count == 3'd7) begin
                    parity <= partial_xor ^ in;
                    valid <= 1'b1;
                    bit_count <= 3'd0;
                    partial_xor <= 1'b0;
                end else begin
                    bit_count <= bit_count + 3'd1;
                    partial_xor <= partial_xor ^ in;
                end
            end
        end
    end
endmodule
