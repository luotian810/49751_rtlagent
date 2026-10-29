`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0, enable = 0, in = 0;
    wire parity, valid;
    integer frame, received, checks, value, b, k, seed, random_value;
    reg expected_parity, expected_valid;
    TopModule dut (.clk(clk), .reset(reset), .enable(enable), .in(in), .parity(parity), .valid(valid));
    always #5 clk = ~clk;
    function reference_parity;
        input integer byte_value;
        integer x, ones, i;
        begin
            x = byte_value; ones = 0;
            for (i = 0; i < 8; i = i + 1) begin
                ones = ones + (x % 2);
                x = x / 2;
            end
            reference_parity = ones % 2;
        end
    endfunction
    task step;
        input rv, ev, iv;
        begin
            @(negedge clk); reset = rv; enable = ev; in = iv;
            #1;
            if (checks > 0 && (parity !== expected_parity || valid !== expected_valid)) begin
                $display("RTL_AGENT_FAIL output changed before rising edge"); $finish;
            end
            @(posedge clk);
            expected_valid = 0;
            if (rv) begin
                frame = 0; received = 0; expected_parity = 0;
            end else if (ev) begin
                // 整组存储后数 1，不复用 DUT 的累计异或实现。
                frame = frame + (iv << received);
                received = received + 1;
                if (received == 8) begin
                    expected_parity = reference_parity(frame);
                    expected_valid = 1;
                    frame = 0; received = 0;
                end
            end
            #1;
            checks = checks + 1;
            if (parity !== expected_parity || valid !== expected_valid) begin
                $display("RTL_AGENT_FAIL check=%0d reset=%b enable=%b in=%b parity=%b valid=%b expected_parity=%b expected_valid=%b",
                         checks, reset, enable, in, parity, valid, expected_parity, expected_valid);
                $finish;
            end
        end
    endtask
    initial begin
        frame = 0; received = 0; checks = 0; expected_parity = 0; expected_valid = 0;
        seed = 20261021;
        step(1, 1, 1);
        // 每种 8 位分组都检验；位间暂停也要检查 valid 清零和 parity 保持。
        for (value = 0; value < 256; value = value + 1)
            for (b = 0; b < 8; b = b + 1) begin
                step(0, 1, (value >> b) & 1);
                step(0, 0, !((value >> b) & 1));
            end
        // 连续分组不插入空拍。
        for (value = 0; value < 32; value = value + 1)
            for (b = 0; b < 8; b = b + 1) step(0, 1, (value >> b) & 1);
        // 未完成的分组被复位丢弃。
        step(0, 1, 1); step(0, 1, 0); step(0, 1, 1); step(1, 1, 1);
        for (k = 0; k < 2000; k = k + 1) begin
            random_value = $random(seed);
            step((k % 31) == 0, (random_value >> 1) & 1, random_value & 1);
        end
        $display("CHECKS=%0d all byte groups, stalls, continuous groups and reset interruptions", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #900000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
