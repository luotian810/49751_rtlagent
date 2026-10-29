`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg reset = 0;
    reg load = 0;
    reg [7:0] data = 0;
    wire [7:0] q;
    integer model, feedback_model, checks, seed_value, k;
    TopModule dut (.clk(clk), .reset(reset), .load(load), .data(data), .q(q));
    always #5 clk = ~clk;

    task step;
        input reset_value;
        input load_value;
        input [7:0] data_value;
        begin
            @(negedge clk);
            reset = reset_value; load = load_value; data = data_value;
            @(posedge clk);
            if (reset_value) model = 1;
            else if (load_value) model = data_value;
            else begin
                // 用整数运算建参考模型，避免逐字复制 DUT 的拼接表达式。
                feedback_model = ((model / 128) ^ (model / 32) ^ (model / 16) ^ (model / 8)) & 1;
                model = ((model * 2) + feedback_model) % 256;
            end
            #1;
            checks = checks + 1;
            if (q !== model[7:0]) begin
                $display("RTL_AGENT_FAIL check=%d q=%h expected=%h reset=%b load=%b data=%h", checks, q, model[7:0], reset, load, data);
                $finish;
            end
        end
    endtask

    initial begin
        model = 0; checks = 0;
        step(1, 1, 8'hff); // 复位必须压过装载。
        for (k = 0; k < 512; k = k + 1) step(0, 0, 0);
        // 穷举每个装载值及其随后 16 步，包括题目允许的全零状态。
        for (seed_value = 0; seed_value < 256; seed_value = seed_value + 1) begin
            step(0, 1, seed_value);
            for (k = 0; k < 16; k = k + 1) step(0, 0, 0);
            step(1, 1, seed_value);
        end
        $display("CHECKS=%0d all seeds + reset priority + 512 free-running cycles", checks);
        $display("RTL_AGENT_PASS");
        $finish;
    end
    initial begin #100000; $display("RTL_AGENT_FAIL watchdog"); $finish; end
endmodule
