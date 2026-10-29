module TopModule(input clk_i,input reset_ni,
 input send_valid_i,input [4:0] send_data_i,output send_ready_o,
 input recv_ready_i,output recv_valid_o,output [4:0] recv_data_o);
 reg [4:0] mem[0:1];
 reg head,tail;
 reg [1:0] used;
 wire take=recv_ready_i && recv_valid_o;
 wire put=send_valid_i && send_ready_o;
 assign recv_valid_o=(used!=0);
 assign recv_data_o=(used==0)?5'b0:mem[head];
 assign send_ready_o=(used<2)||take;
 always @(posedge clk_i or negedge reset_ni) begin
   if(!reset_ni) begin head<=0;tail<=0;used<=0;end
   else begin
     if(take) head<=~head;
     if(put) begin mem[tail]<=send_data_i;tail<=~tail;end
     case({put,take})
       2'b10:used<=used+1'b1;
       2'b01:used<=used-1'b1;
       default:used<=used;
     endcase
   end
 end
endmodule
