module TopModule(input clk, input reset, input in_valid, input [7:0] in_data,
                 output in_ready, output out_valid, output [7:0] out_data,
                 input out_ready);
  reg full;
  reg [7:0] saved;
  assign in_ready = !full || out_ready;
  assign out_valid = full;
  assign out_data = full ? saved : 8'h00;
  always @(posedge clk) begin
    if (reset) begin full<=0;saved<=0;end
    else if (in_ready) begin full<=in_valid;if(in_valid) saved<=in_data;end
  end
endmodule
