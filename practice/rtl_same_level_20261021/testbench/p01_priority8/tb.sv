`timescale 1ns/1ps
module tb;
    reg [7:0] in;
    wire [2:0] index;
    wire valid;
    integer value, remaining_value, expected_index, checks;
    reg expected_valid;
    TopModule dut (.in(in), .index(index), .valid(valid));
    initial begin
        checks = 0;
        for (value = 0; value < 256; value = value + 1) begin
            in = value;
            remaining_value = value;
            expected_index = 0;
            // 用整数反复除二求最高位编号，与 DUT 的逐位扫描不同。
            while (remaining_value > 1) begin
                remaining_value = remaining_value / 2;
                expected_index = expected_index + 1;
            end
            expected_valid = (value != 0);
            #1;
            checks = checks + 1;
            if (index !== expected_index[2:0] || valid !== expected_valid) begin
                $display("RTL_AGENT_FAIL in=%h index=%h valid=%b expected_index=%d expected_valid=%b",
                         in, index, valid, expected_index, expected_valid);
                $finish;
            end
        end
        $display("CHECKS=%0d exhaustive all 8-bit inputs", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
