`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0, load = 0, enable = 0, up = 0;
    reg [3:0] data = 0;
    wire [3:0] q;
    integer expected, checks, state, r, l, e, u, d, k;
    TopModule dut (.clk(clk), .reset(reset), .load(load), .enable(enable), .up(up), .data(data), .q(q));
    always #5 clk = ~clk;
    task step;
        input rv, lv, ev, uv;
        input [3:0] dv;
        begin
            @(negedge clk);
            reset = rv; load = lv; enable = ev; up = uv; data = dv;
            #1;
            if (checks > 0 && q !== expected[3:0]) begin
                $display("RTL_AGENT_FAIL output changed before rising edge"); $finish;
            end
            @(posedge clk);
            if (rv) expected = 0;
            else if (lv) expected = dv;
            else if (ev) begin
                if (uv) expected = expected + 1;
                else expected = expected - 1;
                if (expected > 15) expected = 15;
                if (expected < 0) expected = 0;
            end
            #1;
            checks = checks + 1;
            if (q !== expected[3:0]) begin
                $display("RTL_AGENT_FAIL check=%0d reset=%b load=%b enable=%b up=%b data=%h got=%h expected=%h",
                         checks, reset, load, enable, up, data, q, expected[3:0]);
                $finish;
            end
        end
    endtask
    initial begin
        checks = 0; expected = 0;
        step(1, 1, 1, 1, 15);
        // 每个旧状态 x 每种控制组合 x 每个加载值；先装入旧状态再做被测转换。
        for (state = 0; state < 16; state = state + 1)
            for (r = 0; r < 2; r = r + 1)
                for (l = 0; l < 2; l = l + 1)
                    for (e = 0; e < 2; e = e + 1)
                        for (u = 0; u < 2; u = u + 1)
                            for (d = 0; d < 16; d = d + 1) begin
                                step(0, 1, 0, 0, state);
                                step(r, l, e, u, d);
                            end
        // 连续多拍检验上下界饱和。
        for (k = 0; k < 20; k = k + 1) step(0, 0, 1, 1, 0);
        for (k = 0; k < 40; k = k + 1) step(0, 0, 1, 0, 0);
        $display("CHECKS=%0d exhaustive one-step transitions plus saturation runs", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
