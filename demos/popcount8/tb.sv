`timescale 1ns/1ps
module tb;
    reg [7:0] in;
    wire [3:0] out;
    integer value, bit_index, expected;
    TopModule dut (.in(in), .out(out));

    initial begin
        // 输入空间仅 256 种，直接穷举，不依赖随机覆盖概率。
        for (value = 0; value < 256; value = value + 1) begin
            in = value;
            expected = 0;
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                if ((value >> bit_index) & 1) expected = expected + 1;
            #1;
            if (out !== expected[3:0]) begin
                $display("RTL_AGENT_FAIL in=%h actual=%d expected=%d", in, out, expected);
                $finish;
            end
        end
        $display("CHECKS=256 all input combinations");
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #1000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
