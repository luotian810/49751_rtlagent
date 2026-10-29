module TopModule(input clk, input reset, input [3:0] req, input accept,
                 output reg [3:0] grant);
  reg [1:0] p;
  always @* begin
    grant=0;
    case(p)
      0: if(req[0]) grant=1;else if(req[1]) grant=2;else if(req[2]) grant=4;else if(req[3]) grant=8;
      1: if(req[1]) grant=2;else if(req[2]) grant=4;else if(req[3]) grant=8;else if(req[0]) grant=1;
      2: if(req[2]) grant=4;else if(req[3]) grant=8;else if(req[0]) grant=1;else if(req[1]) grant=2;
      3: if(req[3]) grant=8;else if(req[0]) grant=1;else if(req[1]) grant=2;else if(req[2]) grant=4;
    endcase
  end
  always @(posedge clk) begin
    if(reset) p<=0;
    else if(accept) case(grant)
      4'b0001:p<=1;4'b0010:p<=2;4'b0100:p<=3;4'b1000:p<=0;
      default:p<=p;
    endcase
  end
endmodule
