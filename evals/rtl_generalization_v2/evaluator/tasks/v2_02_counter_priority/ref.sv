module RefModule(input clk, input reset, input load, input en,
                 input [4:0] data, output reg [4:0] q);
  integer value;
  always @(posedge clk) begin
    casez ({reset,load,en})
      3'b1??: value=0;
      3'b01?: value=data;
      3'b001: value=(value+1)%32;
      default: value=value;
    endcase
    q<=value;
  end
endmodule
