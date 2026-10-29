module RefModule(input clk, input reset, input in_valid, input [7:0] in_data,
                 output in_ready, output out_valid, output [7:0] out_data,
                 input out_ready);
  reg [8:0] slot;
  assign out_valid=slot[8];
  assign out_data=slot[8] ? slot[7:0] : 8'h00;
  assign in_ready=(slot[8]==0) || out_ready;
  always @(posedge clk) begin
    if(reset) slot<=9'b0;
    else if(!slot[8] || out_ready)
      slot<=in_valid ? {1'b1,in_data} : 9'b0;
  end
endmodule
