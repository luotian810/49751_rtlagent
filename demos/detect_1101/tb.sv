`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0;
    reg in = 0;
    wire detected;
    integer stream, bit_index, history_model, count, checks, seed;
    integer k, random_value, overlap_hits;
    reg expected;
    reg [6:0] overlap;
    TopModule dut (.clk(clk), .reset(reset), .in(in), .detected(detected));
    always #5 clk = ~clk;

    task step;
        input reset_value;
        input input_value;
        begin
            // 在下降沿施加激励，避免测试台与 DUT 在同一上升沿竞争。
            @(negedge clk);
            reset = reset_value;
            in = input_value;
            @(posedge clk);
            if (reset_value) begin
                history_model = 0;
                count = 0;
                expected = 0;
            end else begin
                history_model = ((history_model * 2) + input_value) % 16;
                count = count + 1;
                expected = (count >= 4) && (history_model == 13);
            end
            #1;
            checks = checks + 1;
            if (detected !== expected) begin
                $display("RTL_AGENT_FAIL check=%d reset=%b in=%b got=%b expected=%b", checks, reset, in, detected, expected);
                $finish;
            end
        end
    endtask

    initial begin
        history_model = 0; count = 0; checks = 0; seed = 2026;
        overlap = 7'b1101101; overlap_hits = 0;
        step(1, 0);
        for (bit_index = 6; bit_index >= 0; bit_index = bit_index - 1) begin
            step(0, overlap[bit_index]);
            if (detected) overlap_hits = overlap_hits + 1;
        end
        if (overlap_hits != 2) begin
            $display("RTL_AGENT_FAIL overlap count=%d", overlap_hits); $finish;
        end
        // 穷举全部 256 个八位输入串，每个串从复位状态开始。
        for (stream = 0; stream < 256; stream = stream + 1) begin
            step(1, 0);
            for (bit_index = 7; bit_index >= 0; bit_index = bit_index - 1)
                step(0, (stream >> bit_index) & 1);
        end
        // 长序列并穿插复位，验证部分匹配被清除及重新计数。
        for (k = 0; k < 512; k = k + 1) begin
            random_value = $random(seed);
            step((k % 37) == 0, random_value & 1);
        end
        $display("CHECKS=%0d overlap + exhaustive streams + deterministic random reset", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #100000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
