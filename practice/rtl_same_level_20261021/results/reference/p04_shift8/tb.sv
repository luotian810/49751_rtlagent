`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0, load = 0, enable = 0, serial_in = 0;
    reg [7:0] data = 0;
    wire [7:0] q;
    integer expected, checks, value, b, e;
    TopModule dut (.clk(clk), .reset(reset), .load(load), .enable(enable),
                   .serial_in(serial_in), .data(data), .q(q));
    always #5 clk = ~clk;
    task step;
        input rv, lv, ev, sv;
        input [7:0] dv;
        begin
            @(negedge clk);
            reset = rv; load = lv; enable = ev; serial_in = sv; data = dv;
            #1;
            if (checks > 0 && q !== expected[7:0]) begin
                $display("RTL_AGENT_FAIL output changed before rising edge"); $finish;
            end
            @(posedge clk);
            if (rv) expected = 0;
            else if (lv) expected = dv;
            else if (ev) expected = (expected * 2 + sv) % 256;
            #1;
            checks = checks + 1;
            if (q !== expected[7:0]) begin
                $display("RTL_AGENT_FAIL check=%0d reset=%b load=%b enable=%b serial_in=%b data=%h got=%h expected=%h",
                         checks, reset, load, enable, serial_in, data, q, expected[7:0]);
                $finish;
            end
        end
    endtask
    initial begin
        expected = 0; checks = 0;
        step(1, 0, 0, 0, 0);
        for (value = 0; value < 256; value = value + 1) begin
            step(1, 1, 1, 1, value); // reset 高于 load。
            for (b = 0; b < 2; b = b + 1)
                for (e = 0; e < 2; e = e + 1) begin
                    step(0, 1, 1, b, value); // load 高于 enable，覆盖全部加载值。
                    step(0, 0, e, b, ~value);
                end
        end
        // 连续串行输入：避免只检验一次移位。
        for (value = 0; value < 32; value = value + 1)
            step(0, 0, 1, value % 2, 0);
        $display("CHECKS=%0d all shift states and input bits, priorities, holds", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
