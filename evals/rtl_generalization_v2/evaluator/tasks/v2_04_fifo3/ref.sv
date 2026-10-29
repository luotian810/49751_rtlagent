module RefModule(input clk, input reset, input push, input pop, input [7:0] din,
                 output [7:0] dout, output empty, output full, output [1:0] count);
  reg [7:0] queue[0:2];
  integer n,k;
  reg take,put;
  assign count=n;
  assign empty=(n==0);
  assign full=(n==3);
  assign dout=(n==0)?8'h00:queue[0];
  always @(posedge clk) begin
    if(reset) n=0;
    else begin
      take=pop && (n>0);
      put=push && ((n<3)||take);
      if(take) begin
        for(k=0;k<2;k=k+1) queue[k]=queue[k+1];
        n=n-1;
      end
      if(put) begin queue[n]=din;n=n+1;end
    end
  end
endmodule
