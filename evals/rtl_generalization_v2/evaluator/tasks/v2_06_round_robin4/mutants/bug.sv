// Deliberate bug: fixed priority ignores round-robin history.
module TopModule(input clk, input reset, input [3:0] req, input accept,
                 output reg [3:0] grant);
  always @* begin
    grant=0;
    if(req[0]) grant=1;else if(req[1]) grant=2;else if(req[2]) grant=4;else if(req[3]) grant=8;
  end
endmodule
