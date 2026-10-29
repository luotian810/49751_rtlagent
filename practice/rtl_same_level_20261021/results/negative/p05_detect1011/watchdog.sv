`timescale 1ns/1ps
module __rtl_agent_watchdog;
  initial begin
    #1000000;
    $display("RTL_AGENT_FAIL: simulation exceeded 1000000 ns");
    $finish;
  end
endmodule
