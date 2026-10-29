module RefModule(input clk, input reset, input [3:0] req, input accept,
                 output reg [3:0] grant);
  integer pointer,i,client;
  always @* begin
    grant=0;
    for(i=0;i<4;i=i+1) begin
      client=(pointer+i)%4;
      if(grant==0 && req[client]) grant[client]=1;
    end
  end
  always @(posedge clk) begin
    if(reset) pointer<=0;
    else if(accept && grant!=0) begin
      if(grant[3]) pointer<=0;
      else if(grant[2]) pointer<=3;
      else if(grant[1]) pointer<=2;
      else pointer<=1;
    end
  end
endmodule
