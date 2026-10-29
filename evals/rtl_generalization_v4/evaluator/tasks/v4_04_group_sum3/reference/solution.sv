module TopModule(input clk_i,input reset_i,input sample_valid_i,
 input [4:0] sample_i,output reg [6:0] sum_o,output reg sum_valid_o);
 reg [1:0] phase;
 reg [6:0] partial_sum;
 always @(posedge clk_i) begin
   if(reset_i) begin phase<=0;partial_sum<=0;sum_o<=0;sum_valid_o<=0;end
   else begin
     sum_valid_o<=0;
     if(sample_valid_i) begin
       if(phase==2) begin
         sum_o<=partial_sum+{2'b00,sample_i};sum_valid_o<=1;
         partial_sum<=0;phase<=0;
       end else begin partial_sum<=partial_sum+{2'b00,sample_i};phase<=phase+1'b1;end
     end
   end
 end
endmodule
