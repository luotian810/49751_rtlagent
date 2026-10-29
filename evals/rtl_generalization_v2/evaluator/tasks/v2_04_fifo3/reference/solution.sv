module TopModule(input clk, input reset, input push, input pop, input [7:0] din,
                 output [7:0] dout, output empty, output full, output reg [1:0] count);
  reg [7:0] mem[0:2];
  reg [1:0] head,tail;
  wire take=pop && !empty;
  wire put=push && (!full || take);
  assign empty=count==0;
  assign full=count==3;
  assign dout=empty?8'h00:mem[head];
  always @(posedge clk) begin
    if(reset) begin head<=0;tail<=0;count<=0;end
    else begin
      if(take) head<=(head==2)?0:head+1'b1;
      if(put) begin mem[tail]<=din;tail<=(tail==2)?0:tail+1'b1;end
      case({put,take})
        2'b10: count<=count+1'b1;
        2'b01: count<=count-1'b1;
        default: count<=count;
      endcase
    end
  end
endmodule
