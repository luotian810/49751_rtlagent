`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0, in = 0;
    wire detected;
    integer recent, received, checks, stream, b, k, seed, random_value, hits;
    reg expected;
    reg [6:0] overlap;
    TopModule dut (.clk(clk), .reset(reset), .in(in), .detected(detected));
    always #5 clk = ~clk;
    task step;
        input rv, iv;
        begin
            @(negedge clk); reset = rv; in = iv;
            #1;
            if (checks > 0 && detected !== expected) begin
                $display("RTL_AGENT_FAIL output changed before rising edge"); $finish;
            end
            @(posedge clk);
            if (rv) begin recent = 0; received = 0; expected = 0; end
            else begin
                recent = (recent * 2 + iv) % 16;
                received = received + 1;
                expected = (received >= 4 && recent == 11);
            end
            #1;
            checks = checks + 1;
            if (detected !== expected) begin
                $display("RTL_AGENT_FAIL check=%0d reset=%b in=%b got=%b expected=%b",
                         checks, reset, in, detected, expected);
                $finish;
            end
        end
    endtask
    initial begin
        recent = 0; received = 0; checks = 0; seed = 20261021;
        overlap = 7'b1011011; hits = 0;
        step(1, 0);
        for (b = 6; b >= 0; b = b - 1) begin
            step(0, overlap[b]);
            if (detected) hits = hits + 1;
        end
        if (hits != 2) begin $display("RTL_AGENT_FAIL overlap hits=%0d", hits); $finish; end
        for (stream = 0; stream < 256; stream = stream + 1) begin
            step(1, 1);
            for (b = 7; b >= 0; b = b - 1) step(0, (stream >> b) & 1);
        end
        // 部分匹配遇到复位，不能跨复位拼成 1011。
        step(1, 0); step(0, 1); step(0, 0); step(1, 1); step(0, 1); step(0, 1);
        for (k = 0; k < 512; k = k + 1) begin
            random_value = $random(seed);
            step((k % 37) == 0, random_value & 1);
        end
        $display("CHECKS=%0d overlap, exhaustive 8-bit streams, resets and seeded random", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
