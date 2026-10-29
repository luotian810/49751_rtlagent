`timescale 1ns/1ps
module tb;
    reg [7:0] in;
    reg [2:0] amount;
    reg right;
    wire [7:0] out;
    reg [7:0] expected;
    integer value, shift_amount, direction, b, checks;
    TopModule dut (.in(in), .amount(amount), .right(right), .out(out));
    initial begin
        checks = 0;
        for (value = 0; value < 256; value = value + 1)
            for (shift_amount = 0; shift_amount < 8; shift_amount = shift_amount + 1)
                for (direction = 0; direction < 2; direction = direction + 1) begin
                    in = value; amount = shift_amount; right = direction;
                    // 按位重映射，避免复用参考实现的 16 位移位算法。
                    for (b = 0; b < 8; b = b + 1) begin
                        if (direction)
                            expected[b] = in[(b + shift_amount) % 8];
                        else
                            expected[b] = in[(b + 8 - shift_amount) % 8];
                    end
                    #1;
                    checks = checks + 1;
                    if (out !== expected) begin
                        $display("RTL_AGENT_FAIL in=%h amount=%d right=%b got=%h expected=%h",
                                 in, amount, right, out, expected);
                        $finish;
                    end
                end
        $display("CHECKS=%0d exhaustive input x amount x direction", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
