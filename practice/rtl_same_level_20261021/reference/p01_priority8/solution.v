// 高位优先：后面的较高位匹配覆盖先前较低位的匹配。
module TopModule (
    input wire [7:0] in,
    output reg [2:0] index,
    output reg valid
);
    integer bit_no;
    always @* begin
        index = 3'd0;
        valid = 1'b0;
        for (bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
            if (in[bit_no]) begin
                index = bit_no[2:0];
                valid = 1'b1;
            end
        end
    end
endmodule
